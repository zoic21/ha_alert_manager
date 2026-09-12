"""Registry of automatic Alert Manager packs."""

from __future__ import annotations

from collections.abc import Collection
from importlib import import_module
from pkgutil import iter_modules

from homeassistant.core import HomeAssistant

from .base import (
    AutomaticPack,
    PackConfigField,
    PackGeneratedAlert,
    PackNeutral,
    PackOccurrence,
    PackRecheck,
)


def discover_packs() -> tuple[AutomaticPack, ...]:
    """Load pack declarations once; adding a module needs no central mapping."""
    packs = []
    ids = set()
    for module in iter_modules(__path__):
        if module.name.startswith("_") or module.name == "base":
            continue
        pack = getattr(import_module(f"{__name__}.{module.name}"), "PACK", None)
        if pack is None:
            continue
        if not isinstance(pack, AutomaticPack) or pack.id in ids:
            raise ValueError(f"Invalid or duplicate pack declaration: {module.name}")
        ids.add(pack.id)
        packs.append(pack)
    return tuple(sorted(packs, key=lambda pack: (pack.order, pack.id)))


PACKS: tuple[AutomaticPack, ...] = discover_packs()
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
