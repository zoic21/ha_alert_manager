"""Registry of automatic Alert Manager packs."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import replace

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


def _with_exceptions(pack: AutomaticPack) -> AutomaticPack:
    """Expose the same sparse device/entity model for each native pack."""
    fields = (PackConfigField("enabled", "boolean", "monitoring", True),)
    if pack.uses_delay:
        fields += (
            PackConfigField(
                "delay", "number", "trigger_delay", 0, 0, 31_536_000, 1, "s"
            ),
        )
    fields += tuple(field for field in pack.config_fields if field.type == "number")
    maps = tuple(
        PackConfigField(
            f"{kind}_overrides",
            f"{kind}_settings_map",
            f"{kind}_overrides",
            {},
            fields=fields,
            sparse=True,
        )
        for kind in ("device", "entity")
    )
    config_fields = tuple(
        replace(field, fields=(fields[0], *field.fields, *maps))
        if field.id == "source_packs"
        else field
        for field in pack.config_fields
    )
    return replace(pack, config_fields=config_fields + maps)


PACKS: tuple[AutomaticPack, ...] = tuple(
    _with_exceptions(pack)
    for pack in (
        UNAVAILABLE_PACK,
        CONNECTIVITY_PACK,
        UNIFI_PACK,
        BATTERY_PACK,
        EXECUTION_ERRORS_PACK,
        FLAPPING_PACK,
    )
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
