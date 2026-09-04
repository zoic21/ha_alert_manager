"""Automatic-pack should-evaluate regression tests."""

from __future__ import annotations

import asyncio

from homeassistant.const import ATTR_DEVICE_CLASS
from homeassistant.core import CoreState, Event

from custom_components.alert_manager.const import (
    EVENT_ALERT_RESOLVED,
    EVENT_ALERT_STARTED,
)
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertStatus
from custom_components.alert_manager.packs import (
    PackNeutral,
    battery,
    connectivity,
    unavailable,
)


def _battery_state(hass, value: str, *, entity_id: str = "sensor.battery"):
    hass.states.set(entity_id, value, {ATTR_DEVICE_CLASS: "battery"})
    return hass.states.get(entity_id)


def _state_event(entity_id, old_state, new_state):
    return Event(
        {
            "entity_id": entity_id,
            "old_state": old_state,
            "new_state": new_state,
        }
    )


def _should_evaluate(pack, hass, new_state, config, old_state=None):
    callback = pack.should_evaluate
    assert callback is not None
    return callback(hass, old_state, new_state, config)


def test_unavailable_pack_filters_only_interesting_new_state(hass):
    """Unavailable is interesting only when the new state is unavailable."""
    normal = hass.states.set("sensor.source", "1")
    unavailable_state = hass.states.set("sensor.source", "unavailable")
    config = {"enabled": True}

    assert not _should_evaluate(unavailable.PACK, hass, normal, config)
    assert _should_evaluate(unavailable.PACK, hass, unavailable_state, config)


def test_connectivity_pack_filters_only_unavailable(hass):
    """Every applicable definitive connectivity state is worth evaluating."""
    attributes = {ATTR_DEVICE_CLASS: "connectivity"}
    on_state = hass.states.set("binary_sensor.link", "on", attributes)
    off_state = hass.states.set("binary_sensor.link", "off", attributes)
    unavailable_state = hass.states.set("binary_sensor.link", "unavailable", attributes)
    config = {"enabled": True}

    assert _should_evaluate(connectivity.PACK, hass, on_state, config)
    assert _should_evaluate(connectivity.PACK, hass, off_state, config)
    assert not _should_evaluate(connectivity.PACK, hass, unavailable_state, config)


def test_battery_filter_leaves_threshold_matching_to_evaluate(hass, registry_entry):
    """Battery should_evaluate only filters unavailable, never the threshold."""
    device_id = "battery-device"
    registry_entry(hass, "sensor.battery", device_id=device_id)
    config = {
        "enabled": True,
        "threshold": 15,
        "device_thresholds": {device_id: 30},
    }

    assert _should_evaluate(battery.PACK, hass, _battery_state(hass, "40"), config)
    assert _should_evaluate(battery.PACK, hass, _battery_state(hass, "30"), config)
    assert _should_evaluate(battery.PACK, hass, _battery_state(hass, "29"), config)
    assert _should_evaluate(battery.PACK, hass, _battery_state(hass, "31"), config)
    assert not _should_evaluate(
        battery.PACK, hass, _battery_state(hass, "unavailable"), config
    )


def test_battery_unavailable_is_neutral(hass):
    """An unavailable reading cannot resolve an existing low-battery alert."""
    state = _battery_state(hass, "unavailable")

    assert isinstance(battery.PACK.evaluate(hass, state, {}), PackNeutral)


def test_active_battery_survives_startup_unavailable_state(hass, entry):
    """A startup availability gap cannot recreate an active battery as pending."""

    async def scenario():
        low_state = _battery_state(hass, "10")
        first = AlertManager(hass, entry)
        await first.async_setup()
        await first.async_update_config({"automatic": {"battery": {"delay": 0}}})

        alert_id = "battery:sensor.battery"
        original = first.records[alert_id]
        assert original.status is AlertStatus.ACTIVE
        detected_at = original.detected_at
        due_at = original.due_at
        active_since = original.active_since
        events_before = len(
            [
                event
                for event in hass.bus.fired
                if event[0] in (EVENT_ALERT_STARTED, EVENT_ALERT_RESOLVED)
            ]
        )
        await first.async_unload()

        hass.state = CoreState.starting
        unavailable_state = hass.states.set("sensor.battery", "unavailable", {})
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        restarted._state_changed(
            _state_event("sensor.battery", low_state, unavailable_state)
        )

        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.ACTIVE
        assert restored.detected_at == detected_at
        assert restored.due_at == due_at
        assert restored.active_since == active_since

        low_again = _battery_state(hass, "9")
        restarted._state_changed(
            _state_event("sensor.battery", unavailable_state, low_again)
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.ACTIVE
        assert restored.detected_at == detected_at
        assert restored.due_at == due_at
        assert restored.active_since == active_since
        lifecycle_events = [
            event
            for event in hass.bus.fired
            if event[0] in (EVENT_ALERT_STARTED, EVENT_ALERT_RESOLVED)
        ]
        assert len(lifecycle_events) == events_before

    asyncio.run(scenario())


def test_battery_threshold_follows_config_and_device_changes(hass, registry_entry):
    """Threshold selection follows changed overrides and device assignments."""
    registry = registry_entry(hass, "sensor.battery", device_id="device-a")
    config = {
        "enabled": True,
        "threshold": 15,
        "device_thresholds": {"device-a": 30, "device-b": 50},
    }
    state = _battery_state(hass, "40")

    assert battery.PACK.evaluate(hass, state, config) is None
    assert battery.PACK.evaluate(hass, state, config) is None

    config["device_thresholds"]["device-a"] = 45
    match = battery.PACK.evaluate(hass, state, config)
    assert match is not None
    assert match.condition_params == {"threshold": "45"}

    config["device_thresholds"]["device-a"] = 30
    registry.device_id = "device-b"
    match = battery.PACK.evaluate(hass, state, config)
    assert match is not None
    assert match.condition_params == {"threshold": "50"}


def test_runtime_battery_filter_evaluates_states(hass, entry, registry_entry):
    """Battery values are evaluated even when they do not cross the threshold."""

    async def scenario():
        device_id = "battery-device"
        registry_entry(hass, "sensor.battery", device_id=device_id)
        _battery_state(hass, "40")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        manager.config["automatic"]["battery"]["device_thresholds"] = {device_id: 30}

        old_state = _battery_state(hass, "40")
        new_state = _battery_state(hass, "35")
        before = len(entry.created_task_names)
        manager._state_changed(_state_event("sensor.battery", old_state, new_state))
        assert len(entry.created_task_names) == before + 1
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert "battery:sensor.battery" not in manager.records

        old_state = _battery_state(hass, "31")
        new_state = _battery_state(hass, "30")
        manager._state_changed(_state_event("sensor.battery", old_state, new_state))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert "battery:sensor.battery" in manager.records

    asyncio.run(scenario())


def test_existing_battery_record_always_forces_evaluation(hass, entry):
    """Any existing occurrence makes every following source event relevant."""

    async def scenario():
        _battery_state(hass, "50")
        manager = AlertManager(hass, entry)
        await manager.async_setup()

        old_state = hass.states.get("sensor.battery")
        new_state = _battery_state(hass, "10")
        manager._state_changed(_state_event("sensor.battery", old_state, new_state))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        alert_id = "battery:sensor.battery"
        record = manager.records[alert_id]

        old_state = hass.states.get("sensor.battery")
        new_state = _battery_state(hass, "9")
        before = len(entry.created_task_names)
        manager._state_changed(_state_event("sensor.battery", old_state, new_state))
        assert len(entry.created_task_names) == before + 1
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert manager.records[alert_id] is record

        old_state = hass.states.get("sensor.battery")
        new_state = _battery_state(hass, "20")
        manager._state_changed(_state_event("sensor.battery", old_state, new_state))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert alert_id not in manager.records

    asyncio.run(scenario())


def test_identical_event_evaluates_when_record_exists(hass, entry):
    """The existing-record shortcut intentionally wins over duplicate filtering."""

    async def scenario():
        _battery_state(hass, "50")
        manager = AlertManager(hass, entry)
        await manager.async_setup()

        old_state = hass.states.get("sensor.battery")
        new_state = _battery_state(hass, "10")
        manager._state_changed(_state_event("sensor.battery", old_state, new_state))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        alert_id = "battery:sensor.battery"
        assert alert_id in manager.records

        old_state = hass.states.get("sensor.battery")
        new_state = _battery_state(hass, "10")
        before = len(entry.created_task_names)
        manager._state_changed(_state_event("sensor.battery", old_state, new_state))

        assert len(entry.created_task_names) == before + 1
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert alert_id in manager.records

    asyncio.run(scenario())


def test_tracking_lifecycle_does_not_evaluate_normal_unavailable_source(hass, entry):
    """Entity creation/removal updates tracked_count without candidate evaluation."""

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        initial_count = manager._tracked_count()
        evaluated: list[str] = []
        original_evaluate = manager.async_evaluate_entity

        async def tracked_evaluate(entity_id, **kwargs):
            evaluated.append(entity_id)
            return await original_evaluate(entity_id, **kwargs)

        manager.async_evaluate_entity = tracked_evaluate

        hass.states.set("sensor.lifecycle", "normal")
        normal = hass.states.get("sensor.lifecycle")
        manager._state_changed(_state_event("sensor.lifecycle", None, normal))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert manager._tracked_count() == initial_count + 1
        assert evaluated == []

        old_state = hass.states.get("sensor.lifecycle")
        manager._state_changed(_state_event("sensor.lifecycle", old_state, None))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert manager._tracked_count() == initial_count
        assert evaluated == []

    asyncio.run(scenario())


def test_tracking_recomputes_when_pack_applicability_changes(hass, entry):
    """State attributes still update tracking when pack applicability changes."""

    async def scenario():
        hass.states.set("sensor.dynamic", "50")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        manager.config["automatic"][unavailable.PACK.id]["enabled"] = False
        manager.config["automatic"][battery.PACK.id]["enabled"] = True
        manager._refresh_tracking()
        assert "sensor.dynamic" not in manager._automatic_tracked_entities

        old_state = hass.states.get("sensor.dynamic")
        hass.states.set("sensor.dynamic", "50", {ATTR_DEVICE_CLASS: "battery"})
        new_state = hass.states.get("sensor.dynamic")
        manager._state_changed(_state_event("sensor.dynamic", old_state, new_state))

        assert "sensor.dynamic" in manager._automatic_tracked_entities

    asyncio.run(scenario())


def test_same_primary_state_attribute_rule_is_not_filtered(hass, entry):
    """Pack filtering must not suppress custom rules driven by attribute changes."""

    async def scenario():
        hass.states.set("sensor.source", "on", {"health": "ok"})
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        created = await manager.async_create_rule(
            {
                "name": "Attribute health",
                "entity_ids": ["sensor.source"],
                "source": "attribute",
                "attribute": "health",
                "operator": "equals",
                "value": "error",
                "duration": 0,
            }
        )
        old_state = hass.states.get("sensor.source")
        hass.states.set("sensor.source", "on", {"health": "error"})
        new_state = hass.states.get("sensor.source")

        manager._state_changed(_state_event("sensor.source", old_state, new_state))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert f"rule:{created['id']}:sensor.source" in manager.records

    asyncio.run(scenario())


def test_entity_exclusion_only_applies_to_automatic_packs(hass, entry):
    """Explicit entity exclusions must not disable user-created custom rules."""

    async def scenario():
        _battery_state(hass, "10")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        manager.config["excluded_entities"] = ["sensor.battery"]
        manager._refresh_config_caches()
        created = await manager.async_create_rule(
            {
                "name": "Excluded battery custom rule",
                "entity_ids": ["sensor.battery"],
                "source": "state",
                "operator": "below",
                "value": 20,
                "duration": 0,
            }
        )

        assert f"rule:{created['id']}:sensor.battery" in manager.records
        assert "battery:sensor.battery" not in manager.records
        assert manager._custom_tracked_count == 1
        assert "sensor.battery" not in manager._automatic_tracked_entities

    asyncio.run(scenario())


def test_device_exclusion_only_applies_to_automatic_packs(
    hass, entry, registry_entry, device_entry
):
    """Explicit device exclusions must not disable custom rules on its entities."""

    async def scenario():
        device_id = "excluded-device"
        device_entry(hass, device_id=device_id)
        registry_entry(hass, "sensor.battery", device_id=device_id)
        _battery_state(hass, "10")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        manager.config["excluded_devices"] = [device_id]
        manager._refresh_config_caches()
        created = await manager.async_create_rule(
            {
                "name": "Excluded device custom rule",
                "entity_ids": ["sensor.battery"],
                "source": "state",
                "operator": "below",
                "value": 20,
                "duration": 0,
            }
        )

        assert f"rule:{created['id']}:sensor.battery" in manager.records
        assert "battery:sensor.battery" not in manager.records
        assert manager._custom_tracked_count == 1
        assert "sensor.battery" not in manager._automatic_tracked_entities

    asyncio.run(scenario())


def test_label_exclusion_only_applies_to_automatic_packs(hass, entry, registry_entry):
    """Excluded labels remain automatic-only and custom tracking stays intact."""

    async def scenario():
        registry_entry(hass, "sensor.battery", labels={"no-alert"})
        _battery_state(hass, "10")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        manager.config["excluded_labels"] = ["no-alert"]
        manager._refresh_config_caches()
        created = await manager.async_create_rule(
            {
                "name": "Excluded label custom rule",
                "entity_ids": ["sensor.battery"],
                "source": "state",
                "operator": "below",
                "value": 20,
                "duration": 0,
            }
        )

        assert f"rule:{created['id']}:sensor.battery" in manager.records
        assert "battery:sensor.battery" not in manager.records
        assert manager._custom_tracked_count == 1
        assert "sensor.battery" not in manager._automatic_tracked_entities

    asyncio.run(scenario())


def test_removed_entity_clears_pending_automatic_alert(hass, entry):
    """A removed entity resolves its pending automatic occurrence."""

    async def scenario():
        _battery_state(hass, "50")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        manager.config["automatic"]["battery"]["delay"] = 300

        old_state = hass.states.get("sensor.battery")
        low_state = _battery_state(hass, "10")
        manager._state_changed(_state_event("sensor.battery", old_state, low_state))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert "battery:sensor.battery" in manager.records
        assert manager.records["battery:sensor.battery"].status.value == "pending"

        removed_state = hass.states.data.pop("sensor.battery")
        manager._state_changed(_state_event("sensor.battery", removed_state, None))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert "battery:sensor.battery" not in manager.records

    asyncio.run(scenario())


def test_removed_entity_clears_acknowledged_automatic_alert(hass, entry):
    """A removed entity resolves an active acknowledged automatic occurrence."""

    async def scenario():
        _battery_state(hass, "50")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        manager.config["automatic"]["battery"]["delay"] = 0

        old_state = hass.states.get("sensor.battery")
        low_state = _battery_state(hass, "10")
        manager._state_changed(_state_event("sensor.battery", old_state, low_state))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        alert_id = "battery:sensor.battery"
        assert manager.records[alert_id].status.value == "active"
        await manager.async_acknowledge(alert_id, "test")
        assert manager.records[alert_id].acknowledged is True

        removed_state = hass.states.data.pop("sensor.battery")
        manager._state_changed(_state_event("sensor.battery", removed_state, None))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert alert_id not in manager.records
        assert any(item.id == alert_id for item in manager.history)

    asyncio.run(scenario())


def test_removed_entity_clears_custom_alert(hass, entry):
    """A removed source also resolves its existing custom-rule occurrence."""

    async def scenario():
        hass.states.set("sensor.source", "error")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        created = await manager.async_create_rule(
            {
                "name": "Removed custom source",
                "entity_ids": ["sensor.source"],
                "source": "state",
                "operator": "equals",
                "value": "error",
                "duration": 0,
            }
        )
        alert_id = f"rule:{created['id']}:sensor.source"
        assert alert_id in manager.records

        removed_state = hass.states.data.pop("sensor.source")
        manager._state_changed(_state_event("sensor.source", removed_state, None))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert alert_id not in manager.records

    asyncio.run(scenario())
