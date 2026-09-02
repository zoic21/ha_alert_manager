"""Registry of automatic Alert Manager packs."""

from __future__ import annotations

from collections.abc import Collection

from homeassistant.core import HomeAssistant

from .base import AutomaticPack, PackConfigField, PackNeutral
from .battery import PACK as BATTERY_PACK
from .connectivity import PACK as CONNECTIVITY_PACK
from .execution_errors import PACK as EXECUTION_ERRORS_PACK
from .unavailable import PACK as UNAVAILABLE_PACK
from .unifi import PACK as UNIFI_PACK

PACKS: tuple[AutomaticPack, ...] = (
    UNAVAILABLE_PACK,
    CONNECTIVITY_PACK,
    UNIFI_PACK,
    BATTERY_PACK,
    EXECUTION_ERRORS_PACK,
)
PACKS_BY_ID = {pack.id: pack for pack in PACKS}


def reset_pack_runtimes(
    hass: HomeAssistant, pack_ids: Collection[str] | None = None
) -> None:
    """Reset transient state for every pack, or for a selected set of packs."""
    for pack in PACKS:
        if pack_ids is None or pack.id in pack_ids:
            pack.reset_runtime(hass)


__all__ = [
    "PACKS",
    "PACKS_BY_ID",
    "AutomaticPack",
    "PackConfigField",
    "PackNeutral",
    "reset_pack_runtimes",
]
