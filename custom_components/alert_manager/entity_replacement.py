"""Explicit entity-reference replacement in YAML and native HA dashboards."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from homeassistant.core import HomeAssistant, valid_entity_id
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util.file import write_utf8_file
from homeassistant.util.yaml import Secrets, parse_yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

from .coherence import (
    _Context,
    _discover_sources,
    _entity_pattern,
    _is_dynamic_reference,
    _ScanState,
    _Source,
    _walk,
    configuration_scan_metadata,
)
from .transactions import async_finish_non_interruptible


@dataclass(slots=True)
class ReplacementFile:
    """Original text and physical occurrences from one preview."""

    source: _Source
    content: str
    occurrences: list[dict[str, Any]] = field(default_factory=list)
    dashboard: Any = None
    dashboard_wrapped: bool = False
    native_updates: list[dict[str, Any]] = field(default_factory=list)


def _validate_yaml(content: str, targets: set[str] | None = None) -> None:
    """Parse every document, accepting native HA tags without resolving them."""
    documents = list(yaml.compose_all(content, Loader=yaml.SafeLoader))
    if targets is None:
        return
    pending = [node for node in documents if node is not None]
    seen = set()
    while pending:
        node = pending.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, MappingNode):
            # Replacing a scene/entity mapping key must never merge two entries.
            keys = set()
            for key, _ in node.value:
                if isinstance(key, ScalarNode) and key.value in targets:
                    if key.value in keys:
                        raise ValueError("replacement_yaml_invalid")
                    keys.add(key.value)
            pending.extend(value for _, value in node.value)
        elif isinstance(node, SequenceNode):
            pending.extend(node.value)


def prepare_replacement(
    config_dir: Path,
    targets: dict[str, str],
    metadata: dict[str, Any],
    scan_esphome: bool,
    dashboards: dict[str, tuple[_Source, str | None]],
    sources: list[_Source] | None = None,
) -> tuple[list[ReplacementFile], int]:
    """Reuse coherence traversal and contexts; run entirely in the executor."""
    sources = (
        sources
        if sources is not None
        else [
            source
            for source in _discover_sources(
                config_dir, metadata["yaml_dashboards"], scan_esphome=scan_esphome
            )
            if source.path.suffix.casefold() in {".yaml", ".yml"}
            and ".storage" not in source.path.parts
            and not source.path.is_symlink()
        ]
    )
    sources = [*sources, *(source for source, _ in dashboards.values())]
    files: list[ReplacementFile] = []
    skipped = 0
    for source in sorted(sources, key=lambda item: item.relative_path):
        try:
            dashboard_content = dashboards.get(source.relative_path, (None, None))[1]
            if dashboard_content is None and (
                source.path.is_symlink()
                or not (
                    os.access(source.path, os.W_OK)
                    and os.access(source.path.parent, os.W_OK)
                )
            ):
                skipped += 1
                continue
            content = (
                dashboard_content
                if dashboard_content is not None
                else source.path.read_bytes().decode("utf-8")
            )
            replacement = _replacement_file(source, content, targets, metadata)
        except OSError, UnicodeError, yaml.YAMLError:
            skipped += 1
            continue
        if replacement.occurrences:
            files.append(replacement)
    return files, skipped


def _replacement_file(
    source: _Source, content: str, targets: dict[str, str], metadata: dict[str, Any]
) -> ReplacementFile:
    """Collect physical occurrences within one coherence object traversal."""
    pattern = _entity_pattern(frozenset(targets))
    documents = list(yaml.compose_all(content, Loader=yaml.SafeLoader))
    replacement = ReplacementFile(source, content)
    seen: set[int] = set()

    def visit(node: ScalarNode, context: _Context, _source: _Source) -> None:
        # Marks point into the original text, preserving comments, quotes,
        # multiline templates, CRLF and !include/!secret tags.
        raw = content[node.start_mark.index : node.end_mark.index]
        for match in pattern.finditer(raw):
            old_entity_id = match.group(1).lower()
            if old_entity_id not in targets or (
                node.value.lower() != old_entity_id
                and _is_dynamic_reference(raw, match)
            ):
                continue
            start = node.start_mark.index + match.start(1)
            if start in seen:
                continue
            seen.add(start)
            replacement.occurrences.append(
                {
                    "id": f"{source.relative_path}:{start}",
                    "old_entity_id": old_entity_id,
                    "new_entity_id": targets[old_entity_id],
                    "start": start,
                    "end": start + len(old_entity_id),
                    "file": source.relative_path,
                    "line": node.start_mark.line
                    + raw[: match.start(1)].count("\n")
                    + 1,
                    "column": start - content.rfind("\n", 0, start),
                    "source_type": context.kind,
                    "source_name": context.name,
                }
            )

    state = _ScanState(
        pattern,
        frozenset(),
        frozenset(),
        frozenset(),
        metadata["template_by_unique_id"],
        metadata["template_by_name"],
        metadata["template_by_config_entry"],
        [],
        set(),
        {},
        scalar_visitor=visit,
        visited_nodes=set(),
    )
    context = _Context(source.kind, source.name or source.relative_path)
    for document in documents:
        if document is not None:
            _walk(document, context, source, state)
    return replacement


def replacement_contents(
    files: list[ReplacementFile], selected: set[str]
) -> list[tuple[ReplacementFile, str]]:
    """Validate the full candidate batch before any file or dashboard is saved."""
    known = {row["id"] for item in files for row in item.occurrences}
    if not selected or not selected <= known:
        raise ValueError("replacement_selection_invalid")
    changes = []
    for item in files:
        rows = [row for row in item.occurrences if row["id"] in selected]
        if not rows:
            continue
        content = item.content
        for row in sorted(rows, key=lambda row: row["start"], reverse=True):
            content = (
                content[: row["start"]] + row["new_entity_id"] + content[row["end"] :]
            )
        try:
            _validate_yaml(content, {row["new_entity_id"] for row in rows})
            if item.dashboard is not None:
                json.loads(content)
        except yaml.YAMLError, ValueError:
            raise ValueError("replacement_yaml_invalid") from None
        changes.append((item, content))
    return changes


def dashboard_configuration(item: ReplacementFile, content: str) -> Any:
    """Extract native config while retaining storage-file line numbers."""
    payload = json.loads(content)
    return payload["data"]["config"] if item.dashboard_wrapped else payload


def correction_signature(row: dict[str, Any]) -> tuple[str, str, int]:
    """One coherence finding covers all occurrences of an entity on its line."""
    return row.get("old_entity_id", row.get("entity_id", "")), row["file"], row["line"]


def verify_files(changes: list[tuple[ReplacementFile, str]]) -> None:
    """Reject previews whose selected YAML files have since been edited."""
    for item, _ in changes:
        if item.dashboard is None and (
            not item.native_updates
            and (
                item.source.path.is_symlink()
                or item.source.path.read_bytes().decode("utf-8") != item.content
            )
        ):
            raise ValueError("replacement_preview_stale")


def save_yaml(item: ReplacementFile, content: str) -> None:
    """Save with HA's atomic file helper and validate the persisted YAML."""
    write_utf8_file(str(item.source.path), content.encode("utf-8"), mode="wb")
    _validate_yaml(item.source.path.read_bytes().decode("utf-8"))


def native_config_updates(
    changes: list[tuple[ReplacementFile, str]], config_dir: Path
) -> list[dict[str, Any]]:
    """Prepare objects for the same REST endpoints used by native HA editors."""
    updates = []
    domains = {
        "automations.yaml": "automation",
        "scripts.yaml": "script",
        "scenes.yaml": "scene",
    }
    for item, content in changes:
        item.native_updates = []
        domain = domains.get(item.source.relative_path)
        if domain is None:
            continue
        parsed = []
        for text in (item.content, content):
            stream = StringIO(text)
            stream.name = str(item.source.path)
            parsed.append(parse_yaml(stream, Secrets(config_dir)))
        before, after = parsed
        if domain == "script":
            objects = [(key, value, after[key]) for key, value in before.items()]
        else:
            objects = [
                (value.get("id"), value, changed)
                for value, changed in zip(before, after, strict=True)
            ]
        changed_objects = [
            (key, original, candidate)
            for key, original, candidate in objects
            if original != candidate
        ]
        # Objects without an ID, includes, and packages have no editable REST target.
        if any(not key for key, _, _ in changed_objects):
            continue
        item.native_updates = [
            {"domain": domain, "key": str(key), "before": original, "after": candidate}
            for key, original, candidate in changed_objects
        ]
        updates.extend(item.native_updates)
    return updates


def verify_native_files(changes: list[tuple[ReplacementFile, str]]) -> None:
    """Validate the actual YAML saved by HA and confirm each selected object."""
    for item, _ in changes:
        if not item.native_updates:
            continue
        content = item.source.path.read_bytes().decode("utf-8")
        _validate_yaml(content)
        stream = StringIO(content)
        stream.name = str(item.source.path)
        current = parse_yaml(stream, Secrets(item.source.path.parent))
        for update in item.native_updates:
            if update["domain"] == "script":
                actual = current.get(update["key"])
            else:
                actual = next(
                    (
                        value
                        for value in current
                        if str(value.get("id")) == update["key"]
                    ),
                    None,
                )
            if actual != update["after"]:
                raise ValueError("replacement_preview_stale")


class EntityReplacement:
    """Own one transient preview and serialize explicit replacement requests."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._lock = asyncio.Lock()
        self._preview_id: str | None = None
        self._files: list[ReplacementFile] = []
        self._prepared_ids: set[str] | None = None

    async def async_preview(
        self, old_entity_id: str, new_entity_id: str, *, scan_esphome: bool = True
    ) -> dict[str, Any]:
        """Snapshot editable sources without renaming the registered entity."""
        if (
            not valid_entity_id(old_entity_id)
            or not valid_entity_id(new_entity_id)
            or old_entity_id == new_entity_id
        ):
            raise ValueError("replacement_entity_invalid")
        self._validate_target(new_entity_id)
        async with self._lock:
            files, skipped = await self._async_collect_files(
                {old_entity_id: new_entity_id}, scan_esphome=scan_esphome
            )
            return {
                **self._store_preview(files, skipped),
                "old_entity_id": old_entity_id,
                "new_entity_id": new_entity_id,
            }

    async def _async_collect_files(
        self,
        targets: dict[str, str],
        *,
        scan_esphome: bool = True,
        findings: list[dict[str, Any]] | None = None,
    ) -> tuple[list[ReplacementFile], int]:
        """Snapshot dashboards and traverse each requested file once."""
        metadata = configuration_scan_metadata(self.hass)
        config_dir = Path(self.hass.config.path())
        filenames = {row["file"] for row in findings} if findings is not None else None
        sources = None
        if filenames is not None:
            sources = []
            for filename in sorted(filenames):
                path = config_dir / filename
                if path.suffix.casefold() not in {".yaml", ".yml"}:
                    continue
                if ".storage" in path.parts:
                    continue
                dashboard = metadata["yaml_dashboards"].get(filename)
                sources.append(
                    _Source(
                        path,
                        filename,
                        "dashboard" if dashboard else "file",
                        dashboard[0] if dashboard else "",
                        dashboard[1] if dashboard else None,
                    )
                )
        dashboard_inputs = {}
        dashboard_objects = {}
        dashboard_configs = {}
        lovelace = self.hass.data.get("lovelace")
        for url_path, dashboard in getattr(lovelace, "dashboards", {}).items():
            if dashboard.mode != "storage":
                continue
            info = dashboard.config or {}
            filename = "lovelace" + (f".{info['id']}" if info.get("id") else "")
            relative_path = f".storage/{filename}"
            if filenames is not None and relative_path not in filenames:
                continue
            if (await dashboard.async_get_info()).get("mode") == "auto-gen":
                continue
            config = await dashboard.async_load(False)
            # Coherence scans the persisted wrapper; keep its exact line numbers.
            content = None
            if findings is None:
                content = await self.hass.async_add_executor_job(
                    lambda config=config: json.dumps(
                        config, ensure_ascii=False, indent=2
                    )
                )
            source = _Source(
                config_dir / relative_path,
                relative_path,
                "dashboard",
                info.get("title") or "Lovelace",
                f"/{url_path or 'lovelace'}",
            )
            dashboard_inputs[relative_path] = (source, content)
            dashboard_objects[relative_path] = dashboard
            dashboard_configs[relative_path] = config
        files, skipped = await self.hass.async_add_executor_job(
            prepare_replacement,
            config_dir,
            targets,
            metadata,
            scan_esphome,
            dashboard_inputs,
            sources,
        )
        matched = []
        signatures = {correction_signature(row) for row in findings or []}
        for item in files:
            item.dashboard = dashboard_objects.get(item.source.relative_path)
            item.dashboard_wrapped = findings is not None and item.dashboard is not None
            if item.dashboard_wrapped:
                original = await self.hass.async_add_executor_job(
                    dashboard_configuration, item, item.content
                )
                if original != dashboard_configs[item.source.relative_path]:
                    continue
            if findings is not None:
                item.occurrences = [
                    row
                    for row in item.occurrences
                    if correction_signature(row) in signatures
                ]
            if item.occurrences:
                matched.append(item)
        return matched, skipped

    async def _async_correction_files(
        self, findings: list[dict[str, Any]], renames: list[dict[str, Any]]
    ) -> tuple[list[ReplacementFile], int]:
        """Resolve newest registry identities and collect only matching findings."""
        latest = {}
        for rename in renames:  # History is newest first, including deleted targets.
            latest.setdefault(rename["old_entity_id"], rename["current_entity_id"])
        missing = {
            row["entity_id"] for row in findings if row.get("entity_id") in latest
        }
        registry = er.async_get(self.hass)
        targets = {
            entity_id: latest[entity_id]
            for entity_id in missing
            if latest[entity_id]
            and latest[entity_id] != entity_id
            and self.hass.states.get(entity_id) is None
            and registry.async_get(entity_id) is None
        }
        if not targets:
            return [], 0
        return await self._async_collect_files(
            targets,
            findings=[row for row in findings if row.get("entity_id") in targets],
        )

    async def async_coherence_report(
        self, report: dict[str, Any] | None, renames: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Add currently editable targets without mutating the persisted report."""
        if report is None:
            return None
        files, _ = await self._async_correction_files(report["results"], renames)
        if not files:
            return report
        targets = {
            correction_signature(row): row["new_entity_id"]
            for item in files
            for row in item.occurrences
        }
        return {
            **report,
            "results": [
                {**row, "correction_target": targets[correction_signature(row)]}
                if correction_signature(row) in targets
                else row
                for row in report["results"]
            ],
        }

    async def async_preview_corrections(
        self, findings: list[dict[str, Any]], renames: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Preview one batch restricted to the selected coherence lines."""
        async with self._lock:
            files, skipped = await self._async_correction_files(findings, renames)
            available = {
                correction_signature(row) for item in files for row in item.occurrences
            }
            if not findings or available != {
                correction_signature(row) for row in findings
            }:
                raise ValueError("replacement_preview_stale")
            return {**self._store_preview(files, skipped), "coherence_correction": True}

    def _store_preview(
        self, files: list[ReplacementFile], skipped: int
    ) -> dict[str, Any]:
        """Use the same admission, native API and rollback path for every batch."""
        self._prepared_ids = None
        self._files = files
        self._preview_id = uuid4().hex
        rows = [
            {key: value for key, value in row.items() if key not in {"start", "end"}}
            for item in files
            for row in item.occurrences
        ]
        return {
            "preview_id": self._preview_id,
            "replacements": rows,
            "replacement_count": len(rows),
            "file_count": len(files),
            "files_skipped": skipped,
        }

    def _validate_selected_targets(self, selected: set[str]) -> None:
        for target in {
            row["new_entity_id"]
            for item in self._files
            for row in item.occurrences
            if row["id"] in selected
        }:
            self._validate_target(target)

    def _validate_target(self, new_entity_id: str) -> None:
        """A replacement must point to a state or a registered HA entity."""
        if (
            self.hass.states.get(new_entity_id) is None
            and er.async_get(self.hass).async_get(new_entity_id) is None
        ):
            raise ValueError("replacement_entity_missing")

    async def async_prepare_apply(
        self, preview_id: str, occurrence_ids: list[str]
    ) -> dict[str, Any]:
        """Validate files and return authenticated native-editor REST operations."""
        async with self._lock:
            if preview_id != self._preview_id:
                raise ValueError("replacement_preview_stale")
            self._validate_selected_targets(set(occurrence_ids))
            changes = await self.hass.async_add_executor_job(
                replacement_contents,
                self._files,
                set(occurrence_ids),
            )
            for item, _ in changes:
                item.native_updates = []
            await self.hass.async_add_executor_job(verify_files, changes)
            updates = await self.hass.async_add_executor_job(
                native_config_updates, changes, Path(self.hass.config.path())
            )
            self._prepared_ids = set(occurrence_ids)
            return {"native_updates": updates}

    async def async_apply(
        self, preview_id: str, occurrence_ids: list[str]
    ) -> dict[str, Any]:
        """Finish admitted writes/rollback even if the requesting socket disconnects."""
        return await async_finish_non_interruptible(
            self._async_apply(preview_id, set(occurrence_ids))
        )

    async def _async_apply(self, preview_id: str, selected: set[str]) -> dict[str, Any]:
        async with self._lock:
            if preview_id != self._preview_id or selected != self._prepared_ids:
                raise ValueError("replacement_preview_stale")
            self._validate_selected_targets(selected)
            changes = await self.hass.async_add_executor_job(
                replacement_contents, self._files, selected
            )
            await self.hass.async_add_executor_job(verify_files, changes)
            await self.hass.async_add_executor_job(verify_native_files, changes)
            for item, _ in changes:
                if item.dashboard is not None:
                    current = await item.dashboard.async_load(False)
                    original = await self.hass.async_add_executor_job(
                        dashboard_configuration, item, item.content
                    )
                    if current != original:
                        raise ValueError("replacement_preview_stale")
            written: list[ReplacementFile] = []
            try:
                for item, content in changes:
                    if item.native_updates:
                        continue
                    written.append(item)
                    if item.dashboard is None:
                        await self.hass.async_add_executor_job(save_yaml, item, content)
                    else:
                        candidate = await self.hass.async_add_executor_job(
                            dashboard_configuration, item, content
                        )
                        await item.dashboard.async_save(candidate)
            except OSError, UnicodeError, yaml.YAMLError, HomeAssistantError:
                for item in reversed(written):
                    if item.dashboard is None:
                        await self.hass.async_add_executor_job(
                            save_yaml, item, item.content
                        )
                    else:
                        original = await self.hass.async_add_executor_job(
                            dashboard_configuration, item, item.content
                        )
                        await item.dashboard.async_save(original)
                raise ValueError("replacement_failed") from None
            self._preview_id = None
            self._prepared_ids = None
            self._files = []
            return {
                "replacement_count": len(selected),
                "file_count": len(changes),
                "yaml_changed": any(
                    item.dashboard is None and not item.native_updates
                    for item, _ in changes
                ),
            }
