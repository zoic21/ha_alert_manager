"""Connectivity automatic pack."""

from __future__ import annotations

from typing import Any

from homeassistant.const import ATTR_DEVICE_CLASS, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State

from ..const import CATEGORY_CONNECTIVITY
from .base import AutomaticPack, PackMatch

_FAILURE_STATES = frozenset(("off", STATE_UNAVAILABLE))


def _applies(_hass: HomeAssistant, state: State) -> bool:
    """Return whether the state is a connectivity binary sensor."""
    return (
        state.entity_id.partition(".")[0] == "binary_sensor"
        and state.attributes.get(ATTR_DEVICE_CLASS) == "connectivity"
    )


def _matches(hass: HomeAssistant, state: State | None) -> bool:
    """Treat off and unavailable as the same connectivity failure."""
    return state is not None and _applies(hass, state) and state.state in _FAILURE_STATES


def _is_same_failure_transition(
    hass: HomeAssistant, old_state: State | None, new_state: State | None
) -> bool:
    """Keep transient off/unavailable changes inside one failure occurrence."""
    if old_state is None or new_state is None:
        return False
    if {old_state.state, new_state.state} != _FAILURE_STATES:
        return False
    # Some integrations briefly expose fewer attributes while reloading. The
    # previous state is enough to identify the entity as a connectivity sensor.
    return _applies(hass, old_state) or _applies(hass, new_state)


def _should_evaluate(
    hass: HomeAssistant,
    old_state: State | None,
    new_state: State | None,
    _config: dict[str, Any],
) -> bool:
    """Evaluate only when the logical connectivity failure changes."""
    if _is_same_failure_transition(hass, old_state, new_state):
        return False
    return _matches(hass, old_state) != _matches(hass, new_state)


def _evaluate(
    _hass: HomeAssistant, state: State, _config: dict[str, Any]
) -> PackMatch | None:
    """Match connectivity binary sensors that are off or unavailable."""
    if not _applies(_hass, state) or state.state not in _FAILURE_STATES:
        return None
    return PackMatch(
        condition_key="automatic.connectivity",
    )


PACK = AutomaticPack(
    id=CATEGORY_CONNECTIVITY,
    translation_key="connectivity",
    prerequisites=(),
    applies=_applies,
    evaluate=_evaluate,
    transition_filter=_should_evaluate,
)
