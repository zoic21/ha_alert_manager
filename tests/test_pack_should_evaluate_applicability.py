"""Automatic pack applicability filtering regressions."""

from __future__ import annotations

from homeassistant.core import State

from custom_components.alert_manager.packs.base import AutomaticPack


def _state(entity_id: str, value: str, attributes=None) -> State:
    return State(entity_id, value, attributes or {})


def test_should_evaluate_always_applies_new_state_first(hass):
    """Unrelated states stop before the pack-specific interest filter."""
    applies_calls = 0
    filter_calls = 0

    def applies(_hass, state):
        nonlocal applies_calls
        applies_calls += 1
        return state.entity_id.startswith("sensor.match_")

    def transition_filter(_hass, _new_state, _config):
        nonlocal filter_calls
        filter_calls += 1
        return True

    pack = AutomaticPack(
        id="test",
        translation_key="test",
        prerequisites=(),
        applies=applies,
        evaluate=lambda _hass, _state, _config: None,
        transition_filter=transition_filter,
    )

    assert not pack.should_evaluate(hass, _state("sensor.other", "on"), {})
    assert applies_calls == 1
    assert filter_calls == 0

    assert pack.should_evaluate(hass, _state("sensor.match_one", "on"), {})
    assert applies_calls == 2
    assert filter_calls == 1


def test_should_evaluate_ignores_missing_new_state(hass):
    """Record-free entity removal has nothing to evaluate."""
    calls = 0

    def applies(_hass, _state):
        nonlocal calls
        calls += 1
        return True

    pack = AutomaticPack(
        id="test",
        translation_key="test",
        prerequisites=(),
        applies=applies,
        evaluate=lambda _hass, _state, _config: None,
    )

    assert not pack.should_evaluate(hass, None, {})
    assert calls == 0


def test_should_evaluate_default_filter_accepts_applicable_state(hass):
    """Packs without a custom interest filter stay conservative."""
    pack = AutomaticPack(
        id="test",
        translation_key="test",
        prerequisites=(),
        applies=lambda _hass, state: state.entity_id.startswith("sensor.match_"),
        evaluate=lambda _hass, _state, _config: None,
    )

    assert not pack.should_evaluate(hass, _state("sensor.other", "on"), {})
    assert pack.should_evaluate(hass, _state("sensor.match_one", "on"), {})
