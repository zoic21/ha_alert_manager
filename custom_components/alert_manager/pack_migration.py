"""Boundary-only conversion of pre-2.4 automatic monitoring settings."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr

from .const import DEFAULT_CONFIG, DEFAULT_DELAY

_MIGRATION_LABEL = "Alert Manager - migrated automatic exclusions"
_MIGRATION_DESCRIPTION = "alert_manager:automatic-exclusions:2.4"


def migrate_pack_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert sparse legacy fields without accessing registries or mutating input.

    Direct exclusions remain solely for the registry boundary to convert. A
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
    for pack_id, defaults in DEFAULT_CONFIG["automatic"].items():
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


async def async_migrate_exclusions(
    hass: HomeAssistant, raw: dict[str, Any]
) -> dict[str, Any]:
    """Assign a dedicated label on the HA event loop, with fail-closed retries.

    Validate all target identities before changing any registry. Never replace
    existing labels, adopt a same-name user label, or drop missing targets.
    """
    from .validation import validate_config, validate_device_list, validate_entity_list

    config = deepcopy(raw)
    entities = config.get("excluded_entities", [])
    devices = config.get("excluded_devices", [])
    if not isinstance(entities, list) or not isinstance(devices, list):
        raise ValueError("Legacy exclusions must be lists")
    entities = validate_entity_list(entities)
    devices = validate_device_list(devices)
    validate_config(
        {
            key: value
            for key, value in config.items()
            if key not in ("excluded_entities", "excluded_devices")
        }
    )
    if entities or devices:
        entity_registry, device_registry = er.async_get(hass), dr.async_get(hass)
        targets = []
        for kind, ids, registry in (
            ("entity", entities, entity_registry),
            ("device", devices, device_registry),
        ):
            for target_id in ids:
                entry = (
                    registry.async_get(target_id)
                    if isinstance(target_id, str)
                    else None
                )
                if entry is None:
                    raise ValueError(
                        f"Cannot migrate excluded {kind} {target_id!r}: "
                        "registry target missing; restore it or explicitly remove "
                        "this exclusion from the source configuration"
                    )
                targets.append((kind, target_id, entry))
        labels = lr.async_get(hass)
        label = labels.async_get_label_by_name(_MIGRATION_LABEL)
        if label is not None and label.description != _MIGRATION_DESCRIPTION:
            raise ValueError(
                f"Migration label name is already in use: {_MIGRATION_LABEL}"
            )
        if label is None:
            label = labels.async_create(
                _MIGRATION_LABEL,
                description=_MIGRATION_DESCRIPTION,
                icon="mdi:bell-off",
            )
        for kind, target_id, entry in targets:
            if label.label_id in entry.labels:
                continue
            try:
                if kind == "entity":
                    entity_registry.async_update_entity(
                        target_id, labels=set(entry.labels) | {label.label_id}
                    )
                else:
                    device_registry.async_update_device(
                        target_id, labels=set(entry.labels) | {label.label_id}
                    )
            except Exception as err:
                raise ValueError(
                    f"Cannot migrate excluded {kind} {target_id!r}: "
                    f"label assignment failed: {err}"
                ) from err
        # HA registries defer writes. Flush their native stores before allowing
        # the source exclusions to disappear from our own durable snapshot.
        # Keep this narrow compatibility boundary fail-closed on HA API changes.
        for registry in (labels, entity_registry, device_registry):
            await registry._store.async_save(registry._data_to_save())
        config["excluded_labels"] = list(
            dict.fromkeys([*config.get("excluded_labels", []), label.label_id])
        )
    config.pop("excluded_entities", None)
    config.pop("excluded_devices", None)
    return config
