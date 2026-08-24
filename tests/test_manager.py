"""Alert Manager lifecycle, detection, persistence and exclusion tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from custom_components.alert_manager.const import (
    DATA_MANAGER,
    EVENT_ALERT_RESOLVED,
    EVENT_ALERT_STARTED,
)
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertStatus
from custom_components.alert_manager.sensor import (
    AlertManagerSensor,
)
from custom_components.alert_manager.sensor import (
    async_setup_entry as async_setup_sensor,
)


def run(coroutine):
    return asyncio.run(coroutine)


def make_manager(hass, entry):
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    return manager


def test_creation_of_single_sensor(hass, entry):
    """The sensor platform creates exactly sensor.alert_manager."""
    manager = make_manager(hass, entry)
    hass.data[DATA_MANAGER] = manager
    entities = []
    run(async_setup_sensor(hass, entry, entities.extend))
    assert len(entities) == 1
    assert isinstance(entities[0], AlertManagerSensor)
    assert entities[0].entity_id == "sensor.alert_manager"
    assert entities[0].native_value == 0
    assert entities[0].extra_state_attributes["alerts"] == []


def test_normal_to_pending_and_no_duplicate(hass, entry):
    """A first-install anomaly starts pending and repeated evaluation is idempotent."""
    hass.states.set("sensor.unas", "unavailable", {"friendly_name": "UNAS"})
    manager = make_manager(hass, entry)
    assert set(manager.records) == {"unavailable:sensor.unas"}
    assert manager.records["unavailable:sensor.unas"].status is AlertStatus.PENDING
    run(manager.async_evaluate_entity("sensor.unas"))
    assert len(manager.records) == 1


def test_pending_cancellation(hass, entry):
    """A recovered condition before due_at returns to normal without an event."""
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)
    hass.states.set("sensor.test", "20")
    run(manager.async_evaluate_entity("sensor.test"))
    assert manager.records == {}
    assert not [item for item in hass.bus.fired if item[0] == EVENT_ALERT_RESOLVED]


def test_pending_to_active(hass, entry, set_now):
    """A still-true condition becomes active exactly when due."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)
    set_now(start + timedelta(seconds=900))
    run(manager.async_evaluate_entity("sensor.test"))
    record = manager.records["unavailable:sensor.test"]
    assert record.status is AlertStatus.ACTIVE
    assert record.active_since == record.due_at


def test_active_resolution_and_events(hass, entry, set_now):
    """Started/resolved events contain the structured documented timestamps."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable", {"friendly_name": "Test"})
    manager = make_manager(hass, entry)
    set_now(start + timedelta(seconds=901))
    run(manager.async_evaluate_entity("sensor.test"))
    hass.states.set("sensor.test", "ok")
    set_now(start + timedelta(seconds=1000))
    run(manager.async_evaluate_entity("sensor.test"))
    assert manager.records == {}
    started = [data for event, data in hass.bus.fired if event == EVENT_ALERT_STARTED]
    resolved = [data for event, data in hass.bus.fired if event == EVENT_ALERT_RESOLVED]
    assert len(started) == len(resolved) == 1
    assert started[0]["id"] == "unavailable:sensor.test"
    assert "active_since" in started[0]
    assert "resolved_at" in resolved[0]


def test_persistence_and_resume_without_duplicate_started(hass, entry, set_now):
    """Pending/active state survives reload and an active alert is not re-announced."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable")
    first = make_manager(hass, entry)
    due = first.records["unavailable:sensor.test"].due_at
    run(first.async_unload())

    set_now(start + timedelta(seconds=300))
    second = make_manager(hass, entry)
    assert second.records["unavailable:sensor.test"].due_at == due
    set_now(start + timedelta(seconds=901))
    run(second.async_evaluate_entity("sensor.test"))
    started_before = len(
        [item for item in hass.bus.fired if item[0] == EVENT_ALERT_STARTED]
    )
    run(second.async_unload())
    third = make_manager(hass, entry)
    assert third.records["unavailable:sensor.test"].status is AlertStatus.ACTIVE
    started_after = len(
        [item for item in hass.bus.fired if item[0] == EVENT_ALERT_STARTED]
    )
    assert started_after == started_before


def test_unavailable_detection_does_not_duplicate_connectivity(hass, entry):
    """Unavailable wins over connectivity for the same entity."""
    hass.states.set(
        "binary_sensor.gateway",
        "unavailable",
        {"device_class": "connectivity"},
    )
    manager = make_manager(hass, entry)
    assert set(manager.records) == {"unavailable:binary_sensor.gateway"}


def test_disabled_entity_and_device_are_ignored(
    hass, entry, registry_entry, device_entry
):
    """Both registry disablers suppress automatic and custom alerts."""
    registry_entry(hass, "sensor.disabled", disabled_by="user")
    hass.states.set("sensor.disabled", "unavailable")
    device = device_entry(hass, disabled_by="user")
    registry_entry(hass, "sensor.device_disabled", device_id=device.id)
    hass.states.set("sensor.device_disabled", "unavailable")
    manager = make_manager(hass, entry)
    assert manager.records == {}


def test_entity_label_exclusion(hass, entry, registry_entry):
    """The configured label on an entity excludes it."""
    hass.label_registry.labels["pas_d_alerte"] = SimpleNamespace(label_id="skip")
    registry_entry(hass, "sensor.test", labels={"skip"})
    hass.states.set("sensor.test", "unavailable")
    assert make_manager(hass, entry).records == {}


def test_device_label_exclusion(hass, entry, registry_entry, device_entry):
    """The configured label on an associated device excludes its entities."""
    hass.label_registry.labels["pas_d_alerte"] = SimpleNamespace(label_id="skip")
    device = device_entry(hass, labels={"skip"})
    registry_entry(hass, "sensor.test", device_id=device.id)
    hass.states.set("sensor.test", "unavailable")
    assert make_manager(hass, entry).records == {}


def test_connectivity_off(hass, entry):
    """A connectivity binary sensor at off becomes pending."""
    hass.states.set("binary_sensor.gateway", "off", {"device_class": "connectivity"})
    manager = make_manager(hass, entry)
    assert "connectivity:binary_sensor.gateway" in manager.records


def test_unifi_tracker_away(hass, entry, registry_entry):
    """Only router-backed UniFi trackers away from home trigger UniFi detection."""
    registry_entry(hass, "device_tracker.ap", platform="unifi")
    hass.states.set("device_tracker.ap", "not_home", {"source_type": "router"})
    manager = make_manager(hass, entry)
    assert "unifi:device_tracker.ap" in manager.records


def test_battery_global_threshold(hass, entry):
    """Battery device class uses the global category threshold."""
    hass.states.set("sensor.battery", "15", {"device_class": "battery"})
    manager = make_manager(hass, entry)
    assert manager.records["battery:sensor.battery"].details.value == 15.0


def test_battery_entity_low_level_override(hass, entry):
    """low_battery_level replaces the category threshold for one sensor."""
    hass.states.set(
        "sensor.battery",
        "20",
        {"device_class": "battery", "low_battery_level": 25},
    )
    manager = make_manager(hass, entry)
    assert "25 %" in manager.records["battery:sensor.battery"].details.condition


@pytest.mark.parametrize(
    ("operator", "state", "expected"),
    [
        ("equals", "off", "off"),
        ("not_equals", "ERROR", "OL CHRG"),
        ("above", "11.2", 9),
        ("below", "0.8", 1),
    ],
)
def test_custom_rule_operator(hass, entry, operator, state, expected):
    """Every V1 custom-rule operator creates the stable rule alert id."""
    hass.states.set("sensor.test", state)
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "Rule",
                "entity_id": "sensor.test",
                "operator": operator,
                "value": expected,
                "duration": 300,
                "severity": "critical",
                "enabled": True,
                "source": "state",
            }
        )
    )
    assert f"rule:{rule['id']}" in manager.records


def test_delay_priority(hass, entry):
    """Entity config outranks alert_delay, category and global delays."""
    hass.states.set("sensor.test", "unavailable", {"alert_delay": 40})
    manager = make_manager(hass, entry)
    run(
        manager.async_update_config(
            {
                "global_delay": 100,
                "automatic": {"unavailable": {"delay": 80}},
                "entity_delays": {"sensor.test": 20},
            }
        )
    )
    assert manager.records["unavailable:sensor.test"].delay == 20


def test_missing_rule_attribute_does_not_trigger_not_equals(hass, entry):
    """A missing attribute is not treated as an arbitrary comparison value."""
    hass.states.set("sensor.test", "ok", {})
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "Missing attribute",
                "entity_id": "sensor.test",
                "source": "attribute",
                "attribute": "missing",
                "operator": "not_equals",
                "value": "ok",
                "duration": 60,
            }
        )
    )
    assert f"rule:{rule['id']}" not in manager.records


def test_unchanged_global_evaluation_does_not_publish(hass, entry):
    """Registry reevaluation does not cause a redundant sensor/Recorder write."""
    manager = make_manager(hass, entry)
    notifications = []
    hass.dispatchers["alert_manager_alerts_updated"].append(
        lambda: notifications.append(True)
    )
    run(manager.async_evaluate_all())
    assert notifications == []


def test_unload_reload_cleans_listeners_and_timers(hass, entry):
    """Unload cancels timers/listeners and a new manager reloads one clean set."""
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)
    assert any(hass.bus.listeners.values())
    assert any(not timer["cancelled"] for timer in hass.timers)
    run(manager.async_unload())
    assert all(not listeners for listeners in hass.bus.listeners.values())
    assert all(timer["cancelled"] for timer in hass.timers)
    reloaded = make_manager(hass, entry)
    assert reloaded.records
    assert sum(len(items) for items in hass.bus.listeners.values()) == 5
