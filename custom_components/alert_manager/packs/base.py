"""Shared model for isolated automatic rule packs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, State


@dataclass(frozen=True, slots=True)
class PackMatch:
    """A matching automatic condition returned by one pack."""

    condition_key: str
    condition_params: dict[str, Any] = field(default_factory=dict)
    value: Any | None = None


@dataclass(frozen=True, slots=True)
class PackConfigField:
    """Describe one pack-owned configuration field for validation and the UI."""

    id: str
    type: str
    translation_key: str
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    step: str | float = "any"
    unit: str | None = None

    def as_public_dict(self) -> dict[str, Any]:
        """Expose a serializable description without frontend pack special cases."""
        return {
            key: value
            for key, value in {
                "id": self.id,
                "type": self.type,
                "translation_key": self.translation_key,
                "default": self.default,
                "minimum": self.minimum,
                "maximum": self.maximum,
                "step": self.step,
                "unit": self.unit,
            }.items()
            if value is not None
        }


@dataclass(frozen=True, slots=True)
class AutomaticPack:
    """Stable metadata and isolated evaluation function for an automatic pack."""

    id: str
    translation_key: str
    prerequisites: tuple[str, ...]
    applies: Callable[[HomeAssistant, State], bool]
    evaluate: Callable[[HomeAssistant, State, dict[str, Any]], PackMatch | None]
    config_fields: tuple[PackConfigField, ...] = ()

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
        result = {
            "id": self.id,
            "translation_key": self.translation_key,
            "prerequisites": list(self.prerequisites),
            "available": self.available(hass),
        }
        if self.config_fields:
            result["config_fields"] = [
                field.as_public_dict() for field in self.config_fields
            ]
        return result
