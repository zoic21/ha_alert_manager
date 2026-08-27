"""UniFi device tracker automatic pack."""

from __future__ import annotations

from typing import Any

from homeassistant.const import STATE_HOME
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from ..const import CATEGORY_UNIFI
from .base import AutomaticPack, PackMatch


def _applies(hass: HomeAssistant, state: State) -> bool:
    """Return whether the state is a router-backed UniFi tracker."""
    if state.entity_id.partition(".")[0] != "device_tracker":
        return False
    registry_entry = er.async_get(hass).async_get(state.entity_id)
    return bool(
        registry_entry is not None
        and registry_entry.platform == "unifi"
        and state.attributes.get("source_type") == "router"
    )


def _should_evaluate(
    hass: HomeAssistant,
    old_state: State | None,
    new_state: State | None,
    _config: dict[str, Any],
) -> bool:
    """Evaluate lifecycle, applicability, or home/away transitions only."""
    if old_state is None:
        return new_state is not None and _applies(hass, new_state)
    if new_state is None:
        return _applies(hass, old_state)
    old_applies = _applies(hass, old_state)
    new_applies = _applies(hass, new_state)
    if old_applies != new_applies:
        return True
    if not new_applies:
        return False
    return (old_state.state == STATE_HOME) != (new_state.state == STATE_HOME)


def _evaluate(
    hass: HomeAssistant, state: State, _config: dict[str, Any]
) -> PackMatch | None:
    """Match router-backed UniFi trackers away from home."""
    if not _applies(hass, state) or state.state == STATE_HOME:
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
