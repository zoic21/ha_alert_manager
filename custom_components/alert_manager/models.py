"""Data models and the pure state machine for Alert Manager."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import uuid4

from .const import MAX_DELAY, MIN_DELAY, OPERATORS, SEVERITIES, VALUE_SOURCES


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
        """Deserialize alert details, rejecting malformed storage data."""
        if not isinstance(data, dict):
            raise ValueError("Alert details must be an object")
        required_strings = ("id", "type", "entity_id", "name", "condition")
        for key in required_strings:
            if not isinstance(data.get(key), str) or not data[key]:
                raise ValueError(f"Alert detail {key} must be a non-empty string")
        if "value" not in data:
            raise ValueError("Alert detail value is required")
        severity = data.get("severity", "warning")
        if severity not in SEVERITIES:
            raise ValueError(f"Unsupported alert severity: {severity}")
        for key in ("device_name", "area", "integration", "unit"):
            if data.get(key) is not None and not isinstance(data[key], str):
                raise ValueError(f"Alert detail {key} must be a string or null")
        allowed = cls.__dataclass_fields__
        values = {key: data[key] for key in allowed if key in data}
        values["severity"] = severity
        return cls(**values)

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
            due_at=calculate_due_at(now, delay),
            delay=delay,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlertRecord:
        """Deserialize a persisted record with strict temporal invariants."""
        if not isinstance(data, dict):
            raise ValueError("Alert record must be an object")
        active_since = data.get("active_since")
        status = AlertStatus(data["status"])
        if status is AlertStatus.NORMAL:
            raise ValueError("Normal alerts must not be persisted")
        delay = data["delay"]
        if isinstance(delay, bool) or not isinstance(delay, int):
            raise ValueError("Alert delay must be an integer")
        if not MIN_DELAY <= delay <= MAX_DELAY:
            raise ValueError("Alert delay is out of range")
        detected_at = _parse_aware_datetime(data["detected_at"], "detected_at")
        due_at = _parse_aware_datetime(data["due_at"], "due_at")
        if due_at.astimezone(UTC) < detected_at.astimezone(UTC):
            raise ValueError("Alert due_at must not precede detected_at")
        parsed_active_since = (
            _parse_aware_datetime(active_since, "active_since")
            if active_since is not None
            else None
        )
        if status is AlertStatus.ACTIVE and parsed_active_since is None:
            raise ValueError("Active alerts require active_since")
        if status is AlertStatus.PENDING and parsed_active_since is not None:
            raise ValueError("Pending alerts must not have active_since")
        if parsed_active_since is not None and parsed_active_since.astimezone(
            UTC
        ) < detected_at.astimezone(UTC):
            raise ValueError("Alert active_since must not precede detected_at")
        return cls(
            details=AlertDetails.from_dict(data["details"]),
            status=status,
            detected_at=detected_at,
            due_at=due_at,
            delay=delay,
            active_since=parsed_active_since,
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


def safe_delay_seconds(value: Any) -> int | None:
    """Parse a finite, integral delay attribute within the supported range."""
    number = safe_float(value)
    if number is None or not number.is_integer():
        return None
    delay = int(number)
    return delay if MIN_DELAY <= delay <= MAX_DELAY else None


def calculate_due_at(detected_at: datetime, delay: int) -> datetime:
    """Add an elapsed duration without daylight-saving wall-clock errors."""
    if detected_at.tzinfo is None or detected_at.utcoffset() is None:
        raise ValueError("Alert timestamps must include a timezone")
    return (detected_at.astimezone(UTC) + timedelta(seconds=delay)).astimezone(
        detected_at.tzinfo
    )


def _parse_aware_datetime(value: Any, field: str) -> datetime:
    """Parse a timezone-aware ISO datetime from persisted storage."""
    if not isinstance(value, str):
        raise ValueError(f"Alert {field} must be an ISO datetime")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"Alert {field} must include a timezone")
    return parsed


def advance_record(record: AlertRecord, now: datetime) -> bool:
    """Advance a due pending record; return whether it changed."""
    if record.status is not AlertStatus.PENDING or now.astimezone(
        UTC
    ) < record.due_at.astimezone(UTC):
        return False
    record.status = AlertStatus.ACTIVE
    record.active_since = record.due_at
    return True
