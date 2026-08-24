"""Config flow for Alert Manager."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN


class AlertManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create the single Alert Manager config entry."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm installation; all options live in the dedicated panel."""
        if user_input is not None:
            return self.async_create_entry(title="Alert Manager", data={})
        return self.async_show_form(step_id="user")
