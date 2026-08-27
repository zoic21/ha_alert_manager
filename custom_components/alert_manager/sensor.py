"""Alert Manager sensors for the main category."""

from __future__ import annotations

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

    async def async_added_to_hass(self) -> None:
        """Subscribe to meaningful manager changes."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_ALERTS_UPDATED, self._async_manager_updated
            )
        )
        self._async_manager_updated()

    @callback
    def _async_manager_updated(self) -> None:
        """Write only when the manager emitted a changed snapshot."""
        self._snapshot = self.manager.public_snapshot()
        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        """Return the number of alerts in this lifecycle partition."""
        if not self.manager.monitoring_enabled:
            return 0
        return self._snapshot[self._count_key]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return only the alerts represented by this sensor."""
        if not self.manager.monitoring_enabled:
            if self._attribute_key == "devices":
                return {"devices": []}
            return {self._attribute_key: []}
        items = self._snapshot[self._items_key]
        return {self._attribute_key: items}
