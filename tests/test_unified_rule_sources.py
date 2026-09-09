"""Unified operation targets and compatibility across configuration boundaries."""

from copy import deepcopy

import pytest
import yaml
from homeassistant.core import State

from custom_components.alert_manager.models import Rule
from custom_components.alert_manager.rule_evaluation import (
    evaluate_rule,
    rule_current_value,
)
from custom_components.alert_manager.storage import _migrate_config_shape
from custom_components.alert_manager.validation import validate_rule_payload
from custom_components.alert_manager.yaml_io import (
    dump_config_yaml,
    dump_rule_yaml,
    parse_config_yaml,
    parse_rule_yaml,
)


def payload(source, attribute=None):
    """Use distinguishable state/attribute values and preserve all rule options."""
    result = {
        "id": "stable-rule",
        "name": "Target",
        "entity_ids": ["sensor.test"],
        "label_ids": ["label"],
        "source": source,
        "attribute": attribute,
        "operator": "above",
        "value": 5,
        "duration": 30,
        "condition_template": "{{ true }}",
        "message": "{{ value }}",
        "enabled": True,
        "from_value": "10",
        "to_value": "20",
        "auto_resolve": 90,
    }
    if "transition" not in source:
        for key in ("from_value", "to_value", "auto_resolve"):
            result.pop(key)
    return result


@pytest.mark.parametrize(
    ("legacy", "unified", "attribute"),
    [
        ("state", "value", None),
        ("attribute", "value", "metrics.power"),
        ("variation", "value_variation", None),
        ("state_variation", "value_variation", None),
        ("attribute_variation", "value_variation", "metrics.power"),
        ("transition", "value_transition", None),
        ("attribute_transition", "value_transition", "metrics.power"),
    ],
)
def test_legacy_targets_migrate_once_through_storage_yaml_and_restore(
    legacy, unified, attribute
):
    raw = payload(legacy, "metrics.power")  # Stale for state-based sources.
    original = deepcopy(raw)
    rule = Rule.from_dict(raw)
    assert raw == original
    assert (rule.source, rule.attribute) == (unified, attribute)
    assert Rule.from_dict(rule.as_dict()).as_dict() == rule.as_dict()
    for key in ("id", "entity_ids", "label_ids", "duration", "message", "enabled"):
        assert rule.as_dict()[key] == raw[key]
    parsed = parse_rule_yaml(yaml.safe_dump(raw), rule_id=raw["id"])
    assert parsed.as_dict() == rule.as_dict()
    assert parse_rule_yaml(dump_rule_yaml(rule), rule_id=rule.id) == rule
    migrated, changed = _migrate_config_shape({"rules": [raw]})
    assert changed
    assert migrated["rules"][0]["source"] == unified
    assert migrated["rules"][0]["attribute"] == attribute
    assert _migrate_config_shape(migrated) == (migrated, False)
    restored = parse_config_yaml(dump_config_yaml(migrated))
    # Configuration YAML intentionally generates new IDs on import.
    assert restored["rules"][0]["source"] == unified
    assert restored["rules"][0].get("attribute") == attribute


@pytest.mark.parametrize("source", ["value", "value_variation", "value_transition"])
@pytest.mark.parametrize("attribute", [None, "", "  ", "metrics.power"])
def test_unified_target_reading_and_yaml_round_trip(source, attribute):
    rule = Rule.from_dict(payload(source, attribute))
    expected_attribute = attribute.strip() or None if attribute else None
    assert rule.attribute == expected_attribute
    state = State("sensor.test", "20", {"metrics": {"power": 10}})
    assert rule_current_value(rule, state) == (
        True,
        10 if expected_attribute else "20",
    )
    assert parse_rule_yaml(dump_rule_yaml(rule), rule_id=rule.id) == rule
    without_id = {
        key: value for key, value in payload(source, attribute).items() if key != "id"
    }
    assert validate_rule_payload(without_id).attribute == expected_attribute
    if expected_attribute:
        assert rule_current_value(rule, State("sensor.test", "20", {})) == (False, None)
    if source != "value_transition":
        result = evaluate_rule(
            rule, state, evaluate_condition=lambda value: (True, None), baseline=0
        )
        assert result.result is True
        assert result.raw_value == (
            10 if expected_attribute else (20 if source == "value_variation" else "20")
        )


@pytest.mark.parametrize(
    "source", ["attribute", "attribute_variation", "attribute_transition"]
)
@pytest.mark.parametrize("attribute", [None, "", "  ", 42])
def test_invalid_legacy_attribute_never_becomes_state(source, attribute):
    raw = payload(source, attribute)
    with pytest.raises(ValueError, match="Attribute is required"):
        Rule.from_dict(raw)
    with pytest.raises(ValueError, match="Attribute is required"):
        parse_rule_yaml(yaml.safe_dump(raw), rule_id=raw["id"])
    migrated, _ = _migrate_config_shape({"rules": [raw]})
    assert migrated["rules"][0]["source"] == source
    with pytest.raises(ValueError, match="Attribute is required"):
        Rule.from_dict(migrated["rules"][0])


@pytest.mark.parametrize("source", ["value", "value_variation"])
def test_missing_attribute_is_diagnostic_error_not_state_fallback(source):
    rule = Rule.from_dict(payload(source, "missing"))
    result = evaluate_rule(
        rule,
        State("sensor.test", "20", {}),
        evaluate_condition=lambda value: (True, None),
        baseline=0,
    )
    assert result.error_code == "attribute_not_found"
    assert result.result is None
