"""UniFi unavailable-state neutrality regressions."""

from __future__ import annotations

import asyncio

from homeassistant.const import STATE_HOME, STATE_UNAVAILABLE
from homeassistant.core import Event

from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.packs import PackNeutral, unifi

_ENTITY_ID = "device_tracker.unifi_client"
_ATTRIBUTES = {"source_type": "router"}


def _event(old_state, new_state):
    return Event(
        {"entity_id": _ENTITY_ID, "old_state": old_state, "new_state": new_state}
    )


def _state(hass, value, *, attributes=None):
    attrs = _ATTRIBUTES if attributes is None else attributes
    hass.states.set(_ENTITY_ID, value, attrs)
    return hass.states.get(_ENTITY_ID)


def test_unifi_returns_neutral_for_unavailable(hass, registry_entry):
    """Home and away are interesting; unavailable is explicitly neutral."""
    registry_entry(hass, _ENTITY_ID, platform="unifi")
    home = _state(hass, STATE_HOME)
    away = _state(hass, "not_home")
    unavailable = _state(hass, STATE_UNAVAILABLE)
    config = {"enabled": True}

    assert unifi.PACK.should_evaluate(hass, home, config)
    assert unifi.PACK.should_evaluate(hass, away, config)
    assert not unifi.PACK.should_evaluate(hass, unavailable, config)
    assert isinstance(unifi.PACK.evaluate(hass, unavailable, config), PackNeutral)


def test_unifi_pending_survives_away_unavailable_then_resolves_home(
    hass, entry, registry_entry, config_entry
):
    """An existing away occurrence survives unavailable with its original timer."""

    async def scenario():
        registry_entry(hass, _ENTITY_ID, platform="unifi")
        config_entry(hass, "unifi")
        home = _state(hass, STATE_HOME)
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        manager.config["automatic"]["unifi"]["enabled"] = True
        manager.config["automatic"]["unifi"]["delay"] = 300
        manager.config["automatic"]["unavailable"]["enabled"] = True
        manager.config["automatic"]["unavailable"]["delay"] = 300

        away = _state(hass, "not_home")
        manager._state_changed(_event(home, away))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        unifi_id = f"unifi:{_ENTITY_ID}"
        unavailable_id = f"unavailable:{_ENTITY_ID}"
        record = manager.records[unifi_id]
        detected_at = record.detected_at
        due_at = record.due_at
        timer = manager._timers[unifi_id]

        unavailable = _state(hass, STATE_UNAVAILABLE, attributes={})
        manager._state_changed(_event(away, unavailable))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert manager.records[unifi_id] is record
        assert record.detected_at == detected_at
        assert record.due_at == due_at
        assert manager._timers[unifi_id] is timer
        assert unavailable_id in manager.records

        home_again = _state(hass, STATE_HOME)
        manager._state_changed(_event(unavailable, home_again))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert unifi_id not in manager.records
        assert unavailable_id not in manager.records

    asyncio.run(scenario())


def test_unifi_home_unavailable_home_never_opens_alert(
    hass, entry, registry_entry, config_entry
):
    """Unavailable cannot turn a home UniFi tracker into an away alert."""

    async def scenario():
        registry_entry(hass, _ENTITY_ID, platform="unifi")
        config_entry(hass, "unifi")
        home = _state(hass, STATE_HOME)
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        manager.config["automatic"]["unifi"]["enabled"] = True
        manager.config["automatic"]["unavailable"]["enabled"] = True

        unavailable = _state(hass, STATE_UNAVAILABLE, attributes={})
        manager._state_changed(_event(home, unavailable))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert f"unifi:{_ENTITY_ID}" not in manager.records
        assert f"unavailable:{_ENTITY_ID}" in manager.records

        home_again = _state(hass, STATE_HOME)
        manager._state_changed(_event(unavailable, home_again))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert f"unifi:{_ENTITY_ID}" not in manager.records
        assert f"unavailable:{_ENTITY_ID}" not in manager.records

    asyncio.run(scenario())


def test_unifi_unavailable_then_away_opens_on_definitive_away(
    hass, entry, registry_entry, config_entry
):
    """Away starts only when the post-unavailable state is definitively away."""

    async def scenario():
        registry_entry(hass, _ENTITY_ID, platform="unifi")
        config_entry(hass, "unifi")
        home = _state(hass, STATE_HOME)
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        manager.config["automatic"]["unifi"]["enabled"] = True
        manager.config["automatic"]["unavailable"]["enabled"] = True

        unavailable = _state(hass, STATE_UNAVAILABLE, attributes={})
        manager._state_changed(_event(home, unavailable))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert f"unifi:{_ENTITY_ID}" not in manager.records

        away = _state(hass, "not_home")
        manager._state_changed(_event(unavailable, away))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert f"unifi:{_ENTITY_ID}" in manager.records
        assert f"unavailable:{_ENTITY_ID}" not in manager.records

    asyncio.run(scenario())
