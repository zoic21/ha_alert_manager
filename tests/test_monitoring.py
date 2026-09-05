"""Main device, monitoring suspension and partitioned entity tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.alert_manager.button import async_setup_entry as setup_button
from custom_components.alert_manager.const import (
    DATA_MANAGER,
    EVENT_ALERT_RESOLVED,
    EVENT_ALERT_STARTED,
    MONITORING_NOTIFICATION_ID,
)
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertStatus
from custom_components.alert_manager.sensor import async_setup_entry as setup_sensors
from custom_components.alert_manager.switch import (
    AlertManagerMonitoringSwitch,
)
from custom_components.alert_manager.switch import async_setup_entry as setup_switch


def run(coroutine):
    return asyncio.run(coroutine)


def event_data(hass, event_type):
    return [data for event, data in hass.bus.fired if event == event_type]


def test_main_device_groups_all_seven_entities(hass, entry):
    """The five sensors, switch and button use one deterministic service device."""
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    hass.data[DATA_MANAGER] = manager
    entities = []
    run(setup_sensors(hass, entry, entities.extend))
    run(setup_switch(hass, entry, entities.extend))
    run(setup_button(hass, entry, entities.extend))

    assert len(entities) == 7
    for entity in entities:
        assert entity._attr_device_info == {
            "identifiers": {("alert_manager", "main")},
            "name": "Alert Manager - Général",
            "entry_type": "service",
        }


def test_monitoring_switch_defaults_on_and_persists_off(hass, entry):
    """A first install is enabled and a disabled state survives reload."""
    first = AlertManager(hass, entry)
    run(first.async_setup())
    switch = AlertManagerMonitoringSwitch(first)
    switch.hass = hass
    assert switch.entity_id == "switch.alert_manager_main_monitoring"
    assert switch.is_on is True

    run(switch.async_turn_off())
    assert switch.is_on is False
    assert hass.stores["alert_manager"]["config"]["monitoring_enabled"] is False
    run(first.async_unload())

    second = AlertManager(hass, entry)
    run(second.async_setup())
    assert second.monitoring_enabled is False
    assert AlertManagerMonitoringSwitch(second).is_on is False


def test_monitoring_switch_rejects_non_admin_users_but_allows_internal_calls(
    hass, entry
):
    """Entity permissions cannot bypass the integration's admin-only contract."""
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    switch = AlertManagerMonitoringSwitch(manager)
    switch.hass = hass
    hass.auth.users["regular-user"] = SimpleNamespace(is_admin=False)
    switch._context = SimpleNamespace(user_id="regular-user")

    with pytest.raises(ServiceValidationError, match="administrator"):
        run(switch.async_turn_off())
    assert switch.is_on is True

    switch._context = SimpleNamespace(user_id=None)
    run(switch.async_turn_off())
    assert switch.is_on is False

    switch._context = SimpleNamespace(user_id="regular-user")
    with pytest.raises(ServiceValidationError, match="administrator"):
        run(switch.async_turn_on())
    assert switch.is_on is False


def test_disabled_monitoring_preserves_records_and_stops_detection(
    hass, entry, set_now
):
    """Suspension keeps records frozen and ignores state changes and due timers."""
    start = datetime(2026, 8, 26, 10, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.pending", "unavailable")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    pending_id = "unavailable:sensor.pending"
    timer = next(item for item in hass.timers if not item["cancelled"])

    run(manager.async_set_monitoring(False))
    assert timer["cancelled"] is True
    assert manager.records[pending_id].paused_at == start
    hass.states.set("sensor.new", "unavailable")
    run(manager.async_evaluate_entity("sensor.new"))
    assert set(manager.records) == {pending_id}

    set_now(start + timedelta(seconds=901))
    timer["action"](start + timedelta(seconds=901))
    assert manager.records[pending_id].status is AlertStatus.PENDING
    assert event_data(hass, EVENT_ALERT_STARTED) == []


def test_monitoring_persistence_failure_restores_state_and_timer(hass, entry):
    """A failed switch write cannot leave monitoring partially suspended."""
    hass.states.set("sensor.pending", "unavailable")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())

    async def fail_save(_config, _records, **_kwargs):
        raise OSError("storage unavailable")

    manager.storage.async_save = fail_save
    with pytest.raises(OSError, match="storage unavailable"):
        run(manager.async_set_monitoring(False))
    assert manager.monitoring_enabled is True
    assert set(manager.records) == {"unavailable:sensor.pending"}
    assert len(manager._timers) == 1


def test_resume_preserves_pending_time_without_duplicate_timers_or_events(
    hass, entry, set_now
):
    """Suspended wall time does not consume a pending alert's delay."""
    start = datetime(2026, 8, 26, 10, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.pending", "unavailable")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    pending_id = "unavailable:sensor.pending"
    original_due_at = manager.records[pending_id].due_at
    original_visible_at = manager.records[pending_id].visible_at
    run(manager.async_set_monitoring(False))
    hass.states.set("sensor.new", "unavailable")
    set_now(start + timedelta(seconds=901))

    assert run(manager.async_set_monitoring(True)) is True
    assert manager.records[pending_id].status is AlertStatus.PENDING
    assert manager.records[pending_id].paused_at is None
    assert manager.records[pending_id].due_at == original_due_at + timedelta(
        seconds=901
    )
    assert manager.records[pending_id].visible_at == original_visible_at + timedelta(
        seconds=901
    )
    assert manager.records["unavailable:sensor.new"].status is AlertStatus.PENDING
    assert event_data(hass, EVENT_ALERT_STARTED) == []
    assert len(manager._timers) == 2

    assert run(manager.async_set_monitoring(True)) is False
    assert event_data(hass, EVENT_ALERT_STARTED) == []
    assert len(manager._timers) == 2


def test_pending_pause_survives_disabled_restart(hass, entry, set_now):
    """The frozen due time remains stable across a disabled integration reload."""
    start = datetime(2026, 8, 26, 10, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.pending", "unavailable")
    first = AlertManager(hass, entry)
    run(first.async_setup())
    alert_id = "unavailable:sensor.pending"
    original_due_at = first.records[alert_id].due_at
    run(first.async_set_monitoring(False))
    run(first.async_unload())

    set_now(start + timedelta(hours=2))
    second = AlertManager(hass, entry)
    run(second.async_setup())
    assert second.records[alert_id].paused_at == start
    assert second.records[alert_id].due_at == original_due_at

    run(second.async_set_monitoring(True))
    assert second.records[alert_id].status is AlertStatus.PENDING
    assert second.records[alert_id].due_at == original_due_at + timedelta(hours=2)


def test_delay_change_keeps_accumulated_pause_out_of_countdown(hass, entry, set_now):
    """Recalculating a delay never starts consuming previously suspended time."""
    start = datetime(2026, 8, 26, 10, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.pending", "unavailable")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    alert_id = "unavailable:sensor.pending"

    set_now(start + timedelta(seconds=100))
    run(manager.async_set_monitoring(False))
    set_now(start + timedelta(seconds=400))
    run(manager.async_update_config({"global_delay": 1200}))
    run(manager.async_set_monitoring(True))

    record = manager.records[alert_id]
    assert record.status is AlertStatus.PENDING
    assert record.paused_seconds == 300
    assert record.due_at == start + timedelta(seconds=1500)


def test_resume_resolves_existing_active_alert_only_once(hass, entry, set_now):
    """An active condition recovered while suspended resolves on reconciliation."""
    start = datetime(2026, 8, 26, 10, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    run(manager.async_update_config({"automatic": {"unavailable": {"delay": 0}}}))
    alert_id = "unavailable:sensor.test"
    assert manager.records[alert_id].status is AlertStatus.ACTIVE
    run(manager.async_set_monitoring(False))
    hass.states.set("sensor.test", "ok")

    run(manager.async_set_monitoring(True))
    assert alert_id not in manager.records
    assert [data["id"] for data in event_data(hass, EVENT_ALERT_RESOLVED)] == [alert_id]
    run(manager.async_set_monitoring(True))
    assert len(event_data(hass, EVENT_ALERT_RESOLVED)) == 1


def test_disabled_startup_notification_is_stable_and_dismissed_on_resume(hass, entry):
    """A disabled reload creates one localized warning which resume removes."""
    hass.stores["alert_manager"] = {
        "config": {"monitoring_enabled": False},
        "alerts": {},
    }
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    assert set(hass.notifications) == {MONITORING_NOTIFICATION_ID}
    notification = hass.notifications[MONITORING_NOTIFICATION_ID]
    assert notification["title"] == "Surveillance Alert Manager désactivée"
    assert "Surveillance Alert Manager" in notification["message"]

    run(manager._async_sync_monitoring_notification())
    assert set(hass.notifications) == {MONITORING_NOTIFICATION_ID}
    run(manager.async_set_monitoring(True))
    assert hass.notifications == {}


def test_partitioned_sensor_attributes_are_exact_and_non_overlapping(
    hass, entry, set_now
):
    """Each sensor contains only the records represented by its state."""
    start = datetime(2026, 8, 26, 10, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.active", "unavailable", {"friendly_name": "Active"})
    hass.states.set("sensor.pending", "unavailable", {"friendly_name": "Pending"})
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    run(
        manager.async_update_config(
            {
                "entity_delays": {"sensor.active": 0, "sensor.pending": 900},
                "pending_display_delay": 0,
            }
        )
    )
    run(manager.async_acknowledge("unavailable:sensor.active", "Loïc"))
    hass.states.set("sensor.other", "unavailable", {"friendly_name": "Other"})
    run(
        manager.async_update_config(
            {
                "entity_delays": {
                    "sensor.active": 0,
                    "sensor.pending": 900,
                    "sensor.other": 0,
                }
            }
        )
    )

    hass.data[DATA_MANAGER] = manager
    sensors = []
    run(setup_sensors(hass, entry, sensors.extend))
    by_id = {sensor.entity_id: sensor for sensor in sensors}
    expected = {
        "sensor.alert_manager_main_active": {"unavailable:sensor.other"},
        "sensor.alert_manager_main_pending": {"unavailable:sensor.pending"},
        "sensor.alert_manager_main_acknowledge": {"unavailable:sensor.active"},
    }
    all_ids = []
    for entity_id, ids in expected.items():
        sensor = by_id[entity_id]
        alerts = sensor.extra_state_attributes["alerts"]
        assert sensor.native_value == len(ids)
        expected_attributes = (
            {"alerts", "runtime", "history_revision"}
            if entity_id == "sensor.alert_manager_main_active"
            else {"alerts"}
        )
        assert set(sensor.extra_state_attributes) == expected_attributes
        assert {alert["id"] for alert in alerts} == ids
        all_ids.extend(alert["id"] for alert in alerts)
    assert len(all_ids) == len(set(all_ids))
    device_sensor = by_id["sensor.alert_manager_device_main_active"]
    assert device_sensor.native_value == 2
    devices = device_sensor.extra_state_attributes["devices"]
    assert {tuple(device["device_ids"]) for device in devices} == {
        ("sensor.active",),
        ("sensor.other",),
    }
    assert all("device_id" not in device for device in devices)
    assert set(device_sensor.extra_state_attributes) == {"devices"}

    run(manager.async_set_monitoring(False))
    assert len(manager.records) == 3
    for sensor in sensors:
        if sensor.entity_id == "sensor.alert_manager_coherence_issue":
            assert sensor.native_value is None
            continue
        assert sensor.native_value == 0
        if sensor is device_sensor:
            assert sensor.extra_state_attributes == {"devices": []}
        elif sensor.entity_id == "sensor.alert_manager_main_active":
            assert sensor.extra_state_attributes == {
                "alerts": [],
                "history_revision": 0,
                "runtime": {
                    "tracked_count": manager.public_snapshot()["tracked_count"],
                    "startup": manager.public_snapshot()["startup"],
                },
            }
        else:
            assert sensor.extra_state_attributes == {"alerts": []}


def test_restored_alerts_are_partitioned_after_restart(hass, entry, set_now):
    """Persisted active and pending runtime data loads into the right sensors."""
    start = datetime(2026, 8, 26, 10, tzinfo=UTC)
    set_now(start)

    async def scenario():
        hass.states.set("sensor.active", "unavailable")
        hass.states.set("sensor.pending", "unavailable")
        first = AlertManager(hass, entry)
        await first.async_setup()
        await first.async_update_config(
            {
                "entity_delays": {"sensor.active": 0},
                "pending_display_delay": 0,
            }
        )
        set_now(start + timedelta(minutes=5))
        await first._async_flush_mature_pending()
        assert "unavailable:sensor.pending" in hass.stores["alert_manager"]["alerts"]
        await first.async_unload()

        second = AlertManager(hass, entry)
        await second.async_setup()
        snapshot = second.public_snapshot()
        assert {alert["id"] for alert in snapshot["alerts"]} == {
            "unavailable:sensor.active"
        }
        assert snapshot["pending"] == []

        reconciliation_timer = next(
            timer
            for timer in hass.timers
            if not timer["cancelled"]
            and "_schedule_startup_reconciliation" in timer["action"].__qualname__
        )
        reconciliation_timer["action"](reconciliation_timer["point"])
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        snapshot = second.public_snapshot()
        assert {alert["id"] for alert in snapshot["alerts"]} == {
            "unavailable:sensor.active"
        }
        assert {alert["id"] for alert in snapshot["pending"]} == {
            "unavailable:sensor.pending"
        }

    run(scenario())
