"""On-demand Home Assistant configuration coherence scanner.

The scanner deliberately has no listeners or polling. It reads the configuration
only when an administrator requests a scan, runs filesystem work in Home Assistant's
executor and persists only the latest report.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from urllib.parse import quote

import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from .const import (
    COHERENCE_STORAGE_KEY,
    COHERENCE_STORAGE_VERSION,
    DATA_COHERENCE_RESULT,
    SIGNAL_COHERENCE_UPDATED,
)

_IGNORED_DIRECTORIES: Final = frozenset(
    {
        ".git",
        ".storage",
        ".venv",
        "__pycache__",
        "backups",
        "blueprints",
        "custom_components",
        "deps",
        "media",
        "node_modules",
        "share",
        "tmp",
        "trash",
        "venv",
        "www",
        "archive",
    }
)
_IGNORED_BRANCH_KEYS: Final = frozenset(
    {"description", "documentation", "example", "event_type", "logger", "url"}
)
_ACTION_KEYS: Final = frozenset(
    {"action", "perform_action", "service", "service_template"}
)
_INTENT_KEYS: Final = frozenset({"condition", "trigger"})
_IGNORED_ENTITY_REFERENCES: Final = frozenset(
    {
        "script.execute",
        "script.run",
        "script.start",
        "script.stop",
        "select.set",
        "script.is_running",
    }
)
_ENTITY_DOMAINS: Final = frozenset(
    {
        "ai_task",
        "air_quality",
        "alarm_control_panel",
        "alert",
        "assist_satellite",
        "automation",
        "binary_sensor",
        "button",
        "calendar",
        "camera",
        "climate",
        "conversation",
        "counter",
        "cover",
        "date",
        "datetime",
        "device_tracker",
        "event",
        "fan",
        "geo_location",
        "group",
        "humidifier",
        "image",
        "image_processing",
        "input_boolean",
        "input_button",
        "input_datetime",
        "input_number",
        "input_select",
        "input_text",
        "lawn_mower",
        "light",
        "lock",
        "media_player",
        "notify",
        "number",
        "person",
        "plant",
        "proximity",
        "remote",
        "scene",
        "schedule",
        "select",
        "sensor",
        "siren",
        "script",
        "stt",
        "sun",
        "switch",
        "text",
        "time",
        "timer",
        "todo",
        "tts",
        "update",
        "vacuum",
        "valve",
        "wake_word",
        "water_heater",
        "weather",
        "zone",
    }
)


@dataclass(frozen=True, slots=True)
class _Context:
    """Configuration object containing an entity reference."""

    kind: str
    name: str
    link_type: str | None = None
    link_target: str | None = None


@dataclass(frozen=True, slots=True)
class _Source:
    """One file to scan and its optional dashboard metadata."""

    path: Path
    relative_path: str
    kind: str = "file"
    name: str = ""
    dashboard_path: str | None = None


@dataclass(slots=True)
class _ScanState:
    """Mutable state local to one executor scan."""

    pattern: re.Pattern[str]
    existing_entities: frozenset[str]
    service_ids: frozenset[str]
    template_by_unique_id: dict[str, str]
    template_by_name: dict[str, str]
    template_by_config_entry: dict[str, str]
    results: list[dict[str, Any]]
    seen: set[tuple[str, str, int]]
    references_checked: int = 0


def _entity_pattern(existing_entities: frozenset[str]) -> re.Pattern[str]:
    """Build a strict entity pattern using known and standard HA domains."""
    domains = _ENTITY_DOMAINS | {
        entity_id.partition(".")[0]
        for entity_id in existing_entities
        if "." in entity_id
    }
    domain_pattern = "|".join(re.escape(domain) for domain in sorted(domains))
    return re.compile(
        rf"(?<![a-zA-Z0-9_./\\@$%&|-])(?:states\.)?"
        rf"((?:{domain_pattern})\.[a-z0-9_]+)"
        rf"(?!\()"
        rf"(?=(?:\.(?:state\b|attributes(?:\.|\[|\b)))|[^a-zA-Z0-9_.-]|$)",
        re.IGNORECASE,
    )


def _is_part_of_concatenation(value: str, match: re.Match[str]) -> bool:
    """Return whether a matched entity literal participates in string building."""
    start, end = match.span(1)
    before = value[:start].rstrip()
    after = value[end:].lstrip()

    if not before.endswith(("'", '"')):
        return False
    quote_char = before[-1]
    if not after.startswith(quote_char):
        return False

    left = before[:-1].rstrip()
    right = after[1:].lstrip()
    return left.endswith(("+", "~", "%")) or right.startswith(
        ("+", "~", "%", ".format")
    )


def _is_dynamic_reference(value: str, match: re.Match[str]) -> bool:
    """Return whether a candidate entity ID is dynamically constructed."""
    entity_id = match.group(1)
    if entity_id.endswith("_"):
        return True

    remaining = value[match.end(1) :].lstrip()
    if remaining.startswith(("(", "{", "[", "*")):
        return True

    return _is_part_of_concatenation(value, match)


def _scalar(node: Node | None) -> str | None:
    """Return the textual value of a scalar YAML node."""
    return node.value if isinstance(node, ScalarNode) else None


def _mapping(node: MappingNode) -> dict[str, Node]:
    """Return string-keyed children of a mapping node."""
    return {
        key.value: value for key, value in node.value if isinstance(key, ScalarNode)
    }


def _template_entity(values: dict[str, Node], state: _ScanState) -> str | None:
    """Resolve a YAML template definition to its registered entity when possible."""
    unique_id = _scalar(values.get("unique_id"))
    if unique_id and unique_id in state.template_by_unique_id:
        return state.template_by_unique_id[unique_id]
    name = _scalar(values.get("name"))
    if name:
        return state.template_by_name.get(name.casefold())
    return None


def _derive_context(
    node: MappingNode,
    parent: _Context,
    source: _Source,
    state: _ScanState,
    *,
    parent_key: str | None,
    sequence_index: int | None,
    in_template: bool,
) -> tuple[_Context, bool]:
    """Identify the closest editable Home Assistant object."""
    values = _mapping(node)
    platform = _scalar(values.get("platform"))
    template_scope = in_template or platform == "template"

    if source.kind == "dashboard" and parent_key == "views":
        view_name = _scalar(values.get("title")) or _scalar(values.get("path"))
        view_name = view_name or f"View {sequence_index or 0}"
        view_path = _scalar(values.get("path")) or str(sequence_index or 0)
        target = (
            f"{source.dashboard_path.rstrip('/')}/{quote(view_path, safe='/-_')}"
            if source.dashboard_path
            else None
        )
        dashboard_name = source.name or source.relative_path
        return (
            _Context(
                "dashboard",
                f"{dashboard_name} · {view_name}",
                "navigate" if target else None,
                target,
            ),
            template_scope,
        )

    if source.kind == "config_entries":
        entry_id = _scalar(values.get("entry_id"))
        domain = _scalar(values.get("domain"))
        if entry_id and domain:
            title = _scalar(values.get("title")) or domain
            template_entity = state.template_by_config_entry.get(entry_id)
            if template_entity:
                return (
                    _Context("template", title, "more_info", template_entity),
                    domain == "template",
                )
            return (
                _Context(
                    "integration",
                    title,
                    "navigate",
                    f"/config/integrations/integration/{quote(domain, safe='_-')}",
                ),
                domain == "template",
            )

    # Once an editable object is identified, nested choose/repeat/sequence blocks
    # belong to it and must not be mistaken for a new script or automation.
    if parent.kind != "file":
        return parent, template_scope

    if template_scope and ("state" in values or "availability" in values):
        entity_id = _template_entity(values, state)
        if entity_id is None and parent.kind == "template":
            return parent, True
        name = _scalar(values.get("name")) or entity_id or parent.name
        return (
            _Context(
                "template",
                name,
                "more_info" if entity_id else None,
                entity_id,
            ),
            True,
        )

    has_trigger = "trigger" in values or "triggers" in values
    has_action = "action" in values or "actions" in values
    automation_id = _scalar(values.get("id"))
    uses_blueprint = "use_blueprint" in values
    if (has_trigger and has_action) or (uses_blueprint and automation_id):
        name = _scalar(values.get("alias")) or automation_id or parent.name
        return (
            _Context(
                "automation",
                name,
                "navigate" if automation_id else None,
                (
                    f"/config/automation/edit/{quote(automation_id, safe='_-')}"
                    if automation_id
                    else None
                ),
            ),
            template_scope,
        )

    if "sequence" in values:
        script_id = _scalar(values.get("id")) or parent_key
        name = _scalar(values.get("alias")) or script_id or parent.name
        return (
            _Context(
                "script",
                name,
                "navigate" if script_id else None,
                (
                    f"/config/script/edit/{quote(script_id, safe='_-')}"
                    if script_id
                    else None
                ),
            ),
            template_scope,
        )

    if source.path.name.startswith("scene") and "entities" in values:
        scene_id = _scalar(values.get("id"))
        name = _scalar(values.get("name")) or scene_id or parent.name
        return (
            _Context(
                "scene",
                name,
                "navigate" if scene_id else None,
                (
                    f"/config/scene/edit/{quote(scene_id, safe='_-')}"
                    if scene_id
                    else None
                ),
            ),
            template_scope,
        )

    return parent, template_scope


def _record_scalar(
    node: ScalarNode,
    context: _Context,
    source: _Source,
    state: _ScanState,
    *,
    skip_plain_value: bool = False,
) -> None:
    """Record missing entity IDs found in one scalar node."""
    value = node.value
    if skip_plain_value and "{{" not in value and "{%" not in value:
        return
    for match in state.pattern.finditer(value):
        if _is_dynamic_reference(value, match):
            continue
        entity_id = match.group(1).lower()
        if entity_id in _IGNORED_ENTITY_REFERENCES or entity_id in state.service_ids:
            continue
        state.references_checked += 1
        if entity_id in state.existing_entities:
            continue
        line = node.start_mark.line + 1 + value[: match.start(1)].count("\n")
        signature = (entity_id, source.relative_path, line)
        if signature in state.seen:
            continue
        state.seen.add(signature)
        result: dict[str, Any] = {
            "entity_id": entity_id,
            "file": source.relative_path,
            "line": line,
            "source_type": context.kind,
            "source_name": context.name,
        }
        if context.link_type and context.link_target:
            result["link"] = {
                "type": context.link_type,
                (
                    "entity_id" if context.link_type == "more_info" else "path"
                ): context.link_target,
            }
        state.results.append(result)


def _walk(
    node: Node,
    context: _Context,
    source: _Source,
    state: _ScanState,
    *,
    parent_key: str | None = None,
    sequence_index: int | None = None,
    in_template: bool = False,
) -> None:
    """Walk YAML/JSON nodes while retaining source locations and object context."""
    if isinstance(node, MappingNode):
        current, template_scope = _derive_context(
            node,
            context,
            source,
            state,
            parent_key=parent_key,
            sequence_index=sequence_index,
            in_template=in_template,
        )
        for key_node, value_node in node.value:
            key = _scalar(key_node)
            if isinstance(key_node, ScalarNode):
                _record_scalar(key_node, current, source, state)
            normalized_key = key.casefold() if key else None
            if normalized_key in _IGNORED_BRANCH_KEYS:
                continue
            child_template_scope = template_scope or normalized_key == "template"
            if isinstance(value_node, ScalarNode):
                _record_scalar(
                    value_node,
                    current,
                    source,
                    state,
                    skip_plain_value=(
                        normalized_key in _ACTION_KEYS or normalized_key in _INTENT_KEYS
                    ),
                )
            else:
                _walk(
                    value_node,
                    current,
                    source,
                    state,
                    parent_key=key,
                    in_template=child_template_scope,
                )
        return

    if isinstance(node, SequenceNode):
        for index, child in enumerate(node.value):
            _walk(
                child,
                context,
                source,
                state,
                parent_key=parent_key,
                sequence_index=index,
                in_template=in_template,
            )
        return

    if isinstance(node, ScalarNode):
        _record_scalar(node, context, source, state)


def _dashboard_sources(config_dir: Path) -> dict[str, tuple[str, str]]:
    """Map Lovelace storage filenames to their title and frontend path."""
    dashboards: dict[str, tuple[str, str]] = {"lovelace": ("Lovelace", "/lovelace")}
    metadata_path = config_dir / ".storage" / "lovelace_dashboards"
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dashboards
    data = payload.get("data", {})
    items = data.get("items", data if isinstance(data, list) else [])
    if not isinstance(items, list):
        return dashboards
    for item in items:
        if not isinstance(item, dict):
            continue
        dashboard_id = item.get("id")
        url_path = item.get("url_path")
        if not isinstance(dashboard_id, str) or not isinstance(url_path, str):
            continue
        dashboards[f"lovelace.{dashboard_id}"] = (
            str(item.get("title") or url_path),
            f"/{url_path.strip('/')}",
        )
    return dashboards


def _discover_sources(
    config_dir: Path,
    yaml_dashboards: dict[str, tuple[str, str]] | None = None,
) -> list[_Source]:
    """Discover supported configuration files without entering unrelated trees."""
    sources: list[_Source] = []
    dashboard_files = yaml_dashboards or {}
    for directory, child_directories, filenames in os.walk(config_dir):
        child_directories[:] = [
            child for child in child_directories if child not in _IGNORED_DIRECTORIES
        ]
        directory_path = Path(directory)
        for filename in filenames:
            path = directory_path / filename
            if path.suffix.casefold() not in {".yaml", ".yml"}:
                continue
            relative_path = path.relative_to(config_dir).as_posix()
            dashboard = dashboard_files.get(relative_path)
            sources.append(
                _Source(
                    path,
                    relative_path,
                    "dashboard" if dashboard else "file",
                    dashboard[0] if dashboard else "",
                    dashboard[1] if dashboard else None,
                )
            )

    storage_dir = config_dir / ".storage"
    for filename, (name, dashboard_path) in _dashboard_sources(config_dir).items():
        path = storage_dir / filename
        if path.is_file():
            sources.append(
                _Source(
                    path,
                    f".storage/{filename}",
                    "dashboard",
                    name,
                    dashboard_path,
                )
            )
    config_entries = storage_dir / "core.config_entries"
    if config_entries.is_file():
        sources.append(
            _Source(
                config_entries,
                ".storage/core.config_entries",
                "config_entries",
                "Home Assistant",
            )
        )
    return sorted(sources, key=lambda source: source.relative_path)


def scan_configuration(
    config_dir: Path,
    existing_entities: frozenset[str],
    service_ids: frozenset[str] = frozenset(),
    template_by_unique_id: dict[str, str] | None = None,
    template_by_name: dict[str, str] | None = None,
    template_by_config_entry: dict[str, str] | None = None,
    yaml_dashboards: dict[str, tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Synchronously scan configuration files; intended for an executor thread."""
    started = time.monotonic()
    state = _ScanState(
        _entity_pattern(existing_entities),
        existing_entities,
        service_ids,
        template_by_unique_id or {},
        template_by_name or {},
        template_by_config_entry or {},
        [],
        set(),
    )
    sources = _discover_sources(config_dir, yaml_dashboards)
    skipped_files = 0
    for source in sources:
        try:
            content = source.path.read_text(encoding="utf-8")
            documents = yaml.compose_all(content, Loader=yaml.SafeLoader)
            root_context = _Context(
                source.kind if source.kind != "config_entries" else "file",
                source.name or source.relative_path,
            )
            for document in documents:
                if document is not None:
                    _walk(document, root_context, source, state)
        except (OSError, UnicodeError, yaml.YAMLError):
            skipped_files += 1

    state.results.sort(
        key=lambda result: (
            result["entity_id"],
            result["file"],
            result["line"],
        )
    )
    return {
        "results": state.results,
        "missing_count": len(state.results),
        "missing_entity_count": len({result["entity_id"] for result in state.results}),
        "files_scanned": len(sources) - skipped_files,
        "files_skipped": skipped_files,
        "references_checked": state.references_checked,
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def _registry_entries(registry: Any) -> list[Any]:
    """Return entity registry entries across supported HA registry containers."""
    entries = getattr(registry, "entities", None)
    if entries is None:
        entries = getattr(registry, "entries", {})
    return list(entries.values())


async def async_scan_configuration(hass: HomeAssistant) -> dict[str, Any]:
    """Collect live HA metadata and run one configuration scan in the executor."""
    registry_entries = _registry_entries(er.async_get(hass))
    existing_entities = {state.entity_id.lower() for state in hass.states.async_all()}
    existing_entities.update(
        entry.entity_id.lower()
        for entry in registry_entries
        if getattr(entry, "disabled_by", None) is not None
    )

    template_by_unique_id: dict[str, str] = {}
    template_by_name: dict[str, str] = {}
    template_by_config_entry: dict[str, str] = {}
    for entry in registry_entries:
        if getattr(entry, "platform", None) != "template":
            continue
        entity_id = entry.entity_id
        if unique_id := getattr(entry, "unique_id", None):
            template_by_unique_id[str(unique_id)] = entity_id
        name = getattr(entry, "original_name", None) or getattr(entry, "name", None)
        if name:
            template_by_name[str(name).casefold()] = entity_id
        if config_entry_id := getattr(entry, "config_entry_id", None):
            template_by_config_entry.setdefault(str(config_entry_id), entity_id)

    service_ids: set[str] = set()
    try:
        services = hass.services.async_services()
    except AttributeError:
        services = {}
    for domain, domain_services in services.items():
        service_ids.update(f"{domain}.{service}".lower() for service in domain_services)

    yaml_dashboards: dict[str, tuple[str, str]] = {}
    lovelace_data = hass.data.get("lovelace")
    for url_path, dashboard in getattr(lovelace_data, "dashboards", {}).items():
        dashboard_path = getattr(dashboard, "path", None)
        if not dashboard_path:
            continue
        try:
            relative_path = (
                Path(dashboard_path).relative_to(Path(hass.config.path())).as_posix()
            )
        except ValueError:
            continue
        config = getattr(dashboard, "config", None) or {}
        title = str(config.get("title") or relative_path)
        yaml_dashboards[relative_path] = (
            title,
            f"/{str(url_path or 'lovelace').strip('/')}",
        )

    return await hass.async_add_executor_job(
        scan_configuration,
        Path(hass.config.path()),
        frozenset(existing_entities),
        frozenset(service_ids),
        template_by_unique_id,
        template_by_name,
        template_by_config_entry,
        yaml_dashboards,
    )


async def async_run_coherence_scan(hass: HomeAssistant) -> dict[str, Any]:
    """Run one scan, persist its result and notify Home Assistant entities."""
    result = await async_scan_configuration(hass)
    result["scanned_at"] = dt_util.now().isoformat()
    await Store[dict[str, Any]](
        hass, COHERENCE_STORAGE_VERSION, COHERENCE_STORAGE_KEY
    ).async_save(result)
    hass.data[DATA_COHERENCE_RESULT] = result
    async_dispatcher_send(hass, SIGNAL_COHERENCE_UPDATED, result)
    return result


async def async_load_coherence_result(
    hass: HomeAssistant,
) -> dict[str, Any] | None:
    """Restore the latest valid coherence report from Home Assistant storage."""
    result = await Store[dict[str, Any]](
        hass, COHERENCE_STORAGE_VERSION, COHERENCE_STORAGE_KEY
    ).async_load()
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("results"), list)
        or not isinstance(result.get("scanned_at"), str)
        or not isinstance(result.get("missing_entity_count"), int)
    ):
        return None
    hass.data[DATA_COHERENCE_RESULT] = result
    return result
