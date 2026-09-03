"""Dry-run custom-rule tester behavior and side-effect guarantees."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.exceptions import TemplateError

from custom_components.alert_manager import manager_templates
from custom_components.alert_manager.manager import AlertManager


def run(coroutine):
    return asyncio.run(coroutine)


def rule(**changes):
    payload = {
        "name": "Draft rule",
        "entity_ids": ["sensor.source"],
        "enabled": True,
        "source": "state",
        "operator": "equals",
        "value": "on",
        "duration": 600,
        "message": None,
        "condition_template": None,
    }
    payload.update(changes)
    if payload["source"] in ("jinja", "unchanged"):
        payload.pop("operator", None)
        payload.pop("value", None)
    return payload


def make_manager(hass, entry):
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    return manager


def runtime_snapshot(manager, hass):
    return {
        "config": deepcopy(manager.config),
        "records": deepcopy(manager.records),
        "history": deepcopy(manager.history),
        "pending_history": deepcopy(manager._pending_history),
        "baselines": deepcopy(manager._variation_baselines),
        "baseline_dirty": manager._variation_baselines_dirty,
        "pack_runtime": deepcopy(manager._pack_runtime),
        "timers": list(manager._timers),
        "hass_timers": len(hass.timers),
        "events": deepcopy(hass.bus.fired),
        "store_saves": hass.store_save_count,
        "snapshot": deepcopy(manager._last_public_snapshot),
        "rule_templates": {
            key: id(value) for key, value in manager._rule_templates.items()
        },
        "message_templates": {
            key: id(value) for key, value in manager._rule_message_templates.items()
        },
        "condition_render_info": {
            key: id(value) for key, value in manager._rule_template_render_info.items()
        },
        "message_render_info": {
            key: id(value) for key, value in manager._rule_message_render_info.items()
        },
        "template_dependents": deepcopy(manager._template_dependents),
        "template_entities": deepcopy(manager._template_entities_by_key),
        "template_time_dependencies": deepcopy(manager._template_time_dependencies),
        "template_dynamic_infos": {
            key: id(value) for key, value in manager._template_dynamic_infos.items()
        },
    }


def test_new_multi_entity_rule_reports_true_false_and_has_no_side_effects(hass, entry):
    """A new draft evaluates every entity without touching any manager state."""
    hass.states.set("sensor.one", "on", {"friendly_name": "One"})
    hass.states.set("sensor.two", "off", {"friendly_name": "Two"})
    manager = make_manager(hass, entry)
    before = runtime_snapshot(manager, hass)

    result = run(
        manager.async_test_rule(
            rule(entity_ids=["sensor.one", "sensor.two"], enabled=False)
        )
    )

    assert result["enabled"] is False
    assert result["matched_count"] == 1
    assert result["not_matched_count"] == 1
    assert [item["status"] for item in result["results"]] == [
        "match",
        "no_match",
    ]
    assert result["results"][0]["name"] == "One"
    assert result["results"][0]["comparison_result"] is True
    assert result["results"][0]["jinja_result"] is None
    assert result["results"][1]["comparison_result"] is False
    assert runtime_snapshot(manager, hass) == before


def test_existing_rule_uses_unsaved_draft_without_changing_saved_rule(hass, entry):
    """A full draft payload overrides the saved definition only for the test."""
    hass.states.set("sensor.source", "on")
    manager = make_manager(hass, entry)
    created = run(manager.async_create_rule(rule(value="off")))
    before = runtime_snapshot(manager, hass)

    draft = {
        key: value for key, value in created.items() if key not in ("id", "version")
    }
    draft["value"] = "on"
    result = run(manager.async_test_rule(draft, rule_id=created["id"]))

    assert result["results"][0]["status"] == "match"
    assert manager.config["rules"][0]["value"] == "off"
    assert runtime_snapshot(manager, hass) == before


def test_test_does_not_resolve_or_reschedule_an_existing_record(hass, entry):
    """Testing a false draft leaves the saved rule's pending alert untouched."""
    hass.states.set("sensor.source", "on")
    manager = make_manager(hass, entry)
    created = run(manager.async_create_rule(rule(duration=600)))
    alert_id = f"rule:{created['id']}:sensor.source"
    assert alert_id in manager.records
    assert alert_id in manager._timers
    before = runtime_snapshot(manager, hass)

    draft = {
        key: value for key, value in created.items() if key not in ("id", "version")
    }
    draft["value"] = "off"
    result = run(manager.async_test_rule(draft, rule_id=created["id"]))

    assert result["results"][0]["status"] == "no_match"
    assert runtime_snapshot(manager, hass) == before


@pytest.mark.parametrize(
    ("payload", "expected_value", "expected"),
    [
        (
            rule(
                source="attribute",
                attribute="data.*.level",
                operator="contains",
                value=["critical", "alarm"],
            ),
            ["ok", "critical"],
            True,
        ),
        (
            rule(
                source="attribute",
                attribute="temperature",
                operator="below",
                value="19",
            ),
            18.2,
            True,
        ),
        (
            rule(
                source="attribute",
                attribute="data.*.level",
                operator="not_contains",
                value="danger",
            ),
            ["ok", "critical"],
            True,
        ),
        (rule(operator="below", value="19"), "18.2", True),
        (rule(operator="between", value=["18", "19"]), "18.2", True),
        (rule(operator="outside", value=["10", "17"]), "18.2", True),
    ],
)
def test_attributes_text_numeric_ranges_and_wildcards(
    hass, entry, payload, expected_value, expected
):
    """The tester exposes values from every comparison family."""
    hass.states.set(
        "sensor.source",
        "18.2",
        {
            "temperature": 18.2,
            "data": [{"level": "ok"}, {"level": "critical"}],
        },
    )
    manager = make_manager(hass, entry)

    result = run(manager.async_test_rule(payload))["results"][0]

    assert result["value"] == expected_value
    assert result["comparison_result"] is expected
    assert result["final_result"] is expected


def test_missing_attribute_and_non_numeric_source_are_actionable_errors(hass, entry):
    """Impossible evaluations return stable reason codes, not Python exceptions."""
    hass.states.set("sensor.source", "warm", {"nested": {"value": "hot"}})
    manager = make_manager(hass, entry)

    missing = run(
        manager.async_test_rule(rule(source="attribute", attribute="nested.missing"))
    )["results"][0]
    numeric = run(manager.async_test_rule(rule(operator="above", value=10)))["results"][
        0
    ]
    missing_entity = run(manager.async_test_rule(rule(entity_ids=["sensor.missing"])))[
        "results"
    ][0]

    assert (missing["status"], missing["reason"]) == (
        "error",
        "attribute_not_found",
    )
    assert (numeric["status"], numeric["reason"]) == (
        "error",
        "numeric_source_required",
    )
    assert (missing_entity["status"], missing_entity["reason"]) == (
        "error",
        "entity_not_found",
    )


def test_jinja_true_false_and_rendered_message_use_runtime_context(hass, entry):
    """Condition and message templates receive entity_id, state and value."""
    hass.states.set("sensor.source", "ready")
    manager = make_manager(hass, entry)

    matched = run(
        manager.async_test_rule(
            rule(
                source="jinja",
                condition_template="{{ true }}",
                message="Entity {{ entity_id }} has value {{ value }}",
            )
        )
    )["results"][0]
    unmatched = run(
        manager.async_test_rule(rule(source="jinja", condition_template="{{ false }}"))
    )["results"][0]

    assert matched["jinja_result"] is True
    assert matched["final_result"] is True
    assert matched["message"] == "Entity sensor.source has value ready"
    assert unmatched["jinja_result"] is False
    assert unmatched["final_result"] is False


def test_jinja_render_error_is_returned_per_entity(hass, entry, monkeypatch):
    """A runtime template error remains diagnostic and does not escape the API."""
    hass.states.set("sensor.source", "on")
    manager = make_manager(hass, entry)
    original = manager_templates.Template.async_render_to_info

    def render(self, variables=None):
        if self.template == "{{ true }}":
            raise TemplateError("render failed")
        return original(self, variables)

    monkeypatch.setattr(manager_templates.Template, "async_render_to_info", render)

    result = run(
        manager.async_test_rule(rule(source="jinja", condition_template="{{ true }}"))
    )["results"][0]

    assert result["status"] == "error"
    assert result["reason"] == "condition_template_error"
    assert result["error_detail"] == "render failed"


def test_message_render_error_does_not_hide_condition_result(hass, entry, monkeypatch):
    """A broken optional message is reported while the rule result stays usable."""
    hass.states.set("sensor.source", "on")
    manager = make_manager(hass, entry)
    original = manager_templates.Template.async_render_to_info

    def render(self, variables=None):
        if self.template == "Broken {{ value }}":
            raise TemplateError("message render failed")
        return original(self, variables)

    monkeypatch.setattr(manager_templates.Template, "async_render_to_info", render)

    result = run(manager.async_test_rule(rule(message="Broken {{ value }}")))[
        "results"
    ][0]

    assert result["status"] == "match"
    assert result["final_result"] is True
    assert result["message"] is None
    assert result["message_error"] == "message render failed"


def test_unchanged_reports_elapsed_time_and_configured_duration(hass, entry, set_now):
    """No-change diagnostics use the same state timestamps as the runtime."""
    now = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    set_now(now)
    hass.states.set("sensor.old", "on", last_updated=now - timedelta(hours=2))
    hass.states.set("sensor.recent", "on", last_updated=now - timedelta(minutes=30))
    manager = make_manager(hass, entry)

    result = run(
        manager.async_test_rule(
            rule(
                entity_ids=["sensor.old", "sensor.recent"],
                source="unchanged",
                duration=3600,
            )
        )
    )["results"]

    assert result[0]["unchanged_seconds"] == 7200
    assert result[0]["duration_reached"] is True
    assert result[1]["unchanged_seconds"] == 1800
    assert result[1]["duration_reached"] is False


def test_variation_reads_existing_baseline_but_never_creates_one(hass, entry):
    """Existing references are read-only and new drafts remain indeterminate."""
    hass.states.set("sensor.source", "10")
    manager = make_manager(hass, entry)
    created = run(
        manager.async_create_rule(
            rule(
                source="state_variation",
                operator="above",
                value=5,
                condition_template="{{ true }}",
            )
        )
    )
    key = f"{created['id']}:sensor.source"
    assert manager._variation_baselines[key] == 10
    hass.states.set("sensor.source", "18")
    before = runtime_snapshot(manager, hass)

    existing_draft = {
        key: value for key, value in created.items() if key not in ("id", "version")
    }
    existing = run(manager.async_test_rule(existing_draft, rule_id=created["id"]))[
        "results"
    ][0]
    new = run(
        manager.async_test_rule(
            rule(
                source="state_variation",
                operator="above",
                value=5,
                condition_template="{{ true }}",
            )
        )
    )["results"][0]

    assert existing["baseline"] == 10
    assert existing["current_value"] == 18
    assert existing["variation"] == 8
    assert existing["status"] == "match"
    assert new["status"] == "indeterminate"
    assert new["reason"] == "baseline_unavailable"
    assert runtime_snapshot(manager, hass) == before


def test_variation_diagnostic_continues_after_a_false_jinja_gate(hass, entry):
    """A dry run exposes the comparison while Jinja keeps the final result false."""
    hass.states.set("sensor.source", "10")
    hass.states.set("binary_sensor.guard", "on")
    manager = make_manager(hass, entry)
    created = run(
        manager.async_create_rule(
            rule(
                source="state_variation",
                operator="above",
                value=5,
                condition_template=("{{ is_state('binary_sensor.guard', 'on') }}"),
                message="Variation {{ value }}",
            )
        )
    )
    hass.states.set("sensor.source", "18")
    hass.states.set("binary_sensor.guard", "off")
    before = runtime_snapshot(manager, hass)
    draft = {
        key: value for key, value in created.items() if key not in ("id", "version")
    }

    result = run(manager.async_test_rule(draft, rule_id=created["id"]))["results"][0]

    assert result["status"] == "no_match"
    assert result["jinja_result"] is False
    assert result["comparison_result"] is True
    assert result["final_result"] is False
    assert result["baseline"] == 10
    assert result["variation"] == 8
    assert result["message"] == "Variation 8.0"
    assert runtime_snapshot(manager, hass) == before


def test_unsaved_variation_definition_change_does_not_reuse_old_baseline(hass, entry):
    """A draft change that would reset runtime also hides the saved baseline."""
    hass.states.set("sensor.source", "10", {"power": 100})
    manager = make_manager(hass, entry)
    created = run(
        manager.async_create_rule(
            rule(
                source="state_variation",
                operator="above",
                value=5,
                condition_template="{{ true }}",
            )
        )
    )
    draft = {
        key: value for key, value in created.items() if key not in ("id", "version")
    }
    draft.update(source="attribute_variation", attribute="power")

    result = run(manager.async_test_rule(draft, rule_id=created["id"]))["results"][0]

    assert result["status"] == "indeterminate"
    assert result["baseline"] is None
