"""Information is presentation metadata, never a detection or delivery policy."""

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
from custom_components.alert_manager.models import AlertHistoryEntry, AlertRecord, Rule
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


@pytest.mark.parametrize("level", ["alert", "info"])
def test_rule_level_validation_and_yaml(level):
    rule = validate_rule_payload(payload(level=level))
    assert Rule.from_dict(rule.as_dict()).level == level
    assert parse_rule_yaml(dump_rule_yaml(rule)).level == level
    assert Rule.create(payload(severity="critical")).level == "alert"
    assert "severity" not in Rule.create(payload(severity="critical")).as_dict()


@pytest.mark.parametrize("level", [None, "warning", "critical", "", True, 1, [], {}])
def test_invalid_level_rejected_by_common_validation(level):
    with pytest.raises(ValueError, match="level"):
        validate_rule_payload(payload(level=level))


@pytest.mark.parametrize("status", ["pending", "active", "acknowledged"])
def test_level_edit_does_not_evaluate_or_touch_lifecycle(
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
    run(manager.async_update_rule(rule["id"], {"level": "info"}))
    assert manager.records[key] is record
    assert record.details.level == "info"
    expected = deepcopy(before)
    expected["details"]["level"] = "info"
    assert record.as_storage_dict() == expected
    assert manager._timers == timers
    assert hass.bus.fired == events
    for name in ("active_count", "pending_count", "acknowledge_count"):
        assert manager.public_snapshot().get(name) == counts.get(name)
    evaluate.assert_not_called()


def test_level_edit_rollback_on_save_failure(hass, entry, monkeypatch):
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
        run(manager.async_update_rule(rule["id"], {"level": "info"}))
    assert manager.records[key].as_storage_dict() == before
    assert manager.config["rules"][0]["level"] == "alert"


def test_transition_level_edit_restart_and_history_snapshot(hass, entry, set_now):
    manager, key, rule = setup(hass, entry, level="info")
    edge(manager, hass, "B")
    run(manager.async_acknowledge(key, "admin"))
    before = manager.records[key].as_storage_dict()
    timers = dict(manager._timers)
    run(manager.async_update_rule(rule["id"], {"level": "alert"}))
    run(manager.async_update_rule(rule["id"], {"level": "info"}))
    assert manager.records[key].as_storage_dict() == before
    assert manager._timers == timers
    run(manager.async_unload())
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    run(manager._async_finish_startup_reconciliation())
    record = manager.records[key]
    assert record.details.level == "info"
    assert record.acknowledged
    assert record.expires_at.isoformat() == before["expires_at"]
    set_now(record.expires_at)
    expire(manager, key)
    archived = manager.history[-1].as_dict()
    run(manager.async_update_rule(rule["id"], {"level": "alert"}))
    run(manager.async_delete_rule(rule["id"]))
    assert manager.history[-1].as_dict() == archived
    assert AlertHistoryEntry.from_dict(archived).level == "info"
    archived.pop("level")
    archived["severity"] = "info"
    assert AlertHistoryEntry.from_dict(archived).level == "alert"
    legacy = deepcopy(before)
    legacy["details"].pop("level")
    legacy["details"]["severity"] = "info"
    assert AlertRecord.from_dict(legacy).details.level == "alert"


@pytest.mark.parametrize("mixed", [False, True])
def test_information_batches_keep_delivery_count_and_kind(hass, entry, mixed):
    async def scenario():
        config = validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [_profile()]}
        )
        delivery = _DeliverySpy()
        runtime = NotificationRuntime(hass, entry, lambda: config, lambda: {}, delivery)
        await runtime.async_setup()
        events = [
            {
                "id": f"rule:test:sensor.{index}",
                "entity_id": f"sensor.{index}",
                "type": "rule",
                "level": "alert" if mixed and index == 1 else "info",
                "device_id": "device",
                "name": "Test",
                "condition": "Done",
            }
            for index in range(2)
        ]
        for event in events:
            await runtime._async_handle_event(EVENT_ALERT_STARTED, event)
        assert list(runtime._batches) == [("profile", "started")]
        await runtime._async_flush_batch("profile", "started")
        for event in events:
            await runtime._async_handle_event(EVENT_ALERT_RESOLVED, event)
        assert list(runtime._batches) == [("profile", "resolved")]
        await runtime._async_flush_batch("profile", "resolved")
        assert len(delivery.calls) == 2
        assert [call["kind"] for call in delivery.calls] == ["started", "resolved"]
        assert all(
            call["level"] == ("alert" if mixed else "info") for call in delivery.calls
        )
        assert ("alerts" if mixed else "information") in delivery.calls[0]["title"]
        assert "resolved" in delivery.calls[1]["title"]
        await runtime.async_unload()

    run(scenario())


def test_information_configuration_export_import_preserves_identity(hass, entry):
    from custom_components.alert_manager.yaml_io import (
        dump_config_yaml,
        parse_config_yaml,
    )

    rule = Rule.create(payload(level="info"))
    config = validate_config({**deepcopy(DEFAULT_CONFIG), "rules": [rule.as_dict()]})
    restored = parse_config_yaml(dump_config_yaml(config), config["rules"])
    assert restored["rules"][0]["id"] == rule.id
    assert restored["rules"][0]["level"] == "info"


def test_concurrent_level_saves_are_serialized(hass, entry):
    async def scenario():
        hass.states.set("sensor.test", "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(payload())
        key = f"rule:{rule['id']}:sensor.test"
        before = manager.records[key].as_storage_dict()
        events = list(hass.bus.fired)
        await asyncio.gather(
            manager.async_update_rule(rule["id"], {"level": "info"}),
            manager.async_update_rule(rule["id"], {"level": "alert"}),
        )
        assert manager.records[key].as_storage_dict() == before
        assert manager.config["rules"][0]["level"] == "alert"
        assert hass.bus.fired == events

    run(scenario())


def test_information_and_alert_produce_identical_state_transitions(
    hass, entry, set_now
):
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    hass.states.set("sensor.test", "off")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    rules = [
        run(manager.async_create_rule(payload(level=level, duration=10)))
        for level in ("alert", "info")
    ]
    now = dt_util.now()
    ids = [f"rule:{rule['id']}:sensor.test" for rule in rules]
    hass.states.set("sensor.test", "on")
    run(manager.async_evaluate_entity("sensor.test"))
    for elapsed in (0, 11):
        set_now(now + timedelta(seconds=elapsed))
        run(manager.async_evaluate_entity("sensor.test"))
        records = []
        for key in ids:
            record = manager.records[key].as_public_dict()
            for field in ("id", "rule_id", "level"):
                record.pop(field)
            records.append(record)
        assert records[0] == records[1]
    run(manager.async_set_acknowledgements(ids, True, "admin"))
    hass.states.set("sensor.test", "off")
    run(manager.async_evaluate_entity("sensor.test"))
    assert all(key not in manager.records for key in ids)
    assert [event[0] for event in hass.bus.fired if event[1].get("id") == ids[0]] == [
        event[0] for event in hass.bus.fired if event[1].get("id") == ids[1]
    ]
    assert {entry.level for entry in manager.history} == {"alert", "info"}


@pytest.mark.parametrize("level", ["alert", "info"])
def test_information_label_exception_is_independent_of_visual_level(hass, entry, level):
    async def scenario():
        profile = _profile(reminder_interval=300)
        profile["exceptions"] = [
            {
                "selector_type": "label",
                "selector_id": "information",
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
            "level": level,
            "labels": ["information"],
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
def test_level_edit_preserves_unprocessed_transition(hass, entry, set_now, confirmed):
    from test_transitions import expire

    manager, key, rule = setup(hass, entry, duration=0 if confirmed else 30)
    edge(manager, hass, "B", flush=not confirmed)
    observations = (
        manager._transition_confirmed if confirmed else manager._transition_observations
    )
    observation = observations[key]
    run(manager.async_update_rule(rule["id"], {"level": "info"}))
    assert observations[key] is observation
    set_now(observation.due_at)
    if confirmed:
        run(manager._async_flush_queued_evaluations())
    else:
        expire(manager, key)
    assert manager.records[key].active_since == observation.due_at
    assert manager.records[key].details.level == "info"
    assert sum(event == EVENT_ALERT_STARTED for event, _ in hass.bus.fired) == 1


@pytest.mark.parametrize("other_change", [False, True])
def test_import_updates_level_of_preserved_transition_record(hass, entry, other_change):
    from custom_components.alert_manager.yaml_io import dump_config_yaml

    manager, key, _rule = setup(hass, entry)
    edge(manager, hass, "B")
    config = deepcopy(manager.get_config())
    config["rules"][0]["level"] = "info"
    if other_change:
        config["notification_batch_delay"] = 60
    run(manager.async_import_config(dump_config_yaml(config)))
    assert manager.records[key].details.level == "info"


@pytest.mark.parametrize("via_import", [False, True])
def test_level_only_save_keeps_template_timers_and_notification_batches(
    hass, entry, monkeypatch, via_import
):
    from unittest.mock import Mock

    from custom_components.alert_manager.yaml_io import dump_config_yaml

    manager, key, rule = setup(hass, entry, duration=30)
    edge(manager, hass, "B")
    cancel = Mock()
    dependency = ("condition", rule["id"], "sensor.edge")
    manager._template_rate_limit_timers[dependency] = cancel
    timers = dict(manager._timers)
    rebuild = Mock(side_effect=AssertionError("Do not rebuild all rule indexes"))
    monkeypatch.setattr(manager, "_rebuild_rule_index", rebuild)
    discard = Mock(side_effect=AssertionError("Do not discard notification batches"))
    monkeypatch.setattr(manager.notification_runtime, "discard_batches", discard)
    if via_import:
        config = deepcopy(manager.get_config())
        config["rules"][0]["level"] = "info"
        run(manager.async_import_config(dump_config_yaml(config)))
    else:
        run(manager.async_update_rule(rule["id"], {"level": "info"}))
    cancel.assert_not_called()
    discard.assert_not_called()
    rebuild.assert_not_called()
    assert manager._timers == timers
    assert manager._template_rate_limit_timers[dependency] is cancel
    assert manager.records[key].details.level == "info"
    assert manager._transition_rules_by_id[rule["id"]].level == "info"
    assert manager._rules_by_entity["sensor.edge"][0].level == "info"
