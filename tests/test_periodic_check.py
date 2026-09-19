"""Periodic safety checks reuse current-state evaluation without invented events."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.core import CoreState
from homeassistant.util import dt as dt_util
from test_transitions import edge, run, setup

from custom_components.alert_manager.const import EVENT_ALERT_STARTED
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertStatus
from custom_components.alert_manager.runtime_phase import RuntimePhase
from custom_components.alert_manager.statistics import RuntimeStatistics


def check(manager):
    run(manager._async_periodic_check(dt_util.now()))


def state_rule(hass, entry, **changes):
    hass.states.set("sensor.test", "0")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    rule = run(
        manager.async_create_rule(
            {
                "name": "Value",
                "entity_ids": ["sensor.test"],
                "operator": "above",
                "value": 10,
                "duration": 60,
                **changes,
            }
        )
    )
    return manager, f"rule:{rule['id']}:sensor.test"


def test_missing_condition_starts_at_check_then_resolves(hass, entry, set_now):
    manager, key = state_rule(hass, entry)
    start = dt_util.now()
    hass.states.set("sensor.test", "20")  # No event delivered.
    set_now(start + timedelta(minutes=10))
    check(manager)
    record = manager.records[key]
    assert record.detected_at == dt_util.now()
    assert record.status is AlertStatus.PENDING
    assert record.due_at == dt_util.now() + timedelta(seconds=60)
    assert manager.statistics.snapshot()["periodic_recoveries"] == 1
    check(manager)
    assert manager.records[key] is record
    assert manager.statistics.snapshot()["periodic_recoveries"] == 1
    manager._cancel_timer(key)
    set_now(record.due_at + timedelta(seconds=30))
    check(manager)
    assert record.status is AlertStatus.ACTIVE
    assert record.detected_at == start + timedelta(minutes=10)
    assert len([e for e in hass.bus.fired if e[0] == EVENT_ALERT_STARTED]) == 1
    hass.states.set("sensor.test", "0")
    check(manager)
    assert key not in manager.records
    assert len(manager.history) == 1
    check(manager)
    assert len(manager.history) == 1
    assert manager.statistics.snapshot()["periodic_recoveries"] == 3


@pytest.mark.parametrize(
    "source,operator", [("unchanged", "equals"), ("value", "unchanged")]
)
def test_missing_inactivity_window_is_not_backdated(
    hass, entry, set_now, source, operator
):
    manager, key = state_rule(hass, entry, source=source, operator=operator)
    manager._pop_record(key)
    manager._cancel_timer(key)
    set_now(dt_util.now() + timedelta(minutes=10))
    check(manager)
    assert manager.records[key].detected_at == dt_util.now()
    assert manager.records[key].due_at == dt_util.now() + timedelta(seconds=60)
    check(manager)
    assert manager.statistics.snapshot()["periodic_recoveries"] == 1


def test_missing_pending_timer_keeps_deadline_and_no_write(hass, entry):
    manager, key = state_rule(hass, entry)
    hass.states.set("sensor.test", "20")
    run(manager.async_evaluate_entity("sensor.test"))
    record = manager.records[key]
    due = record.due_at
    manager._cancel_timer(key)
    writes = hass.store_save_count
    manager._publish_if_changed = Mock()
    check(manager)
    assert key in manager._timers
    assert record.due_at == due
    assert hass.store_save_count == writes
    manager._publish_if_changed.assert_not_called()
    assert manager.statistics.snapshot()["periodic_recoveries"] == 0


def test_unchanged_check_is_silent_preserves_ack_and_uses_indexes(hass, entry):
    manager, key = state_rule(hass, entry, duration=0)
    hass.states.set("sensor.test", "20")
    run(manager.async_evaluate_entity("sensor.test"))
    record = manager.records[key]
    record.acknowledged = True
    record.acknowledged_at = dt_util.now()
    writes = hass.store_save_count
    events = len(hass.bus.fired)
    hass.states.async_all = Mock(side_effect=AssertionError("global state scan"))
    manager._publish_if_changed = Mock()
    check(manager)
    check(manager)
    assert manager.records[key] is record and record.acknowledged
    assert hass.store_save_count == writes
    assert len(hass.bus.fired) == events
    manager._publish_if_changed.assert_not_called()
    assert manager.statistics.snapshot()["periodic_recoveries"] == 0


@pytest.mark.parametrize("source", ["transition", "value_sequence"])
def test_snapshot_never_invents_transition_or_sequence(hass, entry, source):
    changes = {"source": source}
    if source == "value_sequence":
        changes["steps"] = [
            {"operator": "equals", "value": "A"},
            {"operator": "equals", "value": "B"},
        ]
    manager, key, _ = setup(hass, entry, **changes)
    hass.states.set("sensor.edge", "B")
    check(manager)
    assert key not in manager.records
    assert not [e for e in hass.bus.fired if e[0] == EVENT_ALERT_STARTED]


def test_transition_resolution_and_missing_expiry_timer(hass, entry, set_now):
    manager, key, _ = setup(hass, entry)
    edge(manager, hass, "B")
    deadline = manager.records[key].expires_at
    manager._cancel_timer(key)
    check(manager)
    assert key in manager._timers
    assert manager.records[key].expires_at == deadline
    set_now(deadline)
    check(manager)
    assert key not in manager.records
    assert len(manager.history) == 1


def test_transition_current_state_resolution(hass, entry):
    manager, key, _ = setup(hass, entry, resolve_mode="state")
    edge(manager, hass, "B")
    hass.states.set("sensor.edge", "C")
    check(manager)
    assert key not in manager.records
    assert len(manager.history) == 1


def test_sequence_missed_exit_drops_evidence_instead_of_completing(hass, entry):
    manager, key, _ = setup(
        hass,
        entry,
        source="value_sequence",
        steps=[
            {
                "operator": "equals",
                "value": "B",
                "duration_mode": "less_than",
                "duration": 300,
            },
            {"operator": "equals", "value": "C"},
        ],
    )
    edge(manager, hass, "B")
    assert manager._sequence_progress[key].hold_since is not None
    hass.states.set("sensor.edge", "C")
    check(manager)
    assert key not in manager._sequence_progress
    assert key not in manager.records
    assert manager.statistics.snapshot()["periodic_recoveries"] == 1


def test_known_sequence_timer_is_restored(hass, entry):
    manager, key, _ = setup(
        hass,
        entry,
        source="value_sequence",
        steps=[
            {"operator": "equals", "value": "B", "duration": 300},
            {"operator": "equals", "value": "C"},
        ],
    )
    edge(manager, hass, "B")
    progress = manager._sequence_progress[key]
    started = progress.hold_since
    _, cancel, due = manager._sequence_timers.pop(key)
    cancel()
    check(manager)
    assert manager._sequence_timers[key][2] == due
    assert progress.hold_since == started
    assert not progress.completed
    assert manager.statistics.snapshot()["periodic_recoveries"] == 0


@pytest.mark.parametrize(
    "guard",
    [
        "startup",
        "grace",
        "reconciling",
        "stopping",
        "recovery",
        "disabled",
        "unloading",
        "core",
    ],
)
def test_lifecycle_guards(hass, entry, guard):
    manager, _ = state_rule(hass, entry)
    if guard in ("startup", "grace", "reconciling", "stopping"):
        manager._runtime_phase = {
            "startup": RuntimePhase.STARTING,
            "grace": RuntimePhase.STARTUP_GRACE,
            "reconciling": RuntimePhase.RECONCILING,
            "stopping": RuntimePhase.STOPPING,
        }[guard]
    elif guard == "recovery":
        manager._recovery_active = True
    elif guard == "disabled":
        manager.config["monitoring_enabled"] = False
    elif guard == "unloading":
        manager._unloading = True
    else:
        hass.state = CoreState.stopping
    manager.async_evaluate_entity = AsyncMock()
    check(manager)
    manager.async_evaluate_entity.assert_not_called()


def test_interval_cancelled_on_shutdown_and_reload(hass, entry):
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    interval = hass.intervals[-1]
    assert interval["interval"] == timedelta(minutes=10)
    manager._begin_shutdown()
    assert interval["cancelled"]
    run(manager.async_unload())
    replacement = AlertManager(hass, entry)
    run(replacement.async_setup())
    assert sum(not timer["cancelled"] for timer in hass.intervals) == 1
    run(replacement.async_unload())
    assert all(timer["cancelled"] for timer in hass.intervals)


def test_no_overlap_and_lock_recheck(hass, entry):
    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        manager.async_evaluate_entity = AsyncMock()
        async with manager._config_mutation_lock:
            task = asyncio.create_task(manager._async_periodic_check(dt_util.now()))
            await asyncio.sleep(0)
            assert manager._periodic_check_running
            await manager._async_periodic_check(dt_util.now())
            manager.config["monitoring_enabled"] = False
        await task
        manager.async_evaluate_entity.assert_not_called()
        assert not manager._periodic_check_running

    run(scenario())


def test_recovery_counter_uses_existing_24_hour_buckets(hass, set_now):
    start = dt_util.now()
    stats = RuntimeStatistics()
    stats.record_recovery()
    stats.record_recovery()
    assert stats.snapshot()["periodic_recoveries"] == 2
    set_now(start + timedelta(hours=24))
    assert stats.snapshot()["periodic_recoveries"] == 0
    stats.record_recovery()
    assert stats.snapshot()["periodic_recoveries"] == 1
    assert RuntimeStatistics().snapshot()["periodic_recoveries"] == 0


def test_check_never_feeds_occurrence_or_execution_handlers(hass, entry, monkeypatch):
    from dataclasses import replace

    from custom_components.alert_manager import manager_runtime
    from custom_components.alert_manager.packs import execution_errors

    manager, key = state_rule(hass, entry, duration=0)
    hass.states.set("automation.test", "on", {"current": 0})
    manager._automatic_tracked_entities.add("automation.test")
    execution = replace(
        execution_errors.PACK,
        evaluate=Mock(side_effect=AssertionError("execution evaluation")),
    )
    monkeypatch.setitem(manager_runtime.PACKS_BY_ID, execution.id, execution)
    handlers = tuple(
        replace(
            pack,
            occurrence_batch_handler=Mock(
                side_effect=AssertionError("synthetic occurrence")
            ),
        )
        for pack in manager_runtime.OCCURRENCE_PACKS
    )
    monkeypatch.setattr(manager_runtime, "OCCURRENCE_PACKS", handlers)
    hass.states.set("sensor.test", "20")
    check(manager)
    assert manager.records[key].status is AlertStatus.ACTIVE
    execution.evaluate.assert_not_called()
    for pack in handlers:
        pack.occurrence_batch_handler.assert_not_called()
    assert manager.statistics.snapshot()["periodic_recoveries"] == 1


def test_queued_real_event_is_not_counted_as_recovery(hass, entry):
    manager, key, _ = setup(hass, entry)
    edge(manager, hass, "B", flush=False)
    check(manager)
    assert manager.records[key].status is AlertStatus.ACTIVE
    assert manager.statistics.snapshot()["periodic_recoveries"] == 0
    assert len([e for e in hass.bus.fired if e[0] == EVENT_ALERT_STARTED]) == 1


def test_expired_sequence_timer_reuses_deadline_cleanup(hass, entry, set_now):
    manager, key, _ = setup(
        hass,
        entry,
        source="value_sequence",
        sequence_timeout=60,
        steps=[
            {"operator": "equals", "value": "B", "duration": 300},
            {"operator": "equals", "value": "C"},
        ],
    )
    edge(manager, hass, "B")
    original = hass.timers[-1]
    set_now(dt_util.now() + timedelta(seconds=61))
    check(manager)
    assert original["cancelled"]
    assert manager._sequence_timers[key][2] < dt_util.now()
    manager._evaluation_flush_scheduled = True
    hass.timers[-1]["action"](dt_util.now())
    run(manager._async_flush_queued_evaluations())
    assert not manager._sequence_progress[key].completed
    assert manager._sequence_progress[key].hold_since is None
    assert key not in manager.records


def test_message_refresh_is_not_counted_as_value_recovery(hass, entry):
    hass.states.set("sensor.context", "warm")
    manager, key = state_rule(
        hass,
        entry,
        duration=0,
        message="Context: {{ states('sensor.context') }}",
        update_message_when_active=True,
    )
    hass.states.set("sensor.test", "20")
    run(manager.async_evaluate_entity("sensor.test"))
    hass.states.set("sensor.context", "cold")
    check(manager)
    assert manager.records[key].details.message == "Context: cold"
    assert manager.statistics.snapshot()["periodic_recoveries"] == 0


def test_event_during_batch_yield_keeps_normal_transition_evidence(
    hass, entry, monkeypatch
):
    from homeassistant.core import Event

    from custom_components.alert_manager import manager_runtime

    async def scenario():
        hass.states.set("sensor.edge", "A")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(
            {
                "name": "Edge",
                "entity_ids": ["sensor.edge"],
                "source": "transition",
                "from_value": "A",
                "to_value": "B",
                "duration": 0,
                "auto_resolve": 60,
            }
        )
        key = f"rule:{rule['id']}:sensor.edge"
        monkeypatch.setattr(manager_runtime, "_EVALUATION_BATCH_SIZE", 1)
        task = asyncio.create_task(manager._async_periodic_check(dt_util.now()))
        await asyncio.sleep(0)
        old = hass.states.get("sensor.edge")
        new = hass.states.set("sensor.edge", "B")
        manager._state_changed(
            Event(
                {
                    "entity_id": "sensor.edge",
                    "old_state": old,
                    "new_state": new,
                }
            )
        )
        await task
        await manager._async_flush_queued_evaluations()
        assert manager.records[key].status is AlertStatus.ACTIVE
        assert manager.statistics.snapshot()["periodic_recoveries"] == 0
        assert len([e for e in hass.bus.fired if e[0] == EVENT_ALERT_STARTED]) == 1

    run(scenario())
