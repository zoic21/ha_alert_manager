"""The one and only Alert Manager entity."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DATA_MANAGER, PANEL_ICON, SIGNAL_ALERTS_UPDATED
from .manager import AlertManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create exactly one sensor entity."""
    manager: AlertManager = hass.data[DATA_MANAGER]
    async_add_entities([AlertManagerSensor(manager)])


class AlertManagerSensor(SensorEntity):
    """Expose unacknowledged, acknowledged and pending alerts."""

    _attr_has_entity_name = True
    _attr_icon = PANEL_ICON
    _attr_should_poll = False
    _attr_translation_key = "alert_manager"
    _attr_unique_id = "alert_manager"

    def __init__(self, manager: AlertManager) -> None:
        """Initialize the stable sensor entity id."""
        self.manager = manager
        self.entity_id = "sensor.alert_manager"
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
        """Return the unacknowledged active alert count."""
        return self._snapshot["active_count"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return structured current-alert lists, never history or CSV."""
        return self._snapshot
