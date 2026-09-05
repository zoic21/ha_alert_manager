"""Manual reevaluation reuses normal lifecycle and runtime protections."""

import asyncio

import pytest
from test_acknowledgement import active_manager, event_data
from test_websocket import Connection

from custom_components.alert_manager.const import DATA_MANAGER, EVENT_ALERT_RESOLVED
from custom_components.alert_manager.runtime_phase import RuntimePhase
from custom_components.alert_manager.websocket import websocket_alert_reevaluate


@pytest.mark.parametrize("acknowledged", [False, True])
def test_reevaluation_resolves_current_state(hass, entry, set_now, acknowledged):
    manager, alert_id = active_manager(hass, entry, set_now)
    if acknowledged:
        asyncio.run(manager.async_acknowledge(alert_id, "Test"))
    hass.states.set("sensor.test", "ok")

    assert asyncio.run(manager.async_reevaluate_alert(alert_id)) is False
    assert alert_id not in manager.records
    assert len(manager.history) == 1
    assert manager.history[0].acknowledged is acknowledged
    assert len(event_data(hass, EVENT_ALERT_RESOLVED)) == 1
    with pytest.raises(ValueError, match="Unknown or resolved"):
        asyncio.run(manager.async_reevaluate_alert(alert_id))
    assert len(event_data(hass, EVENT_ALERT_RESOLVED)) == 1


def test_reevaluation_preserves_matching_alert_and_other_entities(hass, entry, set_now):
    manager, alert_id = active_manager(hass, entry, set_now)
    asyncio.run(manager.async_acknowledge(alert_id, "Test"))
    record = manager.records[alert_id]
    before = record.as_storage_dict()
    saves = hass.store_save_count
    hass.states.set("sensor.other", "unavailable")

    assert asyncio.run(manager.async_reevaluate_alert(alert_id)) is True
    assert record.as_storage_dict() == before
    assert "unavailable:sensor.other" not in manager.records
    assert hass.store_save_count == saves
    assert not event_data(hass, EVENT_ALERT_RESOLVED)


@pytest.mark.parametrize(
    "phase", [RuntimePhase.STARTUP_GRACE, RuntimePhase.RECONCILING]
)
def test_reevaluation_rejects_startup(hass, entry, set_now, phase):
    manager, alert_id = active_manager(hass, entry, set_now)
    manager._runtime_phase = phase
    with pytest.raises(ValueError, match="requires running monitoring"):
        asyncio.run(manager.async_reevaluate_alert(alert_id))
    assert alert_id in manager.records


def test_reevaluation_rejects_disabled_monitoring(hass, entry, set_now):
    manager, alert_id = active_manager(hass, entry, set_now)
    asyncio.run(manager.async_set_monitoring(False))
    hass.states.set("sensor.test", "ok")
    with pytest.raises(ValueError, match="requires running monitoring"):
        asyncio.run(manager.async_reevaluate_alert(alert_id))
    assert alert_id in manager.records


def test_reevaluation_preserves_pending_deadline_and_discards_recovery(
    hass, entry, set_now
):
    manager, _ = active_manager(hass, entry, set_now)
    hass.states.set("sensor.pending", "unavailable")
    asyncio.run(manager.async_evaluate_entity("sensor.pending"))
    alert_id = "unavailable:sensor.pending"
    due = manager.records[alert_id].due_at
    assert asyncio.run(manager.async_reevaluate_alert(alert_id)) is True
    assert manager.records[alert_id].due_at == due
    hass.states.set("sensor.pending", "ok")
    assert asyncio.run(manager.async_reevaluate_alert(alert_id)) is False
    assert not manager.history
    assert not event_data(hass, EVENT_ALERT_RESOLVED)


def test_reevaluation_websocket_permissions_and_validation(hass, entry, set_now):
    manager, alert_id = active_manager(hass, entry, set_now)
    hass.data[DATA_MANAGER] = manager
    message = {"id": 1, "type": "alert_manager/alerts/reevaluate", "alert_id": alert_id}
    connection = Connection(admin=False)
    asyncio.run(websocket_alert_reevaluate(hass, connection, message))
    assert connection.errors
    assert not connection.results
    connection = Connection(admin=True)
    asyncio.run(websocket_alert_reevaluate(hass, connection, message))
    assert connection.results == [(1, {"present": True})]
    message["alert_id"] = "missing"
    asyncio.run(websocket_alert_reevaluate(hass, connection, message))
    assert connection.errors[-1][1] == "invalid_format"
