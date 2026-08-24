"""WebSocket permission and backend validation tests."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from custom_components.alert_manager.const import DATA_MANAGER
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.websocket import websocket_config_update


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
