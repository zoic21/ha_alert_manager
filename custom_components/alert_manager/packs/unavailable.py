"""Unavailable entity automatic pack."""

from __future__ import annotations

from typing import Any

from homeassistant.const import ATTR_DEVICE_CLASS, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State

from ..const import CATEGORY_UNAVAILABLE
from .base import AutomaticPack, PackMatch


def _applies(_hass: HomeAssistant, _state: State) -> bool:
    """Monitor every eligible Home Assistant entity."""
    return True


def _matches(state: State | None) -> bool:
    """Return whether the optional state currently matches this pack."""
    return state is not None and state.state == STATE_UNAVAILABLE


def _is_connectivity_state(state: State | None) -> bool:
    """Return whether a state belongs to a connectivity binary sensor."""
    return bool(
        state is not None
        and state.entity_id.partition(".")[0] == "binary_sensor"
        and state.attributes.get(ATTR_DEVICE_CLASS) == "connectivity"
    )


def _is_connectivity_failure_reload(
    old_state: State | None, new_state: State | None
) -> bool:
    """Treat off/unavailable churn as one continuous connectivity failure."""
    if old_state is None or new_state is None:
        return False
    if {old_state.state, new_state.state} != {"off", STATE_UNAVAILABLE}:
        return False
    return _is_connectivity_state(old_state) or _is_connectivity_state(new_state)


def _should_evaluate(
    _hass: HomeAssistant,
    old_state: State | None,
    new_state: State | None,
    _config: dict[str, Any],
) -> bool:
    """Evaluate only transitions into or out of unavailable."""
    # A connectivity sensor that was already off did not recover just because
    # its integration briefly reports unavailable while reloading. Avoid an
    # entity re-evaluation here so the existing connectivity occurrence keeps
    # its original detection time, pending timer and notification lifecycle.
    if _is_connectivity_failure_reload(old_state, new_state):
        return False
    return _matches(old_state) != _matches(new_state)


def _evaluate(
    _hass: HomeAssistant, state: State, _config: dict[str, Any]
) -> PackMatch | None:
    """Match only unavailable, for every entity domain."""
    if state.state != STATE_UNAVAILABLE:
        return None
    return PackMatch(
        condition_key="automatic.unavailable",
    )


PACK = AutomaticPack(
    id=CATEGORY_UNAVAILABLE,
    translation_key="unavailable",
    prerequisites=(),
    applies=_applies,
    evaluate=_evaluate,
    transition_filter=_should_evaluate,
)
