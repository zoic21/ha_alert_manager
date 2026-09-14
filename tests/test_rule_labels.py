"""Label changes preserve alert lifecycles and notification routing."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from test_notification_runtime import _DeliverySpy, _profile
from test_transitions import edge, expire, setup

from custom_components.alert_manager.config_defaults import DEFAULT_CONFIG
from custom_components.alert_manager.const import (
    EVENT_ALERT_RESOLVED,
    EVENT_ALERT_STARTED,
)
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import Rule
from custom_components.alert_manager.notification_runtime import NotificationRuntime
from custom_components.alert_manager.validation import (
    validate_config,
    validate_rule_payload,
)
from custom_components.alert_manager.yaml_io import dump_rule_yaml, parse_rule_yaml


def run(coro):
    return asyncio.run(coro)


def payload(**changes):
    return {
        "name": "Test",
        "entity_ids": ["sensor.test"],
        "source": "value",
        "operator": "equals",
        "value": "on",
        "duration": 0,
        **changes,
    }


@pytest.mark.parametrize("labels", [[], ["maintenance"], ["other", "maintenance"]])
def test_rule_labels_validation_and_yaml(labels):
    rule = validate_rule_payload(payload(label_ids=labels))
    assert parse_rule_yaml(dump_rule_yaml(rule)).label_ids == labels
    assert "severity" not in Rule.create(payload(severity="critical")).as_dict()


@pytest.mark.parametrize("status", ["pending", "active", "acknowledged"])
def test_label_edit_does_not_evaluate_or_touch_lifecycle(
    hass, entry, monkeypatch, status
):
    hass.states.set("sensor.test", "on")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    rule = run(
        manager.async_create_rule(payload(duration=60 if status == "pending" else 0))
    )
    key = f"rule:{rule['id']}:sensor.test"
    if status == "acknowledged":
        run(manager.async_set_acknowledgements([key], True, "admin", duration=120))
    record = manager.records[key]
    before = record.as_storage_dict()
    timers = dict(manager._timers)
    events = list(hass.bus.fired)
    counts = manager.public_snapshot()
    evaluate = AsyncMock(side_effect=AssertionError("Presentation must not evaluate"))
    monkeypatch.setattr(manager, "async_evaluate_entity", evaluate)
    # A changed state not yet evaluated must not be consumed by a visual edit.
    hass.states.set("sensor.test", "off")
    run(manager.async_update_rule(rule["id"], {"label_ids": ["maintenance"]}))
    assert manager.records[key] is record
    expected = deepcopy(before)
    expected["details"]["labels"] = ["maintenance"]
    assert record.as_storage_dict() == expected
    assert manager._timers == timers
    assert hass.bus.fired == events
    for name in ("active_count", "pending_count", "acknowledge_count"):
        assert manager.public_snapshot().get(name) == counts.get(name)
    evaluate.assert_not_called()


def test_label_edit_rollback_on_save_failure(hass, entry, monkeypatch):
    hass.states.set("sensor.test", "on")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    rule = run(manager.async_create_rule(payload()))
    key = f"rule:{rule['id']}:sensor.test"
    before = manager.records[key].as_storage_dict()
    monkeypatch.setattr(
        manager, "_async_save_state", AsyncMock(side_effect=OSError("disk"))
    )
    with pytest.raises(OSError):
        run(manager.async_update_rule(rule["id"], {"label_ids": ["maintenance"]}))
    assert manager.records[key].as_storage_dict() == before
    assert manager.config["rules"][0]["label_ids"] == []


def test_maintenance_configuration_export_import_preserves_identity(hass, entry):
    from custom_components.alert_manager.yaml_io import (
        dump_config_yaml,
        parse_config_yaml,
    )

    rule = Rule.create(payload(label_ids=["maintenance"]))
    config = validate_config({**deepcopy(DEFAULT_CONFIG), "rules": [rule.as_dict()]})
    restored = parse_config_yaml(dump_config_yaml(config), config["rules"])
    assert restored["rules"][0]["id"] == rule.id
    assert restored["rules"][0]["label_ids"] == ["maintenance"]


def test_concurrent_label_saves_are_serialized(hass, entry):
    async def scenario():
        hass.states.set("sensor.test", "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(payload())
        key = f"rule:{rule['id']}:sensor.test"
        before = manager.records[key].as_storage_dict()
        events = list(hass.bus.fired)
        await asyncio.gather(
            manager.async_update_rule(rule["id"], {"label_ids": ["maintenance"]}),
            manager.async_update_rule(rule["id"], {"label_ids": []}),
        )
        assert manager.records[key].as_storage_dict() == before
        assert manager.config["rules"][0]["label_ids"] == []
        assert hass.bus.fired == events

    run(scenario())


def test_label_exception_controls_delivery(hass, entry):
    async def scenario():
        profile = _profile(reminder_interval=300)
        profile["exceptions"] = [
            {
                "selector_type": "label",
                "selector_id": "maintenance",
                "notify_on_start": True,
                "notify_on_resolved": False,
                "reminder_interval": None,
            }
        ]
        config = validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [profile]}
        )
        delivery = _DeliverySpy()
        runtime = NotificationRuntime(hass, entry, lambda: config, lambda: {}, delivery)
        await runtime.async_setup()
        event = {
            "id": "rule:test:sensor.test",
            "entity_id": "sensor.test",
            "type": "rule",
            "labels": ["maintenance"],
        }
        await runtime._async_handle_event(EVENT_ALERT_STARTED, event)
        await runtime._async_flush_batch("profile", "started")
        assert runtime._runtime["profile"][event["id"]].next_reminder is None
        await runtime._async_handle_event(EVENT_ALERT_RESOLVED, event)
        assert not runtime._batches
        assert len(delivery.calls) == 1
        assert delivery.calls[0]["kind"] == "started"
        await runtime.async_unload()

    run(scenario())


@pytest.mark.parametrize("confirmed", [False, True])
def test_label_edit_preserves_unprocessed_transition(hass, entry, set_now, confirmed):
    manager, key, rule = setup(hass, entry, duration=0 if confirmed else 30)
    edge(manager, hass, "B", flush=not confirmed)
    observations = (
        manager._transition_confirmed if confirmed else manager._transition_observations
    )
    observation = observations[key]
    run(manager.async_update_rule(rule["id"], {"label_ids": ["maintenance"]}))
    assert observations[key] is observation
    set_now(observation.due_at)
    if confirmed:
        run(manager._async_flush_queued_evaluations())
    else:
        expire(manager, key)
    assert manager.records[key].active_since == observation.due_at
    assert sum(event == EVENT_ALERT_STARTED for event, _ in hass.bus.fired) == 1


def test_automatic_labels_survive_restart(hass, entry, monkeypatch):
    hass.states.set("sensor.test", "unavailable")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    run(
        manager.async_update_config(
            {"automatic": {"unavailable": {"delay": 0, "label_ids": ["maintenance"]}}}
        )
    )
    key = "unavailable:sensor.test"
    record = manager.records[key]
    timers = dict(manager._timers)
    events = list(hass.bus.fired)
    with monkeypatch.context() as patch:
        patch.setattr(
            manager,
            "async_evaluate_all",
            AsyncMock(side_effect=AssertionError("No scan")),
        )
        run(
            manager.async_update_config(
                {"automatic": {"unavailable": {"label_ids": ["other"]}}}
            )
        )
    assert manager.records[key] is record
    assert manager._timers == timers
    assert hass.bus.fired == events
    run(
        manager.async_update_config(
            {"automatic": {"unavailable": {"label_ids": ["updates"]}}}
        )
    )
    run(manager.async_unload())
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    run(manager._async_finish_startup_reconciliation())
    assert manager.records[key].details.labels == ["updates"]
    assert manager.records[key].active_since == record.active_since
