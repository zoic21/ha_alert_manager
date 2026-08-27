"""Versioned persistent storage for Alert Manager."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import label_registry as lr
from homeassistant.helpers.storage import Store

from .const import (
    DEFAULT_CONFIG,
    DEFAULT_EXCLUSION_LABEL,
    DEFAULT_HISTORY_LIMIT,
    HISTORY_STORAGE_KEY,
    HISTORY_STORAGE_VERSION,
    STORAGE_KEY,
    STORAGE_MINOR_VERSION,
    STORAGE_VERSION,
)
from .models import AlertHistoryEntry, AlertRecord

_LOGGER = logging.getLogger(__name__)


class AlertManagerStore(Store[dict[str, Any]]):
    """Store with an explicit migration entry point for future schemas."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Migrate older stored schemas without requiring live registries."""
        if old_major_version > STORAGE_VERSION:
            raise NotImplementedError
        migrated = deepcopy(old_data)
        config, _changed = _migrate_config_shape(migrated.get("config", {}))
        migrated["config"] = config
        _migrate_acknowledgement_shape(migrated.get("alerts", {}))
        _migrate_pending_visibility_shape(migrated.get("alerts", {}))
        return migrated


class AlertManagerStorage:
    """Own configuration and runtime persistence."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize storage."""
        self._hass = hass
        self._store = AlertManagerStore(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
            atomic_writes=True,
            minor_version=STORAGE_MINOR_VERSION,
        )

    async def async_load(
        self,
    ) -> tuple[dict[str, Any], dict[str, AlertRecord], bool]:
        """Load and validate stored data, falling back safely."""
        raw = await self._store.async_load()
        if not isinstance(raw, dict):
            config, migrated = self._migrate_config({})
            return _merge_dict(deepcopy(DEFAULT_CONFIG), config), {}, migrated

        migrated_config, migrated = self._migrate_config(raw.get("config", {}))
        config = _merge_dict(deepcopy(DEFAULT_CONFIG), migrated_config)
        records: dict[str, AlertRecord] = {}
        raw_alerts = raw.get("alerts", {})
        if not isinstance(raw_alerts, dict):
            _LOGGER.warning("Ignoring invalid persisted alerts collection")
            return config, records, True
        for alert_id, record_data in raw_alerts.items():
            if not isinstance(alert_id, str) or not alert_id:
                _LOGGER.warning("Ignoring persisted alert with invalid id %r", alert_id)
                migrated = True
                continue
            if _migrate_acknowledgement_shape({alert_id: record_data}):
                migrated = True
            if _migrate_pending_visibility_shape({alert_id: record_data}):
                migrated = True
            try:
                record = AlertRecord.from_dict(record_data)
            except (KeyError, TypeError, ValueError):
                _LOGGER.warning("Ignoring invalid persisted alert %s", alert_id)
                migrated = True
                continue
            if record.details.id != alert_id:
                _LOGGER.warning(
                    "Ignoring persisted alert with mismatched id %s", alert_id
                )
                migrated = True
                continue
            if alert_id.startswith("rule:") and alert_id.count(":") == 1:
                alert_id = f"{alert_id}:{record.details.entity_id}"
                record.details.id = alert_id
                migrated = True
            records[alert_id] = record
        return config, records, migrated

    def _migrate_config(self, stored: Any) -> tuple[dict[str, Any], bool]:
        """Apply idempotent migrations that may consult Home Assistant registries."""
        config, changed = _migrate_config_shape(stored)
        if "excluded_labels" not in config:
            legacy_name = config.get("exclusion_label", DEFAULT_EXCLUSION_LABEL)
            labels: list[str] = []
            if isinstance(legacy_name, str):
                label = lr.async_get(self._hass).async_get_label_by_name(legacy_name)
                if label is not None:
                    labels.append(label.label_id)
            config["excluded_labels"] = labels
            changed = True
        if "exclusion_label" in config:
            config.pop("exclusion_label")
            changed = True
        return config, changed

    async def async_save(
        self, config: dict[str, Any], records: dict[str, AlertRecord]
    ) -> None:
        """Atomically save a complete snapshot."""
        await self._store.async_save(
            {
                "config": config,
                "alerts": {
                    alert_id: record.as_storage_dict()
                    for alert_id, record in records.items()
                },
            }
        )


class AlertManagerHistoryStorage:
    """Own history persistence independently from live runtime alerts."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the dedicated atomic history store."""
        self._store = Store(
            hass,
            HISTORY_STORAGE_VERSION,
            HISTORY_STORAGE_KEY,
            atomic_writes=True,
        )

    async def async_load(self) -> tuple[list[AlertHistoryEntry], bool]:
        """Load valid history entries and discard malformed records safely."""
        raw = await self._store.async_load()
        if raw is None:
            return [], False
        if not isinstance(raw, dict) or not isinstance(raw.get("events"), list):
            _LOGGER.warning("Ignoring invalid persisted alert history")
            return [], True
        entries: list[AlertHistoryEntry] = []
        changed = False
        seen: set[str] = set()
        for raw_entry in raw["events"]:
            try:
                entry = AlertHistoryEntry.from_dict(raw_entry)
            except (KeyError, TypeError, ValueError):
                _LOGGER.warning("Ignoring invalid persisted alert history entry")
                changed = True
                continue
            if entry.event_id in seen:
                changed = True
                continue
            seen.add(entry.event_id)
            entries.append(entry)
        sorted_entries = sort_history(entries)
        if sorted_entries != entries:
            changed = True
        return sorted_entries, changed

    async def async_save(self, entries: list[AlertHistoryEntry]) -> None:
        """Atomically save only the bounded historical event collection."""
        await self._store.async_save(
            {"events": [entry.as_dict() for entry in sort_history(entries)]}
        )


def sort_history(entries: list[AlertHistoryEntry]) -> list[AlertHistoryEntry]:
    """Sort newest first with stable deterministic timestamp tie breakers."""
    ordered = sorted(
        entries,
        key=lambda entry: (
            entry.resolved_at,
            entry.detected_at,
            entry.event_id,
        ),
        reverse=True,
    )
    seen: set[str] = set()
    unique: list[AlertHistoryEntry] = []
    for entry in ordered:
        if entry.event_id in seen:
            continue
        seen.add(entry.event_id)
        unique.append(entry)
    return unique


def _merge_dict(defaults: dict[str, Any], stored: Any) -> dict[str, Any]:
    """Merge stored dictionaries over defaults without losing new keys."""
    if not isinstance(stored, dict):
        return defaults
    for key, value in stored.items():
        if (
            key in defaults
            and isinstance(defaults[key], dict)
            and isinstance(value, dict)
        ):
            defaults[key] = _merge_dict(defaults[key], value)
        else:
            defaults[key] = value
    return defaults


def _migrate_config_shape(stored: Any) -> tuple[dict[str, Any], bool]:
    """Migrate V1 rule/domain fields; safe to run repeatedly."""
    if not isinstance(stored, dict):
        return {}, True
    config = deepcopy(stored)
    changed = False

    if "monitoring_enabled" not in config:
        config["monitoring_enabled"] = True
        changed = True

    if "history_limit" not in config:
        config["history_limit"] = DEFAULT_HISTORY_LIMIT
        changed = True

    if "pending_display_delay" not in config:
        config["pending_display_delay"] = config.get(
            "active_display_delay", DEFAULT_CONFIG["pending_display_delay"]
        )
        changed = True
    if "active_display_delay" in config:
        config.pop("active_display_delay")
        changed = True

    rules = config.get("rules")
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            if "entity_ids" not in rule and isinstance(rule.get("entity_id"), str):
                rule["entity_ids"] = [rule["entity_id"]]
                changed = True
            if "entity_id" in rule:
                rule.pop("entity_id")
                changed = True
            version = rule.get("version", 1)
            if (
                isinstance(version, int)
                and not isinstance(version, bool)
                and version < 2
            ):
                rule["version"] = 2
                changed = True

    automatic = config.get("automatic")
    if isinstance(automatic, dict):
        unavailable = automatic.get("unavailable")
        if isinstance(unavailable, dict) and "domains" in unavailable:
            unavailable.pop("domains")
            changed = True
    return config, changed


def _migrate_acknowledgement_shape(stored: Any) -> bool:
    """Add the V1.4 acknowledgement flag to older records idempotently."""
    if not isinstance(stored, dict):
        return False
    changed = False
    for record in stored.values():
        if not isinstance(record, dict):
            continue
        if "acknowledged" not in record:
            record["acknowledged"] = False
            changed = True
    return changed


def _migrate_pending_visibility_shape(stored: Any) -> bool:
    """Discard the dev14 delay mistakenly persisted on active alerts."""
    if not isinstance(stored, dict):
        return False
    changed = False
    for record in stored.values():
        if (
            isinstance(record, dict)
            and record.get("status") == "active"
            and "visible_at" in record
        ):
            record.pop("visible_at")
            changed = True
    return changed
