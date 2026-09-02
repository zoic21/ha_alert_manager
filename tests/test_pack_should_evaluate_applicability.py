"""Automatic pack should-evaluate callback regressions."""

from __future__ import annotations

from homeassistant.core import State

from custom_components.alert_manager.packs.base import AutomaticPack


def _state(entity_id: str, value: str, attributes=None) -> State:
    return State(entity_id, value, attributes or {})


def test_should_evaluate_receives_the_complete_transition(hass):
    """The optional callback receives both states and the pack configuration."""
    received = None

    def should_evaluate(_hass, old_state, new_state, config):
        nonlocal received
        received = (old_state, new_state, config)
        return True

    pack = AutomaticPack(
        id="test",
        translation_key="test",
        prerequisites=(),
        applies=lambda _hass, state: state.entity_id.startswith("sensor.match_"),
        evaluate=lambda _hass, _state, _config: None,
        should_evaluate=should_evaluate,
    )
    old_state = _state("sensor.match_one", "off")
    new_state = _state("sensor.match_one", "on")
    config = {"enabled": True}

    assert pack.should_evaluate is not None
    assert pack.should_evaluate(hass, old_state, new_state, config)
    assert received == (old_state, new_state, config)


def test_should_evaluate_is_optional():
    """Packs without a custom callback use the runtime's default path."""
    pack = AutomaticPack(
        id="test",
        translation_key="test",
        prerequisites=(),
        applies=lambda _hass, _state: True,
        evaluate=lambda _hass, _state, _config: None,
    )

    assert pack.should_evaluate is None
