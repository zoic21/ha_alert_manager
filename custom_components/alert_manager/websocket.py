"""Internal WebSocket API used by the dedicated panel."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.websocket_api import ActiveConnection
from homeassistant.core import HomeAssistant

from .coherence import async_run_coherence_scan
from .const import DATA_COHERENCE_RESULT, DATA_MANAGER
from .manager import AlertManager

ERR_NOT_LOADED = "not_loaded"
ERR_VALIDATION = "invalid_format"
ALERT_IDS_SCHEMA = vol.All(
    [vol.All(str, vol.Length(min=1, max=512))],
    vol.Length(min=1, max=1000),
)


def _manager(
    hass: HomeAssistant, connection: ActiveConnection, message_id: int
) -> AlertManager | None:
    """Resolve the single manager and report reload windows cleanly."""
    manager: AlertManager | None = hass.data.get(DATA_MANAGER)
    if manager is None:
        connection.send_error(message_id, ERR_NOT_LOADED, "Alert Manager is not loaded")
    return manager


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command({vol.Required("type"): "alert_manager/config/get"})
async def websocket_config_get(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return complete configuration to an administrator."""
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


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command({vol.Required("type"): "alert_manager/alerts/list"})
async def websocket_alerts_list(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return active and pending alerts to an administrator."""
    if (manager := _manager(hass, connection, msg["id"])) is not None:
        connection.send_result(msg["id"], manager.public_snapshot())


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "alert_manager/alerts/acknowledgement/update",
        vol.Required("alert_ids"): ALERT_IDS_SCHEMA,
        vol.Required("acknowledged"): bool,
    }
)
async def websocket_alert_acknowledgements_update(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Update several acknowledgement states in one durable transaction."""
    if (manager := _manager(hass, connection, msg["id"])) is None:
        return
    try:
        updated = await manager.async_set_acknowledgements(
            msg["alert_ids"],
            msg["acknowledged"],
            getattr(connection.user, "name", None) or None,
        )
    except ValueError as err:
        connection.send_error(msg["id"], ERR_VALIDATION, str(err))
        return
    connection.send_result(msg["id"], {"updated": updated})


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command({vol.Required("type"): "alert_manager/history/list"})
async def websocket_history_list(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return the newest-first completed history to an administrator."""
    if (manager := _manager(hass, connection, msg["id"])) is not None:
        connection.send_result(msg["id"], manager.history_snapshot())


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command({vol.Required("type"): "alert_manager/coherence/scan"})
async def websocket_coherence_scan(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Scan Home Assistant configuration for missing entity references."""
    if _manager(hass, connection, msg["id"]) is None:
        return
    connection.send_result(msg["id"], await async_run_coherence_scan(hass))


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command({vol.Required("type"): "alert_manager/coherence/get"})
async def websocket_coherence_get(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return the latest persisted coherence report without starting a scan."""
    if _manager(hass, connection, msg["id"]) is not None:
        connection.send_result(msg["id"], hass.data.get(DATA_COHERENCE_RESULT))


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {vol.Required("type"): "alert_manager/coherence/deleted_entities/list"}
)
async def websocket_deleted_entities_list(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return deleted entities retained by Home Assistant's entity registry."""
    if (manager := _manager(hass, connection, msg["id"])) is not None:
        connection.send_result(msg["id"], manager.deleted_entities_snapshot())


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {vol.Required("type"): "alert_manager/history/config/get"}
)
async def websocket_history_config_get(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return history retention configuration to an administrator."""
    if (manager := _manager(hass, connection, msg["id"])) is not None:
        connection.send_result(msg["id"], manager.get_history_config())


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "alert_manager/history/config/update",
        vol.Required("retention_limit"): int,
    }
)
async def websocket_history_config_update(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Validate and apply a bounded history retention limit."""
    if (manager := _manager(hass, connection, msg["id"])) is None:
        return
    try:
        result = await manager.async_set_history_limit(msg["retention_limit"])
    except ValueError as err:
        connection.send_error(msg["id"], ERR_VALIDATION, str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "alert_manager/history/clear",
        vol.Required("confirmed"): True,
    }
)
async def websocket_history_clear(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Clear history only after an explicit client confirmation marker."""
    if (manager := _manager(hass, connection, msg["id"])) is not None:
        connection.send_result(msg["id"], await manager.async_clear_history())


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command({vol.Required("type"): "alert_manager/packs/list"})
async def websocket_packs_list(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return automatic pack metadata and availability to an administrator."""
    if (manager := _manager(hass, connection, msg["id"])) is not None:
        connection.send_result(msg["id"], manager.get_packs())


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command({vol.Required("type"): "alert_manager/rules/list"})
async def websocket_rules_list(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return custom rules to an administrator."""
    if (manager := _manager(hass, connection, msg["id"])) is not None:
        connection.send_result(msg["id"], manager.get_config()["rules"])


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "alert_manager/rules/test",
        vol.Required("rule"): dict,
        vol.Optional("rule_id"): str,
    }
)
async def websocket_rule_test(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Evaluate a draft rule without changing Alert Manager state."""
    if (manager := _manager(hass, connection, msg["id"])) is None:
        return
    try:
        result = await manager.async_test_rule(msg["rule"], rule_id=msg.get("rule_id"))
    except ValueError as err:
        connection.send_error(msg["id"], ERR_VALIDATION, str(err))
        return
    connection.send_result(msg["id"], result)


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
        vol.Required("type"): "alert_manager/rules/yaml/validate",
        vol.Required("yaml"): str,
        vol.Optional("rule_id"): str,
    }
)
async def websocket_rule_yaml_validate(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Validate YAML before switching back to the visual rule editor."""
    if (manager := _manager(hass, connection, msg["id"])) is None:
        return
    try:
        rule = manager.validate_rule_yaml(msg["yaml"], rule_id=msg.get("rule_id"))
    except ValueError as err:
        connection.send_error(msg["id"], ERR_VALIDATION, str(err))
        return
    connection.send_result(msg["id"], rule)


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "alert_manager/rules/yaml/create",
        vol.Required("yaml"): str,
    }
)
async def websocket_rule_yaml_create(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Create a custom rule from its YAML representation."""
    if (manager := _manager(hass, connection, msg["id"])) is None:
        return
    try:
        rule = await manager.async_create_rule_yaml(msg["yaml"])
    except ValueError as err:
        connection.send_error(msg["id"], ERR_VALIDATION, str(err))
        return
    connection.send_result(msg["id"], rule)


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "alert_manager/rules/yaml/update",
        vol.Required("rule_id"): str,
        vol.Required("yaml"): str,
    }
)
async def websocket_rule_yaml_update(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Update a custom rule from YAML while retaining its id."""
    if (manager := _manager(hass, connection, msg["id"])) is None:
        return
    try:
        rule = await manager.async_update_rule_yaml(msg["rule_id"], msg["yaml"])
    except ValueError as err:
        connection.send_error(msg["id"], ERR_VALIDATION, str(err))
        return
    connection.send_result(msg["id"], rule)


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command({vol.Required("type"): "alert_manager/config/export"})
async def websocket_config_export(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return a runtime-free YAML configuration export to an administrator."""
    if (manager := _manager(hass, connection, msg["id"])) is None:
        return
    try:
        raw_yaml = manager.export_config_yaml()
    except ValueError as err:
        connection.send_error(msg["id"], ERR_VALIDATION, str(err))
        return
    connection.send_result(msg["id"], {"yaml": raw_yaml})


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {vol.Required("type"): "alert_manager/config/recovery/get"}
)
async def websocket_config_recovery_get(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return recovery state and automatic backup metadata."""
    if (manager := _manager(hass, connection, msg["id"])) is not None:
        connection.send_result(msg["id"], await manager.async_get_recovery_status())


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "alert_manager/config/backups/download",
        vol.Required("backup_id"): vol.All(str, vol.Length(min=1, max=64)),
    }
)
async def websocket_config_backup_download(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Download one validated automatic configuration backup."""
    if (manager := _manager(hass, connection, msg["id"])) is None:
        return
    try:
        result = await manager.async_get_config_backup_download(msg["backup_id"])
    except ValueError as err:
        connection.send_error(msg["id"], ERR_VALIDATION, str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "alert_manager/config/backups/restore",
        vol.Required("backup_id"): vol.All(str, vol.Length(min=1, max=64)),
        vol.Required("confirmed"): True,
    }
)
async def websocket_config_backup_restore(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Restore one backup only after explicit administrator confirmation."""
    if (manager := _manager(hass, connection, msg["id"])) is None:
        return
    try:
        result = await manager.async_restore_config_backup(msg["backup_id"])
    except ValueError as err:
        connection.send_error(msg["id"], ERR_VALIDATION, str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "alert_manager/config/import/validate",
        vol.Required("yaml"): str,
    }
)
async def websocket_config_import_validate(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Prevalidate an import without modifying integration state."""
    if (manager := _manager(hass, connection, msg["id"])) is None:
        return
    try:
        summary = manager.preview_config_import(msg["yaml"])
    except ValueError as err:
        connection.send_error(msg["id"], ERR_VALIDATION, str(err))
        return
    connection.send_result(msg["id"], summary)


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "alert_manager/config/import",
        vol.Required("yaml"): str,
        vol.Required("confirmed"): True,
    }
)
async def websocket_config_import(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Replace the configuration after client-side explicit confirmation."""
    if (manager := _manager(hass, connection, msg["id"])) is None:
        return
    try:
        result = await manager.async_import_config(msg["yaml"])
    except ValueError as err:
        connection.send_error(msg["id"], ERR_VALIDATION, str(err))
        return
    connection.send_result(msg["id"], result)


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
        websocket_alert_acknowledgements_update,
        websocket_history_list,
        websocket_coherence_get,
        websocket_coherence_scan,
        websocket_deleted_entities_list,
        websocket_history_config_get,
        websocket_history_config_update,
        websocket_history_clear,
        websocket_packs_list,
        websocket_rules_list,
        websocket_rule_test,
        websocket_rule_create,
        websocket_rule_update,
        websocket_rule_yaml_validate,
        websocket_rule_yaml_create,
        websocket_rule_yaml_update,
        websocket_rule_delete,
        websocket_config_export,
        websocket_config_recovery_get,
        websocket_config_backup_download,
        websocket_config_backup_restore,
        websocket_config_import_validate,
        websocket_config_import,
    ):
        websocket_api.async_register_command(hass, command)
