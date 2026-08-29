"""Data models and the pure state machine for Alert Manager."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import uuid4

from .const import MAX_DELAY, MIN_DELAY, OPERATORS, VALUE_SOURCES


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
    condition_key: str | None = None
    condition_params: dict[str, Any] | None = None
    rule_id: str | None = None
    rule_name: str | None = None
    device_id: str | None = None
    device_name: str | None = None
    area: str | None = None
    integration: str | None = None
    unit: str | None = None
    message: str | None = None
    source: str | None = None
    operator: str | None = None
    comparison_value: Any = None
    attribute: str | None = None

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
        for key in (
            "rule_id",
            "rule_name",
            "device_id",
            "device_name",
            "area",
            "integration",
            "unit",
            "message",
            "source",
            "operator",
            "attribute",
        ):
            if data.get(key) is not None and not isinstance(data[key], str):
                raise ValueError(f"Alert detail {key} must be a string or null")
        if data.get("condition_key") is not None and not isinstance(
            data["condition_key"], str
        ):
            raise ValueError("Alert detail condition_key must be a string or null")
        if data.get("condition_params") is not None and not isinstance(
            data["condition_params"], dict
        ):
            raise ValueError("Alert detail condition_params must be an object or null")
        allowed = cls.__dataclass_fields__
        values = {key: data[key] for key in allowed if key in data}
        return cls(**values)

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-safe details without empty optional fields."""
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(slots=True)
class AlertHistoryEntry:
    """Immutable JSON-safe snapshot of one completed alert occurrence."""

    event_id: str
    id: str
    type: str
    rule_id: str
    rule_name: str
    entity_id: str
    entity_name: str
    device_id: str | None
    device_name: str | None
    area: str | None
    integration: str | None
    message: str | None
    trigger_value: Any
    source: str | None
    operator: str | None
    comparison_value: Any
    attribute: str | None
    condition: str
    condition_key: str | None
    condition_params: dict[str, Any] | None
    unit: str | None
    detected_at: datetime
    active_at: datetime
    resolved_at: datetime
    pending_duration_seconds: float
    active_duration_seconds: float
    total_duration_seconds: float
    final_status: str
    acknowledged: bool
    acknowledged_at: datetime | None
    acknowledged_by: str | None

    @classmethod
    def resolved(cls, record: AlertRecord, resolved_at: datetime) -> AlertHistoryEntry:
        """Freeze a currently active record at its real resolution time."""
        if record.status is not AlertStatus.ACTIVE or record.active_since is None:
            raise ValueError("Only active alerts can be archived as resolved")
        detected = record.detected_at.astimezone(UTC)
        active = record.active_since.astimezone(UTC)
        # A controller clock can move backwards after an acknowledgement (for
        # example after an NTP correction).  Keep the archived timeline valid
        # instead of creating an entry that will be rejected on the next load.
        resolved = max(
            resolved_at.astimezone(UTC),
            active,
            record.acknowledged_at.astimezone(UTC)
            if record.acknowledged_at is not None
            else active,
        )
        pending_seconds = max(
            0.0, (active - detected).total_seconds() - record.paused_seconds
        )
        active_seconds = max(0.0, (resolved - active).total_seconds())
        identity = "\n".join(
            (
                record.details.id,
                detected.isoformat(),
                active.isoformat(),
                resolved.isoformat(),
            )
        )
        return cls(
            event_id=hashlib.sha256(identity.encode()).hexdigest()[:32],
            id=record.details.id,
            type=record.details.type,
            rule_id=record.details.rule_id or record.details.type,
            rule_name=record.details.rule_name or record.details.type,
            entity_id=record.details.entity_id,
            entity_name=record.details.name,
            device_id=record.details.device_id,
            device_name=record.details.device_name,
            area=record.details.area,
            integration=record.details.integration,
            message=record.details.message,
            trigger_value=_json_safe(record.details.value),
            source=record.details.source,
            operator=record.details.operator,
            comparison_value=_json_safe(record.details.comparison_value),
            attribute=record.details.attribute,
            condition=record.details.condition,
            condition_key=record.details.condition_key,
            condition_params=_json_safe(record.details.condition_params),
            unit=record.details.unit,
            detected_at=detected,
            active_at=active,
            resolved_at=resolved,
            pending_duration_seconds=pending_seconds,
            active_duration_seconds=active_seconds,
            total_duration_seconds=pending_seconds + active_seconds,
            final_status="resolved",
            acknowledged=record.acknowledged,
            acknowledged_at=record.acknowledged_at,
            acknowledged_by=record.acknowledged_by,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlertHistoryEntry:
        """Deserialize one strictly shaped persisted history entry."""
        if not isinstance(data, dict):
            raise ValueError("History entry must be an object")
        required_strings = (
            "event_id",
            "id",
            "type",
            "rule_id",
            "rule_name",
            "entity_id",
            "entity_name",
            "condition",
        )
        for key in required_strings:
            if not isinstance(data.get(key), str) or not data[key]:
                raise ValueError(f"History field {key} must be a non-empty string")
        for key in (
            "device_id",
            "device_name",
            "area",
            "integration",
            "message",
            "source",
            "operator",
            "attribute",
            "condition_key",
            "unit",
            "acknowledged_by",
        ):
            if data.get(key) is not None and (
                not isinstance(data[key], str) or not data[key]
            ):
                raise ValueError(f"History field {key} must be a string or null")
        if "trigger_value" not in data:
            raise ValueError("History trigger_value is required")
        condition_params = data.get("condition_params")
        if condition_params is not None and not isinstance(condition_params, dict):
            raise ValueError("History condition_params must be an object or null")
        if data.get("final_status") != "resolved":
            raise ValueError("Unsupported history final status")
        detected_at = _parse_aware_datetime(data["detected_at"], "detected_at")
        active_at = _parse_aware_datetime(data["active_at"], "active_at")
        resolved_at = _parse_aware_datetime(data["resolved_at"], "resolved_at")
        if not detected_at <= active_at <= resolved_at:
            raise ValueError("History timestamps are inconsistent")
        durations = {}
        for key in (
            "pending_duration_seconds",
            "active_duration_seconds",
            "total_duration_seconds",
        ):
            value = data.get(key)
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(f"History field {key} must be non-negative")
            durations[key] = float(value)
        acknowledged = data.get("acknowledged")
        if not isinstance(acknowledged, bool):
            raise ValueError("History acknowledged must be a boolean")
        acknowledged_at = data.get("acknowledged_at")
        parsed_acknowledged_at = (
            _parse_aware_datetime(acknowledged_at, "acknowledged_at")
            if acknowledged_at is not None
            else None
        )
        if acknowledged and parsed_acknowledged_at is None:
            raise ValueError("Acknowledged history requires acknowledged_at")
        if not acknowledged and (
            parsed_acknowledged_at is not None
            or data.get("acknowledged_by") is not None
        ):
            raise ValueError("Unacknowledged history cannot retain metadata")
        if parsed_acknowledged_at is not None and not (
            active_at <= parsed_acknowledged_at <= resolved_at
        ):
            raise ValueError("History acknowledgement timestamp is inconsistent")
        if not math.isclose(
            durations["total_duration_seconds"],
            durations["pending_duration_seconds"]
            + durations["active_duration_seconds"],
            abs_tol=0.001,
        ):
            raise ValueError("History total duration is inconsistent")
        values = {
            key: data.get(key)
            for key in cls.__dataclass_fields__
            if key
            not in {
                "detected_at",
                "active_at",
                "resolved_at",
                "pending_duration_seconds",
                "active_duration_seconds",
                "total_duration_seconds",
                "acknowledged_at",
            }
        }
        values.update(
            detected_at=detected_at,
            active_at=active_at,
            resolved_at=resolved_at,
            acknowledged_at=parsed_acknowledged_at,
            **durations,
        )
        return cls(**values)

    def as_dict(self) -> dict[str, Any]:
        """Return the exact public and persistent JSON-safe representation."""
        result = asdict(self)
        for key in ("detected_at", "active_at", "resolved_at", "acknowledged_at"):
            if result[key] is not None:
                result[key] = result[key].isoformat()
        return result


def _json_safe(value: Any) -> Any:
    """Copy arbitrary state values into deterministic JSON-compatible data."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return sorted(
            (_json_safe(item) for item in value),
            key=lambda item: json.dumps(item, sort_keys=True),
        )
    return str(value)


@dataclass(slots=True)
class AlertRecord:
    """Persisted alert state."""

    details: AlertDetails
    status: AlertStatus
    detected_at: datetime
    due_at: datetime
    delay: int
    active_since: datetime | None = None
    visible_at: datetime | None = None
    paused_at: datetime | None = None
    paused_seconds: float = 0.0
    acknowledged: bool = False
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None

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
        visible_at = data.get("visible_at")
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
        parsed_visible_at = (
            _parse_aware_datetime(visible_at, "visible_at")
            if visible_at is not None and status is AlertStatus.PENDING
            else None
        )
        paused_at = data.get("paused_at")
        parsed_paused_at = (
            _parse_aware_datetime(paused_at, "paused_at")
            if paused_at is not None
            else None
        )
        paused_seconds = data.get("paused_seconds", 0.0)
        if (
            isinstance(paused_seconds, bool)
            or not isinstance(paused_seconds, int | float)
            or not math.isfinite(paused_seconds)
            or paused_seconds < 0
        ):
            raise ValueError(
                "Alert paused_seconds must be a non-negative finite number"
            )
        if status is AlertStatus.ACTIVE and parsed_active_since is None:
            raise ValueError("Active alerts require active_since")
        if status is AlertStatus.PENDING and parsed_active_since is not None:
            raise ValueError("Pending alerts must not have active_since")
        if status is AlertStatus.ACTIVE and parsed_visible_at is not None:
            raise ValueError("Active alerts must not have visible_at")
        if status is AlertStatus.ACTIVE and parsed_paused_at is not None:
            raise ValueError("Active alerts cannot retain a monitoring pause")
        if parsed_active_since is not None and parsed_active_since.astimezone(
            UTC
        ) < detected_at.astimezone(UTC):
            raise ValueError("Alert active_since must not precede detected_at")
        if parsed_visible_at is not None:
            visible_utc = parsed_visible_at.astimezone(UTC)
            if visible_utc < detected_at.astimezone(UTC):
                raise ValueError("Alert visible_at must not precede detected_at")
            if visible_utc > due_at.astimezone(UTC):
                raise ValueError("Alert visible_at must not follow due_at")
        acknowledged = data.get("acknowledged", False)
        if not isinstance(acknowledged, bool):
            raise ValueError("Alert acknowledged must be a boolean")
        acknowledged_at = data.get("acknowledged_at")
        parsed_acknowledged_at = (
            _parse_aware_datetime(acknowledged_at, "acknowledged_at")
            if acknowledged_at is not None
            else None
        )
        acknowledged_by = data.get("acknowledged_by")
        if acknowledged_by is not None and (
            not isinstance(acknowledged_by, str) or not acknowledged_by
        ):
            raise ValueError("Alert acknowledged_by must be a non-empty string")
        if acknowledged:
            if status is not AlertStatus.ACTIVE:
                raise ValueError("Only active alerts can be acknowledged")
            if parsed_acknowledged_at is None:
                raise ValueError("Acknowledged alerts require acknowledged_at")
            if parsed_acknowledged_at.astimezone(UTC) < parsed_active_since.astimezone(
                UTC
            ):
                raise ValueError("Alert acknowledged_at must not precede active_since")
        elif parsed_acknowledged_at is not None or acknowledged_by is not None:
            raise ValueError("Unacknowledged alerts cannot retain acknowledgement data")
        return cls(
            details=AlertDetails.from_dict(data["details"]),
            status=status,
            detected_at=detected_at,
            due_at=due_at,
            delay=delay,
            active_since=parsed_active_since,
            visible_at=parsed_visible_at,
            paused_at=parsed_paused_at,
            paused_seconds=float(paused_seconds),
            acknowledged=acknowledged,
            acknowledged_at=parsed_acknowledged_at,
            acknowledged_by=acknowledged_by,
        )

    def as_storage_dict(self) -> dict[str, Any]:
        """Serialize for Home Assistant Store."""
        result = {
            "details": self.details.as_dict(),
            "status": self.status.value,
            "detected_at": self.detected_at.isoformat(),
            "due_at": self.due_at.isoformat(),
            "delay": self.delay,
            "active_since": (
                self.active_since.isoformat() if self.active_since else None
            ),
            "acknowledged": self.acknowledged,
        }
        if self.visible_at is not None:
            result["visible_at"] = self.visible_at.isoformat()
        if self.paused_at is not None:
            result["paused_at"] = self.paused_at.isoformat()
        if self.paused_seconds:
            result["paused_seconds"] = self.paused_seconds
        if self.acknowledged:
            result["acknowledged_at"] = self.acknowledged_at.isoformat()
            if self.acknowledged_by is not None:
                result["acknowledged_by"] = self.acknowledged_by
        return result

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
        if self.visible_at is not None:
            result["visible_at"] = self.visible_at.isoformat()
        if self.active_since is not None:
            result["active_since"] = self.active_since.isoformat()
            result["acknowledged"] = self.acknowledged
            if self.acknowledged:
                result["acknowledged_at"] = self.acknowledged_at.isoformat()
                if self.acknowledged_by is not None:
                    result["acknowledged_by"] = self.acknowledged_by
        return result

    def clear_acknowledgement(self) -> None:
        """Reset acknowledgement metadata without changing the alert lifecycle."""
        self.acknowledged = False
        self.acknowledged_at = None
        self.acknowledged_by = None


@dataclass(slots=True)
class Rule:
    """A comparison rule evaluated independently for every source entity."""

    id: str
    name: str
    entity_ids: list[str]
    operator: str
    value: str | int | float | bool | list[str | int | float | bool]
    duration: int
    enabled: bool = True
    source: str = "state"
    attribute: str | None = None
    message: str | None = None
    condition_template: str | None = None
    version: int = 2
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, data: dict[str, Any]) -> Rule:
        """Create a rule with an immutable random identifier."""
        return cls.from_dict({**data, "id": uuid4().hex})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Rule:
        """Deserialize, migrating the V1 entity_id field idempotently."""
        if not isinstance(data, dict):
            raise ValueError("Rule must be an object")
        normalized = dict(data)
        if "entity_ids" not in normalized and "entity_id" in normalized:
            normalized["entity_ids"] = [normalized["entity_id"]]
        normalized.pop("entity_id", None)
        required = {"id", "name", "entity_ids", "duration"}
        if normalized.get("source", "state") != "none":
            required.update(("operator", "value"))
        if missing := required - normalized.keys():
            raise ValueError(f"Missing rule field: {sorted(missing)[0]}")
        if normalized.get("source", "state") == "none":
            # Keep canonical internal values for the dataclass; as_dict omits them
            # and runtime evaluation bypasses them for Jinja-only rules.
            normalized["operator"] = "equals"
            normalized["value"] = ""
            normalized["attribute"] = None
        version = normalized.get("version", 2)
        if isinstance(version, int) and not isinstance(version, bool):
            normalized["version"] = max(version, 2)
        known = cls.__dataclass_fields__
        values = {
            key: normalized[key]
            for key in known
            if key in normalized and key != "extra"
        }
        values["extra"] = {
            key: value
            for key, value in normalized.items()
            if key not in known and key != "severity"
        }
        rule = cls(**values)
        rule.validate()
        return rule

    def validate(self) -> None:
        """Validate invariants shared by storage and the WebSocket API."""
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Rule id is required")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Rule name is required")
        if len(self.name) > 255:
            raise ValueError("Rule name is too long")
        if not isinstance(self.entity_ids, list) or not self.entity_ids:
            raise ValueError("Rule entity_ids must be a non-empty list")
        if any(not isinstance(entity_id, str) for entity_id in self.entity_ids):
            raise ValueError("Rule entity_ids must contain strings")
        if len(set(self.entity_ids)) != len(self.entity_ids):
            raise ValueError("An entity cannot be repeated in the same rule")
        if self.source not in VALUE_SOURCES:
            raise ValueError(f"Unsupported value source: {self.source}")
        if self.source == "attribute" and (
            not isinstance(self.attribute, str)
            or not self.attribute.strip()
            or len(self.attribute) > 255
        ):
            raise ValueError("Attribute is required for attribute rules")
        if self.source != "attribute" and self.attribute is not None:
            raise ValueError("Attribute must be empty for non-attribute rules")
        if self.message is not None and (
            not isinstance(self.message, str) or len(self.message) > 1024
        ):
            raise ValueError("Rule message must not exceed 1024 characters")
        if self.condition_template is not None and (
            not isinstance(self.condition_template, str)
            or not self.condition_template.strip()
            or len(self.condition_template) > 65_536
        ):
            raise ValueError(
                "Rule condition_template must be non-empty text of at most "
                "65536 characters"
            )
        if self.source == "none" and self.condition_template is None:
            raise ValueError("Rule condition_template is required for Jinja-only rules")
        if not isinstance(self.enabled, bool):
            raise ValueError("Rule enabled must be a boolean")
        if (
            isinstance(self.version, bool)
            or not isinstance(self.version, int)
            or self.version < 2
        ):
            raise ValueError("Rule version must be an integer of at least 2")
        if not isinstance(self.duration, int) or isinstance(self.duration, bool):
            raise ValueError("Duration must be an integer")
        if self.duration < 0 or self.duration > 31_536_000:
            raise ValueError("Duration must be between 0 and 31536000 seconds")
        if self.source == "none":
            return
        if self.operator not in OPERATORS:
            raise ValueError(f"Unsupported operator: {self.operator}")
        if self.operator in ("above", "below"):
            if isinstance(self.value, list) or safe_float(self.value) is None:
                raise ValueError("Numeric operators require one finite numeric value")
            return

        values = self.value if isinstance(self.value, list) else [self.value]
        if not values:
            raise ValueError("Text operators require at least one value")
        if any(
            value is None or not isinstance(value, str | int | float | bool)
            for value in values
        ):
            raise ValueError("Text operator values must be scalar")
        normalized = [normalize_scalar(value) for value in values]
        if any(not value for value in normalized):
            raise ValueError("Text operator values must not be empty")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Text operator values must be unique")

    def as_dict(self) -> dict[str, Any]:
        """Serialize a rule including forward-compatible fields."""
        result = asdict(self)
        extra = result.pop("extra", {})
        result.update(extra)
        if self.source == "none":
            result.pop("operator", None)
            result.pop("value", None)
        return {key: value for key, value in result.items() if value is not None}

    def matches(self, current: Any) -> bool:
        """Safely compare a current value to the configured value."""
        if self.source == "none":
            return True
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
        raw_values = self.value if isinstance(self.value, list) else [self.value]
        expected_texts = [normalize_scalar(value) for value in raw_values]
        if self.operator in ("equals", "not_equals"):
            positive_match = current_text in expected_texts
        else:
            positive_match = any(value in current_text for value in expected_texts)
        return (
            positive_match
            if self.operator in ("equals", "contains")
            else not positive_match
        )


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
    """Advance a due pending record at the actual transition time."""
    if record.status is not AlertStatus.PENDING or now.astimezone(
        UTC
    ) < record.due_at.astimezone(UTC):
        return False
    record.status = AlertStatus.ACTIVE
    record.active_since = now
    record.visible_at = None
    return True
