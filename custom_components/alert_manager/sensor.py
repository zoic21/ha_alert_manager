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
    ("active", "mdi:alert-circle", "active_count", "alerts"),
    ("pending", "mdi:clock-alert-outline", "pending_count", "pending"),
    (
        "acknowledge",
        "mdi:check-circle-outline",
        "acknowledge_count",
        "acknowledge",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Replace the legacy aggregate sensor with the three category sensors."""
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
        key: str,
        icon: str,
        count_key: str,
        alerts_key: str,
    ) -> None:
        """Initialize one stable sensor."""
        self.manager = manager
        self._count_key = count_key
        self._alerts_key = alerts_key
        self._attr_icon = icon
        self._attr_translation_key = f"main_{key}"
        self._attr_unique_id = f"alert_manager_main_{key}"
        self.entity_id = f"sensor.alert_manager_main_{key}"
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
            return {"alerts": []}
        return {"alerts": self._snapshot[self._alerts_key]}
