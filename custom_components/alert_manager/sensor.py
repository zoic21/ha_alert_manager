"""Alert Manager sensors for the main category."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    DATA_MANAGER,
    DOMAIN,
    MAIN_DEVICE_IDENTIFIER,
    MAIN_DEVICE_NAME,
    SIGNAL_ALERTS_UPDATED,
)
from .manager import AlertManager

_ATTRIBUTE_SIZE_BUDGET = 15_000

_SENSORS = (
    (
        "main_active",
        "alert_manager_main_active",
        "mdi:alert-circle",
        "active_count",
        "alerts",
        "alerts",
    ),
    (
        "main_pending",
        "alert_manager_main_pending",
        "mdi:clock-alert-outline",
        "pending_count",
        "pending",
        "alerts",
    ),
    (
        "main_acknowledge",
        "alert_manager_main_acknowledge",
        "mdi:check-circle-outline",
        "acknowledge_count",
        "acknowledge",
        "alerts",
    ),
    (
        "device_main_active",
        "alert_manager_device_main_active",
        "mdi:devices",
        "device_active_count",
        "active_devices",
        "devices",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Replace the legacy aggregate sensor with lifecycle and device sensors."""
    entity_registry = er.async_get(hass)
    legacy_entity_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, "alert_manager"
    )
    if legacy_entity_id is not None:
        entity_registry.async_remove(legacy_entity_id)

    manager: AlertManager = hass.data[DATA_MANAGER]
    async_add_entities(
        [AlertManagerSensor(manager, *description) for description in _SENSORS]
    )


class AlertManagerSensor(SensorEntity):
    """Expose exactly one lifecycle partition of the main category."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_info = DeviceInfo(
        identifiers={(DOMAIN, MAIN_DEVICE_IDENTIFIER)},
        name=MAIN_DEVICE_NAME,
        entry_type=DeviceEntryType.SERVICE,
    )

    def __init__(
        self,
        manager: AlertManager,
        translation_key: str,
        unique_id: str,
        icon: str,
        count_key: str,
        items_key: str,
        attribute_key: str,
    ) -> None:
        """Initialize one stable sensor."""
        self.manager = manager
        self._count_key = count_key
        self._items_key = items_key
        self._attribute_key = attribute_key
        self._attr_icon = icon
        self._attr_translation_key = translation_key
        self._attr_unique_id = unique_id
        self.entity_id = f"sensor.{unique_id}"
        self._snapshot: dict[str, Any] = manager.public_snapshot()
        self._last_written_partition: tuple[Any, ...] | None = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to meaningful manager changes."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_ALERTS_UPDATED, self._async_manager_updated
            )
        )
        self._async_manager_updated()

    @callback
    def _async_manager_updated(
        self, snapshot: dict[str, Any] | None = None
    ) -> None:
        """Write only when this sensor's own partition really changed."""
        if snapshot is None:
            snapshot = self.manager.public_snapshot()
        partition = (
            self.manager.monitoring_enabled,
            snapshot[self._count_key],
            snapshot[self._items_key],
        )
        if partition == self._last_written_partition:
            return
        self._snapshot = snapshot
        self._last_written_partition = partition
        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        """Return the number of alerts in this lifecycle partition."""
        if not self.manager.monitoring_enabled:
            return 0
        return self._snapshot[self._count_key]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return compact, Recorder-safe data for this lifecycle partition."""
        if not self.manager.monitoring_enabled:
            if self._attribute_key == "devices":
                return {"devices": []}
            return {self._attribute_key: []}
        items = self._snapshot[self._items_key]
        compactor = (
            _compact_device if self._attribute_key == "devices" else _compact_alert
        )
        return _bounded_attributes(self._attribute_key, items, compactor)


def _compact_alert(alert: dict[str, Any]) -> dict[str, Any]:
    """Keep frozen alert data that cannot be recovered from the entity id."""
    compact = {
        "id": alert.get("id"),
        "entity_id": alert.get("entity_id"),
        "value": alert.get("value"),
        "condition": alert.get("condition"),
        "message": alert.get("message"),
        "rule": alert.get("rule_name") or alert.get("type"),
        "detected_at": alert.get("detected_at"),
        "due_at": alert.get("due_at"),
        "active_since": alert.get("active_since"),
        "acknowledged_at": alert.get("acknowledged_at"),
        "acknowledged_by": alert.get("acknowledged_by"),
    }
    return {key: value for key, value in compact.items() if value is not None}


def _compact_device(device: dict[str, Any]) -> dict[str, Any]:
    """Remove the singular device id and registry-derived area information."""
    fields = (
        "device_ids",
        "device_name",
        "started_at",
        "alert_count",
        "unacknowledged_alert_count",
        "acknowledged_alert_count",
        "alert_ids",
        "messages",
        "rules",
    )
    return {key: device[key] for key in fields if device.get(key) is not None}


def _bounded_attributes(
    attribute_key: str,
    items: list[dict[str, Any]],
    compactor: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    """Never exceed Recorder's state-attribute limit, even with many alerts."""
    compacted: list[dict[str, Any]] = []
    omitted_key = f"{attribute_key}_omitted"
    for item in items:
        candidate = [*compacted, compactor(item)]
        omitted = len(items) - len(candidate)
        attributes: dict[str, Any] = {attribute_key: candidate}
        if omitted:
            attributes[omitted_key] = omitted
        encoded = json.dumps(
            attributes,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode()
        if len(encoded) > _ATTRIBUTE_SIZE_BUDGET:
            break
        compacted = candidate
    result: dict[str, Any] = {attribute_key: compacted}
    if omitted := len(items) - len(compacted):
        result[omitted_key] = omitted
    return result
