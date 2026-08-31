"""Versioned persistent storage for Alert Manager."""

from __future__ import annotations

import json
import logging
import math
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from homeassistant.core import HomeAssistant
from homeassistant.helpers import label_registry as lr
from homeassistant.helpers.storage import Store

from .const import (
    CONFIG_BACKUP_LIMIT,
    CONFIG_BACKUP_STORAGE_KEY,
    CONFIG_BACKUP_STORAGE_VERSION,
    DEFAULT_COHERENCE_SCAN_ESPHOME,
    DEFAULT_COHERENCE_SCHEDULE,
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
from .yaml_io import parse_config_yaml

_LOGGER = logging.getLogger(__name__)


class ConfigStorageError(ValueError):
    """Report an unusable main store without discarding its configuration."""

    def __init__(
        self,
        message: str,
        *,
        faulty_config: Any = None,
        failed_content: str | None = None,
    ) -> None:
        """Keep a defensive copy when a diagnostic export is possible."""
        super().__init__(message)
        self.faulty_config = deepcopy(faulty_config)
        self.failed_content = failed_content


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
        stored_config = migrated.get("config")
        if not isinstance(stored_config, dict):
            raise ConfigStorageError(
                "Stored configuration must be an object",
                faulty_config=stored_config,
            )
        config, _changed = _migrate_config_shape(stored_config)
        migrated["config"] = config
        _migrate_acknowledgement_shape(migrated.get("alerts", {}))
        _migrate_pending_visibility_shape(migrated.get("alerts", {}))
        _migrate_alert_value_sources(migrated.get("alerts", {}))
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
        self.variation_baselines: dict[str, float] = {}

    async def async_load(
        self,
    ) -> tuple[dict[str, Any], dict[str, AlertRecord], bool]:
        """Load stored data and reject unusable configuration without writing."""
        raw_snapshot = await self._async_read_store_snapshot()
        try:
            raw = await self._store.async_load()
        except ConfigStorageError:
            raise
        except Exception as err:
            raise ConfigStorageError(
                f"Unable to read or migrate stored configuration: {err}",
                failed_content=raw_snapshot,
            ) from err
        if raw is None:
            if raw_snapshot is not None:
                faulty_config: Any = None
                try:
                    envelope = json.loads(raw_snapshot)
                    data = envelope.get("data") if isinstance(envelope, dict) else None
                    if isinstance(data, dict):
                        faulty_config = data.get("config")
                except (TypeError, ValueError):
                    pass
                raise ConfigStorageError(
                    "Existing configuration storage could not be loaded",
                    faulty_config=faulty_config,
                    failed_content=(
                        None if faulty_config is not None else raw_snapshot
                    ),
                )
            self.variation_baselines = {}
            config, migrated = self._migrate_config({})
            return _merge_dict(deepcopy(DEFAULT_CONFIG), config), {}, migrated

        if not isinstance(raw, dict):
            raise ConfigStorageError("Stored Alert Manager data must be an object")
        stored_config = raw.get("config")
        if not isinstance(stored_config, dict):
            raise ConfigStorageError(
                "Stored configuration must be an object",
                faulty_config=stored_config,
            )

        migrated_config, migrated = self._migrate_config(stored_config)
        self.variation_baselines, baselines_migrated = _load_variation_baselines(
            raw.get("variation_baselines", {})
        )
        migrated |= baselines_migrated
        config = _merge_dict(deepcopy(DEFAULT_CONFIG), migrated_config)
        records: dict[str, AlertRecord] = {}
        raw_alerts = raw.get("alerts", {})
        if not isinstance(raw_alerts, dict):
            _LOGGER.warning("Ignoring invalid persisted alerts collection")
            return config, records, True
        if _migrate_alert_value_sources(raw_alerts):
            migrated = True
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

    async def _async_read_store_snapshot(self) -> str | None:
        """Capture an existing store before Home Assistant may rename corruption."""
        try:
            path = Path(self._store.path)
            return await self._hass.async_add_executor_job(path.read_text, "utf-8")
        except (AttributeError, OSError, UnicodeError):
            return None

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
                "variation_baselines": dict(self.variation_baselines),
            }
        )


class AlertManagerConfigBackupStorage:
    """Store the three newest validated configuration exports."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize an independent atomic backup store."""
        self._store = Store[dict[str, Any]](
            hass,
            CONFIG_BACKUP_STORAGE_VERSION,
            CONFIG_BACKUP_STORAGE_KEY,
            atomic_writes=True,
        )

    async def _async_load_valid(self) -> list[dict[str, Any]]:
        """Return valid exports without rewriting a damaged backup store."""
        raw = await self._store.async_load()
        if raw is None:
            return []
        if not isinstance(raw, dict) or not isinstance(raw.get("backups"), list):
            _LOGGER.error("Ignoring invalid Alert Manager configuration backup store")
            return []
        valid: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in raw["backups"]:
            if not isinstance(item, dict):
                continue
            backup_id = item.get("id")
            created_at = item.get("created_at")
            raw_yaml = item.get("yaml")
            if (
                not isinstance(backup_id, str)
                or not backup_id
                or backup_id in seen
                or not isinstance(created_at, str)
                or not isinstance(raw_yaml, str)
            ):
                continue
            try:
                parsed_at = datetime.fromisoformat(created_at)
                if parsed_at.tzinfo is None:
                    raise ValueError
                config = parse_config_yaml(raw_yaml)
            except (TypeError, ValueError):
                _LOGGER.warning("Ignoring invalid configuration backup %r", backup_id)
                continue
            seen.add(backup_id)
            valid.append(
                {
                    "id": backup_id,
                    "created_at": parsed_at.astimezone(UTC).isoformat(),
                    "yaml": raw_yaml,
                    "rules": len(config["rules"]),
                }
            )
        return sorted(valid, key=lambda item: item["created_at"], reverse=True)[
            :CONFIG_BACKUP_LIMIT
        ]

    async def async_list(self) -> list[dict[str, Any]]:
        """Return safe metadata for the administrator frontend."""
        return [
            {
                "id": item["id"],
                "created_at": item["created_at"],
                "rules": item["rules"],
            }
            for item in await self._async_load_valid()
        ]

    async def async_get(self, backup_id: str) -> dict[str, Any] | None:
        """Return one validated export by opaque id."""
        return next(
            (
                item
                for item in await self._async_load_valid()
                if item["id"] == backup_id
            ),
            None,
        )

    async def async_create(
        self, raw_yaml: str, *, created_at: datetime
    ) -> dict[str, Any]:
        """Validate through the import parser before rotating atomically."""
        config = parse_config_yaml(raw_yaml)
        timestamp = created_at.astimezone(UTC).isoformat()
        backup = {
            "id": uuid4().hex,
            "created_at": timestamp,
            "yaml": raw_yaml,
            "rules": len(config["rules"]),
        }
        current = await self._async_load_valid()
        await self._store.async_save(
            {"backups": [backup, *current][:CONFIG_BACKUP_LIMIT]}
        )
        return {
            "id": backup["id"],
            "created_at": backup["created_at"],
            "rules": backup["rules"],
        }


def _load_variation_baselines(raw: Any) -> tuple[dict[str, float], bool]:
    """Load finite numeric variation references and discard malformed entries."""
    if not isinstance(raw, dict):
        return {}, True
    baselines: dict[str, float] = {}
    changed = False
    for key, value in raw.items():
        if (
            not isinstance(key, str)
            or not key
            or isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
        ):
            changed = True
            continue
        baselines[key] = float(value)
    return baselines, changed


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
            if isinstance(raw_entry, dict) and raw_entry.get("source") == "none":
                raw_entry = {**raw_entry, "source": "jinja"}
                changed = True
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

    if "coherence_schedule" not in config:
        config["coherence_schedule"] = DEFAULT_COHERENCE_SCHEDULE
        changed = True

    if "coherence_scan_esphome" not in config:
        config["coherence_scan_esphome"] = DEFAULT_COHERENCE_SCAN_ESPHOME
        changed = True

    if "coherence_ignored_entity_references" not in config:
        config["coherence_ignored_entity_references"] = []
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
            if rule.get("source") == "none":
                rule["source"] = "jinja"
                changed = True
            elif rule.get("source") == "variation":
                rule["source"] = "state_variation"
                changed = True
            if "update_message_when_active" not in rule:
                rule["update_message_when_active"] = False
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


def _migrate_alert_value_sources(stored: Any) -> bool:
    """Rename legacy sources in persisted active records."""
    if not isinstance(stored, dict):
        return False
    changed = False
    for record in stored.values():
        if not isinstance(record, dict):
            continue
        details = record.get("details")
        if isinstance(details, dict):
            if details.get("source") == "none":
                details["source"] = "jinja"
                changed = True
            elif details.get("source") == "variation":
                details["source"] = "state_variation"
                changed = True
    return changed
