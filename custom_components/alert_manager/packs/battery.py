"""Low battery automatic pack."""

from __future__ import annotations

from typing import Any

from homeassistant.const import ATTR_DEVICE_CLASS
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from ..const import (
    CATEGORY_BATTERY,
    DEFAULT_BATTERY_THRESHOLD,
    MAX_THRESHOLD,
    MIN_THRESHOLD,
)
from ..models import safe_float
from .base import AutomaticPack, PackConfigField, PackMatch


def _applies(_hass: HomeAssistant, state: State) -> bool:
    """Return whether the state is a battery sensor."""
    return (
        state.entity_id.partition(".")[0] == "sensor"
        and state.attributes.get(ATTR_DEVICE_CLASS) == "battery"
    )


def _evaluate(
    hass: HomeAssistant, state: State, config: dict[str, Any]
) -> PackMatch | None:
    """Match battery sensors at or below their effective threshold."""
    if not _applies(hass, state):
        return None
    value = safe_float(state.state)
    entity_entry = er.async_get(hass).async_get(state.entity_id)
    device_thresholds = config.get("device_thresholds", {})
    device_threshold = (
        safe_float(device_thresholds.get(entity_entry.device_id))
        if entity_entry is not None and entity_entry.device_id
        else None
    )
    entity_threshold = safe_float(state.attributes.get("low_battery_level"))
    threshold = (
        device_threshold
        if device_threshold is not None
        else entity_threshold
        if entity_threshold is not None
        else config["threshold"]
    )
    if value is None or value > threshold:
        return None
    return PackMatch(
        condition=f"Batterie inférieure ou égale à {threshold:g} %",
        value=value,
        condition_key="automatic.battery",
        condition_params={"threshold": f"{threshold:g}"},
    )


PACK = AutomaticPack(
    id=CATEGORY_BATTERY,
    translation_key="battery",
    prerequisites=(),
    applies=_applies,
    evaluate=_evaluate,
    config_fields=(
        PackConfigField(
            id="threshold",
            type="number",
            translation_key="threshold",
            default=DEFAULT_BATTERY_THRESHOLD,
            minimum=MIN_THRESHOLD,
            maximum=MAX_THRESHOLD,
            unit="%",
        ),
        PackConfigField(
            id="device_thresholds",
            type="device_number_map",
            translation_key="device_thresholds",
            default={},
            minimum=MIN_THRESHOLD,
            maximum=MAX_THRESHOLD,
            unit="%",
        ),
    ),
)
