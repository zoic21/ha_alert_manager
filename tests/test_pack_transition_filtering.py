"""Automatic-pack transition filtering regression tests."""

from __future__ import annotations

import asyncio

from homeassistant.const import ATTR_DEVICE_CLASS
from homeassistant.core import Event

from custom_components.alert_manager.packs import battery, connectivity, unavailable
from custom_components.alert_manager.runtime_manager import AlertManager


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


def test_unavailable_pack_owns_transition_filtering(hass):
    """Unavailable treats missing/normal states alike and keeps alert edges."""
    normal = hass.states.set("sensor.source", "1")
    changed = hass.states.set("sensor.source", "2")
    unavailable_state = hass.states.set("sensor.source", "unavailable")
    config = {"enabled": True}

    assert unavailable.PACK.should_evaluate(hass, normal, changed, config) is False
    assert unavailable.PACK.should_evaluate(hass, None, normal, config) is False
    assert unavailable.PACK.should_evaluate(hass, normal, None, config) is False
    assert unavailable.PACK.should_evaluate(hass, None, unavailable_state, config)
    assert unavailable.PACK.should_evaluate(hass, unavailable_state, None, config)
    assert unavailable.PACK.should_evaluate(hass, changed, unavailable_state, config)
    assert unavailable.PACK.should_evaluate(hass, unavailable_state, changed, config)


def test_connectivity_pack_only_keeps_relevant_edges(hass):
    """Connectivity evaluates only transitions into or out of its off match."""
    attributes = {ATTR_DEVICE_CLASS: "connectivity"}
    on_old = hass.states.set("binary_sensor.link", "on", attributes)
    on_new = hass.states.set("binary_sensor.link", "on", attributes)
    off = hass.states.set("binary_sensor.link", "off", attributes)
    config = {"enabled": True}

    assert connectivity.PACK.should_evaluate(hass, on_old, on_new, config) is False
    assert connectivity.PACK.should_evaluate(hass, None, on_new, config) is False
    assert connectivity.PACK.should_evaluate(hass, on_new, None, config) is False
    assert connectivity.PACK.should_evaluate(hass, None, off, config) is True
    assert connectivity.PACK.should_evaluate(hass, off, None, config) is True
    assert connectivity.PACK.should_evaluate(hass, on_new, off, config) is True
    assert connectivity.PACK.should_evaluate(hass, off, on_new, config) is True


def test_battery_filter_uses_per_device_threshold(hass, registry_entry):
    """Battery transitions use the configured device threshold, not the global one."""
    device_id = "battery-device"
    registry_entry(hass, "sensor.battery", device_id=device_id)
    config = {
        "enabled": True,
        "threshold": 15,
        "device_thresholds": {device_id: 30},
    }

    high = _battery_state(hass, "40")
    assert battery.PACK.should_evaluate(hass, None, high, config) is False
    assert battery.PACK.should_evaluate(hass, high, None, config) is False

    old_state = _battery_state(hass, "40")
    new_state = _battery_state(hass, "35")
    assert battery.PACK.should_evaluate(hass, old_state, new_state, config) is False

    old_state = _battery_state(hass, "31")
    new_state = _battery_state(hass, "30")
    assert battery.PACK.should_evaluate(hass, old_state, new_state, config) is True
    assert battery.PACK.should_evaluate(hass, None, new_state, config) is True
    assert battery.PACK.should_evaluate(hass, new_state, None, config) is True

    old_state = _battery_state(hass, "30")
    new_state = _battery_state(hass, "29")
    assert battery.PACK.should_evaluate(hass, old_state, new_state, config) is False

    old_state = _battery_state(hass, "29")
    new_state = _battery_state(hass, "31")
    assert battery.PACK.should_evaluate(hass, old_state, new_state, config) is True


def test_battery_threshold_cache_follows_config_and_device_changes(
    hass, registry_entry
):
    """Cached thresholds cannot survive a changed override or device assignment."""
    battery._cached_effective_threshold.cache_clear()
    registry = registry_entry(hass, "sensor.battery", device_id="device-a")
    config = {
        "enabled": True,
        "threshold": 15,
        "device_thresholds": {"device-a": 30, "device-b": 50},
    }
    state = _battery_state(hass, "40")

    assert battery.PACK.evaluate(hass, state, config) is None
    first_info = battery._cached_effective_threshold.cache_info()
    assert battery.PACK.evaluate(hass, state, config) is None
    second_info = battery._cached_effective_threshold.cache_info()
    assert second_info.hits == first_info.hits + 1

    config["device_thresholds"]["device-a"] = 45
    match = battery.PACK.evaluate(hass, state, config)
    assert match is not None
    assert match.condition_params == {"threshold": "45"}

    config["device_thresholds"]["device-a"] = 30
    registry.device_id = "device-b"
    match = battery.PACK.evaluate(hass, state, config)
    assert match is not None
    assert match.condition_params == {"threshold": "50"}


def test_runtime_battery_filter_respects_device_override(hass, entry, registry_entry):
    """Queue battery work only when the effective device threshold crosses."""

    async def scenario():
        device_id = "battery-device"
        registry_entry(hass, "sensor.battery", device_id=device_id)
        _battery_state(hass, "40")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        manager.config["automatic"]["battery"]["device_thresholds"] = {device_id: 30}

        old_state = _battery_state(hass, "40")
        new_state = _battery_state(hass, "35")
        before = list(entry.created_task_names)
        manager._state_changed(_state_event("sensor.battery", old_state, new_state))
        assert entry.created_task_names == before

        old_state = _battery_state(hass, "31")
        new_state = _battery_state(hass, "30")
        manager._state_changed(_state_event("sensor.battery", old_state, new_state))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert "battery:sensor.battery" in manager.records

    asyncio.run(scenario())


def test_existing_battery_record_still_uses_transition_filter(hass, entry):
    """An existing occurrence does not force evaluation while it remains matching."""

    async def scenario():
        _battery_state(hass, "50")
        manager = AlertManager(hass, entry)
        await manager.async_setup()

        old_state = hass.states.get("sensor.battery")
        new_state = _battery_state(hass, "10")
        manager._state_changed(_state_event("sensor.battery", old_state, new_state))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert "battery:sensor.battery" in manager.records

        old_state = hass.states.get("sensor.battery")
        new_state = _battery_state(hass, "9")
        before = list(entry.created_task_names)
        manager._state_changed(_state_event("sensor.battery", old_state, new_state))
        assert entry.created_task_names == before
        assert manager._evaluation_flush_scheduled is False

        old_state = hass.states.get("sensor.battery")
        new_state = _battery_state(hass, "20")
        manager._state_changed(_state_event("sensor.battery", old_state, new_state))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert "battery:sensor.battery" not in manager.records

    asyncio.run(scenario())


def test_identical_automatic_event_skips_existing_alert_evaluation(hass, entry):
    """Exact duplicate events stay filtered even after an automatic alert exists."""

    async def scenario():
        _battery_state(hass, "50")
        manager = AlertManager(hass, entry)
        await manager.async_setup()

        old_state = hass.states.get("sensor.battery")
        new_state = _battery_state(hass, "10")
        manager._state_changed(_state_event("sensor.battery", old_state, new_state))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert "battery:sensor.battery" in manager.records

        old_state = hass.states.get("sensor.battery")
        new_state = _battery_state(hass, "10")
        before = list(entry.created_task_names)
        manager._state_changed(_state_event("sensor.battery", old_state, new_state))

        assert entry.created_task_names == before
        assert manager._evaluation_flush_scheduled is False

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
