"""Home Assistant actions for Alert Manager."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_ALERT_ID,
    DATA_MANAGER,
    DOMAIN,
    SERVICE_ACKNOWLEDGE,
    SERVICE_UNACKNOWLEDGE,
)
from .manager import AlertManager

SERVICE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_ALERT_ID): vol.All(cv.string, vol.Length(min=1))}
)


async def _actor_name(hass: HomeAssistant, call: ServiceCall) -> str | None:
    """Resolve a Home Assistant user name without exposing its internal id."""
    user_id = call.context.user_id
    if user_id is None:
        return None
    user = await hass.auth.async_get_user(user_id)
    if user is None:
        return None
    return user.name or None


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register actions backed by the single loaded manager."""

    async def handle_acknowledge(call: ServiceCall) -> None:
        manager: AlertManager | None = hass.data.get(DATA_MANAGER)
        if manager is None:
            raise ServiceValidationError("Alert Manager is not loaded")
        try:
            await manager.async_acknowledge(
                call.data[ATTR_ALERT_ID], await _actor_name(hass, call)
            )
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

    async def handle_unacknowledge(call: ServiceCall) -> None:
        manager: AlertManager | None = hass.data.get(DATA_MANAGER)
        if manager is None:
            raise ServiceValidationError("Alert Manager is not loaded")
        try:
            await manager.async_unacknowledge(
                call.data[ATTR_ALERT_ID], await _actor_name(hass, call)
            )
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_ACKNOWLEDGE,
        handle_acknowledge,
        schema=SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UNACKNOWLEDGE,
        handle_unacknowledge,
        schema=SERVICE_SCHEMA,
    )
