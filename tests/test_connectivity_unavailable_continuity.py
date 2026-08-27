"""Connectivity unavailable/reload continuity regressions."""

from __future__ import annotations

import asyncio

from homeassistant.const import ATTR_DEVICE_CLASS, STATE_UNAVAILABLE
from homeassistant.core import Event

from custom_components.alert_manager.packs import connectivity, unavailable
from custom_components.alert_manager.runtime_manager import AlertManager


def _state_event(entity_id, old_state, new_state):
    return Event(
        {
            "entity_id": entity_id,
            "old_state": old_state,
            "new_state": new_state,
        }
    )


def _connectivity_state(hass, value, *, attributes=None):
    attrs = {ATTR_DEVICE_CLASS: "connectivity"}
    if attributes is not None:
        attrs = attributes
    hass.states.set("binary_sensor.link", value, attrs)
    return hass.states.get("binary_sensor.link")


def _should_evaluate(pack, hass, old_state, new_state):
    return pack.should_evaluate(hass, old_state, new_state, {"enabled": True})


def test_connectivity_treats_unavailable_as_off(hass):
    """Off and unavailable are one logical connectivity failure."""
    on_state = _connectivity_state(hass, "on")
    off_state = _connectivity_state(hass, "off")
    unavailable_state = _connectivity_state(hass, STATE_UNAVAILABLE)

    assert _should_evaluate(connectivity.PACK, hass, on_state, off_state)
    assert not _should_evaluate(
        connectivity.PACK, hass, off_state, unavailable_state
    )
    assert not _should_evaluate(
        connectivity.PACK, hass, unavailable_state, off_state
    )
    assert _should_evaluate(connectivity.PACK, hass, unavailable_state, on_state)

    match = connectivity.PACK.evaluate(hass, unavailable_state, {"enabled": True})
    assert match is not None
    assert match.condition_key == "automatic.connectivity"


def test_connectivity_reload_survives_temporary_attribute_loss(hass):
    """A reload remains one failure even if unavailable temporarily loses metadata."""
    off_state = _connectivity_state(hass, "off")
    unavailable_without_attributes = _connectivity_state(
        hass, STATE_UNAVAILABLE, attributes={}
    )

    assert not _should_evaluate(
        connectivity.PACK, hass, off_state, unavailable_without_attributes
    )
    assert not _should_evaluate(
        unavailable.PACK, hass, off_state, unavailable_without_attributes
    )


def test_unavailable_still_handles_real_connectivity_failure_edges(hass):
    """Only off/unavailable churn is suppressed; normal unavailable edges remain."""
    on_state = _connectivity_state(hass, "on")
    unavailable_state = _connectivity_state(hass, STATE_UNAVAILABLE)

    assert _should_evaluate(unavailable.PACK, hass, on_state, unavailable_state)
    assert _should_evaluate(unavailable.PACK, hass, unavailable_state, on_state)


def test_connectivity_pending_survives_off_unavailable_off_reload(hass, entry):
    """A transient integration reload must not restart the connectivity timer."""

    async def scenario():
        _connectivity_state(hass, "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        manager.config["automatic"]["connectivity"]["delay"] = 300

        old_state = hass.states.get("binary_sensor.link")
        off_state = _connectivity_state(hass, "off")
        manager._state_changed(
            _state_event("binary_sensor.link", old_state, off_state)
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        alert_id = "connectivity:binary_sensor.link"
        assert alert_id in manager.records
        record = manager.records[alert_id]
        assert record.status.value == "pending"
        original_detected_at = record.detected_at
        original_due_at = record.due_at
        original_timer = manager._timers[alert_id]
        task_names = list(entry.created_task_names)

        unavailable_state = _connectivity_state(hass, STATE_UNAVAILABLE)
        manager._state_changed(
            _state_event("binary_sensor.link", off_state, unavailable_state)
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert entry.created_task_names == task_names
        assert manager.records[alert_id] is record
        assert record.detected_at == original_detected_at
        assert record.due_at == original_due_at
        assert manager._timers[alert_id] is original_timer
        assert "unavailable:binary_sensor.link" not in manager.records

        off_again = _connectivity_state(hass, "off")
        manager._state_changed(
            _state_event("binary_sensor.link", unavailable_state, off_again)
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert entry.created_task_names == task_names
        assert manager.records[alert_id] is record
        assert record.detected_at == original_detected_at
        assert record.due_at == original_due_at
        assert manager._timers[alert_id] is original_timer
        assert "unavailable:binary_sensor.link" not in manager.records

    asyncio.run(scenario())
