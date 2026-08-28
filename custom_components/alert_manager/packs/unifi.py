"""UniFi device tracker automatic pack."""

from __future__ import annotations

from typing import Any

from homeassistant.const import STATE_HOME, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from ..const import CATEGORY_UNIFI
from .base import AutomaticPack, PackMatch


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
    record_exists: bool,
) -> bool:
    """Evaluate only when the stored occurrence and definitive state disagree."""
    return record_exists != (new_state.state != STATE_HOME)


def _evaluate(
    hass: HomeAssistant, state: State, _config: dict[str, Any]
) -> PackMatch | None:
    """Match router-backed UniFi trackers that are definitively away."""
    if (
        not _applies(hass, state)
        or state.state == STATE_HOME
        or state.state == STATE_UNAVAILABLE
    ):
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
    neutral_states=frozenset((STATE_UNAVAILABLE,)),
)
