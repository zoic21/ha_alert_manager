"""Automatic pack applicability filtering regressions."""

from __future__ import annotations

from homeassistant.core import State

from custom_components.alert_manager.packs.base import AutomaticPack


def _state(entity_id: str, value: str) -> State:
    return State(entity_id, value)


def test_should_evaluate_skips_filter_when_neither_state_applies(hass):
    """Transitions unrelated to a pack stop before its business filter."""
    calls = 0

    def applies(_hass, state):
        return state.entity_id.startswith("sensor.match_")

    def transition_filter(_hass, _old_state, _new_state, _config):
        nonlocal calls
        calls += 1
        return True

    pack = AutomaticPack(
        id="test",
        translation_key="test",
        prerequisites=(),
        applies=applies,
        evaluate=lambda _hass, _state, _config: None,
        transition_filter=transition_filter,
    )

    assert not pack.should_evaluate(
        hass,
        _state("sensor.other", "on"),
        _state("sensor.other", "off"),
        {},
    )
    assert calls == 0


def test_should_evaluate_keeps_resolution_when_only_old_state_applies(hass):
    """Leaving a pack still reaches its filter so stale alerts can resolve."""
    calls = 0

    def applies(_hass, state):
        return state.attributes.get("tracked") is True

    def transition_filter(_hass, old_state, new_state, _config):
        nonlocal calls
        calls += 1
        return bool(old_state and old_state.attributes.get("tracked")) and not bool(
            new_state and new_state.attributes.get("tracked")
        )

    pack = AutomaticPack(
        id="test",
        translation_key="test",
        prerequisites=(),
        applies=applies,
        evaluate=lambda _hass, _state, _config: None,
        transition_filter=transition_filter,
    )

    old_state = State("sensor.example", "10", {"tracked": True})
    new_state = State("sensor.example", "10", {})

    assert pack.should_evaluate(hass, old_state, new_state, {})
    assert calls == 1


def test_should_evaluate_default_filter_uses_central_applicability(hass):
    """Packs without a custom filter evaluate only when one side belongs to them."""
    pack = AutomaticPack(
        id="test",
        translation_key="test",
        prerequisites=(),
        applies=lambda _hass, state: state.entity_id.startswith("sensor.match_"),
        evaluate=lambda _hass, _state, _config: None,
    )

    unrelated = _state("sensor.other", "on")
    matched = _state("sensor.match_one", "on")

    assert not pack.should_evaluate(hass, unrelated, unrelated, {})
    assert pack.should_evaluate(hass, None, matched, {})
    assert pack.should_evaluate(hass, matched, None, {})
