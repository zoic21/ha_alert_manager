"""Automatic pack record/applicability filtering regressions."""

from __future__ import annotations

from homeassistant.core import State

from custom_components.alert_manager.packs.base import AutomaticPack


def _state(entity_id: str, value: str, attributes=None) -> State:
    return State(entity_id, value, attributes or {})


def test_should_evaluate_skips_filter_when_new_state_does_not_apply(hass):
    """An unrelated new state with no record stops before the business filter."""
    calls = 0

    def applies(_hass, state):
        return state.entity_id.startswith("sensor.match_")

    def transition_filter(_hass, _new_state, _config, _record_exists):
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
        _state("sensor.other", "off"),
        {},
        record_exists=False,
    )
    assert calls == 0


def test_should_evaluate_resolves_record_when_new_state_no_longer_applies(hass):
    """A stored occurrence is enough to evaluate when its new state leaves the pack."""
    calls = 0

    def applies(_hass, state):
        return state.attributes.get("tracked") is True

    def transition_filter(_hass, _new_state, _config, _record_exists):
        nonlocal calls
        calls += 1
        return False

    pack = AutomaticPack(
        id="test",
        translation_key="test",
        prerequisites=(),
        applies=applies,
        evaluate=lambda _hass, _state, _config: None,
        transition_filter=transition_filter,
    )

    new_state = _state("sensor.example", "10")

    assert pack.should_evaluate(hass, new_state, {}, record_exists=True)
    assert calls == 0


def test_should_evaluate_default_filter_uses_record_and_new_state(hass):
    """Default packs use applicability plus record existence without old state."""
    pack = AutomaticPack(
        id="test",
        translation_key="test",
        prerequisites=(),
        applies=lambda _hass, state: state.entity_id.startswith("sensor.match_"),
        evaluate=lambda _hass, _state, _config: None,
    )

    unrelated = _state("sensor.other", "on")
    matched = _state("sensor.match_one", "on")

    assert not pack.should_evaluate(hass, unrelated, {}, record_exists=False)
    assert pack.should_evaluate(hass, matched, {}, record_exists=False)
    assert pack.should_evaluate(hass, unrelated, {}, record_exists=True)
    assert not pack.should_evaluate(hass, None, {}, record_exists=False)
    assert pack.should_evaluate(hass, None, {}, record_exists=True)


def test_should_evaluate_neutral_state_never_changes_record(hass):
    """Neutral states preserve both an existing occurrence and the absence of one."""
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
        neutral_states=frozenset(("unavailable",)),
    )
    neutral = _state("sensor.example", "unavailable")

    assert not pack.should_evaluate(hass, neutral, {}, record_exists=False)
    assert not pack.should_evaluate(hass, neutral, {}, record_exists=True)
    assert calls == 0
