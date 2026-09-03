"""Shared authorization checks for non-WebSocket actions."""

from __future__ import annotations

from typing import Any

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError


async def async_require_admin(
    hass: HomeAssistant, context: Context | None
) -> Any | None:
    """Return the calling administrator, while allowing internal HA calls."""
    user_id = getattr(context, "user_id", None)
    if user_id is None:
        return None
    user = await hass.auth.async_get_user(user_id)
    if user is None or not user.is_admin:
        raise ServiceValidationError("Alert Manager actions require an administrator")
    return user
