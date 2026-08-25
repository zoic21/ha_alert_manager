"""WebSocket permission and backend validation tests."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from custom_components.alert_manager.const import DATA_MANAGER
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.websocket import (
    websocket_config_update,
    websocket_packs_list,
    websocket_rule_create,
    websocket_rule_delete,
    websocket_rule_update,
)


class Connection:
    def __init__(self, *, admin):
        self.user = SimpleNamespace(is_admin=admin)
        self.errors = []
        self.results = []

    def send_error(self, message_id, code, message):
        self.errors.append((message_id, code, message))

    def send_result(self, message_id, result=None):
        self.results.append((message_id, result))


def test_websocket_non_admin_is_refused(hass, entry):
    """Every mutating command is protected by the Home Assistant admin decorator."""
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    hass.data[DATA_MANAGER] = manager
    connection = Connection(admin=False)
    asyncio.run(
        websocket_config_update(
            hass,
            connection,
            {"id": 1, "type": "alert_manager/config/update", "config": {}},
        )
    )
    assert connection.errors == [(1, "unauthorized", "Unauthorized")]
    assert connection.results == []


def test_websocket_invalid_frontend_data_gets_readable_error(hass, entry):
    """Invalid durations are rejected server-side even for administrators."""
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    hass.data[DATA_MANAGER] = manager
    connection = Connection(admin=True)
    asyncio.run(
        websocket_config_update(
            hass,
            connection,
            {
                "id": 2,
                "type": "alert_manager/config/update",
                "config": {"global_delay": -1},
            },
        )
    )
    assert connection.results == []
    assert connection.errors[0][1] == "invalid_format"
    assert "between" in connection.errors[0][2]


def test_websocket_exposes_backend_pack_metadata(hass, entry):
    """The panel gets pack labels and availability from the backend registry."""
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    hass.data[DATA_MANAGER] = manager
    connection = Connection(admin=True)

    websocket_packs_list(
        hass,
        connection,
        {"id": 8, "type": "alert_manager/packs/list"},
    )

    packs = connection.results[-1][1]
    assert [pack["id"] for pack in packs] == [
        "unavailable",
        "connectivity",
        "unifi",
        "battery",
    ]
    assert all(pack["name"] and pack["description"] for pack in packs)
    assert next(pack for pack in packs if pack["id"] == "unifi") == {
        "id": "unifi",
        "name": "Équipements UniFi",
        "description": "Surveille les équipements suivis par un routeur UniFi.",
        "prerequisites": ["unifi"],
        "available": False,
    }


def test_websocket_rule_actions_create_update_and_delete(hass, entry):
    """The complete mutating rule API works with panel-shaped payloads."""
    hass.states.set("todo.liste_d_achats", "0")
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    hass.data[DATA_MANAGER] = manager
    connection = Connection(admin=True)
    payload = {
        "name": "Liste vide",
        "entity_ids": ["todo.liste_d_achats"],
        "enabled": True,
        "source": "state",
        "attribute": None,
        "operator": "equals",
        "value": "0",
        "duration": 900,
        "message": None,
    }

    asyncio.run(
        websocket_rule_create(
            hass,
            connection,
            {"id": 3, "type": "alert_manager/rules/create", "rule": payload},
        )
    )
    assert connection.errors == []
    created = connection.results[-1][1]
    assert created["name"] == "Liste vide"
    assert manager.get_config()["rules"] == [created]

    asyncio.run(
        websocket_rule_update(
            hass,
            connection,
            {
                "id": 4,
                "type": "alert_manager/rules/update",
                "rule_id": created["id"],
                "rule": {"enabled": False, "name": "Liste désactivée"},
            },
        )
    )
    updated = connection.results[-1][1]
    assert updated["enabled"] is False
    assert updated["name"] == "Liste désactivée"

    asyncio.run(
        websocket_rule_delete(
            hass,
            connection,
            {
                "id": 5,
                "type": "alert_manager/rules/delete",
                "rule_id": created["id"],
            },
        )
    )
    assert connection.results[-1] == (5, {"deleted": True})
    assert manager.get_config()["rules"] == []
