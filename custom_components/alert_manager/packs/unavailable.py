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


def _should_evaluate(
    hass: HomeAssistant,
    old_state: State | None,
    new_state: State | None,
    _config: dict[str, Any],
) -> bool:
    """Evaluate only lifecycle or transitions into/out of unavailable."""
    if old_state is None:
        return new_state is not None and _applies(hass, new_state)
    if new_state is None:
        return _applies(hass, old_state)
    return (old_state.state == STATE_UNAVAILABLE) != (
        new_state.state == STATE_UNAVAILABLE
    )


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
