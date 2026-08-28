"""UniFi device tracker automatic pack."""

from __future__ import annotations

from typing import Any

from homeassistant.const import STATE_HOME, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from ..const import CATEGORY_UNIFI
from .base import AutomaticPack, PACK_NEUTRAL, PackMatch, PackNeutral


def _is_unifi_tracker(hass: HomeAssistant, state: State) -> bool:
    """Return whether the entity is owned by the UniFi integration."""
    if state.entity_id.partition(".")[0] != "device_tracker":
        return False
    registry_entry = er.async_get(hass).async_get(state.entity_id)
    return bool(registry_entry is not None and registry_entry.platform == "unifi")


def _applies(hass: HomeAssistant, state: State) -> bool:
    """Return whether the state is a router-backed UniFi tracker."""
    if not _is_unifi_tracker(hass, state):
        return False
    # source_type can disappear while the integration is unavailable. Keep the
    # source tracked during that neutral state; it still cannot create an alert.
    return (
        state.state == STATE_UNAVAILABLE
        or state.attributes.get("source_type") == "router"
    )


def _should_evaluate(
    _hass: HomeAssistant,
    new_state: State,
    _config: dict[str, Any],
) -> bool:
    """Evaluate applicable UniFi states except unavailable."""
    return new_state.state != STATE_UNAVAILABLE


def _evaluate(
    hass: HomeAssistant, state: State, _config: dict[str, Any]
) -> PackMatch | PackNeutral | None:
    """Return alert, neutral or healthy UniFi tracker status."""
    if not _applies(hass, state):
        return None
    if state.state == STATE_UNAVAILABLE:
        return PACK_NEUTRAL
    if state.state == STATE_HOME:
        return None
    return PackMatch(
        condition_key="automatic.unifi",
    )


PACK = AutomaticPack(
    id=CATEGORY_UNIFI,
    translation_key="unifi",
    prerequisites=("unifi",),
    applies=_applies,
    evaluate=_evaluate,
    transition_filter=_should_evaluate,
)
