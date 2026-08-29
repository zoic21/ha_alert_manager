"""Strict backend validation for Alert Manager configuration."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from homeassistant.core import valid_entity_id

from .const import (
    ALERT_MANAGER_ENTITY_IDS,
    CATEGORIES,
    COHERENCE_SCHEDULES,
    CUSTOM_RULE_ALLOWED_ENTITY_IDS,
    DEFAULT_CONFIG,
    MAX_DELAY,
    MAX_HISTORY_LIMIT,
    MIN_DELAY,
    MIN_HISTORY_LIMIT,
)
from .models import Rule, safe_float
from .packs import PACKS, PACKS_BY_ID

_DEVICE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_CONFIG_UPDATE_KEYS = {
    "global_delay",
    # Accepted temporarily so a cached dev14 panel can update during upgrade.
    "active_display_delay",
    "pending_display_delay",
    "coherence_schedule",
    "coherence_scan_esphome",
    "coherence_ignored_entity_references",
    "excluded_labels",
    # Accepted only so a cached V1 panel can update safely during migration.
    "exclusion_label",
    "excluded_entities",
    "excluded_devices",
    "entity_delays",
    "automatic",
    "rules",
}
_AUTOMATIC_KEYS = {
    pack.id: {"enabled", "delay", *(field.id for field in pack.config_fields)}
    for pack in PACKS
}
# Accepted only so a cached V1 panel can finish one safe migration update.
_AUTOMATIC_KEYS["unavailable"].add("domains")
_RULE_CLIENT_KEYS = {
    "name",
    "entity_ids",
    "enabled",
    "source",
    "attribute",
    "operator",
    "value",
    "duration",
    "message",
    "condition_template",
}
_REQUIRED_RULE_KEYS = {"name", "entity_ids", "duration"}


def validate_config_update(changes: Any) -> None:
    """Reject unknown fields in a partial WebSocket configuration update."""
    if not isinstance(changes, dict):
        raise ValueError("config must be an object")
    unknown = _unknown_keys(changes, _CONFIG_UPDATE_KEYS)
    if unknown:
        raise ValueError(f"Unknown configuration field: {sorted(unknown)[0]}")
    automatic = changes.get("automatic")
    if automatic is None:
        return
    if not isinstance(automatic, dict):
        raise ValueError("automatic must be an object")
    unknown_categories = _unknown_keys(automatic, set(_AUTOMATIC_KEYS))
    if unknown_categories:
        raise ValueError(f"Unknown automatic category: {sorted(unknown_categories)[0]}")
    for category, category_changes in automatic.items():
        if not isinstance(category_changes, dict):
            raise ValueError(f"automatic.{category} must be an object")
        unknown_fields = _unknown_keys(category_changes, _AUTOMATIC_KEYS[category])
        if unknown_fields:
            field = sorted(unknown_fields)[0]
            raise ValueError(f"Unknown automatic.{category} field: {field}")


def validate_config(config: Any) -> dict[str, Any]:
    """Validate and normalize a complete configuration snapshot."""
    if not isinstance(config, dict):
        raise ValueError("Configuration must be an object")

    result = deepcopy(DEFAULT_CONFIG)
    monitoring_enabled = config.get("monitoring_enabled", result["monitoring_enabled"])
    if not isinstance(monitoring_enabled, bool):
        raise ValueError("monitoring_enabled must be a boolean")
    result["monitoring_enabled"] = monitoring_enabled
    history_limit = config.get("history_limit", result["history_limit"])
    if isinstance(history_limit, bool) or not isinstance(history_limit, int):
        raise ValueError("history_limit must be an integer")
    if not MIN_HISTORY_LIMIT <= history_limit <= MAX_HISTORY_LIMIT:
        raise ValueError(
            f"history_limit must be between {MIN_HISTORY_LIMIT} and {MAX_HISTORY_LIMIT}"
        )
    result["history_limit"] = history_limit
    coherence_schedule = config.get("coherence_schedule", result["coherence_schedule"])
    if coherence_schedule not in COHERENCE_SCHEDULES:
        raise ValueError(
            "coherence_schedule must be one of: " + ", ".join(COHERENCE_SCHEDULES)
        )
    result["coherence_schedule"] = coherence_schedule
    coherence_scan_esphome = config.get(
        "coherence_scan_esphome", result["coherence_scan_esphome"]
    )
    if not isinstance(coherence_scan_esphome, bool):
        raise ValueError("coherence_scan_esphome must be a boolean")
    result["coherence_scan_esphome"] = coherence_scan_esphome
    result["coherence_ignored_entity_references"] = (
        validate_coherence_ignored_entity_references(
            config.get("coherence_ignored_entity_references", [])
        )
    )
    result["global_delay"] = validate_delay(
        config.get("global_delay", result["global_delay"]), "global_delay"
    )
    result["pending_display_delay"] = validate_delay(
        config.get(
            "pending_display_delay",
            config.get("active_display_delay", result["pending_display_delay"]),
        ),
        "pending_display_delay",
    )

    result["excluded_labels"] = validate_label_list(config.get("excluded_labels", []))

    result["excluded_entities"] = validate_entity_list(
        config.get("excluded_entities", [])
    )
    if any(
        entity_id in ALERT_MANAGER_ENTITY_IDS
        for entity_id in result["excluded_entities"]
    ):
        raise ValueError("Alert Manager entities cannot be configured")
    result["excluded_devices"] = validate_device_list(
        config.get("excluded_devices", [])
    )

    entity_delays = config.get("entity_delays", {})
    if not isinstance(entity_delays, dict):
        raise ValueError("entity_delays must be an object")
    normalized_delays: dict[str, int] = {}
    for entity_id, delay in entity_delays.items():
        validate_entity_id(entity_id)
        if entity_id in ALERT_MANAGER_ENTITY_IDS:
            raise ValueError("Alert Manager entities cannot be configured")
        normalized_delays[entity_id] = validate_delay(
            delay, f"entity_delays.{entity_id}"
        )
    result["entity_delays"] = normalized_delays

    automatic = config.get("automatic", {})
    if not isinstance(automatic, dict):
        raise ValueError("automatic must be an object")
    for category in CATEGORIES:
        incoming = automatic.get(category, {})
        if not isinstance(incoming, dict):
            raise ValueError(f"automatic.{category} must be an object")
        category_config = result["automatic"][category]
        enabled = incoming.get("enabled", category_config["enabled"])
        if not isinstance(enabled, bool):
            raise ValueError(f"automatic.{category}.enabled must be a boolean")
        category_config["enabled"] = enabled
        pack_delay = incoming.get("delay", category_config["delay"])
        category_config["delay"] = (
            None
            if pack_delay is None
            else validate_delay(pack_delay, f"automatic.{category}.delay")
        )

        for field in PACKS_BY_ID[category].config_fields:
            raw_value = incoming.get(
                field.id,
                category_config.get(field.id, deepcopy(field.default)),
            )
            category_config[field.id] = _normalize_pack_field(
                category,
                field.id,
                field.type,
                raw_value,
                field.minimum,
                field.maximum,
            )

    rules = config.get("rules", [])
    if not isinstance(rules, list):
        raise ValueError("rules must be a list")
    seen: set[str] = set()
    normalized_rules: list[dict[str, Any]] = []
    for raw_rule in rules:
        if not isinstance(raw_rule, dict):
            raise ValueError("Each rule must be an object")
        rule = Rule.from_dict(raw_rule)
        rule.entity_ids = validate_rule_entity_ids(rule.entity_ids)
        if rule.id in seen:
            raise ValueError(f"Duplicate rule id: {rule.id}")
        seen.add(rule.id)
        normalized_rules.append(rule.as_dict())
    result["rules"] = normalized_rules
    return result


def _normalize_pack_field(
    pack_id: str,
    field_id: str,
    field_type: str,
    value: Any,
    minimum: float | None,
    maximum: float | None,
) -> Any:
    """Normalize one backend-declared pack field."""
    path = f"automatic.{pack_id}.{field_id}"
    if field_type == "number":
        return _validate_pack_number(value, path, minimum, maximum)
    if field_type == "device_number_map":
        if not isinstance(value, dict):
            raise ValueError(f"{path} must be an object")
        normalized: dict[str, float] = {}
        for device_id, threshold in value.items():
            if not isinstance(device_id, str) or not _DEVICE_ID_RE.fullmatch(device_id):
                raise ValueError(f"{path} contains an invalid device id")
            normalized[device_id] = _validate_pack_number(
                threshold,
                f"{path}.{device_id}",
                minimum,
                maximum,
            )
        return normalized
    raise ValueError(f"Unsupported pack configuration field type: {field_type}")


def _validate_pack_number(
    value: Any,
    path: str,
    minimum: float | None,
    maximum: float | None,
) -> float:
    """Return a finite pack number inside its declared bounds."""
    number = safe_float(value)
    if (
        number is None
        or (minimum is not None and number < minimum)
        or (maximum is not None and number > maximum)
    ):
        if minimum is not None and maximum is not None:
            raise ValueError(
                f"{path} must be a finite number between {minimum:g} and {maximum:g}"
            )
        raise ValueError(f"{path} must be a finite number")
    return number


def validate_rule_payload(data: Any, *, rule_id: str | None = None) -> Rule:
    """Validate a rule create/update payload and enforce immutable ids."""
    if not isinstance(data, dict):
        raise ValueError("Rule must be an object")
    missing = _REQUIRED_RULE_KEYS - data.keys()
    if data.get("source", "state") not in ("none", "unchanged"):
        missing |= {"operator"} - data.keys()
        if data.get("operator") != "unchanged":
            missing |= {"value"} - data.keys()
    if missing:
        raise ValueError(f"Missing rule field: {sorted(missing)[0]}")
    if rule_id is None:
        if "id" in data:
            raise ValueError("Rule id is generated by the backend")
        _reject_unknown_rule_fields(data)
        rule = Rule.create(data)
    else:
        supplied_id = data.get("id", rule_id)
        if supplied_id != rule_id:
            raise ValueError("Rule id is immutable")
        rule = Rule.from_dict({**data, "id": rule_id})
    rule.entity_ids = validate_rule_entity_ids(rule.entity_ids)
    return rule


def validate_rule_update_fields(data: Any) -> None:
    """Validate fields supplied by a partial rule update."""
    if not isinstance(data, dict):
        raise ValueError("Rule must be an object")
    _reject_unknown_rule_fields(data, allow_id=True)


def _reject_unknown_rule_fields(
    data: dict[str, Any], *, allow_id: bool = False
) -> None:
    """Keep future storage fields while rejecting arbitrary client payload keys."""
    allowed = _RULE_CLIENT_KEYS | ({"id"} if allow_id else set())
    unknown = _unknown_keys(data, allowed)
    if unknown:
        raise ValueError(f"Unknown rule field: {sorted(unknown)[0]}")


def _unknown_keys(data: dict[Any, Any], allowed: set[str]) -> set[str]:
    """Return unknown keys after rejecting non-string mapping keys safely."""
    invalid = [key for key in data if not isinstance(key, str)]
    if invalid:
        raise ValueError(f"Field names must be strings: {invalid[0]!r}")
    return set(data) - allowed


def validate_delay(value: Any, field: str = "delay") -> int:
    """Validate a duration expressed as integer seconds."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer number of seconds")
    if value < MIN_DELAY or value > MAX_DELAY:
        raise ValueError(f"{field} must be between {MIN_DELAY} and {MAX_DELAY} seconds")
    return value


def validate_entity_id(entity_id: Any) -> str:
    """Validate a Home Assistant entity id."""
    if not isinstance(entity_id, str) or not valid_entity_id(entity_id):
        raise ValueError(f"Invalid entity id: {entity_id}")
    return entity_id


def validate_entity_list(value: Any) -> list[str]:
    """Validate and deduplicate entity ids."""
    if not isinstance(value, list):
        raise ValueError("excluded_entities must be a list")
    return list(dict.fromkeys(validate_entity_id(item) for item in value))


def validate_coherence_ignored_entity_references(value: Any) -> list[str]:
    """Validate exact entity-like references ignored by coherence scans."""
    if not isinstance(value, list):
        raise ValueError("coherence_ignored_entity_references must be a list")
    result: list[str] = []
    for item in value:
        reference = item.strip().casefold() if isinstance(item, str) else item
        try:
            reference = validate_entity_id(reference)
        except ValueError as err:
            raise ValueError(
                "coherence_ignored_entity_references contains an invalid reference"
            ) from err
        if reference not in result:
            result.append(reference)
    return result


def validate_device_list(value: Any) -> list[str]:
    """Validate and deduplicate registry device ids."""
    if not isinstance(value, list):
        raise ValueError("excluded_devices must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not _DEVICE_ID_RE.fullmatch(item):
            raise ValueError(f"Invalid device id: {item}")
        if item not in result:
            result.append(item)
    return result


def validate_label_list(value: Any) -> list[str]:
    """Validate and deduplicate Home Assistant label registry ids."""
    if not isinstance(value, list):
        raise ValueError("excluded_labels must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > 255:
            raise ValueError(f"Invalid label id: {item}")
        label_id = item.strip()
        if label_id not in result:
            result.append(label_id)
    return result


def validate_rule_entity_ids(value: Any) -> list[str]:
    """Validate rule sources without silently accepting duplicates."""
    if not isinstance(value, list) or not value:
        raise ValueError("entity_ids must be a non-empty list")
    result = [validate_entity_id(item) for item in value]
    if any(
        entity_id in ALERT_MANAGER_ENTITY_IDS
        and entity_id not in CUSTOM_RULE_ALLOWED_ENTITY_IDS
        for entity_id in result
    ):
        raise ValueError("Alert Manager entities cannot be monitored")
    if len(set(result)) != len(result):
        raise ValueError("An entity cannot be repeated in the same rule")
    return result
