"""Connectivity automatic pack."""

from __future__ import annotations

from typing import Any

from homeassistant.const import ATTR_DEVICE_CLASS
from homeassistant.core import HomeAssistant, State

from ..const import CATEGORY_CONNECTIVITY
from .base import AutomaticPack, PackMatch


def _applies(_hass: HomeAssistant, state: State) -> bool:
    """Return whether the state is a connectivity binary sensor."""
    return (
        state.entity_id.partition(".")[0] == "binary_sensor"
        and state.attributes.get(ATTR_DEVICE_CLASS) == "connectivity"
    )


def _evaluate(
    _hass: HomeAssistant, state: State, _config: dict[str, Any]
) -> PackMatch | None:
    """Match connectivity binary sensors that are off."""
    if not _applies(_hass, state) or state.state != "off":
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
)
