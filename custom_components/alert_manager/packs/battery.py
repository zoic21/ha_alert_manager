"""Low battery automatic pack."""

from __future__ import annotations

from functools import lru_cache
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


@lru_cache(maxsize=512)
def _cached_effective_threshold(
    entity_id: str,
    device_id: str | None,
    global_threshold: float | int | str,
    device_threshold: float | int | str | None,
) -> float:
    """Cache the normalized effective threshold for one entity/config tuple."""
    del entity_id, device_id
    normalized_device = safe_float(device_threshold)
    if normalized_device is not None:
        return normalized_device
    normalized_global = safe_float(global_threshold)
    return (
        normalized_global
        if normalized_global is not None
        else float(DEFAULT_BATTERY_THRESHOLD)
    )


def _applies(_hass: HomeAssistant, state: State) -> bool:
    """Return whether the state is a battery sensor."""
    return (
        state.entity_id.partition(".")[0] == "sensor"
        and state.attributes.get(ATTR_DEVICE_CLASS) == "battery"
    )


def _effective_threshold(
    hass: HomeAssistant, state: State, config: dict[str, Any]
) -> float:
    """Return the cached global/device threshold effective for this entity."""
    entity_entry = er.async_get(hass).async_get(state.entity_id)
    device_id = (
        entity_entry.device_id
        if entity_entry is not None and entity_entry.device_id
        else None
    )
    device_thresholds = config.get("device_thresholds", {})
    device_threshold = (
        device_thresholds.get(device_id) if device_id is not None else None
    )
    return _cached_effective_threshold(
        state.entity_id,
        device_id,
        config.get("threshold", DEFAULT_BATTERY_THRESHOLD),
        device_threshold,
    )


def _should_evaluate(
    hass: HomeAssistant,
    old_state: State | None,
    new_state: State | None,
    config: dict[str, Any],
) -> bool:
    """Evaluate lifecycle, applicability, or effective threshold crossings only."""
    if old_state is None:
        return new_state is not None and _applies(hass, new_state)
    if new_state is None:
        return _applies(hass, old_state)

    old_applies = _applies(hass, old_state)
    new_applies = _applies(hass, new_state)
    if old_applies != new_applies:
        # Tracking changes even if the current percentage is above the threshold.
        return True
    if not new_applies:
        return False

    threshold = _effective_threshold(hass, new_state, config)
    old_value = safe_float(old_state.state)
    new_value = safe_float(new_state.state)
    old_matches = old_value is not None and old_value <= threshold
    new_matches = new_value is not None and new_value <= threshold
    return old_matches != new_matches


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
