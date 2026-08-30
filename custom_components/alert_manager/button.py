"""Home Assistant button entities for Alert Manager."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coherence import async_run_coherence_scan
from .const import DOMAIN, MAIN_DEVICE_IDENTIFIER, MAIN_DEVICE_NAME


async def async_setup_entry(
    _hass: HomeAssistant,
    _entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the on-demand coherence scan button."""
    async_add_entities([AlertManagerCoherenceButton()])


class AlertManagerCoherenceButton(ButtonEntity):
    """Launch a configuration coherence scan on demand."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:file-search-outline"
    _attr_translation_key = "check_coherence"
    _attr_unique_id = "alert_manager_check_coherence"
    _attr_device_info = DeviceInfo(
        identifiers={(DOMAIN, MAIN_DEVICE_IDENTIFIER)},
        name=MAIN_DEVICE_NAME,
        entry_type=DeviceEntryType.SERVICE,
    )

    def __init__(self) -> None:
        """Initialize the stable button entity id."""
        self.entity_id = "button.alert_manager_check_coherence"

    async def async_press(self) -> None:
        """Run the same scan exposed by the Alert Manager panel."""
        context = getattr(self, "_context", None)
        user_id = getattr(context, "user_id", None)
        if user_id is not None:
            user = await self.hass.auth.async_get_user(user_id)
            if user is None or not user.is_admin:
                raise ServiceValidationError(
                    "Alert Manager coherence scans require an administrator"
                )
        await async_run_coherence_scan(self.hass)
