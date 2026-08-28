"""Alert Manager integration setup."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .coherence import async_load_coherence_result
from .const import (
    DATA_COHERENCE_RESULT,
    DATA_MANAGER,
    DATA_STATIC_REGISTERED,
    DATA_WEBSOCKET_REGISTERED,
    DOMAIN,
    FRONTEND_CACHE_VERSION,
    PANEL_COMPONENT,
    PANEL_ICON,
    PANEL_STATIC_URL,
    PANEL_TITLE,
    PANEL_URL,
    PLATFORMS,
)
from .manager import AlertManager
from .services import async_setup_services
from .websocket import async_register_websocket_commands


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Register actions at domain load so automations can always validate."""
    await async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Alert Manager from its single config entry."""
    manager = AlertManager(hass, entry)
    panel_registered = False
    try:
        await manager.async_setup()
        hass.data[DATA_MANAGER] = manager
        await async_load_coherence_result(hass)

        if not hass.data.get(DATA_STATIC_REGISTERED):
            frontend_dir = Path(__file__).parent / "frontend"
            await hass.http.async_register_static_paths(
                [StaticPathConfig(PANEL_STATIC_URL, str(frontend_dir), True)]
            )
            hass.data[DATA_STATIC_REGISTERED] = True

        if not hass.data.get(DATA_WEBSOCKET_REGISTERED):
            async_register_websocket_commands(hass)
            hass.data[DATA_WEBSOCKET_REGISTERED] = True

        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL,
            webcomponent_name=PANEL_COMPONENT,
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            module_url=(
                f"{PANEL_STATIC_URL}/alert-manager-panel-runtime.js?v={FRONTEND_CACHE_VERSION}"
            ),
            require_admin=True,
            config_panel_domain=DOMAIN,
        )
        panel_registered = True
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        if panel_registered:
            frontend.async_remove_panel(hass, PANEL_URL, warn_if_unknown=False)
        if hass.data.get(DATA_MANAGER) is manager:
            hass.data.pop(DATA_MANAGER)
        with suppress(Exception):
            await manager.async_unload()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Alert Manager cleanly."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    frontend.async_remove_panel(hass, PANEL_URL, warn_if_unknown=False)
    manager: AlertManager | None = hass.data.pop(DATA_MANAGER, None)
    hass.data.pop(DATA_COHERENCE_RESULT, None)
    if manager is not None:
        await manager.async_unload()
    return True
