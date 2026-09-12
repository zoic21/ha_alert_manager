"""Strict, versioned YAML interchange for Alert Manager.

This module deliberately only understands Alert Manager's own comparison rule
model.  It does not interpret Home Assistant automation conditions.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

import yaml

from .config_defaults import CATEGORIES, DEFAULT_CONFIG
from .const import ATTRIBUTE_SOURCES, TRANSITION_SOURCES
from .models import Rule, normalize_rule_source
from .notifications import validate_notification_profiles
from .pack_migration import (
    migrate_exclusions,
    migrate_flapping_precedence,
    migrate_pack_config,
)
from .packs import PACKS_BY_ID
from .validation import validate_config, validate_rule_payload

FORMAT_VERSION = 2
MAX_YAML_SIZE = 1_000_000


_RULE_YAML_KEYS = {
    "blueprint",
    "from_value",
    "to_value",
    "auto_resolve",
    "id",
    "name",
    "enabled",
    "entity_ids",
    "label_ids",
    "source",
    "attribute",
    "operator",
    "value",
    "duration",
    "message",
    "update_message_when_active",
    "condition_template",
    "flapping_enabled",
    "flapping_occurrences",
    "flapping_window",
    "flapping_recovery",
}
_CONFIG_YAML_KEY_ORDER = (
    "monitoring_enabled",
    "coherence_schedule",
    "coherence_scan_esphome",
    "coherence_alert_enabled",
    "coherence_ignored_entity_references",
    "pending_display_delay",
    "excluded_labels",
    "automatic",
    "notification_profiles",
    "notification_batch_delay",
)
_CONFIG_YAML_KEYS = set(_CONFIG_YAML_KEY_ORDER)


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe loader which rejects duplicate mapping keys instead of overwriting."""


def _construct_mapping(
    loader: _UniqueKeyLoader, node: yaml.nodes.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    """Construct mappings without accepting duplicate keys."""
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as err:
            raise ValueError("YAML mapping keys must be scalar") from err
        if duplicate:
            raise ValueError(f"Duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _load_yaml(raw_yaml: Any, *, description: str) -> Any:
    """Parse an UTF-8 YAML string and turn parser errors into API errors."""
    if not isinstance(raw_yaml, str):
        raise ValueError(f"{description} YAML must be text")
    try:
        encoded_size = len(raw_yaml.encode("utf-8"))
    except UnicodeEncodeError as err:
        raise ValueError(f"{description} YAML must contain valid Unicode") from err
    if encoded_size > MAX_YAML_SIZE:
        raise ValueError(f"{description} YAML must not exceed {MAX_YAML_SIZE} bytes")
    try:
        loaded = yaml.load(raw_yaml, Loader=_UniqueKeyLoader)
    except (yaml.YAMLError, ValueError) as err:
        raise ValueError(f"Invalid YAML: {err}") from err
    if loaded is None:
        raise ValueError(f"{description} YAML must not be empty")
    return loaded


def _reject_unknown(data: Mapping[str, Any], allowed: set[str], *, prefix: str) -> None:
    """Reject unknown fields with one concise, stable error."""
    invalid = [key for key in data if not isinstance(key, str)]
    if invalid:
        raise ValueError(f"Invalid {prefix} field name: {invalid[0]!r}")
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"Unknown {prefix} field: {sorted(unknown)[0]}")


def parse_configuration_field_yaml(
    raw_yaml: str, field_id: str, pack_id: str | None = None
) -> Any:
    """Validate only the field owned by a configuration drawer, without mutation."""
    if pack_id in PACKS_BY_ID and field_id == "pack":
        data = _load_yaml(raw_yaml, description="Configuration")
        if not isinstance(data, dict) or set(data) != {"pack"}:
            raise ValueError("Expected one pack mapping")
        from .validation import validate_config_update

        changes = {"automatic": {pack_id: data["pack"]}}
        validate_config_update(changes)
        return validate_config(changes)["automatic"][pack_id]
    if pack_id is None:
        if field_id not in {"excluded_entities", "excluded_devices", "entity_delays"}:
            raise ValueError("Unsupported configuration panel")
    else:
        pack = PACKS_BY_ID.get(pack_id)
        if pack is None or not any(
            field.id == field_id and field.type.endswith("_map")
            for field in pack.config_fields
        ):
            raise ValueError("Unsupported configuration panel")
    data = _load_yaml(raw_yaml, description="Configuration")
    if not isinstance(data, dict):
        raise ValueError("Configuration YAML root must be an object")
    _reject_unknown(data, {field_id}, prefix="configuration panel")
    if field_id not in data:
        raise ValueError(f"Missing configuration field: {field_id}")
    candidate = data if pack_id is None else {"automatic": {pack_id: data}}
    validated = validate_config(candidate)
    return (
        validated[field_id]
        if pack_id is None
        else validated["automatic"][pack_id][field_id]
    )


def rule_to_yaml_data(
    rule: Rule | Mapping[str, Any], *, include_id: bool = False
) -> dict[str, Any]:
    """Return the documented rule shape in a stable human-readable order."""
    data = rule.as_dict() if isinstance(rule, Rule) else dict(rule)
    data = normalize_rule_source(data)
    source = data["source"]
    result: dict[str, Any] = {
        "name": data.get("name"),
        "enabled": data.get("enabled", True),
        "entity_ids": data.get("entity_ids"),
        "label_ids": data.get("label_ids", []),
        "source": source,
    }
    if result["source"] in ATTRIBUTE_SOURCES:
        result["attribute"] = data.get("attribute")
    if result["source"] not in ("jinja", "unchanged", *TRANSITION_SOURCES):
        result["operator"] = data.get("operator")
        if result["operator"] != "unchanged":
            result["value"] = data.get("value")
    if source in TRANSITION_SOURCES:
        result.update(
            {key: data.get(key) for key in ("from_value", "to_value", "auto_resolve")}
        )
    result.update(
        {
            "duration": data.get("duration"),
            "message": data.get("message"),
            "update_message_when_active": data.get("update_message_when_active", False),
            "condition_template": data.get("condition_template"),
            "flapping_enabled": data.get("flapping_enabled", False),
            "flapping_occurrences": data.get("flapping_occurrences"),
            "flapping_window": data.get("flapping_window"),
            "flapping_recovery": data.get("flapping_recovery"),
        }
    )
    if data.get("blueprint") is not None:
        result["blueprint"] = data["blueprint"]
    if include_id:
        return {"id": data.get("id"), **result}
    return result


def dump_rule_yaml(rule: Rule | Mapping[str, Any]) -> str:
    """Serialize one editable rule, intentionally omitting its immutable id."""
    return _dump_yaml(rule_to_yaml_data(rule))


def parse_rule_yaml(raw_yaml: Any, *, rule_id: str | None = None) -> Rule:
    """Parse and validate the YAML representation of one rule.

    Existing rule ids are owned by the URL/WebSocket target and never edited in
    the YAML editor.  An id may be present only when it exactly matches that
    target, which makes pasted exported rules safe to inspect as well.
    """
    data = _load_yaml(raw_yaml, description="Rule")
    if not isinstance(data, dict):
        raise ValueError("Rule YAML root must be an object")
    _reject_unknown(data, _RULE_YAML_KEYS, prefix="rule")
    if rule_id is None:
        if "id" in data:
            raise ValueError("Rule id is generated by the backend")
        try:
            return validate_rule_payload(data)
        except TypeError as err:
            raise ValueError(f"Invalid rule: {err}") from err
    supplied_id = data.pop("id", rule_id)
    if supplied_id != rule_id:
        raise ValueError("Rule id is immutable")
    try:
        return validate_rule_payload(data, rule_id=rule_id)
    except TypeError as err:
        raise ValueError(f"Invalid rule: {err}") from err


def parse_notification_profile_yaml(raw_yaml: str, profile_id: str) -> dict[str, Any]:
    """Validate an editable profile without allowing its identity to change."""
    data = _load_yaml(raw_yaml, description="Notification profile")
    if not isinstance(data, dict):
        raise ValueError("Notification profile YAML root must be an object")
    if data.get("id", profile_id) != profile_id:
        raise ValueError("Notification profile id is immutable")
    return validate_notification_profiles([{**data, "id": profile_id}])[0]


def dump_config_yaml(config: Mapping[str, Any]) -> str:
    """Serialize all persistent configuration, excluding runtime alert data."""
    normalized = validate_config(dict(config))
    config_data = {key: deepcopy(normalized[key]) for key in _CONFIG_YAML_KEY_ORDER}
    rules = [rule_to_yaml_data(rule, include_id=True) for rule in normalized["rules"]]
    return _dump_yaml(
        {
            "version": FORMAT_VERSION,
            "config": config_data,
            "rules": rules,
        }
    )


def parse_config_yaml(
    raw_yaml: Any, existing_rules: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Parse one complete configuration import with an intentionally strict schema."""
    document = _load_yaml(raw_yaml, description="Configuration")
    if not isinstance(document, dict):
        raise ValueError("Configuration YAML root must be an object")
    _reject_unknown(document, {"version", "config", "rules"}, prefix="configuration")
    if document.get("version") not in (1, FORMAT_VERSION):
        raise ValueError(
            f"Unsupported configuration format version: {document.get('version')}"
        )
    config = document.get("config")
    if not isinstance(config, dict):
        raise ValueError("Configuration config must be an object")
    _reject_unknown(
        config,
        _CONFIG_YAML_KEYS
        | (
            {
                "global_delay",
                "entity_delays",
                "excluded_entities",
                "excluded_devices",
            }
            if document.get("version") == 1
            else set()
        ),
        prefix="config",
    )
    # Optional settings use current defaults; format 1 is still used by 2.2/2.3.
    missing_config = (
        _CONFIG_YAML_KEYS
        - {
            "monitoring_enabled",
            "coherence_schedule",
            "coherence_scan_esphome",
            "coherence_alert_enabled",
            "coherence_ignored_entity_references",
            "pending_display_delay",
            "notification_profiles",
            "notification_batch_delay",
        }
        - set(config)
    )
    if missing_config:
        raise ValueError(f"Missing config field: {sorted(missing_config)[0]}")
    automatic = config.get("automatic")
    if not isinstance(automatic, dict):
        raise ValueError("config.automatic must be an object")
    # Exports created before newer packs remain importable; their configuration
    # is filled from the current defaults by validate_config().
    # Only the four historical packs were mandatory in the V1 format.
    required = {"unavailable", "connectivity", "unifi", "battery"}
    allowed_missing = set(CATEGORIES) - required
    missing = set(CATEGORIES) - set(automatic)
    unknown = set(automatic) - set(CATEGORIES)
    if unknown or missing - allowed_missing:
        field = sorted(unknown or missing)[0]
        raise ValueError(f"Invalid automatic pack configuration: {field}")
    for category, settings in automatic.items():
        if not isinstance(settings, dict):
            raise ValueError(f"automatic.{category} must be an object")
        allowed = set(DEFAULT_CONFIG["automatic"][category])
        if document.get("version") == 1:
            allowed |= {"device_thresholds", "failure_thresholds"}
        _reject_unknown(settings, allowed, prefix=f"automatic.{category}")

    rules = document.get("rules")
    if not isinstance(rules, list):
        raise ValueError("Configuration rules must be a list")
    normalized_rules: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_rule in enumerate(rules):
        if not isinstance(raw_rule, dict):
            raise ValueError(f"rules[{index}] must be an object")
        _reject_unknown(raw_rule, _RULE_YAML_KEYS, prefix=f"rules[{index}]")
        rule_id = raw_rule.get("id")
        if rule_id is None:
            try:
                rule = validate_rule_payload(dict(raw_rule))
            except TypeError as err:
                raise ValueError(f"Invalid rules[{index}]: {err}") from err
            # Older portable exports omitted IDs. Reuse an unambiguous unchanged
            # local rule identity instead of duplicating its compatible alerts.
            comparable = {
                key: value for key, value in rule.as_dict().items() if key != "id"
            }
            matches = [
                item["id"]
                for item in existing_rules or []
                if item.get("id") not in seen_ids
                and {key: value for key, value in item.items() if key != "id"}
                == comparable
            ]
            if len(matches) == 1:
                rule = validate_rule_payload(dict(raw_rule), rule_id=matches[0])
            if rule.id in seen_ids:
                raise ValueError(f"Duplicate rule id: {rule.id}")
            seen_ids.add(rule.id)
            normalized_rules.append(rule.as_dict())
            continue
        if not isinstance(rule_id, str) or not rule_id:
            raise ValueError(f"rules[{index}].id must be a non-empty string")
        if rule_id in seen_ids:
            raise ValueError(f"Duplicate rule id: {rule_id}")
        seen_ids.add(rule_id)
        try:
            rule = validate_rule_payload(dict(raw_rule), rule_id=rule_id)
        except TypeError as err:
            raise ValueError(f"Invalid rules[{index}]: {err}") from err
        normalized_rules.append(rule.as_dict())

    candidate = {**deepcopy(config), "rules": normalized_rules}
    if document.get("version") == 1:
        candidate = migrate_flapping_precedence(migrate_pack_config(candidate))
    # Pure conversion makes the preview identical to the configuration imported.
    return validate_config(migrate_exclusions(candidate))


def import_summary(config: Mapping[str, Any]) -> dict[str, Any]:
    """Build the small, safe import preview presented by the panel."""
    automatic = config["automatic"]
    return {
        "rules": len(config["rules"]),
        "enabled_packs": sum(1 for pack in automatic.values() if pack["enabled"]),
        "pack_exceptions": sum(
            len(scope.get(f"{kind}_overrides", {}))
            for pack in automatic.values()
            for scope in (pack, *pack.get("source_packs", {}).values())
            for kind in ("device", "entity")
        ),
        "warnings": [],
    }


def _dump_yaml(data: Any) -> str:
    """Produce deterministic UTF-8 compatible YAML without aliases or sorting."""
    return yaml.safe_dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=88,
    )
