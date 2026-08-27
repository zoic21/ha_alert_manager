"""Registry of automatic Alert Manager packs."""

from __future__ import annotations

from .base import AutomaticPack, PackConfigField
from .battery import PACK as BATTERY_PACK
from .connectivity import PACK as CONNECTIVITY_PACK
from .unavailable import PACK as UNAVAILABLE_PACK
from .unifi import PACK as UNIFI_PACK

PACKS: tuple[AutomaticPack, ...] = (
    UNAVAILABLE_PACK,
    CONNECTIVITY_PACK,
    UNIFI_PACK,
    BATTERY_PACK,
)
PACKS_BY_ID = {pack.id: pack for pack in PACKS}

__all__ = ["PACKS", "PACKS_BY_ID", "AutomaticPack", "PackConfigField"]
