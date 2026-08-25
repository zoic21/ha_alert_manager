"""Internal WebSocket API used by the dedicated panel."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.websocket_api import ActiveConnection
from homeassistant.core import HomeAssistant, callback

from .const import DATA_MANAGER
from .manager import AlertManager

ERR_NOT_LOADED = "not_loaded"
ERR_VALIDATION = "invalid_format"


def _manager(
    hass: HomeAssistant, connection: ActiveConnection, message_id: int
) -> AlertManager | None:
    """Resolve the single manager and report reload windows cleanly."""
    manager: AlertManager | None = hass.data.get(DATA_MANAGER)
    if manager is None:
        connection.send_error(message_id, ERR_NOT_LOADED, "Alert Manager is not loaded")
    return manager


@websocket_api.websocket_command({vol.Required("type"): "alert_manager/config/get"})
@callback
def websocket_config_get(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return complete configuration."""
    if (manager := _manager(hass, connection, msg["id"])) is not None:
        connection.send_result(msg["id"], manager.get_config())


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "alert_manager/config/update",
        vol.Required("config"): dict,
    }
)
async def websocket_config_update(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Validate and apply a partial configuration update."""
    if (manager := _manager(hass, connection, msg["id"])) is None:
        return
    try:
        result = await manager.async_update_config(msg["config"])
    except ValueError as err:
        connection.send_error(msg["id"], ERR_VALIDATION, str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): "alert_manager/alerts/list"})
@callback
def websocket_alerts_list(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return active and pending alerts."""
    if (manager := _manager(hass, connection, msg["id"])) is not None:
        connection.send_result(msg["id"], manager.public_snapshot())


@websocket_api.websocket_command({vol.Required("type"): "alert_manager/packs/list"})
@callback
def websocket_packs_list(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return backend-owned automatic pack metadata and availability."""
    if (manager := _manager(hass, connection, msg["id"])) is not None:
        connection.send_result(msg["id"], manager.get_packs())


@websocket_api.websocket_command({vol.Required("type"): "alert_manager/rules/list"})
@callback
def websocket_rules_list(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return custom rules."""
    if (manager := _manager(hass, connection, msg["id"])) is not None:
        connection.send_result(msg["id"], manager.get_config()["rules"])


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "alert_manager/rules/create",
        vol.Required("rule"): dict,
    }
)
async def websocket_rule_create(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Create a validated rule."""
    if (manager := _manager(hass, connection, msg["id"])) is None:
        return
    try:
        rule = await manager.async_create_rule(msg["rule"])
    except ValueError as err:
        connection.send_error(msg["id"], ERR_VALIDATION, str(err))
        return
    connection.send_result(msg["id"], rule)


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "alert_manager/rules/update",
        vol.Required("rule_id"): str,
        vol.Required("rule"): dict,
    }
)
async def websocket_rule_update(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Update a validated rule without changing its id."""
    if (manager := _manager(hass, connection, msg["id"])) is None:
        return
    try:
        rule = await manager.async_update_rule(msg["rule_id"], msg["rule"])
    except ValueError as err:
        connection.send_error(msg["id"], ERR_VALIDATION, str(err))
        return
    connection.send_result(msg["id"], rule)


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "alert_manager/rules/delete",
        vol.Required("rule_id"): str,
    }
)
async def websocket_rule_delete(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Delete a rule and resolve its active alert."""
    if (manager := _manager(hass, connection, msg["id"])) is None:
        return
    try:
        await manager.async_delete_rule(msg["rule_id"])
    except ValueError as err:
        connection.send_error(msg["id"], ERR_VALIDATION, str(err))
        return
    connection.send_result(msg["id"], {"deleted": True})


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register each command once for the Home Assistant process lifetime."""
    for command in (
        websocket_config_get,
        websocket_config_update,
        websocket_alerts_list,
        websocket_packs_list,
        websocket_rules_list,
        websocket_rule_create,
        websocket_rule_update,
        websocket_rule_delete,
    ):
        websocket_api.async_register_command(hass, command)
