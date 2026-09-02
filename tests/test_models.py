"""Pure model and validation tests."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from custom_components.alert_manager.const import (
    DEFAULT_CONFIG,
    INTEGRATION_VERSION,
    MAX_RULE_CONDITION_TEMPLATE_LENGTH,
    MAX_RULE_ENTITY_IDS,
    MAX_RULE_MESSAGE_LENGTH,
    MAX_RULE_NAME_LENGTH,
    MAX_RULES,
)
from custom_components.alert_manager.models import (
    AlertDetails,
    AlertHistoryEntry,
    AlertRecord,
    AlertStatus,
    Rule,
    advance_record,
    calculate_due_at,
    extract_attribute_value,
    safe_float,
)
from custom_components.alert_manager.storage import (
    _migrate_alert_value_sources,
    _migrate_config_shape,
)
from custom_components.alert_manager.validation import (
    validate_config,
    validate_config_update,
    validate_rule_payload,
    validate_rule_update_fields,
)


def test_execution_errors_pack_alerts_without_delay_by_default():
    """Only execution failures bypass the general 900-second default delay."""
    assert DEFAULT_CONFIG["global_delay"] == 900
    assert DEFAULT_CONFIG["automatic"]["execution_errors"]["delay"] == 0


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
        ("between", "10", [10, 20], True),
        ("between", "20", [10, 20], True),
        ("outside", "9.9", [10, 20], True),
        ("outside", "20.1", [10, 20], True),
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


@pytest.mark.parametrize(
    ("operator", "current", "expected", "matches"),
    [
        ("equals", ["enjoy", "redox"], ["redox", "flow"], True),
        ("not_equals", ["enjoy", "redox"], ["redox", "flow"], False),
        ("contains", ["all_good", "redox_warning"], ["redox", "flow"], True),
        ("not_contains", ["all_good", "redox_warning"], ["redox", "flow"], False),
        ("not_equals", ["enjoy", "redox"], ["flow", "ph"], True),
        ("outside", [15, 21], [10, 20], True),
    ],
)
def test_rule_operators_compare_all_extracted_values(
    operator, current, expected, matches
):
    """Positive operators match any extracted value and negatives invert that."""
    rule = Rule(
        id="array-rule",
        name="Array",
        entity_ids=["sensor.pool"],
        operator=operator,
        value=expected,
        duration=0,
        source="attribute",
        attribute="data.*.key",
    )
    assert rule.matches(current) is matches


def test_attribute_path_extracts_array_fields_and_preserves_exact_attribute_names():
    """Dotted wildcard paths flatten matching fields without breaking exact keys."""
    attributes = {
        "data": [
            {"key": "enjoy", "code": "8.33"},
            {"key": "redox", "code": "8.34"},
            {"code": "8.35"},
            "invalid",
        ],
        "data.*.key": "literal",
    }
    assert extract_attribute_value(attributes, "data.*.key") == (True, "literal")
    del attributes["data.*.key"]
    assert extract_attribute_value(attributes, "data.*.key") == (
        True,
        ["enjoy", "redox"],
    )
    assert extract_attribute_value(attributes, "data.*.missing") == (False, None)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ([1], "exactly two"),
        ([1, 2, 3], "exactly two"),
        (["low", 2], "finite numeric"),
        ([3, 2], "must not exceed"),
        ([1, "nan"], "finite numeric"),
    ],
)
def test_range_rule_rejects_missing_invalid_or_inverted_bounds(value, message):
    """Range rules accept exactly two ordered finite numeric bounds."""
    with pytest.raises(ValueError, match=message):
        Rule(
            id="bad-range",
            name="Bad range",
            entity_ids=["sensor.test"],
            operator="between",
            value=value,
            duration=0,
        ).validate()


def test_selected_value_unchanged_rule_omits_comparison_value():
    """No-change is an operator for state or attribute sources without a value."""
    rule = validate_rule_payload(
        {
            "name": "Stable state",
            "entity_ids": ["sensor.test"],
            "source": "state",
            "operator": "unchanged",
            "duration": 60,
        }
    )
    assert rule.operator == "unchanged"
    assert rule.matches("anything") is True
    assert "value" not in rule.as_dict()


@pytest.mark.parametrize("attribute", ["*.key", "data.*key", "data..*.key"])
def test_attribute_wildcard_path_rejects_ambiguous_syntax(attribute):
    """The wildcard is only accepted as a complete non-root dotted segment."""
    with pytest.raises(ValueError, match="wildcard paths"):
        Rule(
            id="bad-path",
            name="Bad path",
            entity_ids=["sensor.test"],
            operator="equals",
            value="value",
            duration=0,
            source="attribute",
            attribute=attribute,
        ).validate()


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


def test_jinja_only_rule_requires_only_its_template_and_duration():
    """Pure Jinja rules have no comparison but keep strict template validation."""
    rule = validate_rule_payload(
        {
            "name": "Pure Jinja",
            "entity_ids": ["sensor.test"],
            "source": "jinja",
            "duration": 60,
            "condition_template": "{{ value == 'ready' }}",
        }
    )

    assert rule.source == "jinja"
    assert rule.operator == "equals"
    assert rule.value == ""
    assert rule.matches("anything") is True
    assert "operator" not in rule.as_dict()
    assert "value" not in rule.as_dict()


def test_jinja_only_rule_rejects_a_missing_template_without_affecting_normal_rules():
    """Jinja is mandatory only for the explicit comparison-free source."""
    with pytest.raises(ValueError, match="condition_template is required"):
        validate_rule_payload(
            {
                "name": "Missing Jinja",
                "entity_ids": ["sensor.test"],
                "source": "jinja",
                "duration": 0,
            }
        )

    normal = validate_rule_payload(
        {
            "name": "Normal comparison",
            "entity_ids": ["sensor.test"],
            "source": "state",
            "operator": "equals",
            "value": "on",
            "duration": 0,
        }
    )
    assert normal.condition_template is None


def test_variation_rule_requires_a_starting_condition_and_numeric_operator():
    """Variation windows always have an explicit start gate and numeric threshold."""
    with pytest.raises(ValueError, match="required for Variation rules"):
        validate_rule_payload(
            {
                "name": "Missing start gate",
                "entity_ids": ["sensor.test"],
                "source": "state_variation",
                "operator": "above",
                "value": 5,
                "duration": 0,
            }
        )

    rule = validate_rule_payload(
        {
            "name": "Consumption variation",
            "entity_ids": ["sensor.test"],
            "source": "state_variation",
            "operator": "outside",
            "value": [-5, 5],
            "duration": 60,
            "condition_template": "{{ true }}",
        }
    )
    assert rule.source == "state_variation"
    assert rule.matches(6) is True

    with pytest.raises(ValueError, match="numeric operator"):
        validate_rule_payload(
            {
                "name": "Invalid variation",
                "entity_ids": ["sensor.test"],
                "source": "state_variation",
                "operator": "equals",
                "value": 5,
                "duration": 0,
                "condition_template": "{{ true }}",
            }
        )

    attribute_rule = validate_rule_payload(
        {
            "name": "Attribute variation",
            "entity_ids": ["sensor.test"],
            "source": "attribute_variation",
            "attribute": "metrics.power",
            "operator": "above",
            "value": 10,
            "duration": 0,
            "condition_template": "{{ true }}",
        }
    )
    assert attribute_rule.attribute == "metrics.power"

    with pytest.raises(ValueError, match="does not support wildcard"):
        validate_rule_payload(
            {
                "name": "Ambiguous attribute variation",
                "entity_ids": ["sensor.test"],
                "source": "attribute_variation",
                "attribute": "metrics.*.power",
                "operator": "above",
                "value": 10,
                "duration": 0,
                "condition_template": "{{ true }}",
            }
        )


def test_legacy_none_source_is_normalized_to_jinja() -> None:
    """Stored pre-rename rules remain readable but never stay legacy internally."""
    rule = Rule.from_dict(
        {
            "id": "legacy-jinja",
            "name": "Legacy Jinja",
            "entity_ids": ["sensor.test"],
            "source": "none",
            "duration": 0,
            "condition_template": "{{ true }}",
        }
    )

    assert rule.source == "jinja"
    assert rule.as_dict()["source"] == "jinja"

    variation = Rule.from_dict(
        {
            "id": "legacy-variation",
            "name": "Legacy variation",
            "entity_ids": ["sensor.test"],
            "source": "variation",
            "operator": "above",
            "value": 5,
            "duration": 0,
            "condition_template": "{{ true }}",
        }
    )
    assert variation.source == "state_variation"
    assert variation.as_dict()["source"] == "state_variation"


def test_storage_migration_renames_legacy_sources_idempotently() -> None:
    """Configuration and active records are rewritten once to the canonical source."""
    stored_config = {
        "rules": [
            {
                "id": "legacy-jinja",
                "name": "Legacy Jinja",
                "entity_ids": ["sensor.test"],
                "source": "none",
                "duration": 0,
                "condition_template": "{{ true }}",
                "version": 2,
            },
            {
                "id": "legacy-variation",
                "name": "Legacy variation",
                "entity_ids": ["sensor.power"],
                "source": "variation",
                "operator": "above",
                "value": 5,
                "duration": 0,
                "condition_template": "{{ true }}",
                "version": 2,
            },
        ]
    }
    migrated, changed = _migrate_config_shape(stored_config)
    assert changed is True
    assert migrated["rules"][0]["source"] == "jinja"
    assert migrated["rules"][1]["source"] == "state_variation"
    assert migrated["rules"][0]["update_message_when_active"] is False
    remigrated, changed_again = _migrate_config_shape(migrated)
    assert changed_again is False
    assert remigrated["rules"][0]["source"] == "jinja"
    assert remigrated["rules"][1]["source"] == "state_variation"

    alerts = {
        "rule:test:sensor.test": {"details": {"source": "none"}},
        "rule:variation:sensor.power": {"details": {"source": "variation"}},
    }
    assert _migrate_alert_value_sources(alerts) is True
    assert alerts["rule:test:sensor.test"]["details"]["source"] == "jinja"
    assert (
        alerts["rule:variation:sensor.power"]["details"]["source"] == "state_variation"
    )
    assert _migrate_alert_value_sources(alerts) is False


def test_update_message_when_active_must_be_boolean() -> None:
    """The live message option cannot be enabled through truthy string values."""
    with pytest.raises(ValueError, match="must be a boolean"):
        validate_rule_payload(
            {
                "name": "Invalid live message option",
                "entity_ids": ["sensor.test"],
                "source": "state",
                "operator": "equals",
                "value": "on",
                "duration": 0,
                "update_message_when_active": "true",
            }
        )


def test_unchanged_rule_has_no_comparison_and_keeps_jinja_optional():
    """Inactivity rules require only entities and a duration."""
    rule = validate_rule_payload(
        {
            "name": "No updates",
            "entity_ids": ["sensor.test"],
            "source": "unchanged",
            "duration": 300,
        }
    )

    assert rule.source == "unchanged"
    assert rule.operator == "equals"
    assert rule.value == ""
    assert rule.condition_template is None
    assert rule.matches("anything") is True
    assert "operator" not in rule.as_dict()
    assert "value" not in rule.as_dict()


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
    record.visible_at = now + timedelta(seconds=10)
    assert record.status is AlertStatus.PENDING
    assert not advance_record(record, now + timedelta(seconds=899))
    activated_at = now + timedelta(seconds=930)
    assert advance_record(record, activated_at)
    assert record.status is AlertStatus.ACTIVE
    assert record.active_since == activated_at
    assert record.visible_at is None


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
    record.visible_at = now + timedelta(seconds=10)
    record.paused_at = now + timedelta(seconds=5)
    record.paused_seconds = 30.5
    restored = AlertRecord.from_dict(record.as_storage_dict())
    assert restored.details.as_dict()["area"] == "Cuisine"
    assert restored.details.as_dict()["device_id"] == "a" * 32
    assert restored.detected_at == now
    assert restored.paused_at == now + timedelta(seconds=5)
    assert restored.paused_seconds == 30.5
    assert restored.visible_at == now + timedelta(seconds=10)
    assert (
        restored.as_public_dict()["visible_at"]
        == (now + timedelta(seconds=10)).isoformat()
    )
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
    assert (
        validate_config({"coherence_schedule": "weekly"})["coherence_schedule"]
        == "weekly"
    )
    with pytest.raises(ValueError, match="coherence_schedule"):
        validate_config({"coherence_schedule": "hourly"})
    config = validate_config(
        {
            "coherence_scan_esphome": False,
            "coherence_ignored_entity_references": [" Toto.Plop ", "toto.plop"],
        }
    )
    assert config["coherence_scan_esphome"] is False
    assert config["coherence_ignored_entity_references"] == ["toto.plop"]
    with pytest.raises(ValueError, match="coherence_scan_esphome"):
        validate_config({"coherence_scan_esphome": "false"})
    with pytest.raises(ValueError, match="invalid reference"):
        validate_config({"coherence_ignored_entity_references": ["not valid"]})


def test_only_coherence_sensor_is_allowed_as_an_alert_manager_rule_source():
    """The loop-safe result sensor is the sole self-monitoring exception."""
    allowed = validate_rule_payload(
        {
            "name": "Coherence",
            "entity_ids": ["sensor.alert_manager_coherence_issue"],
            "operator": "above",
            "value": 0,
            "duration": 0,
        }
    )
    assert allowed.entity_ids == ["sensor.alert_manager_coherence_issue"]

    with pytest.raises(ValueError, match="Alert Manager entities"):
        validate_rule_payload(
            {
                "name": "Loop",
                "entity_ids": ["sensor.alert_manager_main_active"],
                "operator": "above",
                "value": 0,
                "duration": 0,
            }
        )


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


def test_pack_declared_device_number_map_is_strictly_validated():
    """Pack metadata fields reject malformed device IDs and numeric values."""
    device_id = "a" * 32
    normalized = validate_config(
        {"automatic": {"battery": {"device_thresholds": {device_id: "22"}}}}
    )
    assert normalized["automatic"]["battery"]["device_thresholds"] == {device_id: 22.0}
    with pytest.raises(ValueError, match="invalid device id"):
        validate_config(
            {"automatic": {"battery": {"device_thresholds": {"invalid": 20}}}}
        )
    with pytest.raises(ValueError, match="finite number"):
        validate_config(
            {"automatic": {"battery": {"device_thresholds": {device_id: float("nan")}}}}
        )


def test_pack_declared_entity_number_map_is_strictly_validated():
    """Entity maps enforce their declared domains, bounds and integer step."""
    normalized = validate_config(
        {
            "automatic": {
                "execution_errors": {"failure_thresholds": {"automation.test": "3"}}
            }
        }
    )
    assert normalized["automatic"]["execution_errors"]["failure_thresholds"] == {
        "automation.test": 3
    }
    script = validate_config(
        {
            "automatic": {
                "execution_errors": {"failure_thresholds": {"script.test": "4"}}
            }
        }
    )
    assert script["automatic"]["execution_errors"]["failure_thresholds"] == {
        "script.test": 4
    }
    with pytest.raises(ValueError, match="outside the automation, script domains"):
        validate_config(
            {
                "automatic": {
                    "execution_errors": {"failure_thresholds": {"sensor.test": 3}}
                }
            }
        )
    with pytest.raises(ValueError, match="must be an integer"):
        validate_config(
            {
                "automatic": {
                    "execution_errors": {"failure_thresholds": {"automation.test": 2.5}}
                }
            }
        )
    with pytest.raises(ValueError, match="between 1 and 100"):
        validate_config(
            {
                "automatic": {
                    "execution_errors": {"failure_thresholds": {"automation.test": 0}}
                }
            }
        )


def test_pack_source_files_have_no_localized_fallback_text():
    """Pack modules contain logic and translation keys, never localized prose."""
    pack_directory = Path(__file__).parents[1] / "custom_components/alert_manager/packs"
    for path in pack_directory.glob("*.py"):
        assert path.read_text().isascii(), path


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


def test_rule_collection_and_entity_counts_are_bounded():
    """Large admin payloads are rejected before every item is traversed."""
    with pytest.raises(ValueError, match=f"at most {MAX_RULES}"):
        validate_config({"rules": [{}] * (MAX_RULES + 1)})

    with pytest.raises(ValueError, match=f"at most {MAX_RULE_ENTITY_IDS}"):
        validate_rule_payload(
            {
                "name": "Too many entities",
                "entity_ids": ["sensor.test"] * (MAX_RULE_ENTITY_IDS + 1),
                "operator": "equals",
                "value": "on",
                "duration": 60,
            }
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("name", "x" * (MAX_RULE_NAME_LENGTH + 1), "name is too long"),
        (
            "message",
            "x" * (MAX_RULE_MESSAGE_LENGTH + 1),
            f"must not exceed {MAX_RULE_MESSAGE_LENGTH}",
        ),
        (
            "condition_template",
            "x" * (MAX_RULE_CONDITION_TEMPLATE_LENGTH + 1),
            f"at most {MAX_RULE_CONDITION_TEMPLATE_LENGTH}",
        ),
    ],
)
def test_rule_text_fields_are_bounded(field, value, message):
    """Every user-controlled rule text field has an explicit size limit."""
    payload = {
        "name": "Bounded rule",
        "entity_ids": ["sensor.test"],
        "operator": "equals",
        "value": "on",
        "duration": 60,
        field: value,
    }
    with pytest.raises(ValueError, match=message):
        validate_rule_payload(payload)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"name": "   "}, "name"),
        ({"enabled": "false"}, "enabled"),
        ({"version": True}, "version"),
        ({"source": "attribute", "attribute": 42}, "Attribute"),
        ({"message": 42}, "message"),
        ({"condition_template": ""}, "condition_template"),
        ({"condition_template": 42}, "condition_template"),
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
