"""Shared model for isolated automatic rule packs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntryState
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
    description: str
    prerequisites: tuple[str, ...]
    applies: Callable[[HomeAssistant, State], bool]
    evaluate: Callable[[HomeAssistant, State, dict[str, Any]], PackMatch | None]

    def available(self, hass: HomeAssistant) -> bool:
        """Return whether every required integration has one usable entry."""
        return all(
            any(
                entry.state is ConfigEntryState.LOADED
                for entry in hass.config_entries.async_entries(
                    domain,
                    include_ignore=False,
                    include_disabled=False,
                )
            )
            for domain in self.prerequisites
        )

    def as_public_dict(self, hass: HomeAssistant) -> dict[str, Any]:
        """Expose stable metadata and current runtime availability to the panel."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "prerequisites": list(self.prerequisites),
            "available": self.available(hass),
        }
