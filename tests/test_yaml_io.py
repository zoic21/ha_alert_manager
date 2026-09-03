"""YAML rule and complete configuration interchange tests."""

from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from custom_components.alert_manager.const import DEFAULT_CONFIG
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertStatus
from custom_components.alert_manager.yaml_io import (
    MAX_YAML_SIZE,
    dump_config_yaml,
    dump_rule_yaml,
    parse_config_yaml,
    parse_rule_yaml,
)


def run(coroutine):
    """Run one manager coroutine with the isolated test event loop."""
    return asyncio.run(coroutine)


def rule_yaml(*, name: str = "Temperature") -> str:
    """Return a complete editable Alert Manager rule YAML."""
    return f"""name: {name}
enabled: true
entity_ids:
  - sensor.bay_temperature
source: state
operator: above
value: 33
duration: 900
message: null
"""


def test_rule_yaml_serialization_round_trip() -> None:
    """The editable YAML has no mutable id and parses through shared validation."""
    rule = parse_rule_yaml(rule_yaml())
    rendered = dump_rule_yaml(rule)
    assert "id:" not in rendered
    parsed = parse_rule_yaml(rendered)
    assert parsed.name == "Temperature"
    assert parsed.entity_ids == ["sensor.bay_temperature"]
    assert parsed.value == 33


def test_jinja_only_rule_yaml_omits_irrelevant_comparison_fields() -> None:
    """Pure Jinja YAML remains concise and round-trips through shared validation."""
    rule = parse_rule_yaml(
        """name: Pure Jinja
enabled: true
entity_ids:
  - sensor.bay_temperature
source: jinja
duration: 30
message: null
update_message_when_active: true
condition_template: "{{ value | float(0) > 33 }}"
"""
    )

    rendered = dump_rule_yaml(rule)
    assert "operator:" not in rendered
    assert "value:" not in rendered
    assert "source: jinja" in rendered
    assert "update_message_when_active: true" in rendered
    parsed = parse_rule_yaml(rendered)
    assert parsed.source == "jinja"
    assert parsed.update_message_when_active is True
    assert parsed.condition_template == "{{ value | float(0) > 33 }}"


def test_legacy_none_source_yaml_is_imported_and_exported_as_jinja() -> None:
    """Existing YAML remains importable while every new export is canonical."""
    legacy = """name: Legacy Jinja
enabled: true
entity_ids:
  - sensor.bay_temperature
source: none
duration: 0
message: null
condition_template: "{{ true }}"
"""

    parsed = parse_rule_yaml(legacy)
    assert parsed.source == "jinja"
    rendered = dump_rule_yaml(parsed)
    assert "source: jinja" in rendered
    assert "source: none" not in rendered
    assert "update_message_when_active: false" in rendered


def test_unchanged_rule_yaml_keeps_jinja_optional_and_omits_comparison() -> None:
    """No-change YAML contains only fields that affect inactivity monitoring."""
    rule = parse_rule_yaml(
        """name: No updates
enabled: true
entity_ids:
  - sensor.bay_temperature
source: unchanged
duration: 300
message: null
condition_template: null
"""
    )

    rendered = dump_rule_yaml(rule)
    assert "operator:" not in rendered
    assert "value:" not in rendered
    parsed = parse_rule_yaml(rendered)
    assert parsed.source == "unchanged"
    assert parsed.condition_template is None


def test_variation_rule_yaml_requires_and_preserves_its_starting_condition() -> None:
    """Variation YAML exposes the gate that anchors its persisted reference."""
    raw = """name: Energy variation
enabled: true
entity_ids:
  - sensor.energy
source: state_variation
operator: above
value: 2.5
duration: 300
message: null
condition_template: "{{ is_state('binary_sensor.cycle', 'on') }}"
"""
    rule = parse_rule_yaml(raw)
    rendered = dump_rule_yaml(rule)

    assert rule.source == "state_variation"
    assert rule.condition_template == "{{ is_state('binary_sensor.cycle', 'on') }}"
    assert "source: state_variation" in rendered
    assert "operator: above" in rendered
    assert "condition_template:" in rendered

    with pytest.raises(ValueError, match="required for Variation rules"):
        parse_rule_yaml(
            raw.replace(
                "condition_template: \"{{ is_state('binary_sensor.cycle', 'on') }}\"",
                "condition_template: null",
            )
        )

    attribute_rule = parse_rule_yaml(
        """name: Attribute energy variation
enabled: true
entity_ids:
  - sensor.energy
source: attribute_variation
attribute: metrics.power
operator: above
value: 2.5
duration: 300
message: null
condition_template: "{{ is_state('binary_sensor.cycle', 'on') }}"
"""
    )
    attribute_rendered = dump_rule_yaml(attribute_rule)
    assert attribute_rule.source == "attribute_variation"
    assert attribute_rule.attribute == "metrics.power"
    assert "source: attribute_variation" in attribute_rendered
    assert "attribute: metrics.power" in attribute_rendered


def test_legacy_variation_yaml_is_exported_as_state_variation() -> None:
    """The short-lived variation name migrates without losing its semantics."""
    rule = parse_rule_yaml(
        """name: Legacy variation
enabled: true
entity_ids:
  - sensor.energy
source: variation
operator: above
value: 2.5
duration: 300
message: null
condition_template: "{{ true }}"
"""
    )
    assert rule.source == "state_variation"
    assert "source: state_variation" in dump_rule_yaml(rule)


def test_range_and_selected_unchanged_yaml_shapes_are_strict() -> None:
    """Ranges keep two bounds while selected no-change omits value."""
    range_rule = parse_rule_yaml(
        """name: Temperature range
enabled: true
entity_ids:
  - sensor.temperature
source: state
operator: between
value:
  - 10
  - 20
duration: 60
message: null
condition_template: null
"""
    )
    assert range_rule.value == [10, 20]
    assert "value:\n- 10\n- 20" in dump_rule_yaml(range_rule)

    unchanged_rule = parse_rule_yaml(
        """name: Stable attribute
enabled: true
entity_ids:
  - sensor.pool
source: attribute
attribute: data.*.key
operator: unchanged
duration: 60
message: null
condition_template: null
"""
    )
    rendered = dump_rule_yaml(unchanged_rule)
    assert "operator: unchanged" in rendered
    assert "value:" not in rendered


def test_rule_yaml_syntax_and_business_errors_are_clear() -> None:
    """Syntax and rule-model failures are distinct safe validation failures."""
    with pytest.raises(ValueError, match="Invalid YAML"):
        parse_rule_yaml("name: [broken")
    with pytest.raises(ValueError, match="Attribute is required"):
        parse_rule_yaml(rule_yaml().replace("source: state", "source: attribute"))


@pytest.mark.parametrize(
    "raw_yaml",
    (
        "1: invalid\n",
        "? [invalid, mapping, key]\n: value\n",
        rule_yaml()
        .replace("value: 33", "value: 2026-08-25")
        .replace("operator: above", "operator: equals"),
    ),
)
def test_rule_yaml_rejects_non_string_keys_and_non_json_scalars(raw_yaml) -> None:
    """Unusual safe-YAML values become validation errors, not server failures."""
    with pytest.raises(ValueError):
        parse_rule_yaml(raw_yaml)


def test_yaml_input_size_is_bounded() -> None:
    """A WebSocket client cannot submit an unbounded YAML document."""
    with pytest.raises(ValueError, match="must not exceed"):
        parse_rule_yaml(" " * (MAX_YAML_SIZE + 1))


def test_yaml_rejects_invalid_unicode() -> None:
    """Malformed surrogate text is returned as a normal validation error."""
    with pytest.raises(ValueError, match="valid Unicode"):
        parse_rule_yaml("\ud800")


def test_config_export_is_deterministic_and_reimportable() -> None:
    """The complete YAML export has stable ordering and backend-owned rule ids."""
    config = deepcopy(DEFAULT_CONFIG)
    config["rules"] = [
        {
            "id": "stable-rule-id",
            "name": "Temperature",
            "enabled": True,
            "entity_ids": ["sensor.bay_temperature"],
            "source": "state",
            "operator": "above",
            "value": 33,
            "duration": 900,
        }
    ]
    first = dump_config_yaml(config)
    assert first == dump_config_yaml(config)
    assert first.startswith("version: 1\nconfig:\n")
    assert "  monitoring_enabled: true\n" in first
    assert "  coherence_schedule: none\n" in first
    assert "  coherence_scan_esphome: true\n" in first
    assert "  coherence_ignored_entity_references: []\n" in first
    assert "id: stable-rule-id" not in first
    imported = parse_config_yaml(first)
    assert imported["rules"][0]["id"] != "stable-rule-id"
    assert imported["rules"][0]["id"]
    assert "alerts:" not in first


def test_v15_export_without_monitoring_state_defaults_to_enabled() -> None:
    """Pre-switch V1.5 exports remain importable without weakening validation."""
    exported = dump_config_yaml(deepcopy(DEFAULT_CONFIG))
    legacy = exported.replace("  monitoring_enabled: true\n", "")
    assert parse_config_yaml(legacy)["monitoring_enabled"] is True


def test_older_export_without_coherence_schedule_defaults_to_none() -> None:
    """Exports created before scheduled scans remain importable."""
    exported = dump_config_yaml(deepcopy(DEFAULT_CONFIG))
    legacy = exported.replace("  coherence_schedule: none\n", "")
    assert parse_config_yaml(legacy)["coherence_schedule"] == "none"


def test_older_export_without_coherence_scan_options_uses_defaults() -> None:
    """Exports created before configurable scan scope remain importable."""
    exported = dump_config_yaml(deepcopy(DEFAULT_CONFIG))
    legacy = exported.replace("  coherence_scan_esphome: true\n", "").replace(
        "  coherence_ignored_entity_references: []\n", ""
    )
    imported = parse_config_yaml(legacy)
    assert imported["coherence_scan_esphome"] is True
    assert imported["coherence_ignored_entity_references"] == []


def test_pre_dev14_export_without_pending_display_delay_uses_default() -> None:
    """Earlier complete exports gain the ten-second pending delay safely."""
    exported = dump_config_yaml(deepcopy(DEFAULT_CONFIG))
    legacy = exported.replace("  pending_display_delay: 10\n", "")
    assert parse_config_yaml(legacy)["pending_display_delay"] == 10


def test_older_export_without_execution_errors_pack_uses_default() -> None:
    """Exports created before the new pack remain importable."""
    exported = dump_config_yaml(deepcopy(DEFAULT_CONFIG))
    legacy = exported.replace(
        "    execution_errors:\n"
        "      enabled: true\n"
        "      delay: 0\n"
        "      failure_thresholds: {}\n",
        "",
    )

    imported = parse_config_yaml(legacy)

    assert imported["automatic"]["execution_errors"] == {
        "enabled": True,
        "delay": 0,
        "failure_thresholds": {},
    }


def test_older_export_without_flapping_pack_uses_disabled_default() -> None:
    """Exports created before flapping remain importable without enabling it."""
    exported = dump_config_yaml(deepcopy(DEFAULT_CONFIG))
    legacy = exported.replace(
        "    flapping:\n"
        "      enabled: false\n"
        "      occurrences: 5\n"
        "      window: 3600\n"
        "      recovery: 1800\n"
        "      device_overrides: {}\n",
        "",
    )

    imported = parse_config_yaml(legacy)

    assert imported["automatic"]["flapping"] == DEFAULT_CONFIG["automatic"]["flapping"]


def test_dev14_active_display_delay_import_is_migrated() -> None:
    """The short-lived dev14 YAML key keeps its value with corrected semantics."""
    exported = dump_config_yaml(deepcopy(DEFAULT_CONFIG))
    legacy = exported.replace("pending_display_delay", "active_display_delay")
    imported = parse_config_yaml(legacy)
    assert imported["pending_display_delay"] == 10
    assert "active_display_delay" not in imported


def test_config_import_accepts_legacy_ids_and_rejects_duplicates_and_runtime() -> None:
    """Legacy ids remain importable, but collisions and runtime are rejected."""
    config = dump_config_yaml({**deepcopy(DEFAULT_CONFIG), "rules": []})
    duplicate_rules = """rules:
  - id: same
    name: One
    enabled: true
    entity_ids: [sensor.one]
    source: state
    operator: equals
    value: on
    duration: 0
    message: null
  - id: same
    name: Two
    enabled: true
    entity_ids: [sensor.two]
    source: state
    operator: equals
    value: on
    duration: 0
    message: null
"""
    with pytest.raises(ValueError, match="Duplicate rule id"):
        parse_config_yaml(config.replace("rules: []\n", duplicate_rules))
    valid = config
    with pytest.raises(ValueError, match="Unknown configuration field: alerts"):
        parse_config_yaml(valid + "alerts: {}\n")


def test_import_replaces_config_and_rebuilds_independent_rule_instances(hass, entry):
    """A valid import recreates independent state for every entity of one rule."""
    hass.states.set("sensor.one", "on")
    hass.states.set("sensor.two", "on")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    config = deepcopy(DEFAULT_CONFIG)
    config["rules"] = [
        {
            "id": "stable-multi-rule",
            "name": "Two sources",
            "enabled": True,
            "entity_ids": ["sensor.one", "sensor.two"],
            "source": "state",
            "operator": "equals",
            "value": "on",
            "duration": 0,
        }
    ]
    result = run(manager.async_import_config(dump_config_yaml(config)))
    imported_rule_id = manager.config["rules"][0]["id"]
    assert imported_rule_id != "stable-multi-rule"
    assert result["summary"] == {
        "rules": 1,
        "enabled_packs": 5,
        "entity_delays": 0,
        "warnings": [],
    }
    assert set(manager.records) >= {
        f"rule:{imported_rule_id}:sensor.one",
        f"rule:{imported_rule_id}:sensor.two",
    }
    assert all(
        manager.records[alert_id].status is AlertStatus.ACTIVE
        for alert_id in (
            f"rule:{imported_rule_id}:sensor.one",
            f"rule:{imported_rule_id}:sensor.two",
        )
    )


def test_invalid_import_keeps_existing_configuration_and_runtime(hass, entry):
    """Pre-parse failures cannot change the current config or pending records."""
    hass.states.set("sensor.one", "unavailable")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    before_config = manager.get_config()
    before_records = deepcopy(manager.records)
    with pytest.raises(ValueError, match="Unsupported configuration format"):
        run(manager.async_import_config("version: 99\nconfig: {}\nrules: []\n"))
    assert manager.get_config() == before_config
    assert manager.records == before_records


def test_import_write_failure_rolls_back_configuration_and_runtime(hass, entry):
    """A storage failure after evaluation restores the old in-memory snapshot."""
    hass.states.set("sensor.one", "unavailable")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    before_config = manager.get_config()
    before_records = deepcopy(manager.records)

    async def fail_save(_config, _records):
        raise OSError("storage unavailable")

    manager.storage.async_save = fail_save
    with pytest.raises(OSError, match="storage unavailable"):
        run(manager.async_import_config(dump_config_yaml(deepcopy(DEFAULT_CONFIG))))
    assert manager.get_config() == before_config
    assert manager.records == before_records
