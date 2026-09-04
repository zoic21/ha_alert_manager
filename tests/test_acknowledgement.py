"""Alert acknowledgement model, actions, events and migration tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError

from custom_components.alert_manager.const import (
    DATA_MANAGER,
    EVENT_ALERT_ACKNOWLEDGED,
    EVENT_ALERT_RESOLVED,
    EVENT_ALERT_UNACKNOWLEDGED,
)
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertStatus
from custom_components.alert_manager.sensor import AlertManagerSensor
from custom_components.alert_manager.services import (
    async_setup_services,
)


def run(coroutine):
    return asyncio.run(coroutine)


def active_manager(hass, entry, set_now, entity_id="sensor.test"):
    start = datetime(2026, 8, 25, 14, tzinfo=UTC)
    set_now(start)
    hass.states.set(entity_id, "unavailable", {"friendly_name": "Test"})
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    run(manager.async_update_config({"pending_display_delay": 0}))
    set_now(start + timedelta(seconds=901))
    run(manager.async_evaluate_entity(entity_id))
    return manager, f"unavailable:{entity_id}"


def event_data(hass, event_type):
    return [data for event, data in hass.bus.fired if event == event_type]


def test_acknowledge_and_unacknowledge_are_persistent_and_idempotent(
    hass, entry, set_now
):
    """Acknowledgement removes an alert from the sensor's active count."""
    manager, alert_id = active_manager(hass, entry, set_now)
    active_count = manager.public_snapshot()["active_count"]
    saves = hass.store_save_count

    assert run(manager.async_acknowledge(alert_id, "Loïc")) is True
    snapshot = manager.public_snapshot()
    alert = snapshot["acknowledge"][0]
    assert active_count == 1
    assert snapshot["active_count"] == 0
    assert snapshot["acknowledge_count"] == 1
    assert snapshot["alerts"] == []
    assert (
        AlertManagerSensor(
            manager,
            "main_active",
            "alert_manager_main_active",
            "mdi:alert-circle",
            "active_count",
            "alerts",
            "alerts",
        ).native_value
        == 0
    )
    assert alert["acknowledged"] is True
    assert alert["acknowledged_by"] == "Loïc"
    assert alert["acknowledged_at"].endswith("+00:00")
    assert hass.store_save_count == saves + 1
    acknowledged_event = event_data(hass, EVENT_ALERT_ACKNOWLEDGED)
    assert len(acknowledged_event) == 1
    assert acknowledged_event[0]["id"] == alert_id
    assert acknowledged_event[0]["acknowledged"] is True
    assert acknowledged_event[0]["acknowledged_at"] == alert["acknowledged_at"]
    assert acknowledged_event[0]["acknowledged_by"] == "Loïc"

    assert run(manager.async_acknowledge(alert_id, "Someone else")) is False
    assert hass.store_save_count == saves + 1
    assert len(event_data(hass, EVENT_ALERT_ACKNOWLEDGED)) == 1

    assert run(manager.async_unacknowledge(alert_id, "Loïc")) is True
    snapshot = manager.public_snapshot()
    alert = snapshot["alerts"][0]
    assert snapshot["active_count"] == 1
    assert snapshot["acknowledge_count"] == 0
    assert (
        AlertManagerSensor(
            manager,
            "main_active",
            "alert_manager_main_active",
            "mdi:alert-circle",
            "active_count",
            "alerts",
            "alerts",
        ).native_value
        == 1
    )
    assert alert["acknowledged"] is False
    assert "acknowledged_at" not in alert
    assert "acknowledged_by" not in alert
    unacknowledged = event_data(hass, EVENT_ALERT_UNACKNOWLEDGED)
    assert len(unacknowledged) == 1
    assert unacknowledged[0]["id"] == alert_id
    assert "unacknowledged_at" in unacknowledged[0]
    assert unacknowledged[0]["unacknowledged_by"] == "Loïc"
    assert unacknowledged[0]["previous_acknowledged_by"] == "Loïc"

    saves = hass.store_save_count
    assert run(manager.async_unacknowledge(alert_id, None)) is False
    assert hass.store_save_count == saves
    assert len(event_data(hass, EVENT_ALERT_UNACKNOWLEDGED)) == 1


def test_bulk_acknowledgement_uses_one_storage_write(hass, entry, set_now):
    """A group action persists and publishes the whole selection once."""
    start = datetime(2026, 8, 25, 14, tzinfo=UTC)
    set_now(start)
    for entity_id in ("sensor.one", "sensor.two"):
        hass.states.set(entity_id, "unavailable")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    run(manager.async_update_config({"global_delay": 0}))
    alert_ids = ["unavailable:sensor.one", "unavailable:sensor.two"]
    saves = hass.store_save_count

    assert run(manager.async_set_acknowledgements(alert_ids, True, "Loïc")) == alert_ids
    assert hass.store_save_count == saves + 1
    assert all(manager.records[alert_id].acknowledged for alert_id in alert_ids)
    assert len(event_data(hass, EVENT_ALERT_ACKNOWLEDGED)) == 2

    saves = hass.store_save_count
    assert (
        run(manager.async_set_acknowledgements(alert_ids, False, "Loïc")) == alert_ids
    )
    assert hass.store_save_count == saves + 1
    assert all(not manager.records[alert_id].acknowledged for alert_id in alert_ids)
    assert len(event_data(hass, EVENT_ALERT_UNACKNOWLEDGED)) == 2


def test_acknowledgement_survives_restart_without_replaying_event(hass, entry, set_now):
    """Persisted acknowledgement reloads as state, never as a new action."""
    first, alert_id = active_manager(hass, entry, set_now)
    run(first.async_acknowledge(alert_id, None))
    run(first.async_unload())
    before = len(event_data(hass, EVENT_ALERT_ACKNOWLEDGED))

    second = AlertManager(hass, entry)
    run(second.async_setup())
    snapshot = second.public_snapshot()
    alert = snapshot["acknowledge"][0]
    assert snapshot["active_count"] == 0
    assert snapshot["acknowledge_count"] == 1
    assert alert["acknowledged"] is True
    assert "acknowledged_by" not in alert
    assert len(event_data(hass, EVENT_ALERT_ACKNOWLEDGED)) == before


def test_resolution_discards_acknowledgement_and_recurrence_starts_clean(
    hass, entry, set_now
):
    """Resolved metadata is emitted once and a later occurrence is unacknowledged."""
    manager, alert_id = active_manager(hass, entry, set_now)
    run(manager.async_acknowledge(alert_id, "Loïc"))
    hass.states.set("sensor.test", "ok")
    run(manager.async_evaluate_entity("sensor.test"))
    assert alert_id not in manager.records
    resolved = event_data(hass, EVENT_ALERT_RESOLVED)[0]
    assert resolved["acknowledged"] is True
    assert resolved["acknowledged_by"] == "Loïc"

    hass.states.set("sensor.test", "unavailable")
    run(manager.async_evaluate_entity("sensor.test"))
    record = manager.records[alert_id]
    assert record.status is AlertStatus.PENDING
    assert record.acknowledged is False
    set_now(record.due_at + timedelta(seconds=1))
    run(manager.async_evaluate_entity("sensor.test"))
    assert manager.public_snapshot()["alerts"][0]["acknowledged"] is False


def test_pending_and_unknown_alerts_are_rejected(hass, entry, set_now):
    """Actions target exactly one known active alert."""
    start = datetime(2026, 8, 25, 14, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())

    with pytest.raises(ValueError, match="Pending alert"):
        run(manager.async_acknowledge("unavailable:sensor.test", None))
    with pytest.raises(ValueError, match="Unknown or resolved"):
        run(manager.async_acknowledge("unavailable:sensor.unknown", None))
    with pytest.raises(ValueError, match="Pending alert"):
        run(manager.async_unacknowledge("unavailable:sensor.test", None))


def test_legacy_active_record_migrates_idempotently(hass, entry, set_now):
    """Legacy acknowledgement data migrates and dev14 active delay is removed."""
    start = datetime(2026, 8, 25, 14, tzinfo=UTC)
    set_now(start + timedelta(seconds=901))
    hass.states.set("sensor.test", "unavailable", {"friendly_name": "Legacy"})
    hass.stores["alert_manager"] = {
        "config": {},
        "alerts": {
            "unavailable:sensor.test": {
                "details": {
                    "id": "unavailable:sensor.test",
                    "type": "unavailable",
                    "entity_id": "sensor.test",
                    "name": "Legacy",
                    "value": "unavailable",
                    "condition": "État indisponible",
                },
                "status": "active",
                "detected_at": start.isoformat(),
                "due_at": (start + timedelta(seconds=900)).isoformat(),
                "delay": 900,
                "active_since": (start + timedelta(seconds=900)).isoformat(),
                "visible_at": (start + timedelta(seconds=910)).isoformat(),
            }
        },
    }

    first = AlertManager(hass, entry)
    run(first.async_setup())
    assert first.public_snapshot()["alerts"][0]["acknowledged"] is False
    assert first.records["unavailable:sensor.test"].visible_at is None
    assert (
        hass.stores["alert_manager"]["alerts"]["unavailable:sensor.test"][
            "acknowledged"
        ]
        is False
    )
    assert (
        "visible_at"
        not in hass.stores["alert_manager"]["alerts"]["unavailable:sensor.test"]
    )
    run(first.async_unload())
    saves = hass.store_save_count

    second = AlertManager(hass, entry)
    run(second.async_setup())
    assert second.public_snapshot()["alerts"][0]["acknowledged"] is False
    assert hass.store_save_count == saves


def test_services_use_user_context_and_system_calls_keep_author_absent(
    hass, entry, set_now
):
    """Service handlers resolve display names and validate pending/unknown ids."""
    manager, alert_id = active_manager(hass, entry, set_now, "sensor.user")
    hass.data[DATA_MANAGER] = manager
    hass.auth.users["user-1"] = SimpleNamespace(name="Loïc", is_admin=True)
    run(async_setup_services(hass))

    run(
        hass.services.async_call(
            "alert_manager",
            "acknowledge",
            {"alert_id": alert_id},
            context=Context(user_id="user-1"),
        )
    )
    assert manager.records[alert_id].acknowledged_by == "Loïc"
    run(
        hass.services.async_call(
            "alert_manager",
            "unacknowledge",
            {"alert_id": alert_id},
            context=Context(),
        )
    )
    unacknowledged = event_data(hass, EVENT_ALERT_UNACKNOWLEDGED)[0]
    assert "unacknowledged_by" not in unacknowledged
    run(
        hass.services.async_call(
            "alert_manager",
            "acknowledge",
            {"alert_id": alert_id},
            context=Context(),
        )
    )
    assert manager.records[alert_id].acknowledged_by is None
    assert "acknowledged_by" not in event_data(hass, EVENT_ALERT_ACKNOWLEDGED)[-1]

    with pytest.raises(ServiceValidationError, match="Unknown or resolved"):
        run(
            hass.services.async_call(
                "alert_manager",
                "acknowledge",
                {"alert_id": "unavailable:sensor.unknown"},
            )
        )

    assert ("alert_manager", "acknowledge") in hass.services.handlers
    assert ("alert_manager", "unacknowledge") in hass.services.handlers


def test_services_reject_non_admin_user_context(hass, entry, set_now):
    """Authenticated non-admin users cannot change acknowledgement state."""
    manager, alert_id = active_manager(hass, entry, set_now, "sensor.restricted")
    hass.data[DATA_MANAGER] = manager
    hass.auth.users["user-2"] = SimpleNamespace(name="Reader", is_admin=False)
    run(async_setup_services(hass))

    with pytest.raises(ServiceValidationError, match="administrator"):
        run(
            hass.services.async_call(
                "alert_manager",
                "acknowledge",
                {"alert_id": alert_id},
                context=Context(user_id="user-2"),
            )
        )
    assert manager.records[alert_id].acknowledged is False

    run(
        hass.services.async_call(
            "alert_manager",
            "acknowledge",
            {"alert_id": alert_id},
            context=Context(),
        )
    )
    assert manager.records[alert_id].acknowledged is True

    with pytest.raises(ServiceValidationError, match="administrator"):
        run(
            hass.services.async_call(
                "alert_manager",
                "unacknowledge",
                {"alert_id": alert_id},
                context=Context(user_id="user-2"),
            )
        )
    assert manager.records[alert_id].acknowledged is True


def test_services_remain_discoverable_without_a_loaded_entry(hass):
    """Domain actions stay registered and report the unloaded state clearly."""
    run(async_setup_services(hass))
    with pytest.raises(ServiceValidationError, match="not loaded"):
        run(
            hass.services.async_call(
                "alert_manager",
                "acknowledge",
                {"alert_id": "unavailable:sensor.test"},
            )
        )


def test_failed_persistence_rolls_back_acknowledgement(hass, entry, set_now):
    """A failed atomic Store write cannot leak partial state or an event."""
    manager, alert_id = active_manager(hass, entry, set_now)
    original_save = manager.storage.async_save

    async def fail_save(_config, _records, **_kwargs):
        raise OSError("disk full")

    manager.storage.async_save = fail_save
    with pytest.raises(OSError, match="disk full"):
        run(manager.async_acknowledge(alert_id, "Loïc"))
    assert manager.records[alert_id].acknowledged is False
    snapshot = manager.public_snapshot()
    assert snapshot["alerts"][0]["acknowledged"] is False
    assert snapshot["acknowledge"] == []
    assert not event_data(hass, EVENT_ALERT_ACKNOWLEDGED)
    manager.storage.async_save = original_save
