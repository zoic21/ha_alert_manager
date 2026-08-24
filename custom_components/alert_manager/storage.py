"""Versioned persistent storage for Alert Manager."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DEFAULT_CONFIG,
    STORAGE_KEY,
    STORAGE_MINOR_VERSION,
    STORAGE_VERSION,
)
from .models import AlertRecord

_LOGGER = logging.getLogger(__name__)


class AlertManagerStore(Store[dict[str, Any]]):
    """Store with an explicit migration entry point for future schemas."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Migrate older data; V1 has no predecessor yet."""
        if old_major_version > STORAGE_VERSION:
            raise NotImplementedError
        return old_data


class AlertManagerStorage:
    """Own configuration and runtime persistence."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize storage."""
        self._store = AlertManagerStore(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
            atomic_writes=True,
            minor_version=STORAGE_MINOR_VERSION,
        )

    async def async_load(self) -> tuple[dict[str, Any], dict[str, AlertRecord]]:
        """Load and validate stored data, falling back safely."""
        raw = await self._store.async_load()
        if not isinstance(raw, dict):
            return deepcopy(DEFAULT_CONFIG), {}

        config = _merge_dict(deepcopy(DEFAULT_CONFIG), raw.get("config", {}))
        records: dict[str, AlertRecord] = {}
        for alert_id, record_data in raw.get("alerts", {}).items():
            try:
                record = AlertRecord.from_dict(record_data)
            except (KeyError, TypeError, ValueError):
                _LOGGER.warning("Ignoring invalid persisted alert %s", alert_id)
                continue
            if record.details.id != alert_id:
                _LOGGER.warning(
                    "Ignoring persisted alert with mismatched id %s", alert_id
                )
                continue
            records[alert_id] = record
        return config, records

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
