"""Low battery automatic pack."""

from __future__ import annotations

from typing import Any

from homeassistant.const import ATTR_DEVICE_CLASS, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State

from ..const import (
    CATEGORY_BATTERY,
    DEFAULT_BATTERY_THRESHOLD,
    MAX_THRESHOLD,
    MIN_THRESHOLD,
)
from ..models import safe_float
from .base import AutomaticPack, PackConfigField, PackMatch, PackNeutral


def _applies(_hass: HomeAssistant, state: State) -> bool:
    """Return whether the state is a battery sensor."""
    return (
        state.entity_id.partition(".")[0] == "sensor"
        and state.attributes.get(ATTR_DEVICE_CLASS) == "battery"
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
) -> PackMatch | PackNeutral | None:
    """Match low batteries while preserving them through unavailability."""
    if state.state == STATE_UNAVAILABLE:
        return PackNeutral()
    if not _applies(hass, state):
        return None
    value = safe_float(state.state)
    threshold = config.get("threshold", DEFAULT_BATTERY_THRESHOLD)
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
    should_evaluate=_should_evaluate,
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
    ),
)
