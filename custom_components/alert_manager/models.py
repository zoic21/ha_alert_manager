"""Data models and the pure state machine for Alert Manager."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import uuid4

from .const import OPERATORS, SEVERITIES, VALUE_SOURCES


class AlertStatus(StrEnum):
    """Internal alert status."""

    NORMAL = "normal"
    PENDING = "pending"
    ACTIVE = "active"


@dataclass(slots=True)
class AlertDetails:
    """Stable and display information for an alert."""

    id: str
    type: str
    entity_id: str
    name: str
    value: Any
    condition: str
    severity: str = "warning"
    device_name: str | None = None
    area: str | None = None
    integration: str | None = None
    unit: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlertDetails:
        """Deserialize alert details."""
        allowed = cls.__dataclass_fields__
        return cls(**{key: data.get(key) for key in allowed})

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-safe details without empty optional fields."""
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(slots=True)
class AlertRecord:
    """Persisted alert state."""

    details: AlertDetails
    status: AlertStatus
    detected_at: datetime
    due_at: datetime
    delay: int
    active_since: datetime | None = None

    @classmethod
    def pending(cls, details: AlertDetails, delay: int, now: datetime) -> AlertRecord:
        """Create a pending alert."""
        return cls(
            details=details,
            status=AlertStatus.PENDING,
            detected_at=now,
            due_at=now + timedelta(seconds=delay),
            delay=delay,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlertRecord:
        """Deserialize a persisted record."""
        active_since = data.get("active_since")
        return cls(
            details=AlertDetails.from_dict(data["details"]),
            status=AlertStatus(data["status"]),
            detected_at=datetime.fromisoformat(data["detected_at"]),
            due_at=datetime.fromisoformat(data["due_at"]),
            delay=int(data["delay"]),
            active_since=(
                datetime.fromisoformat(active_since) if active_since else None
            ),
        )

    def as_storage_dict(self) -> dict[str, Any]:
        """Serialize for Home Assistant Store."""
        return {
            "details": self.details.as_dict(),
            "status": self.status.value,
            "detected_at": self.detected_at.isoformat(),
            "due_at": self.due_at.isoformat(),
            "delay": self.delay,
            "active_since": (
                self.active_since.isoformat() if self.active_since else None
            ),
        }

    def as_public_dict(self) -> dict[str, Any]:
        """Serialize for the sensor, events and WebSocket API."""
        result = self.details.as_dict()
        result.update(
            {
                "detected_at": self.detected_at.isoformat(),
                "due_at": self.due_at.isoformat(),
                "delay": self.delay,
            }
        )
        if self.active_since is not None:
            result["active_since"] = self.active_since.isoformat()
        return result


@dataclass(slots=True)
class Rule:
    """A custom V1 comparison rule."""

    id: str
    name: str
    entity_id: str
    operator: str
    value: str | int | float | bool
    duration: int
    severity: str = "warning"
    enabled: bool = True
    source: str = "state"
    attribute: str | None = None
    message: str | None = None
    version: int = 1
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, data: dict[str, Any]) -> Rule:
        """Create a rule with an immutable random identifier."""
        return cls.from_dict({**data, "id": uuid4().hex})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Rule:
        """Deserialize while preserving unknown future fields."""
        known = cls.__dataclass_fields__
        values = {key: data[key] for key in known if key in data and key != "extra"}
        values["extra"] = {
            key: value for key, value in data.items() if key not in known
        }
        rule = cls(**values)
        rule.validate()
        return rule

    def validate(self) -> None:
        """Validate invariants shared by storage and the WebSocket API."""
        if not self.id or not isinstance(self.id, str):
            raise ValueError("Rule id is required")
        if not self.name or not isinstance(self.name, str):
            raise ValueError("Rule name is required")
        if self.operator not in OPERATORS:
            raise ValueError(f"Unsupported operator: {self.operator}")
        if self.severity not in SEVERITIES:
            raise ValueError(f"Unsupported severity: {self.severity}")
        if self.source not in VALUE_SOURCES:
            raise ValueError(f"Unsupported value source: {self.source}")
        if self.source == "attribute" and not self.attribute:
            raise ValueError("Attribute is required for attribute rules")
        if self.source == "state" and self.attribute is not None:
            raise ValueError("Attribute must be empty for state rules")
        if not isinstance(self.duration, int) or isinstance(self.duration, bool):
            raise ValueError("Duration must be an integer")
        if self.duration < 0 or self.duration > 31_536_000:
            raise ValueError("Duration must be between 0 and 31536000 seconds")
        if self.operator in ("above", "below") and safe_float(self.value) is None:
            raise ValueError("Numeric operators require a finite numeric value")

    def as_dict(self) -> dict[str, Any]:
        """Serialize a rule including forward-compatible fields."""
        result = asdict(self)
        extra = result.pop("extra", {})
        result.update(extra)
        return {key: value for key, value in result.items() if value is not None}

    def matches(self, current: Any) -> bool:
        """Safely compare a current value to the configured value."""
        if self.operator in ("above", "below"):
            current_number = safe_float(current)
            expected_number = safe_float(self.value)
            if current_number is None or expected_number is None:
                return False
            return (
                current_number > expected_number
                if self.operator == "above"
                else current_number < expected_number
            )

        current_text = normalize_scalar(current)
        expected_text = normalize_scalar(self.value)
        equal = current_text == expected_text
        return equal if self.operator == "equals" else not equal


def safe_float(value: Any) -> float | None:
    """Convert to a finite float without accepting booleans."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_scalar(value: Any) -> str:
    """Normalize exact comparisons while keeping them predictable."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def advance_record(record: AlertRecord, now: datetime) -> bool:
    """Advance a due pending record; return whether it changed."""
    if record.status is not AlertStatus.PENDING or now < record.due_at:
        return False
    record.status = AlertStatus.ACTIVE
    record.active_since = record.due_at
    return True
