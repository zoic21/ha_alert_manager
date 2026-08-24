"""Strict backend validation for Alert Manager configuration."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from homeassistant.core import valid_entity_id

from .const import (
    CATEGORIES,
    DEFAULT_CONFIG,
    MAX_DELAY,
    MAX_THRESHOLD,
    MIN_DELAY,
    MIN_THRESHOLD,
)
from .models import Rule, safe_float

_DOMAIN_RE = re.compile(r"^[a-z0-9_]+$")
_DEVICE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_CONFIG_UPDATE_KEYS = {
    "global_delay",
    "exclusion_label",
    "excluded_entities",
    "excluded_devices",
    "entity_delays",
    "automatic",
    "rules",
}
_AUTOMATIC_KEYS = {
    "unavailable": {"enabled", "delay", "domains"},
    "connectivity": {"enabled", "delay"},
    "unifi": {"enabled", "delay"},
    "battery": {"enabled", "delay", "threshold"},
}
_RULE_CLIENT_KEYS = {
    "name",
    "entity_id",
    "enabled",
    "source",
    "attribute",
    "operator",
    "value",
    "duration",
    "severity",
    "message",
}


def validate_config_update(changes: Any) -> None:
    """Reject unknown fields in a partial WebSocket configuration update."""
    if not isinstance(changes, dict):
        raise ValueError("config must be an object")
    unknown = changes.keys() - _CONFIG_UPDATE_KEYS
    if unknown:
        raise ValueError(f"Unknown configuration field: {sorted(unknown)[0]}")
    automatic = changes.get("automatic")
    if automatic is None:
        return
    if not isinstance(automatic, dict):
        raise ValueError("automatic must be an object")
    unknown_categories = automatic.keys() - _AUTOMATIC_KEYS.keys()
    if unknown_categories:
        raise ValueError(f"Unknown automatic category: {sorted(unknown_categories)[0]}")
    for category, category_changes in automatic.items():
        if not isinstance(category_changes, dict):
            raise ValueError(f"automatic.{category} must be an object")
        unknown_fields = category_changes.keys() - _AUTOMATIC_KEYS[category]
        if unknown_fields:
            field = sorted(unknown_fields)[0]
            raise ValueError(f"Unknown automatic.{category} field: {field}")


def validate_config(config: Any) -> dict[str, Any]:
    """Validate and normalize a complete configuration snapshot."""
    if not isinstance(config, dict):
        raise ValueError("Configuration must be an object")

    result = deepcopy(DEFAULT_CONFIG)
    result["global_delay"] = validate_delay(
        config.get("global_delay", result["global_delay"]), "global_delay"
    )

    exclusion_label = config.get("exclusion_label", result["exclusion_label"])
    if not isinstance(exclusion_label, str) or not exclusion_label.strip():
        raise ValueError("exclusion_label must be a non-empty string")
    if len(exclusion_label) > 255:
        raise ValueError("exclusion_label is too long")
    result["exclusion_label"] = exclusion_label.strip()

    result["excluded_entities"] = validate_entity_list(
        config.get("excluded_entities", [])
    )
    result["excluded_devices"] = validate_device_list(
        config.get("excluded_devices", [])
    )

    entity_delays = config.get("entity_delays", {})
    if not isinstance(entity_delays, dict):
        raise ValueError("entity_delays must be an object")
    normalized_delays: dict[str, int] = {}
    for entity_id, delay in entity_delays.items():
        validate_entity_id(entity_id)
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
        category_config["delay"] = validate_delay(
            incoming.get("delay", category_config["delay"]),
            f"automatic.{category}.delay",
        )

        if category == "unavailable":
            domains = incoming.get("domains", category_config["domains"])
            if not isinstance(domains, list) or not domains:
                raise ValueError(
                    "automatic.unavailable.domains must be a non-empty list"
                )
            normalized_domains: list[str] = []
            for domain in domains:
                if not isinstance(domain, str) or not _DOMAIN_RE.fullmatch(domain):
                    raise ValueError(f"Invalid entity domain: {domain}")
                if domain not in normalized_domains:
                    normalized_domains.append(domain)
            category_config["domains"] = normalized_domains

        if category == "battery":
            threshold = safe_float(
                incoming.get("threshold", category_config["threshold"])
            )
            if threshold is None or not MIN_THRESHOLD <= threshold <= MAX_THRESHOLD:
                raise ValueError(
                    "automatic.battery.threshold must be a finite number "
                    f"between {MIN_THRESHOLD:g} and {MAX_THRESHOLD:g}"
                )
            category_config["threshold"] = threshold

    rules = config.get("rules", [])
    if not isinstance(rules, list):
        raise ValueError("rules must be a list")
    seen: set[str] = set()
    normalized_rules: list[dict[str, Any]] = []
    for raw_rule in rules:
        if not isinstance(raw_rule, dict):
            raise ValueError("Each rule must be an object")
        rule = Rule.from_dict(raw_rule)
        validate_entity_id(rule.entity_id)
        if rule.id in seen:
            raise ValueError(f"Duplicate rule id: {rule.id}")
        seen.add(rule.id)
        normalized_rules.append(rule.as_dict())
    result["rules"] = normalized_rules
    return result


def validate_rule_payload(data: Any, *, rule_id: str | None = None) -> Rule:
    """Validate a rule create/update payload and enforce immutable ids."""
    if not isinstance(data, dict):
        raise ValueError("Rule must be an object")
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
    validate_entity_id(rule.entity_id)
    if len(rule.name) > 255:
        raise ValueError("Rule name is too long")
    if rule.attribute is not None and (
        not isinstance(rule.attribute, str)
        or not rule.attribute.strip()
        or len(rule.attribute) > 255
    ):
        raise ValueError("Invalid attribute name")
    if rule.message is not None and (
        not isinstance(rule.message, str) or len(rule.message) > 1024
    ):
        raise ValueError("Rule message must not exceed 1024 characters")
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
    unknown = data.keys() - allowed
    if unknown:
        raise ValueError(f"Unknown rule field: {sorted(unknown)[0]}")


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
