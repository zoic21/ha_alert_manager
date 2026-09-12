"""Boundary-only conversion of pre-2.4 automatic monitoring settings."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .config_defaults import DEFAULT_CONFIG
from .const import DEFAULT_DELAY


def migrate_pack_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert sparse legacy fields without accessing registries or mutating input.

    Direct exclusions remain for the final validated exception conversion. A
    failed conversion must retain the original persisted/exported source intact.
    """
    from .validation import validate_delay

    config = deepcopy(raw)
    delay = validate_delay(config.pop("global_delay", DEFAULT_DELAY), "global_delay")
    entity_delays = config.pop("entity_delays", {})
    if not isinstance(entity_delays, dict):
        raise ValueError("entity_delays must be an object")
    automatic = config.setdefault("automatic", {})
    if not isinstance(automatic, dict):
        raise ValueError("automatic must be an object")
    # Legacy global delays never applied to packs introduced after this schema.
    for pack_id in (
        "unavailable",
        "connectivity",
        "unifi",
        "battery",
        "execution_errors",
        "flapping",
    ):
        defaults = DEFAULT_CONFIG["automatic"][pack_id]
        pack = automatic.setdefault(pack_id, {})
        if not isinstance(pack, dict):
            raise ValueError(f"automatic.{pack_id} must be an object")
        if "delay" in defaults:
            if pack.get("delay", defaults["delay"]) is None:
                pack["delay"] = delay
            elif "delay" not in pack:
                pack["delay"] = 0 if pack_id == "execution_errors" else delay
            overrides = pack.setdefault("entity_overrides", {})
            for entity_id, value in entity_delays.items():
                settings = overrides.setdefault(entity_id, {})
                if "delay" in settings and settings["delay"] != value:
                    raise ValueError(
                        f"Conflicting legacy delay for {pack_id}:{entity_id}"
                    )
                settings["delay"] = value
        legacy_field, target_kind, new_field = {
            "battery": ("device_thresholds", "device", "threshold"),
            "execution_errors": ("failure_thresholds", "entity", "failure_threshold"),
        }.get(pack_id, (None, None, None))
        if legacy_field in pack:
            legacy = pack.pop(legacy_field)
            if not isinstance(legacy, dict):
                raise ValueError(
                    f"automatic.{pack_id}.{legacy_field} must be an object"
                )
            overrides = pack.setdefault(f"{target_kind}_overrides", {})
            for target_id, value in legacy.items():
                settings = overrides.setdefault(target_id, {})
                if new_field in settings and settings[new_field] != value:
                    raise ValueError(
                        f"Conflicting legacy setting for {pack_id}:{target_id}"
                    )
                settings[new_field] = value
    return config


def migrate_flapping_precedence(raw: dict[str, Any]) -> dict[str, Any]:
    """Freeze only source fields that previously beat legacy entity settings.

    Invoke only for the old configuration schema, never per runtime event.
    Custom-rule source priority is independent and stays in the rule evaluator.
    """
    config = deepcopy(raw)
    pack = config.get("automatic", {}).get("flapping", {})
    for source in pack.get("source_packs", {}).values():
        explicit = {
            key: source[key]
            for key in ("occurrences", "window", "recovery")
            if source.get(key) is not None
        }
        if not explicit:
            continue
        for entity_id in pack.get("entity_overrides", {}):
            source.setdefault("entity_overrides", {}).setdefault(entity_id, {}).update(
                explicit
            )
    return config


def migrate_exclusions(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert legacy exclusions to disabled exceptions without registry writes."""
    from .packs import PACKS
    from .validation import validate_config, validate_device_list, validate_entity_list

    config = deepcopy(raw)
    entities = config.pop("excluded_entities", [])
    devices = config.pop("excluded_devices", [])
    if not isinstance(entities, list) or not isinstance(devices, list):
        raise ValueError("Legacy exclusions must be lists")
    entities = validate_entity_list(entities)
    devices = validate_device_list(devices)
    # Validate before merging, then validate the resulting map sizes and fields.
    # Keep orphan targets: they must stay excluded if they reappear later.
    validated = validate_config(config)
    if not entities and not devices:
        return config
    for pack in PACKS:
        settings = validated["automatic"][pack.id]
        fields = {field.id for field in pack.config_fields}
        for kind, targets in (("entity", entities), ("device", devices)):
            key = f"{kind}_overrides"
            if key not in fields:
                continue
            overrides = settings.setdefault(key, {})
            for target_id in targets:
                overrides.setdefault(target_id, {})["enabled"] = False
    return validate_config(validated)
