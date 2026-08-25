"""Connectivity automatic pack."""

from __future__ import annotations

from typing import Any

from homeassistant.const import ATTR_DEVICE_CLASS
from homeassistant.core import HomeAssistant, State

from ..const import CATEGORY_CONNECTIVITY
from .base import AutomaticPack, PackMatch


def _evaluate(
    _hass: HomeAssistant, state: State, _config: dict[str, Any]
) -> PackMatch | None:
    """Match connectivity binary sensors that are off."""
    if (
        state.entity_id.partition(".")[0] != "binary_sensor"
        or state.attributes.get(ATTR_DEVICE_CLASS) != "connectivity"
        or state.state != "off"
    ):
        return None
    return PackMatch("Connectivité désactivée")


PACK = AutomaticPack(
    id=CATEGORY_CONNECTIVITY,
    name="Connectivité",
    prerequisites=(),
    evaluate=_evaluate,
)
