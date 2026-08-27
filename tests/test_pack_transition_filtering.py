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
    """Unavailable ignores ordinary churn and handles its own state edges."""
    normal = hass.states.set("sensor.source", "1")
    changed = hass.states.set("sensor.source", "2")
    unavailable_state = hass.states.set("sensor.source", "unavailable")
    config = {"enabled": True}

    assert unavailable.PACK.should_evaluate(hass, normal, changed, config) is False
    assert (
        unavailable.PACK.should_evaluate(hass, changed, unavailable_state, config) is True
    )
    assert (
        unavailable.PACK.should_evaluate(hass, unavailable_state, changed, config) is True
    )
    assert unavailable.PACK.should_evaluate(hass, None, normal, config) is True
    assert unavailable.PACK.should_evaluate(hass, normal, None, config) is True


def test_connectivity_pack_only_keeps_relevant_edges(hass):
    """Connectivity ignores on-to-on changes but keeps off crossings."""
    attributes = {ATTR_DEVICE_CLASS: "connectivity"}
    on_old = hass.states.set("binary_sensor.link", "on", attributes)
    on_new = hass.states.set("binary_sensor.link", "on", attributes)
    off = hass.states.set("binary_sensor.link", "off", attributes)
    config = {"enabled": True}

    assert connectivity.PACK.should_evaluate(hass, on_old, on_new, config) is False
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

    old_state = _battery_state(hass, "40")
    new_state = _battery_state(hass, "35")
    assert battery.PACK.should_evaluate(hass, old_state, new_state, config) is False

    old_state = _battery_state(hass, "31")
    new_state = _battery_state(hass, "30")
    assert battery.PACK.should_evaluate(hass, old_state, new_state, config) is True

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
