"""Connectivity automatic pack."""

from __future__ import annotations

from typing import Any

from homeassistant.const import ATTR_DEVICE_CLASS, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from ..const import CATEGORY_CONNECTIVITY
from .base import AutomaticPack, PackMatch

_FAILURE_STATES = frozenset(("off", STATE_UNAVAILABLE))


def _applies(hass: HomeAssistant, state: State) -> bool:
    """Return whether the state is a connectivity binary sensor."""
    if state.entity_id.partition(".")[0] != "binary_sensor":
        return False
    if state.attributes.get(ATTR_DEVICE_CLASS) == "connectivity":
        return True
    # Some integrations temporarily drop state attributes while reloading.
    # Registry metadata remains stable and preserves the pack identity.
    registry_entry = er.async_get(hass).async_get(state.entity_id)
    return bool(
        registry_entry is not None
        and getattr(registry_entry, "original_device_class", None) == "connectivity"
    )


def _matches(hass: HomeAssistant, state: State | None) -> bool:
    """Treat off and unavailable as the same connectivity failure."""
    return (
        state is not None and _applies(hass, state) and state.state in _FAILURE_STATES
    )


def _should_evaluate(
    hass: HomeAssistant,
    old_state: State | None,
    new_state: State | None,
    _config: dict[str, Any],
) -> bool:
    """Evaluate only when the logical connectivity failure changes."""
    return _matches(hass, old_state) != _matches(hass, new_state)


def _evaluate(
    hass: HomeAssistant, state: State, _config: dict[str, Any]
) -> PackMatch | None:
    """Match connectivity binary sensors that are off or unavailable."""
    if not _applies(hass, state) or state.state not in _FAILURE_STATES:
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
