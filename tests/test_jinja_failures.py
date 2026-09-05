"""Indeterminate Jinja results preserve occurrences and event-driven recovery."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import timedelta

import pytest
from homeassistant.core import Event
from homeassistant.exceptions import TemplateError

from custom_components.alert_manager import manager_templates
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertStatus


@pytest.fixture
def render_control(monkeypatch):
    """Model HA RenderInfo, which retains dependencies when result() raises."""
    control = {"error": True, "result": "true", "domain": False, "own": False}
    original = manager_templates.Template.async_render_to_info

    class Info:
        def __init__(self):
            dependency = (
                "sensor.alert_manager_main_active"
                if control["own"]
                else "sensor.dependency"
            )
            self.entities = frozenset() if control["domain"] else {dependency}
            self.domains = {"sensor"} if control["domain"] else set()
            self.domains_lifecycle = self.domains

        def result(self):
            if control["error"]:
                raise TemplateError("dependency is not numeric")
            return control["result"]

        def filter(self, entity_id):
            return entity_id in self.entities or entity_id.split(".")[0] in self.domains

        filter_lifecycle = filter

    def render(template, variables=None):
        if template.template == "{{ value }}":
            return Info()
        return original(template, variables)

    monkeypatch.setattr(manager_templates.Template, "async_render_to_info", render)
    return control


async def make_rule(hass, entry, **changes):
    hass.states.set("sensor.source", "10")
    manager = AlertManager(hass, entry)
    await manager.async_setup()
    config = {
        "name": "Jinja failure",
        "entity_ids": ["sensor.source"],
        "source": "jinja",
        "condition_template": "{{ value }}",
        "duration": 0,
    }
    config.update(changes)
    created = await manager.async_create_rule(config)
    return manager, f"rule:{created['id']}:sensor.source"


async def dependency_changed(hass, manager):
    old_state = hass.states.get("sensor.dependency")
    hass.states.set("sensor.dependency", "1")
    manager._state_changed(
        Event(
            {
                "entity_id": "sensor.dependency",
                "old_state": old_state,
                "new_state": hass.states.get("sensor.dependency"),
            }
        )
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)


@pytest.mark.parametrize("domain", [False, True])
def test_failed_first_render_recovers_from_dependency(
    hass, entry, render_control, domain, caplog
):
    async def scenario():
        render_control["domain"] = domain
        manager, alert_id = await make_rule(hass, entry)
        assert alert_id not in manager.records
        assert "dependency is not numeric" in caplog.text
        pair = (manager._rules[0].id, "sensor.source")
        assert pair in manager._rule_template_render_info
        if domain:
            assert ("condition", *pair) in manager._template_dynamic_infos
        else:
            assert ("condition", *pair) in manager._template_dependents[
                "sensor.dependency"
            ]
        result = await manager.async_test_rule(
            {
                k: v
                for k, v in manager.config["rules"][0].items()
                if k not in ("id", "version")
            }
        )
        assert result["results"][0]["reason"] == "condition_template_error"
        render_control["error"] = False
        await dependency_changed(hass, manager)
        assert manager.records[alert_id].status is AlertStatus.ACTIVE

    asyncio.run(scenario())


@pytest.mark.parametrize("duration,acknowledge", [(300, False), (0, False), (0, True)])
def test_error_preserves_occurrence_and_recovery_can_resolve(
    hass, entry, render_control, duration, acknowledge
):
    async def scenario():
        render_control["error"] = False
        manager, alert_id = await make_rule(hass, entry, duration=duration)
        record = manager.records[alert_id]
        if acknowledge:
            await manager.async_acknowledge(alert_id, None)
        before = asdict(record)
        events = list(hass.bus.fired)
        render_control["error"] = True
        await dependency_changed(hass, manager)
        assert manager.records[alert_id] is record
        assert asdict(record) == before
        assert hass.bus.fired == events
        render_control.update(error=False, result="false")
        await dependency_changed(hass, manager)
        assert alert_id not in manager.records

    asyncio.run(scenario())


def test_indeterminate_pending_keeps_existing_deadline(
    hass, entry, render_control, set_now
):
    async def scenario():
        render_control["error"] = False
        manager, alert_id = await make_rule(hass, entry, duration=300)
        record = manager.records[alert_id]
        due_at = record.due_at
        render_control["error"] = True
        set_now(due_at + timedelta(seconds=1))
        await manager.async_evaluate_entity("sensor.source")
        assert manager.records[alert_id] is record
        assert record.due_at == due_at
        assert record.status is AlertStatus.ACTIVE

    asyncio.run(scenario())


@pytest.mark.parametrize("initial_failure", [False, True])
def test_message_error_preserves_last_value_and_tracks_recovery(
    hass, entry, render_control, initial_failure
):
    async def scenario():
        render_control.update(error=initial_failure, result="Last valid message")
        manager, alert_id = await make_rule(
            hass,
            entry,
            condition_template="{{ true }}",
            message="{{ value }}",
            update_message_when_active=True,
        )
        expected = None if initial_failure else "Last valid message"
        assert manager.records[alert_id].details.message == expected
        render_control["error"] = True
        await dependency_changed(hass, manager)
        assert manager.records[alert_id].details.message == expected
        assert any(
            key[0] == "message"
            for key in manager._template_dependents["sensor.dependency"]
        )
        render_control.update(error=False, result="Recovered")
        await dependency_changed(hass, manager)
        assert manager.records[alert_id].details.message == "Recovered"

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["condition", "message"])
def test_failed_render_rejects_own_dependencies(hass, entry, render_control, kind):
    async def scenario():
        render_control["own"] = True
        changes = (
            {"condition_template": "{{ true }}", "message": "{{ value }}"}
            if kind == "message"
            else {}
        )
        manager, alert_id = await make_rule(hass, entry, **changes)
        assert not manager._template_dependents
        assert not manager._template_dynamic_infos
        if kind == "condition":
            assert alert_id not in manager.records
        else:
            assert manager.records[alert_id].details.message is None

    asyncio.run(scenario())


def test_variation_first_error_does_not_start_window(hass, entry, render_control):
    async def scenario():
        manager, alert_id = await make_rule(
            hass,
            entry,
            source="state_variation",
            operator="above",
            value=5,
        )
        assert not manager._variation_baselines
        assert alert_id not in manager.records
        hass.states.set("sensor.source", "20")
        render_control["error"] = False
        await dependency_changed(hass, manager)
        assert list(manager._variation_baselines.values()) == [20]
        assert alert_id not in manager.records
        hass.states.set("sensor.source", "26")
        await manager.async_evaluate_entity("sensor.source")
        assert manager.records[alert_id].details.value == 6

    asyncio.run(scenario())


def test_explicit_frozen_message_edit_preserves_last_value_on_error(
    hass, entry, render_control
):
    async def scenario():
        manager, alert_id = await make_rule(
            hass, entry, condition_template="{{ true }}", message="Last valid message"
        )
        await manager.async_update_rule(
            manager._rules[0].id, {"message": "{{ value }}"}
        )
        assert manager.records[alert_id].details.message == "Last valid message"
        assert "sensor.dependency" not in manager._template_dependents

    asyncio.run(scenario())
