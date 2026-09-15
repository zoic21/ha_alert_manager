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
        {"resolve_mode": "invalid"},
        {"resolve_mode": None},
        {"resolve_mode": []},
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


@pytest.mark.parametrize("resolve_mode", ["duration", "state"])
def test_transition_yaml_round_trip(resolve_mode):
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
            "resolve_mode": resolve_mode,
        }
    )
    restored = parse_rule_yaml(dump_rule_yaml(rule))
    assert restored.from_value is False
    assert restored.to_value is True
    assert restored.duration == 0
    assert restored.auto_resolve == 120
    assert restored.resolve_mode == resolve_mode


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


@pytest.mark.parametrize("attribute", [False, True])
def test_legacy_active_transition_survives_migration(hass, entry, set_now, attribute):
    """Legacy stored sources retain the same acknowledged episode and expiration."""
    manager, key, rule = setup(
        hass, entry, source="value_transition", attribute="mode" if attribute else None
    )
    edge(manager, hass, "A" if attribute else "B", {"mode": "B"})
    run(manager.async_acknowledge(key, "admin"))
    record = manager.records[key]
    deadline = record.expires_at
    detected_at = record.detected_at
    # Simulate a configuration and active record written before this migration.
    legacy_source = "attribute_transition" if attribute else "transition"
    record.details.source = legacy_source
    manager.config["rules"][0]["source"] = legacy_source
    if not attribute:
        manager.config["rules"][0]["attribute"] = "stale"
        record.details.attribute = "stale"
    run(manager.async_unload())
    restored = AlertManager(hass, entry)
    run(restored.async_setup())
    assert restored.records[key].details.source == "value_transition"
    assert restored.records[key].details.attribute == ("mode" if attribute else None)
    run(restored._async_finish_startup_reconciliation())
    assert restored.records[key].expires_at == deadline
    assert restored.records[key].detected_at == detected_at
    assert restored.records[key].acknowledged
    assert restored.records[key].details.rule_id == rule["id"]
    assert not restored.history
    set_now(deadline + timedelta(seconds=1))
    expire(restored, key)
    assert key not in restored.records
    assert len(restored.history) == 1


@pytest.mark.parametrize("attribute", [False, True])
def test_state_resolution_keeps_ack_and_ignores_unrelated_updates(
    hass, entry, set_now, attribute
):
    manager, key, _ = setup(
        hass,
        entry,
        source="value_transition",
        resolve_mode="state",
        attribute="mode" if attribute else None,
    )

    def update(value, **attrs):
        edge(
            manager, hass, "available" if attribute else value, {"mode": value, **attrs}
        )

    update("B")
    record = manager.records[key]
    assert record.status is AlertStatus.ACTIVE
    assert record.expires_at is None
    run(manager.async_acknowledge(key, "admin"))
    set_now(dt_util.now() + timedelta(seconds=120))
    update("B", unrelated=1)
    assert manager.records[key] is record
    assert record.acknowledged
    assert key not in manager._timers
    update("C")
    assert key not in manager.records
    assert len(manager.history) == 1
    assert manager.history[-1].condition_params.get("resolution_reason") != "automatic"
    update("B")  # C → B is not the configured edge.
    assert key not in manager.records
    update("A")
    update("B")
    assert manager.records[key] is not record
    assert not manager.records[key].acknowledged


def test_state_resolution_waits_for_known_value(hass, entry):
    manager, key, _ = setup(hass, entry, resolve_mode="state")
    edge(manager, hass, "B")
    record = manager.records[key]
    for state in ("unknown", "unavailable", "B"):
        edge(manager, hass, state)
        assert manager.records[key] is record
    edge(manager, hass, "C")
    assert key not in manager.records


@pytest.mark.parametrize("leave_before_confirmation", [False, True])
def test_state_resolution_hold(hass, entry, set_now, leave_before_confirmation):
    manager, key, _ = setup(hass, entry, resolve_mode="state", duration=30)
    now = dt_util.now()
    edge(manager, hass, "B")
    assert manager.records[key].status is AlertStatus.PENDING
    if leave_before_confirmation:
        set_now(now + timedelta(seconds=10))
        edge(manager, hass, "C")
        assert not manager.history
    else:
        set_now(now + timedelta(seconds=30))
        expire(manager, key)
        assert manager.records[key].status is AlertStatus.ACTIVE
        assert manager.records[key].expires_at is None
        edge(manager, hass, "C")
        assert len(manager.history) == 1
    assert key not in manager.records


def test_state_resolution_coalesced_activation_and_departure(hass, entry):
    manager, key, _ = setup(hass, entry, resolve_mode="state")
    edge(manager, hass, "B", flush=False)
    edge(manager, hass, "C")
    assert key not in manager.records
    assert len(manager.history) == 1


@pytest.mark.parametrize("arrival_maintained", [False, True])
def test_state_resolution_restored_and_reconciled(hass, entry, arrival_maintained):
    manager, key, _ = setup(hass, entry, resolve_mode="state")
    edge(manager, hass, "B")
    run(manager.async_acknowledge(key, "admin"))
    run(manager.async_unload())
    if not arrival_maintained:
        hass.states.set("sensor.edge", "C")
    restored = AlertManager(hass, entry)
    run(restored.async_setup())
    run(restored._async_finish_startup_reconciliation())
    assert (key in restored.records) is arrival_maintained
    if arrival_maintained:
        assert restored.records[key].expires_at is None
        assert restored.records[key].acknowledged
        edge(restored, hass, "C")
        assert key not in restored.records


def test_resolution_mode_edit_replaces_deadline(hass, entry, set_now):
    manager, key, rule = setup(hass, entry)
    edge(manager, hass, "B")
    record = manager.records[key]
    deadline = record.expires_at
    run(manager.async_update_rule(rule["id"], {"resolve_mode": "state"}))
    assert manager.records[key] is record
    assert record.expires_at is None
    set_now(deadline + timedelta(seconds=1))
    expire(manager, key)
    assert manager.records[key] is record
    run(manager.async_update_rule(rule["id"], {"resolve_mode": "duration"}))
    assert record.expires_at == dt_util.now() + timedelta(seconds=60)
    set_now(record.expires_at)
    expire(manager, key)
    assert key not in manager.records


def test_state_resolution_pause_rechecks_without_new_edge(hass, entry):
    manager, key, _ = setup(hass, entry, resolve_mode="state")
    edge(manager, hass, "B")
    run(manager.async_set_monitoring(False))
    edge(manager, hass, "C")
    assert key in manager.records
    run(manager.async_set_monitoring(True))
    assert key not in manager.records
    edge(manager, hass, "B")
    assert key not in manager.records


@pytest.mark.parametrize("attribute", [None, "mode"])
@pytest.mark.parametrize(
    "operator,value,stay,resolve",
    [
        ("above", 10, "5", "15"),
        ("below", 10, "15", "5"),
        ("between", [10, 20], "5", "15"),
        ("outside", [10, 20], "15", "5"),
        ("equals", ["done", "off"], "running", "done"),
        ("not_equals", ["B", "running"], "running", "done"),
        ("contains", ["done"], "running", "all done"),
        ("not_contains", ["B", "running"], "running", "done"),
    ],
)
def test_transition_resolution_comparison(
    hass, entry, attribute, operator, value, stay, resolve
):
    manager, key, rule = setup(
        hass,
        entry,
        source="value_transition",
        attribute=attribute,
        resolve_mode="condition",
        resolve_condition={"operator": operator, "value": value},
    )

    def update(value):
        edge(
            manager,
            hass,
            "ok" if attribute else value,
            {"mode": value} if attribute else None,
        )

    update("B")
    assert key in manager.records
    assert manager.records[key].expires_at is None
    for invalid in ("unknown", "unavailable"):
        update(invalid)
        assert key in manager.records
    update(stay)
    assert key in manager.records
    update(resolve)
    assert key not in manager.records
    assert len(manager.history) == 1
    restored = parse_rule_yaml(dump_rule_yaml(Rule.from_dict(rule)))
    assert restored.resolve_condition == {"operator": operator, "value": value}
