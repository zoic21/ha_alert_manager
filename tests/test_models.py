"""Pure model and validation tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.alert_manager.models import (
    AlertDetails,
    AlertRecord,
    AlertStatus,
    Rule,
    advance_record,
    safe_float,
)
from custom_components.alert_manager.validation import (
    validate_config,
    validate_rule_payload,
)


@pytest.mark.parametrize(
    ("operator", "current", "expected", "matches"),
    [
        ("equals", "off", "off", True),
        ("not_equals", "OL CHRG", "OL", True),
        ("above", "11.2", 9, True),
        ("below", "0.8", 1, True),
    ],
)
def test_rule_operators(operator, current, expected, matches):
    """equals, not_equals, above and below all use predictable comparison."""
    rule = Rule(
        id="rule-id",
        name="Test",
        entity_id="sensor.test",
        operator=operator,
        value=expected,
        duration=60,
    )
    assert rule.matches(current) is matches


def test_numeric_rule_rejects_non_finite_values():
    """Numeric comparisons never accept NaN, infinities or booleans."""
    assert safe_float("nan") is None
    assert safe_float("inf") is None
    assert safe_float(True) is None
    with pytest.raises(ValueError, match="finite numeric"):
        Rule(
            id="bad",
            name="Bad",
            entity_id="sensor.test",
            operator="above",
            value="not-number",
            duration=1,
        ).validate()


def test_pending_record_advances_at_due_time():
    """The pure state machine keeps detected_at/due_at stable."""
    now = datetime(2026, 8, 24, 12, tzinfo=UTC)
    details = AlertDetails(
        id="battery:sensor.test",
        type="battery",
        entity_id="sensor.test",
        name="Test",
        value=10,
        condition="Low",
    )
    record = AlertRecord.pending(details, 900, now)
    assert record.status is AlertStatus.PENDING
    assert not advance_record(record, now + timedelta(seconds=899))
    assert advance_record(record, now + timedelta(seconds=900))
    assert record.status is AlertStatus.ACTIVE
    assert record.active_since == record.due_at


def test_storage_round_trip_preserves_structured_data():
    """Persisted records retain typed dictionaries and datetimes."""
    now = datetime(2026, 8, 24, 12, tzinfo=UTC)
    details = AlertDetails(
        id="unavailable:sensor.test",
        type="unavailable",
        entity_id="sensor.test",
        name="Test",
        value="unavailable",
        condition="État indisponible",
        area="Cuisine",
    )
    restored = AlertRecord.from_dict(
        AlertRecord.pending(details, 15, now).as_storage_dict()
    )
    assert restored.details.as_dict()["area"] == "Cuisine"
    assert restored.detected_at == now


def test_frontend_payload_validation():
    """Backend validation rejects ids, operators, durations and rule id injection."""
    with pytest.raises(ValueError, match="generated"):
        validate_rule_payload(
            {
                "id": "chosen-by-client",
                "name": "Bad",
                "entity_id": "sensor.test",
                "operator": "equals",
                "value": "1",
                "duration": 10,
            }
        )
    with pytest.raises(ValueError, match="Invalid entity id"):
        validate_config({"excluded_entities": ["invalid"]})
    with pytest.raises(ValueError, match="integer"):
        validate_config({"global_delay": 2.5})
