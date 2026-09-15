"""Deterministic sequence timing and conservative observations."""

from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.core import State

# Integration-level event/timer/lifecycle tests use the same harness as simple edges.
from homeassistant.util import dt as dt_util
from test_transitions import edge, run, setup

from custom_components.alert_manager.const import EVENT_ALERT_STARTED
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertStatus, Rule
from custom_components.alert_manager.sequences import SequenceProgress
from custom_components.alert_manager.yaml_io import dump_rule_yaml, parse_rule_yaml

START = datetime(2026, 1, 1, tzinfo=UTC)


def sequence(**changes):
    return Rule.from_dict(
        {
            "id": "sequence",
            "name": "Cycle",
            "entity_ids": ["sensor.power"],
            "source": "value_sequence",
            "steps": [
                {"operator": "above", "value": 100, "duration": 300},
                {"operator": "below", "value": 10, "duration": 120},
            ],
            **changes,
        }
    )


def observe(progress, value, seconds, **kwargs):
    return progress.observe(
        State("sensor.power", str(value)), START + timedelta(seconds=seconds), **kwargs
    )


def test_order_continuity_and_next_step_no_backdating():
    p = SequenceProgress(sequence())
    assert observe(p, 5, 0) is None
    assert p.started_at is None
    observe(p, 120, 10)
    observe(p, 350, 150)
    observe(p, 110, 309)
    assert p.hold_since == START + timedelta(seconds=10)
    observe(p, 110, 310)
    assert p.index == 1
    observe(p, 80, 400)
    observe(p, 20, 500)
    assert p.index == 1
    observe(p, 5, 600)
    assert observe(p, 6, 719) is None
    evidence = observe(p, 6, 720)
    assert len(evidence) == 2
    assert evidence[1]["seconds"] == 120
    assert observe(p, 6, 900) is None
    observe(p, 120, 1000)
    observe(p, 120, 1300)
    observe(p, 5, 1400)
    assert observe(p, 5, 1520) is not None


def test_interrupted_hold_restarts_only_current_step():
    p = SequenceProgress(sequence())
    observe(p, 120, 0)
    observe(p, 120, 300)
    observe(p, 5, 400)
    observe(p, 18, 450)
    assert p.index == 1 and p.hold_since is None
    assert p.reason == "interrupted"
    observe(p, 5, 500)
    assert observe(p, 5, 619) is None
    assert observe(p, 5, 620)


@pytest.mark.parametrize(
    "mode,duration,maximum,exit_at,valid",
    [
        ("less_than", 300, 0, 299, True),
        ("less_than", 300, 0, 300, False),
        ("between", 120, 300, 119, False),
        ("between", 120, 300, 120, True),
        ("between", 120, 300, 300, True),
        ("between", 120, 300, 301, False),
    ],
)
def test_exit_modes(mode, duration, maximum, exit_at, valid):
    rule = sequence(
        steps=[
            {
                "operator": "above",
                "value": 100,
                "duration_mode": mode,
                "duration": duration,
                "duration_max": maximum,
            },
            {"operator": "below", "value": 10, "duration": 10},
        ]
    )
    p = SequenceProgress(rule)
    observe(p, 120, 0)
    observe(p, 150, exit_at)
    assert p.index == 0
    observe(p, 5, exit_at)
    assert p.index == int(valid)
    if valid:
        assert p.hold_since == START + timedelta(seconds=exit_at)
        assert observe(p, 5, exit_at + 10)


@pytest.mark.parametrize("invalid", ["unknown", "unavailable", "oops", "nan", "inf"])
def test_invalid_cannot_validate_exit(invalid):
    p = SequenceProgress(
        sequence(
            steps=[
                {
                    "operator": "above",
                    "value": 100,
                    "duration_mode": "less_than",
                    "duration": 300,
                },
                {"operator": "below", "value": 10},
            ]
        )
    )
    observe(p, 120, 0)
    observe(p, invalid, 10)
    observe(p, 5, 20)
    assert p.index == 0 and not p.completed


@pytest.mark.parametrize("operator", ["not_equals", "not_contains"])
def test_missing_attribute_and_unknown_never_negative_success(operator):
    p = SequenceProgress(
        sequence(
            attribute="power",
            steps=[
                {"operator": operator, "value": "running"},
                {"operator": "equals", "value": "idle"},
            ],
        )
    )
    for state in [
        State("sensor.power", "ok"),
        State("sensor.power", "ok", {"power": "unknown"}),
        State("sensor.power", "unavailable", {"power": "idle"}),
    ]:
        assert p.observe(state, START) is None
        assert p.index == 0


def test_timeout_and_outgoing_deadline_race():
    p = SequenceProgress(sequence(sequence_timeout=400))
    observe(p, 120, 0)
    observe(p, 5, 300, previous=State("sensor.power", "120"))
    assert p.index == 1 and p.hold_since == START + timedelta(seconds=300)
    observe(p, 5, 400)
    assert p.index == 0 and p.started_at is None and p.reason == "expired"


def test_yaml_and_readonly_diagnostics():
    rule = sequence()
    assert (
        parse_rule_yaml(dump_rule_yaml(rule), rule_id=rule.id).as_dict()
        == rule.as_dict()
    )
    p = SequenceProgress(rule)
    observe(p, 120, 0)
    before = p.hold_since
    result = p.snapshot(State("sensor.power", "120"), START + timedelta(seconds=200))
    assert result["matching"] is True and result["remaining"] == 100
    result["completed"].append({})
    assert p.hold_since == before and not p.completed


@pytest.mark.parametrize(
    "changes",
    [
        {"steps": []},
        {"steps": [{}] * 21},
        {"sequence_timeout": True},
        {"duration": 5},
        {"condition_template": "{{ true }}"},
        {"resolve_mode": "state"},
        {"steps": [{"operator": "above", "value": 2, "duration_mode": "exactly"}] * 2},
        {"steps": [{"operator": "above", "value": "nan"}] * 2},
        {
            "steps": [{"operator": "equals", "value": 1, "entity_id": "sensor.other"}]
            * 2
        },
    ],
)
def test_schema_rejects_unsupported_or_unbounded_input(changes):
    with pytest.raises(ValueError):
        sequence(**changes)


def setup_sequence(hass, entry, **changes):
    return setup(
        hass,
        entry,
        source="value_sequence",
        from_value=None,
        to_value=None,
        steps=[
            {"operator": "above", "value": 100, "duration": 30},
            {"operator": "below", "value": 10, "duration": 20},
        ],
        **changes,
    )


def sequence_timer(manager, hass, key):
    due = manager._sequence_progress[key].deadline()
    return next(
        timer
        for timer in reversed(hass.timers)
        if timer["point"] == due and not timer["cancelled"]
    )


def fire_sequence_timer(manager, hass, key):
    timer = sequence_timer(manager, hass, key)
    manager._evaluation_flush_scheduled = True
    timer["action"](dt_util.now())
    run(manager._async_flush_queued_evaluations())


def test_sequence_handoff_resolution_history_and_restart(hass, entry, set_now):
    manager, key, _rule = setup_sequence(hass, entry)
    now = dt_util.now()
    assert not manager._sequence_progress  # no snapshot reconstruction
    edge(manager, hass, "120")
    assert key not in manager.records  # no pending alert for incomplete scenarios
    set_now(now + timedelta(seconds=30))
    fire_sequence_timer(manager, hass, key)
    assert manager._sequence_progress[key].index == 1
    edge(manager, hass, "5")
    set_now(now + timedelta(seconds=50))
    fire_sequence_timer(manager, hass, key)
    record = manager.records[key]
    assert record.status is AlertStatus.ACTIVE
    assert len(record.details.condition_params["evidence"]) == 2
    assert record.details.condition_key == "rule.sequence"
    assert len([e for e in hass.bus.fired if e[0] == EVENT_ALERT_STARTED]) == 1
    run(manager.async_unload())
    restored = AlertManager(hass, entry)
    run(restored.async_setup())
    run(restored._async_finish_startup_reconciliation())
    assert not restored._sequence_progress
    assert (
        restored.records[key].details.condition_params["evidence"]
        == record.details.condition_params["evidence"]
    )
    set_now(record.expires_at)
    restored._evaluation_flush_scheduled = True
    restored._timer_due(key)
    run(restored._async_flush_queued_evaluations())
    assert key not in restored.records
    assert (
        restored.history[-1].condition_params["evidence"]
        == record.details.condition_params["evidence"]
    )


@pytest.mark.parametrize(
    "operation", ["monitor", "disable", "edit", "delete", "unload"]
)
def test_running_sequence_cleanup_and_stale_callback(hass, entry, set_now, operation):
    manager, key, rule = setup_sequence(hass, entry)
    now = dt_util.now()
    edge(manager, hass, "120")
    timer = sequence_timer(manager, hass, key)
    if operation == "monitor":
        run(manager.async_set_monitoring(False))
        run(manager.async_set_monitoring(True))
    elif operation == "disable":
        run(manager.async_update_rule(rule["id"], {"enabled": False}))
        run(manager.async_update_rule(rule["id"], {"enabled": True}))
    elif operation == "edit":
        run(
            manager.async_update_rule(
                rule["id"],
                {
                    "steps": [
                        {"operator": "above", "value": 200},
                        {"operator": "below", "value": 5},
                    ]
                },
            )
        )
    elif operation == "delete":
        run(manager.async_delete_rule(rule["id"]))
    else:
        run(manager.async_unload())
    assert key not in manager._sequence_progress
    assert timer["cancelled"]
    set_now(now + timedelta(seconds=30))
    timer["action"](dt_util.now())
    assert key not in manager._sequence_progress and key not in manager.records


def test_sequence_tester_does_not_mutate_and_reads_current_progress(hass, entry):
    manager, key, rule = setup_sequence(hass, entry)
    edge(manager, hass, "120")
    progress = manager._sequence_progress[key]
    timer = sequence_timer(manager, hass, key)
    result = run(manager.async_test_rule({}, rule_id=rule["id"]))["results"][0]
    assert result["reason"] == "sequence_required"
    assert result["sequence"]["matching"] is True
    assert result["sequence"]["reason"] == "holding"
    assert manager._sequence_progress[key] is progress
    assert sequence_timer(manager, hass, key) is timer
    draft = run(
        manager.async_test_rule(
            {
                "steps": [
                    {"operator": "below", "value": 50},
                    {"operator": "above", "value": 200},
                ]
            },
            rule_id=rule["id"],
        )
    )["results"][0]
    assert draft["sequence"]["reason"] == "waiting"
    assert progress.hold_since is not None


def test_sequence_outgoing_event_and_timer_cannot_complete_twice(hass, entry, set_now):
    manager, key, _rule = setup_sequence(hass, entry)
    now = dt_util.now()
    edge(manager, hass, "120")
    stale = sequence_timer(manager, hass, key)
    set_now(now + timedelta(seconds=30))
    edge(manager, hass, "5")
    stale["action"](dt_util.now())
    assert manager._sequence_progress[key].index == 1
    set_now(now + timedelta(seconds=50))
    stale = sequence_timer(manager, hass, key)
    edge(manager, hass, "15")
    stale["action"](dt_util.now())
    assert manager.records[key].status is AlertStatus.ACTIVE
    assert len([e for e in hass.bus.fired if e[0] == EVENT_ALERT_STARTED]) == 1


def test_sequence_entities_are_independent(hass, entry, set_now):
    from homeassistant.core import Event

    hass.states.set("sensor.second", "0")
    manager, key, rule = setup_sequence(
        hass, entry, entity_ids=["sensor.edge", "sensor.second"]
    )
    now = dt_util.now()
    edge(manager, hass, "120")
    second = f"rule:{rule['id']}:sensor.second"
    assert second not in manager._sequence_progress
    set_now(now + timedelta(seconds=15))
    old = hass.states.get("sensor.second")
    hass.states.set("sensor.second", "150")
    manager._evaluation_flush_scheduled = True
    manager._state_changed(
        Event(
            {
                "entity_id": "sensor.second",
                "old_state": old,
                "new_state": hass.states.get("sensor.second"),
            }
        )
    )
    run(manager._async_flush_queued_evaluations())
    assert manager._sequence_progress[key].hold_since == now
    assert manager._sequence_progress[second].hold_since == now + timedelta(seconds=15)


def test_timer_waits_for_a_state_event_already_queued(hass, entry, set_now):
    from homeassistant.core import Event

    manager, key, _rule = setup_sequence(hass, entry)
    now = dt_util.now()
    edge(manager, hass, "120")
    timer = sequence_timer(manager, hass, key)
    old = hass.states.get("sensor.edge")
    set_now(now + timedelta(seconds=30))
    hass.states.set("sensor.edge", "5")
    manager._evaluation_flush_scheduled = True
    timer["action"](dt_util.now())
    manager._state_changed(
        Event(
            {
                "entity_id": "sensor.edge",
                "old_state": old,
                "new_state": hass.states.get("sensor.edge"),
            }
        )
    )
    run(manager._async_flush_queued_evaluations())
    assert manager._sequence_progress[key].index == 1
    assert manager._sequence_progress[key].hold_since == dt_util.now()


def test_matching_updates_reuse_timer_and_unknown_at_deadline_cancels(
    hass, entry, set_now
):
    manager, key, _rule = setup_sequence(hass, entry)
    now = dt_util.now()
    edge(manager, hass, "120")
    timer = sequence_timer(manager, hass, key)
    set_now(now + timedelta(seconds=15))
    edge(manager, hass, "180")
    assert sequence_timer(manager, hass, key) is timer
    set_now(now + timedelta(seconds=30))
    edge(manager, hass, "unknown")
    assert manager._sequence_progress[key].index == 0
    assert manager._sequence_progress[key].hold_since is None
    assert timer["cancelled"]


def test_switching_to_a_simple_rule_and_yaml_does_not_keep_sequence_fields(hass, entry):
    manager, key, rule = setup_sequence(hass, entry)
    edge(manager, hass, "120")
    changed = run(
        manager.async_update_rule_yaml(
            rule["id"],
            "name: Simple\nentity_ids: [sensor.edge]\nsource: value\n"
            "operator: above\nvalue: 50\nduration: 0\n",
        )
    )
    assert "steps" not in changed and "sequence_timeout" not in changed
    assert key not in manager._sequence_progress


def test_failed_edit_restores_progress_and_deadline(hass, entry, monkeypatch, set_now):
    manager, key, rule = setup_sequence(hass, entry)
    now = dt_util.now()
    edge(manager, hass, "120")
    original = manager._sequence_progress[key].hold_since

    async def fail():
        raise OSError("storage unavailable")

    monkeypatch.setattr(manager, "_async_save_state", fail)
    with pytest.raises(OSError):
        run(
            manager.async_update_rule(
                rule["id"],
                {
                    "steps": [
                        {"operator": "above", "value": 200},
                        {"operator": "below", "value": 5},
                    ]
                },
            )
        )
    assert manager._sequence_progress[key].hold_since == original
    set_now(now + timedelta(seconds=30))
    fire_sequence_timer(manager, hass, key)
    assert manager._sequence_progress[key].index == 1


def test_registry_disabled_entity_cannot_progress(hass, entry, set_now):
    from types import SimpleNamespace

    manager, key, _rule = setup_sequence(hass, entry)
    now = dt_util.now()
    edge(manager, hass, "120")
    timer = sequence_timer(manager, hass, key)
    manager._entity_registry.entities["sensor.edge"] = SimpleNamespace(
        disabled_by="user", platform="test"
    )
    set_now(now + timedelta(seconds=30))
    timer["action"](dt_util.now())
    assert key not in manager._sequence_progress and key not in manager.records


def test_repeated_full_sequence_keeps_ack_and_emits_an_occurrence(hass, entry, set_now):
    manager, key, _rule = setup_sequence(hass, entry)
    now = dt_util.now()
    edge(manager, hass, "120")
    set_now(now + timedelta(seconds=30))
    edge(manager, hass, "5")
    set_now(now + timedelta(seconds=50))
    fire_sequence_timer(manager, hass, key)
    record = manager.records[key]
    record.acknowledged = True
    record.acknowledged_at = dt_util.now()
    edge(manager, hass, "120")
    set_now(now + timedelta(seconds=80))
    edge(manager, hass, "5")
    set_now(now + timedelta(seconds=100))
    edge(manager, hass, "20", flush=False)
    occurrences = []
    manager._evaluate_transitions(
        "sensor.edge", dt_util.now(), emit_events=True, new_occurrences=occurrences
    )
    assert len(occurrences) == 1
    assert manager.records[key] is record and record.acknowledged
    assert record.expires_at == dt_util.now() + timedelta(seconds=60)
    assert (
        record.details.condition_params["last_occurrence"] == dt_util.now().isoformat()
    )
