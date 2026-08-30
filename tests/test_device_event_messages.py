"""Device alert event message fallback tests."""

from __future__ import annotations

import asyncio

from custom_components.alert_manager.const import EVENT_DEVICE_ALERT_STARTED
from custom_components.alert_manager.manager import AlertManager


def run(coroutine):
    return asyncio.run(coroutine)


def make_manager(hass, entry):
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    return manager


def fire_device_event_timers(hass):
    """Run every pending device-event debounce timer."""
    for timer in list(hass.timers):
        if timer["cancelled"]:
            continue
        if "_schedule_device_event_timer" not in timer["action"].__qualname__:
            continue
        timer["action"](timer["point"])


def test_device_event_uses_rule_name_only_when_message_is_empty(
    hass, entry, registry_entry, device_entry
):
    """Event messages fall back per alert without changing the public snapshot."""
    device = device_entry(hass, name="Baie")
    registry_entry(hass, "sensor.rack", device_id=device.id)
    hass.states.set("sensor.rack", "hot")
    manager = make_manager(hass, entry)

    run(
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
    run(
        manager.async_create_rule(
            {
                "name": "Ventilation",
                "entity_ids": ["sensor.rack"],
                "operator": "equals",
                "value": "hot",
                "duration": 0,
            }
        )
    )

    device_snapshot = manager.public_snapshot()["active_devices"][0]
    assert device_snapshot["messages"] == ["Rack hot"]
    assert device_snapshot["rules"] == ["Temperature", "Ventilation"]

    fire_device_event_timers(hass)
    events = [
        data for event, data in hass.bus.fired if event == EVENT_DEVICE_ALERT_STARTED
    ]

    assert len(events) == 1
    assert events[0]["messages"] == ["Rack hot", "Ventilation"]
    assert events[0]["rules"] == ["Temperature", "Ventilation"]
