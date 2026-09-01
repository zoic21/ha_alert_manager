"""Low battery automatic pack."""

from __future__ import annotations

from typing import Any

from homeassistant.const import ATTR_DEVICE_CLASS, STATE_UNAVAILABLE
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


def _effective_threshold(
    hass: HomeAssistant, state: State, config: dict[str, Any]
) -> float:
    """Return the global or device-specific threshold for this entity."""
    entity_entry = er.async_get(hass).async_get(state.entity_id)
    device_id = (
        entity_entry.device_id
        if entity_entry is not None and entity_entry.device_id
        else None
    )
    device_thresholds = config.get("device_thresholds", {})
    device_threshold = safe_float(
        device_thresholds.get(device_id) if device_id is not None else None
    )
    if device_threshold is not None:
        return device_threshold
    global_threshold = safe_float(config.get("threshold", DEFAULT_BATTERY_THRESHOLD))
    return (
        global_threshold
        if global_threshold is not None
        else float(DEFAULT_BATTERY_THRESHOLD)
    )


def _should_evaluate(
    _hass: HomeAssistant,
    _old_state: State | None,
    new_state: State,
    _config: dict[str, Any],
) -> bool:
    """Evaluate applicable battery states except unavailable."""
    return new_state.state != STATE_UNAVAILABLE


def _evaluate(
    hass: HomeAssistant, state: State, config: dict[str, Any]
) -> PackMatch | None:
    """Match battery sensors at or below their effective threshold."""
    if not _applies(hass, state):
        return None
    value = safe_float(state.state)
    threshold = _effective_threshold(hass, state, config)
    if value is None or value > threshold:
        return None
    return PackMatch(
        condition_key="automatic.battery",
        condition_params={"threshold": f"{threshold:g}"},
        value=value,
    )


PACK = AutomaticPack(
    id=CATEGORY_BATTERY,
    translation_key="battery",
    prerequisites=(),
    applies=_applies,
    evaluate=_evaluate,
    transition_filter=_should_evaluate,
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
