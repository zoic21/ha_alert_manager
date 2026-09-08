"""Transition edges, hold deadlines and episode persistence regressions."""

import asyncio
from datetime import timedelta

import pytest
from homeassistant.core import Event
from homeassistant.util import dt as dt_util

from custom_components.alert_manager.const import EVENT_ALERT_STARTED
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertRecord, AlertStatus, Rule
from custom_components.alert_manager.yaml_io import dump_rule_yaml, parse_rule_yaml


def run(coro):
    return asyncio.run(coro)


def setup(hass, entry, **changes):
    hass.states.set("sensor.edge", "A", {"mode": "A"})
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    rule = run(
        manager.async_create_rule(
            {
                "name": "Edge",
                "entity_ids": ["sensor.edge"],
                "source": "transition",
                "from_value": "A",
                "to_value": "B",
                "duration": 0,
                "auto_resolve": 60,
                **changes,
            }
        )
    )
    return manager, f"rule:{rule['id']}:sensor.edge", rule


def edge(manager, hass, state, attrs=None, *, flush=True):
    old = hass.states.get("sensor.edge")
    hass.states.set("sensor.edge", state, attrs or {})
    manager._evaluation_flush_scheduled = True
    manager._state_changed(
        Event(
            {
                "entity_id": "sensor.edge",
                "old_state": old,
                "new_state": hass.states.get("sensor.edge"),
            }
        )
    )
    if flush:
        run(manager._async_flush_queued_evaluations())


def expire(manager, alert_id):
    manager._evaluation_flush_scheduled = True
    manager._timer_due(alert_id)
    run(manager._async_flush_queued_evaluations())


def test_immediate_edge_survives_coalescing_and_repeats_keep_ack(hass, entry, set_now):
    manager, key, _ = setup(hass, entry)
    now = dt_util.now()
    edge(manager, hass, "B", flush=False)
    edge(manager, hass, "C")
    record = manager.records[key]
    assert record.status is AlertStatus.ACTIVE
    assert record.expires_at == now + timedelta(seconds=60)
    record.acknowledged = True
    record.acknowledged_at = now
    set_now(now + timedelta(seconds=20))
    edge(manager, hass, "A")
    edge(manager, hass, "B")
    assert manager.records[key] is record
    assert record.acknowledged
    assert record.expires_at == now + timedelta(seconds=80)
    assert len([e for e in hass.bus.fired if e[0] == EVENT_ALERT_STARTED]) == 1
    set_now(record.expires_at)
    expire(manager, key)
    assert key not in manager.records
    history = manager.history[-1]
    assert history.condition_params["resolution_reason"] == "automatic"
    assert history.condition_params["from_value"] == "A"
    assert history.trigger_value == "B"
    edge(manager, hass, "A")
    edge(manager, hass, "B")
    assert not manager.records[key].acknowledged


@pytest.mark.parametrize("attribute", [False, True])
def test_hold_interruption_unrelated_updates_and_repeated_confirmation(
    hass, entry, set_now, attribute
):
    manager, key, _ = setup(
        hass,
        entry,
        duration=30,
        **(
            {"source": "attribute_transition", "attribute": "mode"} if attribute else {}
        ),
    )
    now = dt_util.now()

    def update(value, **attrs):
        edge(
            manager, hass, "available" if attribute else value, {"mode": value, **attrs}
        )

    update("B")
    assert manager.records[key].status is AlertStatus.PENDING
    due = manager.records[key].due_at
    set_now(now + timedelta(seconds=10))
    update("B", other=1)
    assert manager.records[key].due_at == due
    update("C")
    assert key not in manager.records
    update("B")
    assert key not in manager.records
    update("A")
    update("B")
    set_now(now + timedelta(seconds=40))
    expire(manager, key)
    record = manager.records[key]
    assert record.status is AlertStatus.ACTIVE
    assert record.expires_at == now + timedelta(seconds=100)
    record.acknowledged = True
    record.acknowledged_at = dt_util.now()
    set_now(now + timedelta(seconds=50))
    update("A")
    update("B")
    assert record.expires_at == now + timedelta(seconds=100)
    set_now(now + timedelta(seconds=80))
    expire(manager, key)
    assert record.expires_at == now + timedelta(seconds=140)
    assert record.acknowledged


def test_initial_discovery_unknown_and_tester_never_arm(hass, entry):
    manager, key, rule = setup(hass, entry)
    for value in ("unknown", "B", "unavailable", "B"):
        edge(manager, hass, value)
    assert key not in manager.records
    hass.states.set("sensor.edge", "B")
    run(manager.async_evaluate_all())
    result = run(
        manager.async_test_rule(
            {k: v for k, v in rule.items() if k not in ("id", "version")}
        )
    )
    assert result["results"][0]["reason"] == "transition_required"
    assert not manager._transition_observations
    assert not manager._transition_confirmed
    assert key not in manager.records


def test_active_deadline_restored_pending_not_restored(hass, entry, set_now):
    manager, key, rule = setup(hass, entry)
    edge(manager, hass, "B")
    record = manager.records[key]
    deadline = record.expires_at
    assert AlertRecord.from_dict(record.as_storage_dict()).expires_at == deadline
    run(manager.async_unload())
    restored = AlertManager(hass, entry)
    run(restored.async_setup())
    assert restored.records[key].expires_at == deadline
    set_now(deadline + timedelta(seconds=1))
    run(restored._async_finish_startup_reconciliation())
    expire(restored, key)
    assert key not in restored.records
    run(restored.async_update_rule(rule["id"], {"duration": 30}))
    edge(restored, hass, "A")
    edge(restored, hass, "B")
    run(restored.async_unload())
    reloaded = AlertManager(hass, entry)
    run(reloaded.async_setup())
    assert key not in reloaded.records
    assert not reloaded._transition_observations


def test_rule_changes_discard_holds_and_stale_timer_cannot_activate(
    hass, entry, set_now
):
    manager, key, rule = setup(hass, entry, duration=30)
    edge(manager, hass, "B")
    timers = [
        t
        for t in hass.timers
        if not t["cancelled"] and t["point"] <= manager.records[key].due_at
    ]
    run(manager.async_update_rule(rule["id"], {"to_value": "C"}))
    assert key not in manager.records
    assert not manager._transition_observations
    set_now(dt_util.now() + timedelta(seconds=60))
    for timer in timers:
        timer["action"](dt_util.now())
    run(manager._async_flush_queued_evaluations())
    assert key not in manager.records


@pytest.mark.parametrize(
    "changes",
    [
        {"from_value": None},
        {"to_value": []},
        {"auto_resolve": 0},
        {"auto_resolve": True},
        {"from_value": "unknown"},
        {"to_value": "A"},
    ],
)
def test_transition_validation(changes):
    with pytest.raises(ValueError):
        Rule.from_dict(
            {
                "id": "edge",
                "name": "Edge",
                "entity_ids": ["sensor.edge"],
                "source": "transition",
                "from_value": "A",
                "to_value": "B",
                **changes,
            }
        )


def test_transition_yaml_round_trip():
    rule = Rule.from_dict(
        {
            "id": "edge",
            "name": "Edge",
            "entity_ids": ["sensor.edge"],
            "source": "attribute_transition",
            "attribute": "mode",
            "from_value": False,
            "to_value": True,
            "auto_resolve": 120,
        }
    )
    restored = parse_rule_yaml(dump_rule_yaml(rule))
    assert restored.from_value is False
    assert restored.to_value is True
    assert restored.duration == 0
    assert restored.auto_resolve == 120


def test_hold_completed_before_coalesced_departure(hass, entry, set_now):
    manager, key, _ = setup(hass, entry, duration=30)
    now = dt_util.now()
    edge(manager, hass, "B", flush=False)
    set_now(now + timedelta(seconds=31))
    edge(manager, hass, "C")
    assert manager.records[key].status is AlertStatus.ACTIVE


def test_expiration_during_repeat_hold_starts_new_episode(hass, entry, set_now):
    manager, key, _ = setup(hass, entry, duration=30)
    now = dt_util.now()
    edge(manager, hass, "B")
    set_now(now + timedelta(seconds=30))
    expire(manager, key)
    first = manager.records[key]
    set_now(now + timedelta(seconds=80))
    edge(manager, hass, "A")
    edge(manager, hass, "B")
    set_now(now + timedelta(seconds=90))
    expire(manager, key)
    assert manager.records[key] is not first
    assert manager.records[key].status is AlertStatus.PENDING
    assert len(manager.history) == 1
    set_now(now + timedelta(seconds=110))
    expire(manager, key)
    assert manager.records[key].status is AlertStatus.ACTIVE


def test_pause_does_not_resume_unobserved_hold(hass, entry, set_now):
    manager, key, _ = setup(hass, entry, duration=30)
    edge(manager, hass, "B")
    run(manager.async_set_monitoring(False))
    set_now(dt_util.now() + timedelta(seconds=60))
    run(manager.async_set_monitoring(True))
    assert key not in manager.records
    edge(manager, hass, "A")
    edge(manager, hass, "B")
    assert manager.records[key].status is AlertStatus.PENDING
