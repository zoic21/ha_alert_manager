"""Persistent monitoring switch for the main Alert Manager category."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    DATA_MANAGER,
    DOMAIN,
    MAIN_DEVICE_IDENTIFIER,
    MAIN_DEVICE_NAME,
    SIGNAL_MONITORING_UPDATED,
)
from .manager import AlertManager
from .permissions import async_require_admin


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the main category monitoring switch."""
    manager: AlertManager = hass.data[DATA_MANAGER]
    async_add_entities([AlertManagerMonitoringSwitch(manager)])


class AlertManagerMonitoringSwitch(SwitchEntity):
    """Persistently suspend and resume anomaly evaluation."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:shield-search"
    _attr_translation_key = "main_monitoring"
    _attr_unique_id = "alert_manager_main_monitoring"
    _attr_device_info = DeviceInfo(
        identifiers={(DOMAIN, MAIN_DEVICE_IDENTIFIER)},
        name=MAIN_DEVICE_NAME,
        entry_type=DeviceEntryType.SERVICE,
    )

    def __init__(self, manager: AlertManager) -> None:
        """Initialize the stable main category switch."""
        self.manager = manager
        self.entity_id = "switch.alert_manager_main_monitoring"

    async def async_added_to_hass(self) -> None:
        """Subscribe to monitoring changes from the manager."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_MONITORING_UPDATED, self._async_manager_updated
            )
        )

    @property
    def is_on(self) -> bool:
        """Return the persisted monitoring state."""
        return self.manager.monitoring_enabled

    async def async_turn_on(self, **_kwargs: object) -> None:
        """Resume monitoring and reconcile the current Home Assistant state."""
        await async_require_admin(self.hass, getattr(self, "_context", None))
        await self.manager.async_set_monitoring(True)

    async def async_turn_off(self, **_kwargs: object) -> None:
        """Suspend all new detection without deleting existing alerts."""
        await async_require_admin(self.hass, getattr(self, "_context", None))
        await self.manager.async_set_monitoring(False)

    @callback
    def _async_manager_updated(self) -> None:
        """Publish the changed switch state."""
        self.async_write_ha_state()
