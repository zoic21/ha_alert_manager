"""Unavailable entity automatic pack."""

from __future__ import annotations

from typing import Any

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State

from ..const import CATEGORY_UNAVAILABLE
from .base import AutomaticPack, PackMatch


def _evaluate(
    _hass: HomeAssistant, state: State, _config: dict[str, Any]
) -> PackMatch | None:
    """Match only unavailable, for every entity domain."""
    if state.state != STATE_UNAVAILABLE:
        return None
    return PackMatch("État indisponible")


PACK = AutomaticPack(
    id=CATEGORY_UNAVAILABLE,
    name="Entités indisponibles",
    prerequisites=(),
    evaluate=_evaluate,
)
