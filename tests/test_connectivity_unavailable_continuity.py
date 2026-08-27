"""Connectivity unavailable/reload continuity regressions."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from homeassistant.const import ATTR_DEVICE_CLASS, STATE_UNAVAILABLE
from homeassistant.core import Event

from custom_components.alert_manager.packs import connectivity, unavailable
from custom_components.alert_manager.runtime_manager import AlertManager


def _event(entity_id, old_state, new_state):
    return Event(
        {"entity_id": entity_id, "old_state": old_state, "new_state": new_state}
    )


def _state(hass, value, *, attributes=None):
    attrs = {ATTR_DEVICE_CLASS: "connectivity"}
    if attributes is not None:
        attrs = attributes
    hass.states.set("binary_sensor.link", value, attrs)
    return hass.states.get("binary_sensor.link")


def _should(pack, hass, old_state, new_state):
    return pack.should_evaluate(hass, old_state, new_state, {"enabled": True})


def test_connectivity_treats_unavailable_as_off(hass):
    """Off and unavailable are one logical connectivity failure."""
    on_state = _state(hass, "on")
    off_state = _state(hass, "off")
    unavailable_state = _state(hass, STATE_UNAVAILABLE)

    assert _should(connectivity.PACK, hass, on_state, off_state)
    assert not _should(connectivity.PACK, hass, off_state, unavailable_state)
    assert not _should(connectivity.PACK, hass, unavailable_state, off_state)
    assert _should(connectivity.PACK, hass, unavailable_state, on_state)

    match = connectivity.PACK.evaluate(hass, unavailable_state, {"enabled": True})
    assert match is not None
    assert match.condition_key == "automatic.connectivity"


def test_connectivity_reload_survives_temporary_attribute_loss(hass):
    """Registry metadata preserves connectivity identity during reloads."""
    hass.entity_registry.entries["binary_sensor.link"] = SimpleNamespace(
        original_device_class="connectivity"
    )
    off_state = _state(hass, "off")
    unavailable_state = _state(hass, STATE_UNAVAILABLE, attributes={})

    assert not _should(connectivity.PACK, hass, off_state, unavailable_state)
    assert _should(unavailable.PACK, hass, off_state, unavailable_state)
    assert (
        connectivity.PACK.evaluate(hass, unavailable_state, {"enabled": True})
        is not None
    )


def test_unavailable_still_handles_real_connectivity_failure_edges(hass):
    """Unavailable remains independent from the connectivity failure state."""
    on_state = _state(hass, "on")
    unavailable_state = _state(hass, STATE_UNAVAILABLE)

    assert _should(unavailable.PACK, hass, on_state, unavailable_state)
    assert _should(unavailable.PACK, hass, unavailable_state, on_state)


def test_connectivity_pending_survives_off_unavailable_off_reload(hass, entry):
    """Connectivity keeps its timer while unavailable owns a separate alert."""

    async def scenario():
        _state(hass, "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        manager.config["automatic"]["connectivity"]["delay"] = 300
        manager.config["automatic"]["unavailable"]["enabled"] = True
        manager.config["automatic"]["unavailable"]["delay"] = 300

        old_state = hass.states.get("binary_sensor.link")
        off_state = _state(hass, "off")
        manager._state_changed(_event("binary_sensor.link", old_state, off_state))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        connectivity_id = "connectivity:binary_sensor.link"
        unavailable_id = "unavailable:binary_sensor.link"
        assert connectivity_id in manager.records
        record = manager.records[connectivity_id]
        assert record.status.value == "pending"
        detected_at = record.detected_at
        due_at = record.due_at
        timer = manager._timers[connectivity_id]

        unavailable_state = _state(hass, STATE_UNAVAILABLE)
        manager._state_changed(
            _event("binary_sensor.link", off_state, unavailable_state)
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert manager.records[connectivity_id] is record
        assert record.detected_at == detected_at
        assert record.due_at == due_at
        assert manager._timers[connectivity_id] is timer
        assert unavailable_id in manager.records
        assert manager.records[unavailable_id] is not record

        off_again = _state(hass, "off")
        manager._state_changed(
            _event("binary_sensor.link", unavailable_state, off_again)
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert manager.records[connectivity_id] is record
        assert record.detected_at == detected_at
        assert record.due_at == due_at
        assert manager._timers[connectivity_id] is timer
        assert unavailable_id not in manager.records

    asyncio.run(scenario())
