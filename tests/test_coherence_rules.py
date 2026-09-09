"""Custom rules share the ordinary coherence reference scan."""

import asyncio
from types import SimpleNamespace

from custom_components.alert_manager.coherence import (
    async_scan_configuration,
    scan_configuration,
)
from custom_components.alert_manager.coherence_rules import snapshot_rules
from custom_components.alert_manager.const import DATA_MANAGER
from custom_components.alert_manager.models import Rule


def rule(**changes):
    values = {
        "id": "rule-1",
        "name": "Room",
        "entity_ids": ["sensor.missing"],
        "operator": "eq",
        "value": "sensor.not_a_reference",
        "duration": 0,
        "enabled": False,
        "condition_template": "{{ states('sensor.condition') | int > 0 }}",
        "message": (
            "{{ states('sensor.message') }} {{ states('sensor.prefix_' ~ room) }}"
        ),
    }
    return Rule(**(values | changes))


def test_rule_fields_exclusions_and_snapshot(tmp_path):
    source = rule()
    snapshot = snapshot_rules([source])
    source.entity_ids.clear()
    source.condition_template = "{{ states('sensor.changed') }}"
    report = scan_configuration(
        tmp_path,
        frozenset({"sensor.condition"}),
        custom_rules=snapshot,
    )
    assert {row["entity_id"] for row in report["results"]} == {
        "sensor.missing",
        "sensor.message",
    }
    assert report["files_scanned"] == 0
    for row in report["results"]:
        assert row["source_type"] == "custom_rule"
        assert row["source_name"] == "Room"
        assert row["link"] == {"type": "custom_rule", "path": "rule-1"}
        assert row["file"].startswith("alert_manager/rules/rule-1/")
    assert not scan_configuration(
        tmp_path,
        frozenset({"sensor.condition"}),
        custom_rules=snapshot,
        ignored_entity_references=frozenset({"sensor.missing", "sensor.message"}),
    )["results"]


def test_jinja_rule_ignores_source_placeholder_and_plain_messages(tmp_path):
    report = scan_configuration(
        tmp_path,
        frozenset(),
        custom_rules=snapshot_rules(
            [
                rule(
                    source="jinja",
                    condition_template="{{ true }}",
                    message="Look at sensor.example",
                ),
            ]
        ),
    )
    assert report["results"] == []


def test_same_reference_in_two_rules_and_recovery(tmp_path):
    rules = [rule(id=key, condition_template=None, message=None) for key in ("a", "b")]
    report = scan_configuration(
        tmp_path, frozenset(), custom_rules=snapshot_rules(rules)
    )
    assert report["missing_count"] == 2
    assert report["missing_entity_count"] == 1
    assert not scan_configuration(
        tmp_path,
        frozenset({"sensor.missing"}),
        custom_rules=snapshot_rules(rules),
    )["results"]
    assert not scan_configuration(tmp_path, frozenset(), custom_rules=())["results"]


def test_async_scan_includes_manager_rules(hass, tmp_path):
    hass.config.path = lambda: str(tmp_path)
    hass.data[DATA_MANAGER] = SimpleNamespace(rules=[rule()])
    report = asyncio.run(async_scan_configuration(hass))
    assert {row["entity_id"] for row in report["results"]} == {
        "sensor.missing",
        "sensor.condition",
        "sensor.message",
    }
