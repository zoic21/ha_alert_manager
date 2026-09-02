"""Connectivity unavailable/reload continuity regressions."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from homeassistant.const import ATTR_DEVICE_CLASS, STATE_UNAVAILABLE
from homeassistant.core import Event

from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.packs import PackNeutral, connectivity, unavailable


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


def _should(pack, hass, new_state):
    callback = pack.should_evaluate
    assert callback is not None
    return callback(hass, None, new_state, {"enabled": True})


def test_connectivity_returns_neutral_for_unavailable(hass):
    """Filtering ignores unavailable while evaluate explicitly marks it neutral."""
    on_state = _state(hass, "on")
    off_state = _state(hass, "off")
    unavailable_state = _state(hass, STATE_UNAVAILABLE)

    assert _should(connectivity.PACK, hass, on_state)
    assert _should(connectivity.PACK, hass, off_state)
    assert not _should(connectivity.PACK, hass, unavailable_state)

    evaluation = connectivity.PACK.evaluate(hass, unavailable_state, {"enabled": True})
    assert isinstance(evaluation, PackNeutral)


def test_connectivity_reload_survives_temporary_attribute_loss(hass):
    """Registry metadata preserves connectivity identity during reloads."""
    hass.entity_registry.entries["binary_sensor.link"] = SimpleNamespace(
        original_device_class="connectivity"
    )
    unavailable_state = _state(hass, STATE_UNAVAILABLE, attributes={})

    assert not _should(connectivity.PACK, hass, unavailable_state)
    assert _should(unavailable.PACK, hass, unavailable_state)
    evaluation = connectivity.PACK.evaluate(hass, unavailable_state, {"enabled": True})
    assert isinstance(evaluation, PackNeutral)


def test_unavailable_still_handles_real_connectivity_failure_edges(hass):
    """Unavailable remains independent from connectivity status."""
    on_state = _state(hass, "on")
    unavailable_state = _state(hass, STATE_UNAVAILABLE)

    assert _should(unavailable.PACK, hass, unavailable_state)
    assert not _should(unavailable.PACK, hass, on_state)


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


def test_connectivity_on_unavailable_on_never_opens_alert(hass, entry):
    """Unavailable cannot turn a healthy connectivity sensor into a failure."""

    async def scenario():
        on_state = _state(hass, "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        manager.config["automatic"]["unavailable"]["enabled"] = True

        unavailable_state = _state(hass, STATE_UNAVAILABLE)
        manager._state_changed(
            _event("binary_sensor.link", on_state, unavailable_state)
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert "connectivity:binary_sensor.link" not in manager.records
        assert "unavailable:binary_sensor.link" in manager.records

        on_again = _state(hass, "on")
        manager._state_changed(
            _event("binary_sensor.link", unavailable_state, on_again)
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert "connectivity:binary_sensor.link" not in manager.records
        assert "unavailable:binary_sensor.link" not in manager.records

    asyncio.run(scenario())


def test_connectivity_unavailable_then_off_opens_on_definitive_off(hass, entry):
    """A failure starts only when the post-unavailable state is definitively off."""

    async def scenario():
        on_state = _state(hass, "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        manager.config["automatic"]["unavailable"]["enabled"] = True

        unavailable_state = _state(hass, STATE_UNAVAILABLE)
        manager._state_changed(
            _event("binary_sensor.link", on_state, unavailable_state)
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert "connectivity:binary_sensor.link" not in manager.records

        off_state = _state(hass, "off")
        manager._state_changed(
            _event("binary_sensor.link", unavailable_state, off_state)
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert "connectivity:binary_sensor.link" in manager.records
        assert "unavailable:binary_sensor.link" not in manager.records

    asyncio.run(scenario())
