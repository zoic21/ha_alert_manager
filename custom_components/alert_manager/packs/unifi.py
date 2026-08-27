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


def _matches(hass: HomeAssistant, state: State | None) -> bool:
    """Return whether the optional state currently matches this pack."""
    return state is not None and _applies(hass, state) and state.state != STATE_HOME


def _should_evaluate(
    hass: HomeAssistant,
    old_state: State | None,
    new_state: State | None,
    _config: dict[str, Any],
) -> bool:
    """Evaluate only transitions into or out of the away condition."""
    return _matches(hass, old_state) != _matches(hass, new_state)


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
