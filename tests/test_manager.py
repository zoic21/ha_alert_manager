"""Alert Manager lifecycle, detection, persistence and exclusion tests."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Event

from custom_components.alert_manager.const import (
    ALERT_MANAGER_ENTITY_IDS,
    DATA_MANAGER,
    EVENT_ALERT_RESOLVED,
    EVENT_ALERT_STARTED,
    EVENT_DEVICE_ALERT_STARTED,
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


def fire_device_event_timers(hass):
    """Run every pending 10-second device-event debounce timer."""
    for timer in list(hass.timers):
        if timer["cancelled"]:
            continue
        if "_schedule_device_event_timer" not in timer["action"].__qualname__:
            continue
        timer["action"](timer["point"])


def test_creation_of_partitioned_sensors(hass, entry, registry_entry):
    """The sensor platform exposes three partitions and one device counter."""
    registry_entry(
        hass,
        "sensor.legacy_alerts",
        platform="alert_manager",
        unique_id="alert_manager",
    )
    manager = make_manager(hass, entry)
    hass.data[DATA_MANAGER] = manager
    entities = []
    run(async_setup_sensor(hass, entry, entities.extend))
    assert len(entities) == 4
    assert all(isinstance(entity, AlertManagerSensor) for entity in entities)
    assert {entity.entity_id for entity in entities} == {
        "sensor.alert_manager_main_active",
        "sensor.alert_manager_main_pending",
        "sensor.alert_manager_main_acknowledge",
        "sensor.alert_manager_device_main_active",
    }
    assert {entity._attr_unique_id for entity in entities} == {
        "alert_manager_main_active",
        "alert_manager_main_pending",
        "alert_manager_main_acknowledge",
        "alert_manager_device_main_active",
    }
    assert all(entity.native_value == 0 for entity in entities)
    assert {entity.entity_id: entity.extra_state_attributes for entity in entities} == {
        "sensor.alert_manager_main_active": {"alerts": []},
        "sensor.alert_manager_main_pending": {"alerts": []},
        "sensor.alert_manager_main_acknowledge": {"alerts": []},
        "sensor.alert_manager_device_main_active": {"devices": []},
    }
    assert all(
        entity._attr_device_info["identifiers"] == {("alert_manager", "main")}
        for entity in entities
    )
    assert "sensor.legacy_alerts" not in hass.entity_registry.entries


def test_normal_to_pending_and_no_duplicate(hass, entry):
    """A first-install anomaly starts pending and repeated evaluation is idempotent."""
    hass.states.set("sensor.unas", "unavailable", {"friendly_name": "UNAS"})
    manager = make_manager(hass, entry)
    assert set(manager.records) == {"unavailable:sensor.unas"}
    assert manager.records["unavailable:sensor.unas"].status is AlertStatus.PENDING
    run(manager.async_evaluate_entity("sensor.unas"))
    assert len(manager.records) == 1


def test_matching_updates_keep_the_original_trigger_value(hass, entry):
    """A still-abnormal value cannot overwrite the occurrence trigger snapshot."""
    hass.states.set("sensor.temperature", "11")
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "High temperature",
                "entity_ids": ["sensor.temperature"],
                "operator": "above",
                "value": 10,
                "duration": 900,
                "source": "state",
            }
        )
    )
    alert_id = f"rule:{rule['id']}:sensor.temperature"
    assert manager.records[alert_id].details.value == "11"

    hass.states.set("sensor.temperature", "12")
    run(manager.async_evaluate_entity("sensor.temperature"))

    assert manager.records[alert_id].details.value == "11"


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


def test_pending_alert_is_exposed_after_configured_display_delay(
    hass, entry, set_now, registry_entry, device_entry
):
    """Only the transient pending row waits for the presentation deadline."""
    start = datetime(2026, 8, 27, 10, tzinfo=UTC)
    set_now(start)
    device = device_entry(hass, name="Onduleur")
    registry_entry(hass, "sensor.ups", device_id=device.id)
    hass.states.set("sensor.ups", "unavailable")
    manager = make_manager(hass, entry)
    run(manager.async_update_config({"entity_delays": {"sensor.ups": 30}}))
    record = manager.records["unavailable:sensor.ups"]
    assert record.status is AlertStatus.PENDING
    assert record.visible_at == start + timedelta(seconds=10)
    assert manager.public_snapshot()["pending_count"] == 0

    set_now(start + timedelta(seconds=10))
    run(manager.async_evaluate_entity("sensor.ups"))
    assert manager.public_snapshot()["active_count"] == 0
    assert manager.public_snapshot()["pending_count"] == 1
    assert not [
        event for event, _data in hass.bus.fired if event == EVENT_DEVICE_ALERT_STARTED
    ]

    set_now(start + timedelta(seconds=30))
    run(manager.async_evaluate_entity("sensor.ups"))
    snapshot = manager.public_snapshot()
    assert record.status is AlertStatus.ACTIVE
    assert record.visible_at is None
    assert snapshot["active_count"] == 1
    assert snapshot["pending_count"] == 0
    assert snapshot["device_active_count"] == 1
    assert snapshot["active_devices"][0]["device_name"] == "Onduleur"
    assert snapshot["active_devices"][0]["alert_ids"] == ["unavailable:sensor.ups"]
    fire_device_event_timers(hass)
    events = [
        data for event, data in hass.bus.fired if event == EVENT_DEVICE_ALERT_STARTED
    ]
    assert len(events) == 1
    assert events[0]["device_id"] == device.id


def test_short_rule_delay_skips_pending_display_before_active(hass, entry, set_now):
    """A short rule becomes active without briefly exposing a pending row."""
    start = datetime(2026, 8, 27, 10, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "on")
    manager = make_manager(hass, entry)
    run(manager.async_update_config({"pending_display_delay": 10}))
    rule = run(
        manager.async_create_rule(
            {
                "name": "Short rule",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "on",
                "duration": 5,
            }
        )
    )
    record = manager.records[f"rule:{rule['id']}:sensor.test"]
    assert record.visible_at == start + timedelta(seconds=5)
    assert manager.public_snapshot()["pending_count"] == 0

    set_now(start + timedelta(seconds=5))
    run(manager.async_evaluate_entity("sensor.test"))
    assert record.visible_at is None
    assert manager.public_snapshot()["active_count"] == 1


def test_transient_pending_alert_never_reaches_public_lists(hass, entry, set_now):
    """A flapping condition that clears within ten seconds stays invisible."""
    start = datetime(2026, 8, 27, 10, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)

    for offset in (2, 6):
        set_now(start + timedelta(seconds=offset))
        hass.states.set("sensor.test", "ok")
        run(manager.async_evaluate_entity("sensor.test"))
        snapshot = manager.public_snapshot()
        assert snapshot["pending_count"] == 0
        assert snapshot["active_count"] == 0
        if offset == 2:
            set_now(start + timedelta(seconds=4))
            hass.states.set("sensor.test", "unavailable")
            run(manager.async_evaluate_entity("sensor.test"))

    assert not [
        event for event, _data in hass.bus.fired if event == EVENT_DEVICE_ALERT_STARTED
    ]


def test_pending_timer_runs_on_home_assistant_event_loop(hass, entry, set_now):
    """Timer jobs stay on the HA loop before creating config-entry tasks."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)
    timer = hass.timers[-1]
    assert timer["action"]._hass_callback is True

    async def fire_timer():
        set_now(start + timedelta(seconds=900))
        timer["action"](start + timedelta(seconds=900))
        await asyncio.sleep(0)

    run(fire_timer())
    record = manager.records["unavailable:sensor.test"]
    assert record.status is AlertStatus.ACTIVE
    assert entry.created_task_names == ["alert_manager timer unavailable:sensor.test"]


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
    assert started[0]["condition"] == "État indisponible"
    assert started[0]["condition_key"] == "automatic.unavailable"
    assert started[0]["condition_params"] == {}
    assert "severity" not in started[0]
    assert "severity" not in resolved[0]
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


@pytest.mark.parametrize("startup_state", [None, "unknown"])
def test_active_alert_survives_uncertain_state_during_restart(
    hass, entry, set_now, startup_state
):
    """A missing or unknown startup state cannot resolve a persisted alert."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable")
    first = make_manager(hass, entry)
    run(first.async_update_config({"automatic": {"unavailable": {"delay": 0}}}))
    assert first.records["unavailable:sensor.test"].status is AlertStatus.ACTIVE
    run(first.async_unload())

    if startup_state is None:
        hass.states.data.pop("sensor.test")
    else:
        hass.states.set("sensor.test", startup_state)
    restarted = make_manager(hass, entry)
    assert restarted.records["unavailable:sensor.test"].status is AlertStatus.ACTIVE

    hass.states.set("sensor.test", "ok")
    run(restarted.async_evaluate_entity("sensor.test"))
    assert restarted.records == {}


def test_unavailable_detection_does_not_duplicate_connectivity(hass, entry):
    """Unavailable wins over connectivity for the same entity."""
    hass.states.set(
        "binary_sensor.gateway",
        "unavailable",
        {"device_class": "connectivity"},
    )
    manager = make_manager(hass, entry)
    assert set(manager.records) == {"unavailable:binary_sensor.gateway"}


def test_unknown_is_not_an_unavailable_alert(hass, entry):
    """The unavailable pack deliberately excludes unknown states."""
    hass.states.set("automation.test", "unknown")
    assert make_manager(hass, entry).records == {}


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


def test_unifi_tracker_away(hass, entry, registry_entry, config_entry):
    """Only router-backed UniFi trackers away from home trigger UniFi detection."""
    config_entry(hass, "unifi")
    registry_entry(hass, "device_tracker.ap", platform="unifi")
    hass.states.set("device_tracker.ap", "not_home", {"source_type": "router"})
    manager = make_manager(hass, entry)
    assert "unifi:device_tracker.ap" in manager.records


def test_battery_global_threshold(hass, entry):
    """Battery device class uses the global category threshold."""
    hass.states.set("sensor.battery", "15", {"device_class": "battery"})
    manager = make_manager(hass, entry)
    assert manager.records["battery:sensor.battery"].details.value == 15.0


def test_battery_ignores_low_battery_level_attribute(hass, entry):
    """Only pack-owned global and device thresholds affect battery alerts."""
    hass.states.set(
        "sensor.battery",
        "20",
        {"device_class": "battery", "low_battery_level": 25},
    )
    manager = make_manager(hass, entry)
    assert "battery:sensor.battery" not in manager.records


def test_battery_device_threshold_overrides_entity_and_global_thresholds(
    hass, entry, registry_entry, device_entry
):
    """The battery pack owns a replaceable per-device threshold mapping."""
    device = device_entry(hass, name="Télécommande")
    registry_entry(hass, "sensor.remote_battery", device_id=device.id)
    hass.states.set(
        "sensor.remote_battery",
        "20",
        {"device_class": "battery", "low_battery_level": 10},
    )
    manager = make_manager(hass, entry)
    assert "battery:sensor.remote_battery" not in manager.records

    run(
        manager.async_update_config(
            {"automatic": {"battery": {"device_thresholds": {device.id: 25}}}}
        )
    )
    record = manager.records["battery:sensor.remote_battery"]
    assert "25 %" in record.details.condition

    run(
        manager.async_update_config(
            {"automatic": {"battery": {"device_thresholds": {}}}}
        )
    )
    assert manager.config["automatic"]["battery"]["device_thresholds"] == {}
    assert "battery:sensor.remote_battery" not in manager.records


def test_custom_rule_requires_its_optional_jinja_condition(hass, entry):
    """A tracked Jinja dependency can open and resolve a matching rule."""
    hass.states.set("sensor.source", "on")
    hass.states.set("input_boolean.guard", "off")

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(
            {
                "name": "Guarded rule",
                "entity_ids": ["sensor.source"],
                "operator": "equals",
                "value": "on",
                "duration": 0,
                "condition_template": "{{ is_state('input_boolean.guard', 'on') }}",
            }
        )
        alert_id = f"rule:{rule['id']}:sensor.source"
        assert alert_id not in manager.records

        hass.states.set("input_boolean.guard", "on")
        manager._state_changed(Event({"entity_id": "input_boolean.guard"}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert manager.records[alert_id].status is AlertStatus.ACTIVE

        hass.states.set("input_boolean.guard", "off")
        manager._state_changed(Event({"entity_id": "input_boolean.guard"}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert alert_id not in manager.records

    run(scenario())


def test_custom_rule_rejects_invalid_jinja_syntax(hass, entry):
    """Invalid templates never reach storage or runtime evaluation."""
    hass.states.set("sensor.source", "on")
    manager = make_manager(hass, entry)
    with pytest.raises(ValueError, match="Invalid rule condition_template"):
        run(
            manager.async_create_rule(
                {
                    "name": "Invalid Jinja",
                    "entity_ids": ["sensor.source"],
                    "operator": "equals",
                    "value": "on",
                    "duration": 0,
                    "condition_template": "{% if %}",
                }
            )
        )


def test_custom_rule_message_updates_pending_then_freezes_when_active(
    hass, entry, set_now
):
    """A Jinja message follows dependencies only until activation."""
    start = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.source", "on")
    hass.states.set("sensor.context", "warm")

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(
            {
                "name": "Templated message",
                "entity_ids": ["sensor.source"],
                "operator": "equals",
                "value": "on",
                "duration": 60,
                "message": (
                    "{{ entity_id }} vaut {{ value }} et le contexte est "
                    "{{ states('sensor.context') }}"
                ),
            }
        )
        alert_id = f"rule:{rule['id']}:sensor.source"
        expected = "sensor.source vaut on et le contexte est warm"
        assert manager.records[alert_id].status is AlertStatus.PENDING
        assert manager.records[alert_id].details.message == expected
        assert manager.records[alert_id].details.condition == expected

        hass.states.set("sensor.context", "hot")
        manager._state_changed(Event({"entity_id": "sensor.context"}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        updated = "sensor.source vaut on et le contexte est hot"
        assert manager.records[alert_id].details.message == updated
        assert manager.records[alert_id].details.condition == updated

        set_now(start + timedelta(seconds=60))
        await manager.async_evaluate_entity("sensor.source")
        assert manager.records[alert_id].status is AlertStatus.ACTIVE

        hass.states.set("sensor.context", "cold")
        manager._state_changed(Event({"entity_id": "sensor.context"}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert manager.records[alert_id].details.message == updated
        assert manager.records[alert_id].details.condition == updated
        assert (
            hass.stores["alert_manager"]["alerts"][alert_id]["details"]["message"]
            == updated
        )

        await manager.async_unload()
        reloaded = AlertManager(hass, entry)
        await reloaded.async_setup()
        assert reloaded.records[alert_id].details.message == updated
        assert reloaded.records[alert_id].details.condition == updated

    run(scenario())


def test_custom_rule_rejects_invalid_message_jinja_syntax(hass, entry):
    """An invalid Jinja message is rejected before it reaches storage."""
    hass.states.set("sensor.source", "on")
    manager = make_manager(hass, entry)
    with pytest.raises(ValueError, match="Invalid rule message template"):
        run(
            manager.async_create_rule(
                {
                    "name": "Invalid message",
                    "entity_ids": ["sensor.source"],
                    "operator": "equals",
                    "value": "on",
                    "duration": 0,
                    "message": "{% if %}",
                }
            )
        )


@pytest.mark.parametrize(
    ("operator", "state", "expected"),
    [
        ("equals", "off", "off"),
        ("not_equals", "ERROR", "OL CHRG"),
        ("contains", "OL CHRG", ["ERROR", "CHRG"]),
        ("not_contains", "OL CHRG", ["ERROR", "WARN"]),
        ("above", "11.2", 9),
        ("below", "0.8", 1),
    ],
)
def test_custom_rule_operator(hass, entry, operator, state, expected):
    """Every custom-rule operator creates the stable rule alert id."""
    hass.states.set("sensor.test", state)
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "Rule",
                "entity_ids": ["sensor.test"],
                "operator": operator,
                "value": expected,
                "duration": 300,
                "enabled": True,
                "source": "state",
            }
        )
    )
    record = manager.records[f"rule:{rule['id']}:sensor.test"]
    assert record.details.rule_id == rule["id"]
    assert record.details.rule_name == "Rule"
    assert record.details.condition_key == "rule.generated"
    assert record.details.condition_params == {
        "source": "state",
        "attribute": None,
        "operator": operator,
        "expected": (
            " / ".join(str(value) for value in expected)
            if isinstance(expected, list)
            else str(expected)
        ),
        "unit": None,
        "duration": 300,
    }


def test_custom_rule_message_remains_untranslated_user_text(hass, entry):
    """A custom message remains the compatible condition without a key."""
    hass.states.set("sensor.test", "on")
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "User rule",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "on",
                "duration": 0,
                "message": "My custom message",
            }
        )
    )
    details = manager.records[f"rule:{rule['id']}:sensor.test"].details
    assert details.condition == "My custom message"
    assert details.condition_key is None
    assert details.condition_params is None


def test_delay_priority(hass, entry):
    """Entity, pack and global delays follow the documented priority."""
    hass.states.set("sensor.test", "unavailable")
    hass.states.set("sensor.custom", "on")
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

    run(manager.async_update_config({"entity_delays": {}}))
    assert manager.records["unavailable:sensor.test"].delay == 80

    run(manager.async_update_config({"automatic": {"unavailable": {"delay": None}}}))
    assert manager.records["unavailable:sensor.test"].delay == 100

    run(manager.async_update_config({"entity_delays": {"sensor.custom": 1}}))
    rule = run(
        manager.async_create_rule(
            {
                "name": "Custom duration",
                "entity_ids": ["sensor.custom"],
                "operator": "equals",
                "value": "on",
                "duration": 10,
            }
        )
    )
    assert manager.records[f"rule:{rule['id']}:sensor.custom"].delay == 10


def test_shortened_automatic_delay_uses_real_activation_time(hass, entry, set_now):
    """A pending alert activated by a shorter delay starts at the config change."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)

    changed_at = start + timedelta(minutes=15)
    set_now(changed_at)
    run(manager.async_update_config({"automatic": {"unavailable": {"delay": 10}}}))

    record = manager.records["unavailable:sensor.test"]
    assert record.status is AlertStatus.ACTIVE
    assert record.due_at == start + timedelta(seconds=10)
    assert record.active_since == changed_at


def test_missing_rule_attribute_does_not_trigger_not_equals(hass, entry):
    """A missing attribute is not treated as an arbitrary comparison value."""
    hass.states.set("sensor.test", "ok", {})
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "Missing attribute",
                "entity_ids": ["sensor.test"],
                "source": "attribute",
                "attribute": "missing",
                "operator": "not_equals",
                "value": "ok",
                "duration": 60,
            }
        )
    )
    assert f"rule:{rule['id']}:sensor.test" not in manager.records


def test_unchanged_global_evaluation_does_not_publish(hass, entry):
    """Registry reevaluation does not cause a redundant sensor/Recorder write."""
    manager = make_manager(hass, entry)
    notifications = []
    hass.dispatchers["alert_manager_alerts_updated"].append(
        lambda: notifications.append(True)
    )
    run(manager.async_evaluate_all())
    assert notifications == []


def test_unavailable_monitors_every_domain_but_not_alert_manager(
    hass, entry, registry_entry
):
    """Unavailable applies to all domains while excluding the integration itself."""
    hass.states.set("automation.unrelated", "unavailable")
    hass.states.set("sensor.relevant", "unavailable")
    registry_entry(hass, "sensor.alert_manager_copy", platform="alert_manager")
    hass.states.set("sensor.alert_manager_copy", "unavailable")
    for entity_id in ALERT_MANAGER_ENTITY_IDS:
        hass.states.set(entity_id, "unavailable")
    manager = make_manager(hass, entry)
    assert set(manager.records) == {
        "unavailable:automation.unrelated",
        "unavailable:sensor.relevant",
    }


def test_custom_rules_reject_alert_manager_entities(hass, entry, registry_entry):
    """Visual and YAML-backed rule APIs cannot monitor the integration itself."""
    registry_entry(hass, "sensor.renamed_alerts", platform="alert_manager")
    manager = make_manager(hass, entry)
    payload = {
        "name": "Self monitoring",
        "entity_ids": ["sensor.alert_manager_main_active"],
        "operator": "above",
        "value": 0,
        "duration": 0,
        "enabled": True,
        "source": "state",
    }

    with pytest.raises(ValueError, match="Alert Manager entities"):
        run(manager.async_create_rule(payload))

    payload["entity_ids"] = ["sensor.renamed_alerts"]
    with pytest.raises(ValueError, match="Alert Manager entities"):
        run(manager.async_create_rule(payload))


def test_existing_self_rules_are_removed_during_migration(hass, entry):
    """An inert self-rule from an earlier release is cleaned without data loss."""
    hass.stores["alert_manager"] = {
        "config": {
            "rules": [
                {
                    "id": "self-rule",
                    "name": "Self monitoring",
                    "entity_ids": ["sensor.alert_manager_main_pending"],
                    "operator": "above",
                    "value": 0,
                    "duration": 0,
                }
            ]
        },
        "alerts": {},
    }

    manager = make_manager(hass, entry)

    assert manager.get_config()["rules"] == []
    assert hass.stores["alert_manager"]["config"]["rules"] == []


def test_state_listener_skips_irrelevant_entities(hass, entry):
    """Unrelated state events do not allocate config-entry evaluation tasks."""
    manager = make_manager(hass, entry)
    run(
        manager.async_update_config(
            {
                "automatic": {
                    "unavailable": {"enabled": False},
                    "connectivity": {"enabled": False},
                    "unifi": {"enabled": False},
                    "battery": {"enabled": False},
                }
            }
        )
    )
    entry.created_task_names.clear()

    async def fire_events():
        manager._state_changed(Event({"entity_id": "automation.unrelated"}))
        await asyncio.sleep(0)

    run(fire_events())
    assert entry.created_task_names == []


def test_rule_mutation_uses_one_atomic_storage_write(hass, entry):
    """A rule change and its immediate evaluation persist in one snapshot."""
    hass.states.set("sensor.test", "on")
    manager = make_manager(hass, entry)
    hass.store_save_count = 0
    run(
        manager.async_create_rule(
            {
                "name": "One write",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "on",
                "duration": 0,
            }
        )
    )
    assert hass.store_save_count == 1


def test_configuration_write_failure_restores_runtime_state(hass, entry):
    """A failed settings write leaves configuration, alerts and timers unchanged."""
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)
    before_config = manager.get_config()
    before_records = deepcopy(manager.records)

    async def fail_save(_config, _records):
        raise OSError("storage unavailable")

    manager.storage.async_save = fail_save
    with pytest.raises(OSError, match="storage unavailable"):
        run(manager.async_update_config({"entity_delays": {"sensor.test": 0}}))
    assert manager.get_config() == before_config
    assert manager.records == before_records
    assert [timer for timer in hass.timers if not timer["cancelled"]]


def test_rule_write_failures_restore_create_update_and_delete(hass, entry):
    """Every rule mutation rolls back fully when persistence is unavailable."""
    hass.states.set("sensor.test", "on")
    manager = make_manager(hass, entry)
    payload = {
        "name": "Atomic rule",
        "entity_ids": ["sensor.test"],
        "operator": "equals",
        "value": "on",
        "duration": 60,
    }
    original_save = manager.storage.async_save

    async def fail_save(_config, _records):
        raise OSError("storage unavailable")

    manager.storage.async_save = fail_save
    with pytest.raises(OSError, match="storage unavailable"):
        run(manager.async_create_rule(payload))
    assert manager.get_config()["rules"] == []
    assert manager.records == {}

    manager.storage.async_save = original_save
    rule = run(manager.async_create_rule(payload))
    before_config = manager.get_config()
    before_records = deepcopy(manager.records)
    manager.storage.async_save = fail_save

    with pytest.raises(OSError, match="storage unavailable"):
        run(manager.async_update_rule(rule["id"], {"duration": 0}))
    assert manager.get_config() == before_config
    assert manager.records == before_records

    with pytest.raises(OSError, match="storage unavailable"):
        run(manager.async_delete_rule(rule["id"]))
    assert manager.get_config() == before_config
    assert manager.records == before_records


def test_custom_rule_entities_have_independent_lifecycles(hass, entry, set_now):
    """Each rule/entity pair owns its pending clock, activation and resolution."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.one", "on", {"friendly_name": "Capteur un"})
    hass.states.set("sensor.two", "on", {"friendly_name": "Capteur deux"})
    hass.states.set("sensor.three", "off")
    manager = make_manager(hass, entry)
    run(manager.async_update_config({"pending_display_delay": 0}))
    rule = run(
        manager.async_create_rule(
            {
                "name": "Plusieurs sources",
                "entity_ids": ["sensor.one", "sensor.two", "sensor.three"],
                "operator": "equals",
                "value": "on",
                "duration": 60,
            }
        )
    )
    one_id = f"rule:{rule['id']}:sensor.one"
    two_id = f"rule:{rule['id']}:sensor.two"
    assert set(manager.records) == {one_id, two_id}
    assert manager.public_snapshot()["pending_count"] == 2
    assert manager.records[one_id].details.name == "Capteur un"

    set_now(start + timedelta(seconds=30))
    hass.states.set("sensor.one", "off")
    run(manager.async_evaluate_entity("sensor.one"))
    assert one_id not in manager.records
    assert manager.records[two_id].detected_at == start

    set_now(start + timedelta(seconds=60))
    run(manager.async_evaluate_entity("sensor.two"))
    assert manager.records[two_id].status is AlertStatus.ACTIVE
    snapshot = manager.public_snapshot()
    assert snapshot["active_count"] == 1
    assert snapshot["pending_count"] == 0

    hass.states.set("sensor.one", "on")
    run(manager.async_evaluate_entity("sensor.one"))
    assert manager.records[one_id].detected_at == start + timedelta(seconds=60)
    assert manager.records[one_id].status is AlertStatus.PENDING


def test_same_entity_can_belong_to_multiple_rules(hass, entry):
    """Rule ids keep two matching rules on the same source independent."""
    hass.states.set("sensor.test", "on")
    manager = make_manager(hass, entry)
    rules = [
        run(
            manager.async_create_rule(
                {
                    "name": name,
                    "entity_ids": ["sensor.test"],
                    "operator": "equals",
                    "value": "on",
                    "duration": 0,
                    "message": f"{name} message",
                }
            )
        )
        for name in ("First", "Second")
    ]
    assert set(manager.records) == {f"rule:{rule['id']}:sensor.test" for rule in rules}
    snapshot = manager.public_snapshot()
    assert snapshot["active_count"] == 2
    assert snapshot["active_devices"][0]["messages"] == [
        "First message",
        "Second message",
    ]
    assert snapshot["active_devices"][0]["rules"] == ["First", "Second"]


def test_device_event_debounces_new_alerts_and_includes_rule_message_arrays(
    hass, entry, registry_entry, device_entry
):
    """The device event waits for ten quiet seconds and emits the final group."""
    device = device_entry(hass, name="Baie")
    registry_entry(hass, "sensor.rack", device_id=device.id)
    hass.states.set("sensor.rack", "hot")
    manager = make_manager(hass, entry)

    first = run(
        manager.async_create_rule(
            {
                "name": "Temperature",
                "entity_ids": ["sensor.rack"],
                "operator": "equals",
                "value": "hot",
                "duration": 0,
                "message": "Rack hot",
            }
        )
    )
    first_timer = next(
        timer
        for timer in reversed(hass.timers)
        if not timer["cancelled"]
        and "_schedule_device_event_timer" in timer["action"].__qualname__
    )
    assert not [
        event for event, _data in hass.bus.fired if event == EVENT_DEVICE_ALERT_STARTED
    ]

    second = run(
        manager.async_create_rule(
            {
                "name": "Ventilation",
                "entity_ids": ["sensor.rack"],
                "operator": "equals",
                "value": "hot",
                "duration": 0,
                "message": "Fan stopped",
            }
        )
    )
    assert first_timer["cancelled"] is True
    fire_device_event_timers(hass)
    events = [
        data for event, data in hass.bus.fired if event == EVENT_DEVICE_ALERT_STARTED
    ]
    assert len(events) == 1
    assert set(events[0]["alert_ids"]) == {
        f"rule:{first['id']}:sensor.rack",
        f"rule:{second['id']}:sensor.rack",
    }
    assert events[0]["messages"] == ["Rack hot", "Fan stopped"]
    assert events[0]["rules"] == ["Temperature", "Ventilation"]


def test_device_sensor_keeps_messages_and_rules_inside_each_device():
    """The device sensor exposes no misleading global message/rule arrays."""
    devices = [
        {
            "device_id": "one",
            "messages": ["Battery low", "Offline"],
            "rules": ["Battery", "Unavailable"],
        },
        {
            "device_id": "two",
            "messages": ["Offline", "Temperature high"],
            "rules": ["Unavailable", "Temperature"],
        },
    ]
    manager = SimpleNamespace(
        monitoring_enabled=True,
        public_snapshot=lambda: {
            "device_active_count": 2,
            "active_devices": devices,
        },
    )
    sensor = AlertManagerSensor(
        manager,
        "device_main_active",
        "alert_manager_device_main_active",
        "mdi:devices",
        "device_active_count",
        "active_devices",
        "devices",
    )

    assert sensor.extra_state_attributes == {"devices": devices}


def test_tracked_count_combines_custom_instances_and_automatic_entities(
    hass, entry, registry_entry
):
    """Tracked total counts rule/entity pairs plus unique automatic sources."""
    hass.label_registry.labels["pas_d_alerte"] = SimpleNamespace(label_id="skip")
    hass.states.set("sensor.one", "ok")
    hass.states.set("sensor.two", "ok")
    registry_entry(hass, "sensor.excluded", labels={"skip"})
    hass.states.set("sensor.excluded", "ok")
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "Two custom instances",
                "entity_ids": ["sensor.one", "sensor.excluded"],
                "operator": "equals",
                "value": "alert",
                "duration": 0,
            }
        )
    )

    # Two eligible automatic entities plus two configured custom instances.
    assert manager.public_snapshot()["tracked_count"] == 4

    run(manager.async_update_rule(rule["id"], {"enabled": False}))
    assert manager.public_snapshot()["tracked_count"] == 2


def test_rule_delay_update_can_activate_immediately(hass, entry, set_now):
    """A shortened duration is recalculated from the original detection time."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "on")
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "Delay",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "on",
                "duration": 900,
            }
        )
    )
    set_now(start + timedelta(seconds=600))
    run(manager.async_update_rule(rule["id"], {"duration": 300}))
    record = manager.records[f"rule:{rule['id']}:sensor.test"]
    assert record.status is AlertStatus.ACTIVE
    assert record.due_at == start + timedelta(seconds=300)
    assert record.active_since == start + timedelta(seconds=600)


def test_removing_entity_delay_replaces_the_complete_mapping(hass, entry):
    """Saving an empty entity-delay mapping really removes existing overrides."""
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)
    run(manager.async_update_config({"entity_delays": {"sensor.test": 20}}))
    assert manager.records["unavailable:sensor.test"].delay == 20

    run(manager.async_update_config({"entity_delays": {}}))

    assert manager.config["entity_delays"] == {}
    assert manager.records["unavailable:sensor.test"].delay == 900


def test_rule_delay_extension_rechecks_an_active_instance(hass, entry, set_now):
    """Extending a duration can return a just-active instance to pending."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "on")
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "Extended delay",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "on",
                "duration": 0,
            }
        )
    )
    hass.bus.fired.clear()
    run(manager.async_update_rule(rule["id"], {"duration": 60}))
    record = manager.records[f"rule:{rule['id']}:sensor.test"]
    assert record.status is AlertStatus.PENDING
    assert record.active_since is None
    assert record.due_at == start + timedelta(seconds=60)
    assert not [
        event for event, _data in hass.bus.fired if event == EVENT_ALERT_RESOLVED
    ]


def test_entity_delay_extension_returns_active_automatic_alert_to_pending(
    hass, entry, set_now
):
    """Automatic delay changes retain the id and original detection time."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)
    run(manager.async_update_config({"entity_delays": {"sensor.test": 0}}))
    record = manager.records["unavailable:sensor.test"]
    assert record.status is AlertStatus.ACTIVE
    assert record.detected_at == start

    hass.bus.fired.clear()
    run(manager.async_update_config({"entity_delays": {"sensor.test": 60}}))
    record = manager.records["unavailable:sensor.test"]
    assert record.details.id == "unavailable:sensor.test"
    assert record.detected_at == start
    assert record.due_at == start + timedelta(seconds=60)
    assert record.status is AlertStatus.PENDING
    assert record.active_since is None
    assert not [
        event for event, _data in hass.bus.fired if event == EVENT_ALERT_RESOLVED
    ]


def test_pack_availability_cleans_timers_and_preserves_enabled_choice(
    hass, entry, registry_entry, config_entry
):
    """An unavailable conditional pack is inert without changing its setting."""
    registry_entry(hass, "device_tracker.ap", platform="unifi")
    hass.states.set("device_tracker.ap", "not_home", {"source_type": "router"})
    manager = make_manager(hass, entry)
    metadata = {pack["id"]: pack for pack in manager.get_packs()}
    assert metadata["unavailable"]["available"] is True
    assert metadata["connectivity"]["available"] is True
    assert metadata["battery"]["available"] is True
    assert metadata["unifi"]["available"] is False
    assert manager.records == {}
    assert not [timer for timer in hass.timers if not timer["cancelled"]]

    unifi_entry = config_entry(hass, "unifi")
    assert run(manager.async_refresh_pack_availability()) is True
    assert "unifi:device_tracker.ap" in manager.records
    assert manager.get_config()["automatic"]["unifi"]["enabled"] is True
    assert [timer for timer in hass.timers if not timer["cancelled"]]

    unifi_entry.state = ConfigEntryState.NOT_LOADED
    assert run(manager.async_refresh_pack_availability()) is True
    assert manager.records == {}
    assert not [timer for timer in hass.timers if not timer["cancelled"]]
    assert manager.get_config()["automatic"]["unifi"]["enabled"] is True

    unifi_entry.state = ConfigEntryState.LOADED
    assert run(manager.async_refresh_pack_availability()) is True
    assert "unifi:device_tracker.ap" in manager.records
    assert manager.get_config()["automatic"]["unifi"]["enabled"] is True


def test_pack_entry_state_listener_re_evaluates_automatically(
    hass, entry, registry_entry, config_entry
):
    """A prerequisite entry state transition schedules the availability refresh."""
    unifi_entry = config_entry(hass, "unifi")
    registry_entry(hass, "device_tracker.ap", platform="unifi")
    hass.states.set("device_tracker.ap", "not_home", {"source_type": "router"})

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        assert "unifi:device_tracker.ap" in manager.records

        unifi_entry.set_state(ConfigEntryState.NOT_LOADED)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert "unifi:device_tracker.ap" not in manager.records
        assert entry.created_task_names[-1] == "alert_manager pack availability"

    run(scenario())


@pytest.mark.parametrize(
    ("state", "disabled_by", "source"),
    [
        (ConfigEntryState.NOT_LOADED, None, "user"),
        (ConfigEntryState.LOADED, "user", "user"),
        (ConfigEntryState.LOADED, None, "ignore"),
    ],
)
def test_unifi_pack_requires_a_usable_config_entry(
    hass, entry, config_entry, state, disabled_by, source
):
    """Unloaded, disabled and ignored UniFi entries do not enable the pack."""
    config_entry(
        hass,
        "unifi",
        state=state,
        disabled_by=disabled_by,
        source=source,
    )
    manager = make_manager(hass, entry)
    unifi = next(pack for pack in manager.get_packs() if pack["id"] == "unifi")
    assert unifi["available"] is False


def test_same_device_alerts_remain_individual_in_state_and_events(
    hass, entry, registry_entry, device_entry
):
    """Device grouping data never changes individual counters or events."""
    device = device_entry(hass, name="Onduleur")
    registry_entry(hass, "sensor.ups_status", device_id=device.id)
    registry_entry(hass, "sensor.ups_battery", device_id=device.id)
    hass.states.set("sensor.ups_status", "unavailable")
    hass.states.set("sensor.ups_battery", "unavailable")
    manager = make_manager(hass, entry)
    run(
        manager.async_update_config(
            {
                "entity_delays": {
                    "sensor.ups_status": 0,
                    "sensor.ups_battery": 60,
                },
                "pending_display_delay": 0,
            }
        )
    )

    snapshot = manager.public_snapshot()
    assert snapshot["active_count"] == 1
    assert snapshot["pending_count"] == 1
    assert len(snapshot["alerts"]) == len(snapshot["pending"]) == 1
    assert snapshot["alerts"][0]["device_id"] == device.id
    assert snapshot["pending"][0]["device_id"] == device.id
    assert snapshot["alerts"][0]["id"] != snapshot["pending"][0]["id"]

    run(
        manager.async_update_config(
            {
                "entity_delays": {
                    "sensor.ups_status": 0,
                    "sensor.ups_battery": 0,
                }
            }
        )
    )
    started = [data for event, data in hass.bus.fired if event == EVENT_ALERT_STARTED]
    assert {data["id"] for data in started} == {
        "unavailable:sensor.ups_status",
        "unavailable:sensor.ups_battery",
    }
    fire_device_event_timers(hass)
    device_started = [
        data for event, data in hass.bus.fired if event == EVENT_DEVICE_ALERT_STARTED
    ]
    assert len(device_started) == 1
    assert device_started[0]["device_id"] == device.id
    assert set(device_started[0]["alert_ids"]) <= {
        "unavailable:sensor.ups_status",
        "unavailable:sensor.ups_battery",
    }
    assert manager.public_snapshot()["active_count"] == 2

    hass.states.set("sensor.ups_status", "ok")
    hass.states.set("sensor.ups_battery", "ok")
    run(manager.async_evaluate_entity("sensor.ups_status"))
    run(manager.async_evaluate_entity("sensor.ups_battery"))
    resolved = [data for event, data in hass.bus.fired if event == EVENT_ALERT_RESOLVED]
    assert {data["id"] for data in resolved} == {
        "unavailable:sensor.ups_status",
        "unavailable:sensor.ups_battery",
    }


def test_devices_with_the_same_name_share_one_active_group(
    hass, entry, registry_entry, device_entry
):
    """Duplicate registry devices keep one counter and one lifecycle event."""
    first_device = device_entry(hass, "a" * 32, name="Onduleur")
    second_device = device_entry(hass, "b" * 32, name=" onduleur ")
    registry_entry(hass, "sensor.ups_one", device_id=first_device.id)
    registry_entry(hass, "sensor.ups_two", device_id=second_device.id)
    hass.states.set("sensor.ups_one", "unavailable")
    hass.states.set("sensor.ups_two", "ok")
    manager = make_manager(hass, entry)
    run(
        manager.async_update_config(
            {
                "entity_delays": {"sensor.ups_one": 0, "sensor.ups_two": 0},
                "pending_display_delay": 0,
            }
        )
    )

    initial = manager.public_snapshot()
    assert initial["device_active_count"] == 1
    assert initial["active_devices"][0]["device_ids"] == [first_device.id]
    fire_device_event_timers(hass)
    device_events = [
        data for event, data in hass.bus.fired if event == EVENT_DEVICE_ALERT_STARTED
    ]
    assert len(device_events) == 1
    assert device_events[0]["device_ids"] == [first_device.id]

    hass.states.set("sensor.ups_two", "unavailable")
    run(manager.async_evaluate_entity("sensor.ups_two"))
    snapshot = manager.public_snapshot()
    assert snapshot["device_active_count"] == 1
    device = snapshot["active_devices"][0]
    assert device["device_id"] == first_device.id
    assert device["device_ids"] == [first_device.id, second_device.id]
    assert device["device_name"] == "Onduleur"
    assert device["alert_count"] == 2
    assert set(device["alert_ids"]) == {
        "unavailable:sensor.ups_one",
        "unavailable:sensor.ups_two",
    }
    assert device["messages"] == []
    assert device["rules"] == ["unavailable"]
    device_events = [
        data for event, data in hass.bus.fired if event == EVENT_DEVICE_ALERT_STARTED
    ]
    assert len(device_events) == 1

    hass.states.set("sensor.ups_one", "ok")
    run(manager.async_evaluate_entity("sensor.ups_one"))
    remaining = manager.public_snapshot()["active_devices"][0]
    assert remaining["device_id"] == second_device.id
    assert remaining["device_ids"] == [second_device.id]
    assert (
        len(
            [
                event
                for event, _data in hass.bus.fired
                if event == EVENT_DEVICE_ALERT_STARTED
            ]
        )
        == 1
    )


def test_entities_without_devices_are_counted_individually(hass, entry):
    """Each device-less entity acts as one stable fallback device."""
    hass.states.set("sensor.one", "unavailable", {"friendly_name": "Capteur un"})
    hass.states.set("sensor.two", "unavailable")
    manager = make_manager(hass, entry)
    run(
        manager.async_update_config(
            {
                "entity_delays": {"sensor.one": 0, "sensor.two": 0},
                "pending_display_delay": 0,
            }
        )
    )

    snapshot = manager.public_snapshot()
    assert snapshot["device_active_count"] == 2
    assert {
        (device["device_id"], device["device_name"])
        for device in snapshot["active_devices"]
    } == {
        ("sensor.one", "Capteur un"),
        ("sensor.two", "sensor.two"),
    }
    assert all(
        device["device_ids"] == [device["device_id"]]
        for device in snapshot["active_devices"]
    )
    fire_device_event_timers(hass)
    events = [
        data for event, data in hass.bus.fired if event == EVENT_DEVICE_ALERT_STARTED
    ]
    assert {event["device_id"] for event in events} == {
        "sensor.one",
        "sensor.two",
    }

    run(manager.async_evaluate_entity("sensor.one"))
    assert (
        len(
            [
                event
                for event, _data in hass.bus.fired
                if event == EVENT_DEVICE_ALERT_STARTED
            ]
        )
        == 2
    )


def test_rule_configuration_cleanup_is_silent(hass, entry):
    """Removing a source or disabling a rule emits no resolution notification."""
    hass.states.set("sensor.one", "on")
    hass.states.set("sensor.two", "on")
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "Cleanup",
                "entity_ids": ["sensor.one", "sensor.two"],
                "operator": "equals",
                "value": "on",
                "duration": 0,
            }
        )
    )
    hass.bus.fired.clear()
    run(manager.async_update_rule(rule["id"], {"entity_ids": ["sensor.one"]}))
    assert f"rule:{rule['id']}:sensor.two" not in manager.records
    assert not [
        event for event, _data in hass.bus.fired if event == EVENT_ALERT_RESOLVED
    ]

    run(manager.async_update_rule(rule["id"], {"enabled": False}))
    assert f"rule:{rule['id']}:sensor.one" not in manager.records
    assert not [
        event for event, _data in hass.bus.fired if event == EVENT_ALERT_RESOLVED
    ]


def test_custom_rules_ignore_selected_exclusion_labels(hass, entry, registry_entry):
    """An explicit rule still monitors a label-excluded source."""
    hass.label_registry.labels["pas_d_alerte"] = SimpleNamespace(label_id="skip")
    registry_entry(hass, "sensor.test", labels={"skip"})
    hass.states.set("sensor.test", "on")
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "Explicit",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "on",
                "duration": 0,
            }
        )
    )
    assert f"rule:{rule['id']}:sensor.test" in manager.records


def test_legacy_rule_and_label_configuration_migrate_idempotently(hass, entry):
    """V1 entity_id and exclusion-label names become V1.1 registry ids."""
    hass.label_registry.labels["pas_d_alerte"] = SimpleNamespace(label_id="skip")
    hass.states.set("sensor.test", "on", {"friendly_name": "Legacy sensor"})
    detected_at = datetime(2026, 8, 24, 12, tzinfo=UTC)
    hass.stores["alert_manager"] = {
        "config": {
            "exclusion_label": "pas_d_alerte",
            "active_display_delay": 7,
            "automatic": {"unavailable": {"domains": ["sensor"]}},
            "rules": [
                {
                    "id": "legacy",
                    "name": "Legacy",
                    "entity_id": "sensor.test",
                    "operator": "equals",
                    "value": "on",
                    "duration": 60,
                    "version": 1,
                }
            ],
        },
        "alerts": {
            "rule:legacy": {
                "details": {
                    "id": "rule:legacy",
                    "type": "rule",
                    "entity_id": "sensor.test",
                    "name": "Legacy sensor",
                    "value": "on",
                    "condition": "État égal à on",
                },
                "status": "pending",
                "detected_at": detected_at.isoformat(),
                "due_at": (detected_at + timedelta(seconds=60)).isoformat(),
                "delay": 60,
                "active_since": None,
            }
        },
    }
    manager = make_manager(hass, entry)
    rule = manager.get_config()["rules"][0]
    assert rule["entity_ids"] == ["sensor.test"]
    assert "entity_id" not in rule
    assert rule["version"] == 2
    assert manager.get_config()["excluded_labels"] == ["skip"]
    assert manager.get_config()["monitoring_enabled"] is True
    assert manager.get_config()["history_limit"] == 100
    assert manager.get_config()["pending_display_delay"] == 7
    assert "active_display_delay" not in manager.get_config()
    assert manager.history == []
    assert "domains" not in manager.get_config()["automatic"]["unavailable"]
    assert "rule:legacy:sensor.test" in manager.records
    assert manager.records["rule:legacy:sensor.test"].detected_at == detected_at
    assert manager.records["rule:legacy:sensor.test"].details.rule_id == "legacy"
    assert manager.records["rule:legacy:sensor.test"].details.rule_name == "Legacy"
    assert manager.records["rule:legacy:sensor.test"].details.source == "state"
    assert manager.records["rule:legacy:sensor.test"].details.operator == "equals"
    assert manager.records["rule:legacy:sensor.test"].details.comparison_value == "on"
    assert hass.stores["alert_manager"]["config"]["monitoring_enabled"] is True
    assert hass.stores["alert_manager"]["config"]["pending_display_delay"] == 7

    run(manager.async_unload())
    reloaded = make_manager(hass, entry)
    assert reloaded.get_config()["rules"] == [rule]
    assert reloaded.get_config()["excluded_labels"] == ["skip"]


def test_invalid_alerts_collection_is_ignored(hass, entry):
    """A malformed storage collection is removed during successful startup."""
    hass.stores["alert_manager"] = {"config": {}, "alerts": []}
    manager = make_manager(hass, entry)
    assert manager.records == {}
    assert hass.stores["alert_manager"]["alerts"] == {}


def test_invalid_stored_configuration_is_replaced_with_defaults(hass, entry):
    """A malformed stored rule is cleaned instead of failing every startup."""
    hass.stores["alert_manager"] = {
        "config": {"rules": [{"id": "incomplete"}]},
        "alerts": {},
    }
    manager = make_manager(hass, entry)
    assert manager.get_config()["rules"] == []
    assert hass.stores["alert_manager"]["config"]["rules"] == []


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
