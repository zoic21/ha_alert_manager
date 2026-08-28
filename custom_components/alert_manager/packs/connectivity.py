"""Connectivity automatic pack."""

from __future__ import annotations

from typing import Any

from homeassistant.const import ATTR_DEVICE_CLASS, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from ..const import CATEGORY_CONNECTIVITY
from .base import AutomaticPack, PackMatch, PackNeutral


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


def _should_evaluate(
    _hass: HomeAssistant,
    new_state: State,
    _config: dict[str, Any],
) -> bool:
    """Evaluate applicable connectivity states except unavailable."""
    return new_state.state != STATE_UNAVAILABLE


def _evaluate(
    hass: HomeAssistant, state: State, _config: dict[str, Any]
) -> PackMatch | PackNeutral | None:
    """Return alert, neutral or healthy connectivity status."""
    if not _applies(hass, state):
        return None
    if state.state == STATE_UNAVAILABLE:
        return PackNeutral()
    if state.state != "off":
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
