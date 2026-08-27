"""Unavailable entity automatic pack."""

from __future__ import annotations

from typing import Any

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State

from ..const import CATEGORY_UNAVAILABLE
from .base import AutomaticPack, PackMatch


def _applies(_hass: HomeAssistant, _state: State) -> bool:
    """Monitor every eligible Home Assistant entity."""
    return True


def _matches(state: State | None) -> bool:
    """Return whether the optional state currently matches this pack."""
    return state is not None and state.state == STATE_UNAVAILABLE


def _should_evaluate(
    _hass: HomeAssistant,
    old_state: State | None,
    new_state: State | None,
    _config: dict[str, Any],
) -> bool:
    """Evaluate only transitions into or out of unavailable."""
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
