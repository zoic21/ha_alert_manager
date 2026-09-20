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
    assert evidence[0]["started_value"] == "120"
    assert evidence[0]["completed_value"] == "110"
    assert evidence[1]["started_value"] == "5"
    assert evidence[1]["completed_value"] == "6"
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
        assert p.completed[0]["started_value"] == "120"
        assert p.completed[0]["completed_value"] == "5"
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
        {"resolve_mode": "invalid"},
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
        steps=changes.pop(
            "steps",
            [
                {"operator": "above", "value": 100, "duration": 30},
                {"operator": "below", "value": 10, "duration": 20},
            ],
        ),
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


@pytest.mark.parametrize("instant", [False, True])
def test_sequence_handoff_resolution_history_and_restart(hass, entry, set_now, instant):
    changes = (
        {
            "steps": [
                {"operator": "above", "value": 100, "duration": 0},
                {"operator": "below", "value": 10, "duration": 0},
            ]
        }
        if instant
        else {}
    )
    manager, key, _rule = setup_sequence(hass, entry, **changes)
    now = dt_util.now()
    assert not manager._sequence_progress  # no snapshot reconstruction
    edge(manager, hass, "120")
    assert key not in manager.records  # no pending alert for incomplete scenarios
    set_now(now + timedelta(seconds=30))
    if not instant:
        fire_sequence_timer(manager, hass, key)
    assert manager._sequence_progress[key].index == 1
    edge(manager, hass, "5")
    set_now(now + timedelta(seconds=50))
    if not instant:
        fire_sequence_timer(manager, hass, key)
    record = manager.records[key]
    assert record.status is AlertStatus.ACTIVE
    assert len(record.details.condition_params["evidence"]) == 2
    assert record.details.condition_params["evidence"][0]["started_value"] == "120"
    assert record.details.condition_params["evidence"][1]["completed_value"] == "5"
    assert record.details.condition_key == "rule.sequence"
    public = manager._public_alert_record(record)
    assert public["source"] == "value_sequence"
    assert public["condition_params"]["steps"] == manager._rules[0].steps
    assert (
        public["condition_params"]["evidence"]
        == record.details.condition_params["evidence"]
    )
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


@pytest.mark.parametrize("mode", ["duration", "state", "condition"])
@pytest.mark.parametrize("attribute", [None, "power"])
def test_sequence_resolution_modes_and_restart(hass, entry, set_now, mode, attribute):
    manager, key, rule = setup_sequence(
        hass,
        entry,
        resolve_mode=mode,
        attribute=attribute,
        resolve_condition={"operator": "above", "value": 20}
        if mode == "condition"
        else None,
    )

    def update(value):
        edge(
            manager,
            hass,
            "ok" if attribute else str(value),
            {"power": value} if attribute else None,
        )

    now = dt_util.now()
    update(120)
    set_now(now + timedelta(seconds=30))
    update(5)
    set_now(now + timedelta(seconds=50))
    fire_sequence_timer(manager, hass, key)
    record = manager.records[key]
    assert record.status is AlertStatus.ACTIVE
    assert (record.expires_at is not None) == (mode == "duration")
    run(manager.async_acknowledge(key, "admin"))
    run(manager.async_unload())
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    run(manager._async_finish_startup_reconciliation())
    assert manager.records[key].acknowledged
    for invalid in ("unknown", "unavailable", "nan", "invalid"):
        update(invalid)
        assert key in manager.records
    update(15)
    if mode == "state":
        assert key not in manager.records
        assert len(manager.history) == 1
        return
    assert key in manager.records
    update(25)
    if mode == "condition":
        assert key not in manager.records
        assert len(manager.history) == 1
    else:
        assert key in manager.records
        set_now(manager.records[key].expires_at)
        manager._evaluation_flush_scheduled = True
        manager._timer_due(key)
        run(manager._async_flush_queued_evaluations())
        assert key not in manager.records
    restored = parse_rule_yaml(dump_rule_yaml(Rule.from_dict(rule)))
    assert restored.resolve_mode == mode
    assert restored.resolve_condition == rule.get("resolve_condition")


@pytest.mark.parametrize(
    "condition",
    [
        None,
        {},
        {"operator": "unchanged", "value": 1},
        {"operator": "above", "value": "nan"},
        {"operator": "between", "value": [10, 1]},
        {"operator": "equals", "value": "ok", "entity_id": "sensor.other"},
    ],
)
def test_invalid_resolution_comparisons_rejected(condition):
    with pytest.raises(ValueError):
        sequence(resolve_mode="condition", resolve_condition=condition)


def test_last_step_exit_resolves_immediately(hass, entry, set_now):
    manager, key, _ = setup_sequence(hass, entry, resolve_mode="state")
    now = dt_util.now()
    edge(manager, hass, "120")
    set_now(now + timedelta(seconds=30))
    edge(manager, hass, "5")
    set_now(now + timedelta(seconds=50))
    edge(manager, hass, "15")
    assert key not in manager.records
    assert len(manager.history) == 1
    assert len(manager.history[0].condition_params["evidence"]) == 2


def test_resolution_edits_cancel_stale_expiration(hass, entry, set_now):
    manager, key, rule = setup_sequence(hass, entry)
    now = dt_util.now()
    edge(manager, hass, "120")
    set_now(now + timedelta(seconds=30))
    edge(manager, hass, "5")
    set_now(now + timedelta(seconds=50))
    fire_sequence_timer(manager, hass, key)
    record = manager.records[key]
    old_expiry = record.expires_at
    run(
        manager.async_update_rule(
            rule["id"],
            {
                "resolve_mode": "condition",
                "resolve_condition": {"operator": "above", "value": 20},
            },
        )
    )
    assert record.expires_at is None
    set_now(old_expiry)
    manager._evaluation_flush_scheduled = True
    manager._timer_due(key)
    run(manager._async_flush_queued_evaluations())
    assert manager.records[key] is record
    run(manager.async_update_rule(rule["id"], {"resolve_mode": "duration"}))
    assert record.expires_at == dt_util.now() + timedelta(seconds=60)
    assert manager._transition_rules_by_id[rule["id"]].resolve_condition is None


@pytest.mark.parametrize("source", ["value_sequence", "value_transition"])
@pytest.mark.parametrize("mode", ["duration", "state", "condition"])
def test_resolution_notification_preview_follows_mode(
    hass, entry, monkeypatch, source, mode
):
    setup_rule = setup_sequence if source == "value_sequence" else setup
    manager, _, rule = setup_rule(
        hass,
        entry,
        resolve_mode=mode,
        resolve_condition={"operator": "below", "value": 10}
        if mode == "condition"
        else None,
    )
    monkeypatch.setattr(
        manager.notification_runtime,
        "preview_profiles",
        lambda *_: {
            "started": [],
            "reminder": [],
            "resolved": [{"id": "recovery", "name": "Recovery"}],
        },
    )
    result = run(manager.async_test_rule({}, rule_id=rule["id"]))["results"][0]
    assert result["notification_resolved_profiles"] == (
        [] if mode == "duration" else [{"id": "recovery", "name": "Recovery"}]
    )


def test_condition_resolution_waits_while_monitoring_paused(hass, entry):
    manager, key, _ = setup(
        hass,
        entry,
        resolve_mode="condition",
        resolve_condition={"operator": "equals", "value": "C"},
    )
    edge(manager, hass, "B")
    record = manager.records[key]
    run(manager.async_set_monitoring(False))
    edge(manager, hass, "C")
    assert manager.records[key] is record
    run(manager.async_set_monitoring(True))
    assert key not in manager.records
    assert len(manager.history) == 1


def test_sequence_evidence_uses_attribute_and_restarted_hold_values():
    p = SequenceProgress(sequence(attribute="power"))

    def sample(value, seconds):
        return p.observe(
            State("sensor.power", "ok", {"power": value}),
            START + timedelta(seconds=seconds),
        )

    sample(150, 0)
    sample("unknown", 100)
    sample(200, 200)
    sample(250, 500)
    sample(5, 600)
    evidence = sample(0, 720)
    assert evidence[0]["started_value"] == 200
    assert evidence[0]["completed_value"] == 250
    assert evidence[0]["started_at"] == (START + timedelta(seconds=200)).isoformat()
    assert evidence[1]["completed_value"] == 0


@pytest.mark.parametrize("disabled", [0, 1, 2])
def test_disabled_steps_are_skipped_but_evidence_keeps_original_positions(disabled):
    steps = [
        {"operator": "above", "value": 100},
        {"operator": "below", "value": 10},
        {"operator": "equals", "value": "done"},
    ]
    steps[disabled]["enabled"] = False
    p = SequenceProgress(sequence(steps=steps))
    enabled = [i for i in range(3) if i != disabled]
    values = [120, 5, "done"]
    for i in enabled:
        evidence = observe(p, values[i], i * 10)
    assert [item["step"] for item in evidence] == [i + 1 for i in enabled]
    assert p.waiting_for_exit
    assert observe(p, values[enabled[-1]], 40) is None
    assert p.waiting_for_exit
    observe(p, 50, 50)
    assert not p.waiting_for_exit


def test_all_disabled_steps_have_no_deadline_or_alert_and_roundtrip_yaml(hass, entry):
    rule = sequence(
        steps=[
            {"operator": "above", "value": 100, "enabled": False},
            {"operator": "below", "value": 10, "enabled": False},
        ]
    )
    p = SequenceProgress(rule)
    assert observe(p, 120, 0) is None
    assert p.deadline() is None
    assert p.snapshot(State("sensor.power", "120"), START)["reason"] == "disabled"
    assert parse_rule_yaml(dump_rule_yaml(rule), rule_id=rule.id).steps == rule.steps
    hass.states.set("sensor.power", "120")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    result = run(
        manager.async_test_rule(
            {
                key: value
                for key, value in rule.as_dict().items()
                if key not in ("id", "version")
            }
        )
    )["results"][0]
    assert result["status"] == "indeterminate"
    assert result["sequence"]["reason"] == "disabled"
    assert result["operator"] is None
    assert result["comparison_value"] is None


@pytest.mark.parametrize("enabled", [None, "false", 0, 1])
def test_step_enabled_is_strict_boolean(enabled):
    with pytest.raises(ValueError, match="Invalid sequence step"):
        sequence(
            steps=[
                {"operator": "above", "value": 100, "enabled": enabled},
                {"operator": "below", "value": 10},
            ]
        )


def test_disabled_final_step_resolution_uses_last_enabled_step(hass, entry, set_now):
    manager, key, rule = setup_sequence(hass, entry, resolve_mode="state")
    steps = [dict(step) for step in rule["steps"]]
    steps[-1]["enabled"] = False
    run(manager.async_update_rule(rule["id"], {"steps": steps}))
    now = dt_util.now()
    edge(manager, hass, "120")
    set_now(now + timedelta(seconds=30))
    fire_sequence_timer(manager, hass, key)
    assert key in manager.records
    evidence = manager.records[key].details.condition_params["evidence"]
    assert [item["step"] for item in evidence] == [1]
    edge(manager, hass, "5")
    assert key not in manager.records
    assert manager.history[-1].condition_params["evidence"] == evidence


def test_disabling_a_step_discards_pending_progress_and_stale_timer(
    hass, entry, set_now
):
    manager, key, rule = setup_sequence(hass, entry)
    edge(manager, hass, "120")
    stale = sequence_timer(manager, hass, key)
    steps = [dict(step, enabled=False) for step in rule["steps"]]
    run(manager.async_update_rule(rule["id"], {"steps": steps}))
    set_now(stale["point"])
    stale["action"](None)
    run(manager._async_flush_queued_evaluations())
    assert key not in manager.records
    assert not manager._sequence_timers
    steps[0]["enabled"] = True
    run(manager.async_update_rule(rule["id"], {"steps": steps}))
    edge(manager, hass, "5")
    edge(manager, hass, "120")
    assert sequence_timer(manager, hass, key)["point"] == dt_util.now() + timedelta(
        seconds=30
    )


def test_pending_sequence_progress_publishes_then_hands_off_once(hass, entry, set_now):
    manager, key, _ = setup_sequence(hass, entry)
    now = dt_util.now()
    edge(manager, hass, "120")
    assert not manager._sequence_progress[key].completed
    assert run(manager.async_reevaluate_alert(key))
    assert manager.public_snapshot()["pending_count"] == 1
    assert (
        manager.public_snapshot()["pending"][0]["condition_params"]["current_step"][
            "step"
        ]
        == 1
    )
    set_now(now + timedelta(seconds=30))
    fire_sequence_timer(manager, hass, key)
    snapshot = manager.public_snapshot()
    assert snapshot["pending_count"] == 1
    pending = snapshot["pending"][0]
    assert pending["id"] == key
    assert pending["due_at"] is None
    assert pending["condition_key"] == "rule.sequence_pending"
    assert pending["condition_params"]["count"] == 1
    assert pending["condition_params"]["total"] == 2
    assert pending["condition_params"]["next"] == 2
    assert pending["condition_params"]["evidence"][0]["completed_value"] == "120"
    assert manager._last_public_snapshot == snapshot
    assert key not in manager.records
    assert not manager.history
    assert not [e for e in hass.bus.fired if e[0] == EVENT_ALERT_STARTED]
    assert run(manager.async_reevaluate_alert(key))
    # Reads do not mutate proof, restart timers or expose mutable steps.
    pending["condition_params"]["steps"][0]["value"] = -1
    assert manager._sequence_progress[key].rule.steps[0]["value"] == 100
    edge(manager, hass, "5")
    set_now(now + timedelta(seconds=50))
    fire_sequence_timer(manager, hass, key)
    snapshot = manager.public_snapshot()
    assert snapshot["pending_count"] == 0
    assert snapshot["active_count"] == 1
    assert snapshot["alerts"][0]["id"] == key
    assert len([e for e in hass.bus.fired if e[0] == EVENT_ALERT_STARTED]) == 1
    # A second progression must not duplicate the existing active episode.
    edge(manager, hass, "120")
    set_now(now + timedelta(seconds=80))
    fire_sequence_timer(manager, hass, key)
    assert manager.public_snapshot()["pending_count"] == 0
    assert manager.public_snapshot()["active_count"] == 1


def test_pending_sequence_expiration_is_silent_and_not_persisted(hass, entry, set_now):
    from custom_components.alert_manager.const import EVENT_ALERT_RESOLVED

    manager, key, _ = setup_sequence(hass, entry, sequence_timeout=60)
    now = dt_util.now()
    edge(manager, hass, "120")
    set_now(now + timedelta(seconds=30))
    fire_sequence_timer(manager, hass, key)
    assert manager.public_snapshot()["pending_count"] == 1
    run(manager._async_save_state())
    restored = AlertManager(hass, entry)
    run(restored.async_setup())
    run(restored._async_finish_startup_reconciliation())
    assert restored.public_snapshot()["pending_count"] == 1
    # The persisted progression was discarded; the current value starts step 1.
    assert restored._sequence_progress[key].index == 0
    assert restored._sequence_progress[key].hold_since == dt_util.now()
    assert not restored._sequence_progress[key].completed
    run(restored.async_unload())
    set_now(now + timedelta(seconds=60))
    fire_sequence_timer(manager, hass, key)
    assert manager.public_snapshot()["pending_count"] == 0
    assert manager._last_public_snapshot["pending_count"] == 0
    assert not manager.history and not manager._pending_history
    assert not [e for e in hass.bus.fired if e[0] == EVENT_ALERT_RESOLVED]


@pytest.mark.parametrize(
    "operation", ["monitor", "disable", "edit", "delete", "unload"]
)
def test_visible_sequence_cleanup(hass, entry, set_now, operation):
    manager, key, rule = setup_sequence(hass, entry, sequence_timeout=120)
    now = dt_util.now()
    edge(manager, hass, "120")
    set_now(now + timedelta(seconds=30))
    fire_sequence_timer(manager, hass, key)
    assert manager.public_snapshot()["pending_count"] == 1
    stale = sequence_timer(manager, hass, key)
    if operation == "monitor":
        run(manager.async_set_monitoring(False))
        run(manager.async_set_monitoring(True))
    elif operation == "disable":
        run(manager.async_update_rule(rule["id"], {"enabled": False}))
    elif operation == "edit":
        run(manager.async_update_rule(rule["id"], {"sequence_timeout": 200}))
    elif operation == "delete":
        run(manager.async_delete_rule(rule["id"]))
    else:
        run(manager.async_unload())
    stale["action"](stale["point"])
    assert manager.public_snapshot()["pending_count"] == 0
    assert not manager.history


def test_pending_sequence_counts_only_enabled_steps_and_keeps_evidence(
    hass, entry, set_now
):
    manager, key, _ = setup_sequence(
        hass,
        entry,
        steps=[
            {"operator": "above", "value": 100, "enabled": False},
            {"operator": "above", "value": 100, "duration": 30},
            {"operator": "below", "value": 10, "duration": 20},
        ],
    )
    now = dt_util.now()
    edge(manager, hass, "120")
    set_now(now + timedelta(seconds=30))
    fire_sequence_timer(manager, hass, key)
    params = manager.public_snapshot()["pending"][0]["condition_params"]
    assert (params["count"], params["total"], params["next"]) == (1, 2, 3)
    assert params["evidence"][0]["step"] == 2
    edge(manager, hass, "unknown")
    assert manager.public_snapshot()["pending_count"] == 1
    assert manager.public_snapshot()["pending"][0]["condition_params"] == params


@pytest.mark.parametrize("mode", ["at_least", "less_than", "between"])
def test_pending_hold_payload_tracks_interruption_and_restart(
    hass, entry, set_now, mode
):
    manager, key, _ = setup_sequence(
        hass,
        entry,
        steps=[
            {
                "operator": "above",
                "value": 100,
                "duration": 30,
                "duration_mode": mode,
                **({"duration_max": 60} if mode == "between" else {}),
            },
            {"operator": "below", "value": 10, "duration": 20},
        ],
    )
    now = dt_util.now()
    edge(manager, hass, "120")
    params = manager.public_snapshot()["pending"][0]["condition_params"]
    assert params["current_step"] == {
        "step": 1,
        "started_at": now.isoformat(),
        "started_value": "120",
    }
    assert params["evidence"] == []
    # Invalid input interrupts all modes without proving an exit.
    edge(manager, hass, "unavailable")
    assert manager.public_snapshot()["pending_count"] == 0
    set_now(now + timedelta(seconds=10))
    edge(manager, hass, "130")
    params = manager.public_snapshot()["pending"][0]["condition_params"]
    assert (
        params["current_step"]["started_at"]
        == (now + timedelta(seconds=10)).isoformat()
    )
    assert params["current_step"]["started_value"] == "130"
    assert not manager.history
    assert key not in manager.records


@pytest.mark.parametrize("attribute", [None, "mode"])
@pytest.mark.parametrize("initial", ["1", "unknown", None])
def test_startup_observes_first_step_without_a_new_edge(
    hass, entry, set_now, attribute, initial
):
    """The value held across reboot can start 1 -> 2 -> 3 after reconciliation."""
    manager, key, _ = setup_sequence(
        hass,
        entry,
        attribute=attribute,
        steps=[
            {"operator": "equals", "value": "1", "duration": 0},
            {"operator": "equals", "value": "2", "duration": 0},
            {
                "operator": "equals",
                "value": "3",
                "duration": 120,
                "duration_mode": "less_than",
            },
        ],
    )
    edge(manager, hass, "1", {"mode": "1"})
    run(manager.async_unload())
    if initial is None:
        hass.states.data.pop("sensor.edge", None)
    else:
        hass.states.set("sensor.edge", initial, {"mode": initial})
    now = dt_util.now() + timedelta(hours=1)
    set_now(now)
    restored = AlertManager(hass, entry)
    run(restored.async_setup())
    assert not restored._sequence_progress
    run(restored._async_finish_startup_reconciliation())
    if initial != "1":
        assert not restored._sequence_progress[key].completed
        edge(restored, hass, "1", {"mode": "1"})
    progress = restored._sequence_progress[key]
    assert progress.index == 1
    assert progress.completed[0]["started_at"] == now.isoformat()
    assert restored.public_snapshot()["pending_count"] == 1
    edge(restored, hass, "2", {"mode": "2"})
    set_now(now + timedelta(seconds=19))
    edge(restored, hass, "3", {"mode": "3"})
    assert key not in restored.records  # Less-than requires a proven exit.
    set_now(now + timedelta(seconds=40))
    edge(restored, hass, "4", {"mode": "4"})
    assert restored.records[key].status is AlertStatus.ACTIVE
    assert len(restored.records[key].details.condition_params["evidence"]) == 3


def test_startup_sequence_hold_starts_now_and_keeps_its_timer(hass, entry, set_now):
    manager, key, _ = setup_sequence(hass, entry)
    edge(manager, hass, "120")
    run(manager.async_unload())
    now = dt_util.now() + timedelta(hours=1)
    set_now(now)
    restored = AlertManager(hass, entry)
    run(restored.async_setup())
    run(restored._async_finish_startup_reconciliation())
    progress = restored._sequence_progress[key]
    assert progress.index == 0
    assert progress.hold_since == now
    assert progress.deadline() == now + timedelta(seconds=30)
    set_now(now + timedelta(seconds=30))
    fire_sequence_timer(restored, hass, key)
    assert progress.index == 1
    edge(restored, hass, "5")
    set_now(now + timedelta(seconds=50))
    fire_sequence_timer(restored, hass, key)
    assert restored.records[key].status is AlertStatus.ACTIVE


@pytest.mark.parametrize("mode", ["less_than", "between"])
@pytest.mark.parametrize("expiry_source", ["timer", "event"])
def test_bounded_step_expiration_discards_pending_sequence(
    hass, entry, set_now, mode, expiry_source
):
    """A failed last step removes pending immediately and cannot reuse steps 1/2."""
    from custom_components.alert_manager.const import EVENT_ALERT_RESOLVED

    manager, key, _ = setup_sequence(
        hass,
        entry,
        steps=[
            {"operator": "equals", "value": "1", "duration": 0},
            {"operator": "equals", "value": "2", "duration": 0},
            {
                "operator": "equals",
                "value": "3",
                "duration_mode": mode,
                "duration": 120 if mode == "less_than" else 10,
                **({"duration_max": 120} if mode == "between" else {}),
            },
        ],
    )
    now = dt_util.now()
    for value in ("1", "2", "3"):
        edge(manager, hass, value)
    progress = manager._sequence_progress[key]
    assert progress.index == 2
    assert manager.public_snapshot()["pending_count"] == 1
    expiry = now + timedelta(seconds=120, microseconds=mode == "between")
    assert progress.deadline() == expiry
    timer = sequence_timer(manager, hass, key)
    set_now(expiry)
    if expiry_source == "timer":
        fire_sequence_timer(manager, hass, key)
    else:
        edge(manager, hass, "4")
        assert timer["cancelled"]
    assert manager.public_snapshot()["pending_count"] == 0
    assert manager._last_public_snapshot["pending_count"] == 0
    assert progress.index == 0 and not progress.completed
    assert progress.hold_since is None and progress.started_at is None
    assert key not in manager._sequence_timers
    assert not manager.records and not manager.history and not manager._pending_history
    assert not [
        e for e in hass.bus.fired if e[0] in (EVENT_ALERT_STARTED, EVENT_ALERT_RESOLVED)
    ]
    edge(manager, hass, "3")
    edge(manager, hass, "4")
    assert manager.public_snapshot()["pending_count"] == 0
    assert key not in manager.records
    # A full fresh cycle is still allowed; the old timer cannot erase it.
    for value in ("1", "2", "3"):
        edge(manager, hass, value)
    timer["action"](dt_util.now())
    assert manager._sequence_progress[key].index == 2
    set_now(expiry + timedelta(seconds=20))
    edge(manager, hass, "4")
    assert manager.records[key].status is AlertStatus.ACTIVE


@pytest.mark.parametrize(
    "mode,offset,valid",
    [
        ("less_than", -1, True),
        ("less_than", 0, False),
        ("between", 0, True),
        ("between", 1, False),
    ],
)
def test_bounded_hold_exit_at_upper_boundary(mode, offset, valid):
    p = SequenceProgress(
        sequence(
            steps=[
                {"operator": "equals", "value": "1", "duration": 0},
                {
                    "operator": "equals",
                    "value": "3",
                    "duration_mode": mode,
                    "duration": 120 if mode == "less_than" else 10,
                    **({"duration_max": 120} if mode == "between" else {}),
                },
            ]
        )
    )
    observe(p, 1, 0)
    observe(p, 3, 0)
    evidence = p.observe(
        State("sensor.power", "4"), START + timedelta(seconds=120, microseconds=offset)
    )
    assert bool(evidence) is valid
    assert not p.completed and p.hold_since is None


@pytest.mark.parametrize("attribute", [None, "mode"])
@pytest.mark.parametrize("mode", ["less_than", "between", "at_least"])
def test_completing_exit_starts_next_pending_cycle(
    hass, entry, set_now, attribute, mode
):
    from custom_components.alert_manager.const import EVENT_ALERT_RESOLVED

    manager, key, _ = setup_sequence(
        hass,
        entry,
        attribute=attribute,
        resolve_mode="state",
        steps=[
            {"operator": "equals", "value": "1", "duration": 0},
            {"operator": "equals", "value": "2", "duration": 0},
            {
                "operator": "equals",
                "value": "3",
                "duration_mode": mode,
                "duration": 120 if mode == "less_than" else 10,
                **({"duration_max": 120} if mode == "between" else {}),
            },
        ],
    )
    now = dt_util.now()
    for value in ("1", "2", "3"):
        edge(manager, hass, value, {"mode": value})
    stale = sequence_timer(manager, hass, key)
    for cycle in (1, 2):
        set_now(now + timedelta(seconds=20 * cycle))
        edge(manager, hass, "1", {"mode": "1"})
        assert key not in manager.records
        snapshot = manager.public_snapshot()
        assert snapshot["pending_count"] == 1 and snapshot["active_count"] == 0
        progress = manager._sequence_progress[key]
        assert progress.index == 1 and not progress.waiting_for_exit
        assert len(progress.completed) == 1
        assert progress.completed[0]["started_value"] == "1"
        assert progress.completed[0]["started_at"] == dt_util.now().isoformat()
        evidence = manager.history[-1].condition_params["evidence"]
        assert len(evidence) == 3
        assert evidence[-1]["completed_value"] == "1"
        assert len([e for e in hass.bus.fired if e[0] == EVENT_ALERT_STARTED]) == cycle
        assert len([e for e in hass.bus.fired if e[0] == EVENT_ALERT_RESOLVED]) == cycle
        stale["action"](dt_util.now())
        assert progress.index == 1
        if cycle == 1:
            for value in ("2", "3"):
                edge(manager, hass, value, {"mode": value})


def test_completing_exit_starts_new_hold_without_backdating(hass, entry, set_now):
    manager, key, _ = setup_sequence(
        hass,
        entry,
        resolve_mode="state",
        steps=[
            {"operator": "equals", "value": "1", "duration": 10},
            {
                "operator": "equals",
                "value": "3",
                "duration_mode": "less_than",
                "duration": 120,
            },
        ],
    )
    now = dt_util.now()
    edge(manager, hass, "1")
    set_now(now + timedelta(seconds=10))
    fire_sequence_timer(manager, hass, key)
    edge(manager, hass, "3")
    set_now(now + timedelta(seconds=20))
    edge(manager, hass, "1")
    progress = manager._sequence_progress[key]
    assert progress.index == 0 and progress.hold_since == dt_util.now()
    assert progress.deadline() == now + timedelta(seconds=30)
    assert manager.public_snapshot()["pending_count"] == 1
    set_now(now + timedelta(seconds=30))
    fire_sequence_timer(manager, hass, key)
    assert progress.index == 1
    assert len(manager.history) == 1


@pytest.mark.parametrize("via_import", [False, True])
def test_pending_sequence_label_edit_preserves_progress(hass, entry, via_import):
    """Labels refresh immediately without losing completed steps or a hold."""
    from custom_components.alert_manager.yaml_io import dump_config_yaml

    manager, key, rule = setup(
        hass,
        entry,
        source="value_sequence",
        label_ids=["old"],
        steps=[
            {"operator": "equals", "value": "B"},
            {"operator": "equals", "value": "C", "duration": 60},
        ],
    )
    edge(manager, hass, "B")
    edge(manager, hass, "C")
    progress = manager._sequence_progress[key]
    before = progress.copy()
    timer = manager._sequence_timers[key]
    if via_import:
        config = manager.get_config()
        config["rules"][0]["label_ids"] = ["new"]
        run(manager.async_import_config(dump_config_yaml(config)))
    else:
        run(manager.async_update_rule(rule["id"], {"label_ids": ["new"]}))
    assert manager.public_snapshot()["pending"][0]["labels"] == ["new"]
    assert manager._sequence_progress[key] is progress
    assert progress.completed == before.completed
    assert progress.hold_since == before.hold_since
    assert manager._sequence_timers[key] is timer
    # A configuration rebuild must also preserve the new presentation.
    run(manager.async_update_config({"excluded_labels": ["unrelated"]}))
    assert manager.public_snapshot()["pending"][0]["labels"] == ["new"]


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"auto_resolve": 0}, "auto_resolve"),
        ({"sequence_timeout": -1}, "sequence_timeout"),
    ],
)
def test_sequence_global_duration_errors_identify_field(changes, field):
    with pytest.raises(ValueError, match=f"^{field}: Invalid sequence duration"):
        sequence(**changes)


@pytest.mark.parametrize(
    ("step", "field"),
    [
        ({"duration": -1}, "duration"),
        ({"duration_mode": "between", "duration_max": -1}, "duration_max"),
        ({"duration_mode": "between", "duration_max": 0}, "duration_max"),
        ({"duration_mode": "less_than", "duration": 0}, "duration"),
        ({"value": "not a number"}, "value"),
    ],
)
def test_sequence_step_errors_identify_index_and_field(step, field):
    with pytest.raises(ValueError, match=rf"^steps\[1\]\.{field}:"):
        sequence(
            steps=[
                {"operator": "above", "value": 100},
                {"operator": "below", "value": 10, **step},
            ]
        )
