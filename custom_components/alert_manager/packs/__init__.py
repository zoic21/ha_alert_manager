"""Registry of automatic Alert Manager packs."""

from __future__ import annotations

from collections.abc import Collection

from homeassistant.core import HomeAssistant

from .base import (
    AutomaticPack,
    PackConfigField,
    PackGeneratedAlert,
    PackNeutral,
    PackOccurrence,
    PackRecheck,
)
from .battery import PACK as BATTERY_PACK
from .connectivity import PACK as CONNECTIVITY_PACK
from .execution_errors import PACK as EXECUTION_ERRORS_PACK
from .flapping import PACK as FLAPPING_PACK
from .unavailable import PACK as UNAVAILABLE_PACK
from .unifi import PACK as UNIFI_PACK

PACKS: tuple[AutomaticPack, ...] = (
    UNAVAILABLE_PACK,
    CONNECTIVITY_PACK,
    UNIFI_PACK,
    BATTERY_PACK,
    EXECUTION_ERRORS_PACK,
    FLAPPING_PACK,
)
PACKS_BY_ID = {pack.id: pack for pack in PACKS}
OCCURRENCE_PACKS = tuple(
    pack for pack in PACKS if pack.occurrence_batch_handler is not None
)


def reset_pack_runtimes(
    hass: HomeAssistant, pack_ids: Collection[str] | None = None
) -> None:
    """Reset transient state for every pack, or for a selected set of packs."""
    for pack in PACKS:
        if pack_ids is None or pack.id in pack_ids:
            pack.reset_runtime(hass)


__all__ = [
    "OCCURRENCE_PACKS",
    "PACKS",
    "PACKS_BY_ID",
    "AutomaticPack",
    "PackConfigField",
    "PackGeneratedAlert",
    "PackNeutral",
    "PackOccurrence",
    "PackRecheck",
    "reset_pack_runtimes",
]
