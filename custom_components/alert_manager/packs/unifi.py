"""UniFi device tracker automatic pack."""

from __future__ import annotations

from typing import Any

from homeassistant.const import STATE_HOME
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from ..const import CATEGORY_UNIFI
from .base import AutomaticPack, PackMatch


def _evaluate(
    hass: HomeAssistant, state: State, _config: dict[str, Any]
) -> PackMatch | None:
    """Match router-backed UniFi trackers away from home."""
    if state.entity_id.partition(".")[0] != "device_tracker":
        return None
    registry_entry = er.async_get(hass).async_get(state.entity_id)
    if (
        registry_entry is None
        or registry_entry.platform != "unifi"
        or state.attributes.get("source_type") != "router"
        or state.state == STATE_HOME
    ):
        return None
    return PackMatch("Équipement UniFi absent")


PACK = AutomaticPack(
    id=CATEGORY_UNIFI,
    name="Équipements UniFi",
    prerequisites=("unifi",),
    evaluate=_evaluate,
)
