"""Shared model for isolated automatic rule packs."""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, State

from ..models import AlertDetails


@dataclass(frozen=True, slots=True)
class PackMatch:
    """A matching automatic condition returned by one pack."""

    condition_key: str
    condition_params: dict[str, Any] = field(default_factory=dict)
    value: Any | None = None


@dataclass(frozen=True, slots=True)
class PackNeutral:
    """Signal that one pack must preserve its current occurrence unchanged."""


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
    entity_domains: tuple[str, ...] | None = None
    fields: tuple[PackConfigField, ...] = ()

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
                "entity_domains": list(self.entity_domains)
                if self.entity_domains is not None
                else None,
                "fields": [field.as_public_dict() for field in self.fields]
                if self.fields
                else None,
            }.items()
            if value is not None
        }


PackShouldEvaluate = Callable[
    [HomeAssistant, State | None, State, dict[str, Any]], bool
]
PackResetHandler = Callable[[HomeAssistant], None]
PackEvaluation = PackMatch | PackNeutral | None


@dataclass(frozen=True, slots=True)
class PackOccurrence:
    """Describe one genuinely new source anomaly seen during normal runtime."""

    source: AlertDetails
    state: State
    occurred_at: datetime
    active_alert_ids: Collection[str] = frozenset()


@dataclass(frozen=True, slots=True)
class PackGeneratedAlert:
    """Describe an immediate alert emitted by an occurrence-driven pack."""

    key: str
    condition_key: str
    condition_params: dict[str, Any]
    value: Any
    resolve_at: datetime
    rule_name: str | None = None


@dataclass(frozen=True, slots=True)
class PackOccurrenceResult:
    """Report a persisted occurrence-data change and an optional alert."""

    alert: PackGeneratedAlert | None = None


PackOccurrenceHandler = Callable[
    [HomeAssistant, PackOccurrence, dict[str, Any], dict[str, Any]],
    PackOccurrenceResult | None,
]


@dataclass(frozen=True, slots=True)
class AutomaticPack:
    """Stable metadata and isolated evaluation function for an automatic pack."""

    id: str
    translation_key: str
    prerequisites: tuple[str, ...]
    applies: Callable[[HomeAssistant, State], bool]
    evaluate: Callable[[HomeAssistant, State, dict[str, Any]], PackEvaluation]
    should_evaluate: PackShouldEvaluate | None = None
    reset_handler: PackResetHandler | None = None
    config_fields: tuple[PackConfigField, ...] = ()
    uses_delay: bool = True
    occurrence_handler: PackOccurrenceHandler | None = None

    def reset_runtime(self, hass: HomeAssistant) -> None:
        """Discard optional transient state owned by this pack."""
        if self.reset_handler is not None:
            self.reset_handler(hass)

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
        if not self.uses_delay:
            result["uses_delay"] = False
        if self.config_fields:
            result["config_fields"] = [
                field.as_public_dict() for field in self.config_fields
            ]
        return result
