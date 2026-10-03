"""Explicit entity-reference replacement in YAML and native HA dashboards."""

from __future__ import annotations

import asyncio
import json
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
    native_updates: list[dict[str, Any]] = field(default_factory=list)


def _validate_yaml(content: str, new_entity_id: str | None = None) -> None:
    """Parse every document, accepting native HA tags without resolving them."""
    documents = list(yaml.compose_all(content, Loader=yaml.SafeLoader))
    if new_entity_id is None:
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
            if (
                sum(
                    isinstance(key, ScalarNode) and key.value == new_entity_id
                    for key, _ in node.value
                )
                > 1
            ):
                raise ValueError("replacement_yaml_invalid")
            pending.extend(value for _, value in node.value)
        elif isinstance(node, SequenceNode):
            pending.extend(node.value)


def prepare_replacement(
    config_dir: Path,
    old_entity_id: str,
    metadata: dict[str, Any],
    scan_esphome: bool,
    dashboards: dict[str, tuple[_Source, str]],
) -> tuple[list[ReplacementFile], int]:
    """Reuse coherence traversal and contexts; run entirely in the executor."""
    sources = [
        source
        for source in _discover_sources(
            config_dir, metadata["yaml_dashboards"], scan_esphome=scan_esphome
        )
        if source.path.suffix.casefold() in {".yaml", ".yml"}
        and ".storage" not in source.path.parts
        and not source.path.is_symlink()
    ]
    sources.extend(source for source, _ in dashboards.values())
    files: list[ReplacementFile] = []
    skipped = 0
    for source in sorted(sources, key=lambda item: item.relative_path):
        try:
            content = (
                dashboards[source.relative_path][1]
                if source.relative_path in dashboards
                else source.path.read_bytes().decode("utf-8")
            )
            replacement = _replacement_file(source, content, old_entity_id, metadata)
        except OSError, UnicodeError, yaml.YAMLError:
            skipped += 1
            continue
        if replacement.occurrences:
            files.append(replacement)
    return files, skipped


def _replacement_file(
    source: _Source, content: str, old_entity_id: str, metadata: dict[str, Any]
) -> ReplacementFile:
    """Collect physical occurrences within one coherence object traversal."""
    pattern = _entity_pattern(frozenset({old_entity_id}))
    documents = list(yaml.compose_all(content, Loader=yaml.SafeLoader))
    replacement = ReplacementFile(source, content)
    seen: set[int] = set()

    def visit(node: ScalarNode, context: _Context, _source: _Source) -> None:
        # Marks point into the original text, preserving comments, quotes,
        # multiline templates, CRLF and !include/!secret tags.
        raw = content[node.start_mark.index : node.end_mark.index]
        for match in pattern.finditer(raw):
            if match.group(1).lower() != old_entity_id or (
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
    files: list[ReplacementFile], selected: set[str], new_entity_id: str
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
            content = content[: row["start"]] + new_entity_id + content[row["end"] :]
        try:
            _validate_yaml(content, new_entity_id)
            if item.dashboard is not None:
                json.loads(content)
        except yaml.YAMLError, ValueError:
            raise ValueError("replacement_yaml_invalid") from None
        changes.append((item, content))
    return changes


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
        self._new_entity_id = ""
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
            metadata = configuration_scan_metadata(self.hass)
            config_dir = Path(self.hass.config.path())
            dashboard_inputs = {}
            dashboard_objects = {}
            lovelace = self.hass.data.get("lovelace")
            for url_path, dashboard in getattr(lovelace, "dashboards", {}).items():
                if dashboard.mode != "storage":
                    continue
                if (await dashboard.async_get_info()).get("mode") == "auto-gen":
                    continue
                config = await dashboard.async_load(False)
                content = await self.hass.async_add_executor_job(
                    lambda config=config: json.dumps(
                        config, ensure_ascii=False, indent=2
                    )
                )
                info = dashboard.config or {}
                filename = "lovelace" + (f".{info['id']}" if info.get("id") else "")
                relative_path = f".storage/{filename}"
                source = _Source(
                    config_dir / relative_path,
                    relative_path,
                    "dashboard",
                    info.get("title") or "Lovelace",
                    f"/{url_path or 'lovelace'}",
                )
                dashboard_inputs[relative_path] = (source, content)
                dashboard_objects[relative_path] = dashboard
            files, skipped = await self.hass.async_add_executor_job(
                prepare_replacement,
                config_dir,
                old_entity_id,
                metadata,
                scan_esphome,
                dashboard_inputs,
            )
            for item in files:
                item.dashboard = dashboard_objects.get(item.source.relative_path)
            self._prepared_ids = None
            self._files = files
            self._new_entity_id = new_entity_id
            self._preview_id = uuid4().hex
            rows = [
                {
                    key: value
                    for key, value in row.items()
                    if key not in {"start", "end"}
                }
                for item in files
                for row in item.occurrences
            ]
            return {
                "preview_id": self._preview_id,
                "old_entity_id": old_entity_id,
                "new_entity_id": new_entity_id,
                "replacements": rows,
                "replacement_count": len(rows),
                "file_count": len(files),
                "files_skipped": skipped,
            }

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
            self._validate_target(self._new_entity_id)
            changes = await self.hass.async_add_executor_job(
                replacement_contents,
                self._files,
                set(occurrence_ids),
                self._new_entity_id,
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
            self._validate_target(self._new_entity_id)
            changes = await self.hass.async_add_executor_job(
                replacement_contents, self._files, selected, self._new_entity_id
            )
            await self.hass.async_add_executor_job(verify_files, changes)
            await self.hass.async_add_executor_job(verify_native_files, changes)
            for item, _ in changes:
                if item.dashboard is not None:
                    current = await item.dashboard.async_load(False)
                    original = await self.hass.async_add_executor_job(
                        json.loads, item.content
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
                            json.loads, content
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
                            json.loads, item.content
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
