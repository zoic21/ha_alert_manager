"""Connectivity automatic pack."""

from __future__ import annotations

from typing import Any

from homeassistant.const import ATTR_DEVICE_CLASS, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from ..const import CATEGORY_CONNECTIVITY
from .base import AutomaticPack, PackMatch


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


def _is_neutral(state: State | None) -> bool:
    """Return whether the state must not change connectivity status."""
    return state is not None and state.state == STATE_UNAVAILABLE


def _matches(hass: HomeAssistant, state: State | None) -> bool:
    """Return whether a definitive state is a connectivity failure."""
    return state is not None and _applies(hass, state) and state.state == "off"


def _should_evaluate(
    hass: HomeAssistant,
    old_state: State | None,
    new_state: State | None,
    _config: dict[str, Any],
) -> bool:
    """Ignore entry into unavailable and evaluate the next definitive state."""
    if _is_neutral(new_state):
        return False
    if _is_neutral(old_state):
        if new_state is None:
            # Entity removal is rare; stay conservative so a preserved occurrence
            # cannot survive after its source disappears.
            return old_state.entity_id.partition(".")[0] == "binary_sensor"
        return _applies(hass, old_state) or _applies(hass, new_state)
    return _matches(hass, old_state) != _matches(hass, new_state)


def _evaluate(
    hass: HomeAssistant, state: State, _config: dict[str, Any]
) -> PackMatch | None:
    """Match connectivity binary sensors only when definitively off."""
    if not _matches(hass, state):
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
    neutral_states=frozenset((STATE_UNAVAILABLE,)),
)
