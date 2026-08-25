"""Low battery automatic pack."""

from __future__ import annotations

from typing import Any

from homeassistant.const import ATTR_DEVICE_CLASS
from homeassistant.core import HomeAssistant, State

from ..const import CATEGORY_BATTERY
from ..models import safe_float
from .base import AutomaticPack, PackMatch


def _evaluate(
    _hass: HomeAssistant, state: State, config: dict[str, Any]
) -> PackMatch | None:
    """Match battery sensors at or below their effective threshold."""
    if (
        state.entity_id.partition(".")[0] != "sensor"
        or state.attributes.get(ATTR_DEVICE_CLASS) != "battery"
    ):
        return None
    value = safe_float(state.state)
    override = safe_float(state.attributes.get("low_battery_level"))
    threshold = override if override is not None else config["threshold"]
    if value is None or value > threshold:
        return None
    return PackMatch(
        condition=f"Batterie inférieure ou égale à {threshold:g} %",
        value=value,
    )


PACK = AutomaticPack(
    id=CATEGORY_BATTERY,
    name="Batteries faibles",
    prerequisites=(),
    evaluate=_evaluate,
)
