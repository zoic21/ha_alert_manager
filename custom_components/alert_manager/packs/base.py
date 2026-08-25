"""Shared model for isolated automatic rule packs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant, State


@dataclass(frozen=True, slots=True)
class PackMatch:
    """A matching automatic condition returned by one pack."""

    condition: str
    value: Any | None = None


@dataclass(frozen=True, slots=True)
class AutomaticPack:
    """Stable metadata and isolated evaluation function for an automatic pack."""

    id: str
    name: str
    prerequisites: tuple[str, ...]
    evaluate: Callable[[HomeAssistant, State, dict[str, Any]], PackMatch | None]
