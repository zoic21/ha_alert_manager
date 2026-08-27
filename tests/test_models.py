"""Pure model and validation tests."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from custom_components.alert_manager.const import INTEGRATION_VERSION
from custom_components.alert_manager.models import (
    AlertDetails,
    AlertHistoryEntry,
    AlertRecord,
    AlertStatus,
    Rule,
    advance_record,
    calculate_due_at,
    safe_float,
)
from custom_components.alert_manager.validation import (
    validate_config,
    validate_config_update,
    validate_rule_payload,
    validate_rule_update_fields,
)


@pytest.mark.parametrize(
    ("operator", "current", "expected", "matches"),
    [
        ("equals", "off", "off", True),
        ("not_equals", "OL CHRG", "OL", True),
        ("contains", "OL CHRG", "CHRG", True),
        ("not_contains", "OL CHRG", "ERROR", True),
        ("equals", "idle", ["off", "idle"], True),
        ("not_equals", "idle", ["off", "unknown"], True),
        ("contains", "OL CHRG", ["ERROR", "CHRG"], True),
        ("not_contains", "OL CHRG", ["ERROR", "WARN"], True),
        ("above", "11.2", 9, True),
        ("below", "0.8", 1, True),
    ],
)
def test_rule_operators(operator, current, expected, matches):
    """All scalar and multi-value operators use predictable comparison."""
    rule = Rule(
        id="rule-id",
        name="Test",
        entity_ids=["sensor.test"],
        operator=operator,
        value=expected,
        duration=60,
    )
    assert rule.matches(current) is matches


@pytest.mark.parametrize(
    ("operator", "current", "expected"),
    [
        ("equals", "idle", ["idle", "off"]),
        ("not_equals", "idle", ["idle", "off"]),
        ("contains", "OL CHRG", ["CHRG", "ERROR"]),
        ("not_contains", "OL CHRG", ["CHRG", "ERROR"]),
    ],
)
def test_negative_text_operators_are_the_inverse_of_positive_operators(
    operator, current, expected
):
    """Negative operators only match when none of the configured values match."""
    rule = Rule(
        id="rule-id",
        name="Test",
        entity_ids=["sensor.test"],
        operator=operator,
        value=expected,
        duration=60,
    )
    expected_match = operator in ("equals", "contains")
    assert rule.matches(current) is expected_match


def test_text_rule_values_must_be_non_empty_unique_scalars():
    """Lists cannot contain empty, duplicate or structured comparison values."""
    for value in (
        [],
        ["on", " on "],
        ["on", {"nested": True}],
        [date(2026, 8, 25)],
    ):
        with pytest.raises(ValueError, match="Text operators?"):
            Rule(
                id="bad",
                name="Bad",
                entity_ids=["sensor.test"],
                operator="contains",
                value=value,
                duration=1,
            ).validate()


def test_incomplete_rule_payload_has_a_validation_error():
    """A malformed visual payload never leaks a constructor TypeError."""
    with pytest.raises(ValueError, match="Missing rule field: duration"):
        validate_rule_payload(
            {
                "name": "Incomplete",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "on",
            }
        )


def test_numeric_rule_rejects_non_finite_values():
    """Numeric comparisons never accept NaN, infinities or booleans."""
    assert safe_float("nan") is None
    assert safe_float("inf") is None
    assert safe_float(True) is None
    with pytest.raises(ValueError, match="finite numeric"):
        Rule(
            id="bad",
            name="Bad",
            entity_ids=["sensor.test"],
            operator="above",
            value="not-number",
            duration=1,
        ).validate()
    with pytest.raises(ValueError, match="one finite numeric"):
        Rule(
            id="bad-list",
            name="Bad",
            entity_ids=["sensor.test"],
            operator="above",
            value=[1, 2],
            duration=1,
        ).validate()


def test_pending_record_advances_at_due_time():
    """The state machine records the real activation time, even if evaluated late."""
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
    activated_at = now + timedelta(seconds=930)
    assert advance_record(record, activated_at)
    assert record.status is AlertStatus.ACTIVE
    assert record.active_since == activated_at


def test_delay_is_elapsed_time_across_daylight_saving_change():
    """A 15-minute delay remains 15 elapsed minutes across a DST fallback."""
    paris = ZoneInfo("Europe/Paris")
    detected_at = datetime(2026, 10, 25, 2, 55, tzinfo=paris, fold=0)
    due_at = calculate_due_at(detected_at, 900)
    assert due_at.fold == 1
    assert due_at.hour == 2
    assert due_at.minute == 10
    assert due_at.astimezone(UTC) - detected_at.astimezone(UTC) == timedelta(
        seconds=900
    )


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
        device_id="a" * 32,
        area="Cuisine",
    )
    record = AlertRecord.pending(details, 15, now)
    record.paused_at = now + timedelta(seconds=5)
    record.paused_seconds = 30.5
    restored = AlertRecord.from_dict(record.as_storage_dict())
    assert restored.details.as_dict()["area"] == "Cuisine"
    assert restored.details.as_dict()["device_id"] == "a" * 32
    assert restored.detected_at == now
    assert restored.paused_at == now + timedelta(seconds=5)
    assert restored.paused_seconds == 30.5
    assert "paused_at" not in restored.as_public_dict()
    assert "paused_seconds" not in restored.as_public_dict()


def test_history_preserves_integration_and_survives_a_backward_clock_step():
    """Resolution stays loadable when the clock moves behind acknowledgement."""
    detected_at = datetime(2026, 8, 24, 12, tzinfo=UTC)
    details = AlertDetails(
        id="unavailable:sensor.test",
        type="unavailable",
        entity_id="sensor.test",
        name="Test",
        value="unavailable",
        condition="Unavailable",
        integration="mqtt",
    )
    record = AlertRecord.pending(details, 0, detected_at)
    assert advance_record(record, detected_at)
    record.acknowledged = True
    record.acknowledged_at = detected_at + timedelta(minutes=2)
    record.acknowledged_by = "Loïc"

    history = AlertHistoryEntry.resolved(
        record,
        detected_at + timedelta(minutes=1),
    )

    assert history.integration == "mqtt"
    assert history.resolved_at == record.acknowledged_at
    assert AlertHistoryEntry.from_dict(history.as_dict()) == history


def test_legacy_severity_is_removed_from_stored_alerts_and_rules():
    """Beta data loads without exposing the removed alert-level concept."""
    details = AlertDetails.from_dict(
        {
            "id": "unavailable:sensor.test",
            "type": "unavailable",
            "entity_id": "sensor.test",
            "name": "Test",
            "value": "unavailable",
            "condition": "État indisponible",
            "severity": "critical",
        }
    )
    assert "severity" not in details.as_dict()

    rule = Rule.from_dict(
        {
            "id": "legacy-rule",
            "name": "Legacy",
            "entity_id": "sensor.test",
            "operator": "equals",
            "value": "on",
            "duration": 60,
            "severity": "warning",
        }
    )
    assert "severity" not in rule.as_dict()
    assert rule.entity_ids == ["sensor.test"]
    assert "entity_id" not in rule.as_dict()
    assert rule.version == 2

    normalized = validate_config({"rules": [rule.as_dict()]})
    assert "severity" not in normalized["rules"][0]


def test_storage_rejects_naive_dates_and_incomplete_details():
    """Corrupt persisted timestamps and required fields are ignored safely."""
    now = datetime(2026, 8, 24, 12, tzinfo=UTC)
    record = AlertRecord.pending(
        AlertDetails(
            id="battery:sensor.test",
            type="battery",
            entity_id="sensor.test",
            name="Test",
            value=10,
            condition="Low",
        ),
        60,
        now,
    ).as_storage_dict()
    record["detected_at"] = "2026-08-24T12:00:00"
    with pytest.raises(ValueError, match="timezone"):
        AlertRecord.from_dict(record)

    record["detected_at"] = now.isoformat()
    del record["details"]["name"]
    with pytest.raises(ValueError, match="name"):
        AlertRecord.from_dict(record)


def test_frontend_payload_validation():
    """Backend validation rejects ids, operators, durations and rule id injection."""
    with pytest.raises(ValueError, match="generated"):
        validate_rule_payload(
            {
                "id": "chosen-by-client",
                "name": "Bad",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "1",
                "duration": 10,
            }
        )
    with pytest.raises(ValueError, match="Invalid entity id"):
        validate_config({"excluded_entities": ["invalid"]})
    with pytest.raises(ValueError, match="integer"):
        validate_config({"global_delay": 2.5})


def test_unknown_frontend_fields_are_rejected():
    """Typos and arbitrary client fields fail instead of being silently ignored."""
    with pytest.raises(ValueError, match="Unknown configuration field"):
        validate_config_update({"global_delai": 60})
    with pytest.raises(ValueError, match="Unknown automatic.battery field"):
        validate_config_update({"automatic": {"battery": {"seuil": 10}}})
    with pytest.raises(ValueError, match="Unknown rule field"):
        validate_rule_payload(
            {
                "name": "Bad field",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "on",
                "duration": 60,
                "template": "{{ dangerous }}",
            }
        )
    with pytest.raises(ValueError, match="Unknown rule field"):
        validate_rule_update_fields({"template": "{{ dangerous }}"})
    with pytest.raises(ValueError, match="Unknown rule field: severity"):
        validate_rule_payload(
            {
                "name": "No levels",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "on",
                "duration": 60,
                "severity": "critical",
            }
        )


def test_rule_entity_ids_must_be_unique():
    """One source cannot be evaluated twice inside the same rule."""
    with pytest.raises(ValueError, match="repeated"):
        validate_rule_payload(
            {
                "name": "Duplicate",
                "entity_ids": ["sensor.test", "sensor.test"],
                "operator": "equals",
                "value": "on",
                "duration": 60,
            }
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"name": "   "}, "name"),
        ({"enabled": "false"}, "enabled"),
        ({"version": True}, "version"),
        ({"source": "attribute", "attribute": 42}, "Attribute"),
        ({"message": 42}, "message"),
    ],
)
def test_rule_metadata_types_are_strict(changes, message):
    """Malformed rule metadata cannot become truthy or fail during evaluation."""
    rule = {
        "id": "strict-rule",
        "name": "Strict",
        "entity_ids": ["sensor.test"],
        "operator": "equals",
        "value": "on",
        "duration": 60,
    }

    with pytest.raises(ValueError, match=message):
        Rule.from_dict({**rule, **changes})


def test_backend_and_frontend_versions_stay_in_sync():
    """The panel cache key and distributable metadata use one release version."""
    root = Path(__file__).parents[1]
    manifest = json.loads(
        (root / "custom_components/alert_manager/manifest.json").read_text()
    )
    package = json.loads((root / "package.json").read_text())
    assert manifest["version"] == package["version"] == INTEGRATION_VERSION
