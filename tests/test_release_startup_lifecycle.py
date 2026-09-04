"""Release-2.1 startup reconciliation and restored-state regressions."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from homeassistant.const import ATTR_DEVICE_CLASS, ATTR_FRIENDLY_NAME
from homeassistant.core import CoreState, Event
from homeassistant.util import dt as dt_util

from custom_components.alert_manager.const import (
    EVENT_ALERT_RESOLVED,
    EVENT_ALERT_STARTED,
    SIGNAL_ALERTS_UPDATED,
)
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import (
    AlertRecord,
    AlertStatus,
    advance_record,
)
from custom_components.alert_manager.runtime_phase import RuntimePhase
from custom_components.alert_manager.transactions import (
    StartupReconciliationTransaction,
)


def _fire_startup_reconciliation(hass) -> None:
    """Fire the active bounded-grace timer once."""
    timer = next(
        timer
        for timer in hass.timers
        if not timer["cancelled"]
        and "_schedule_startup_reconciliation" in timer["action"].__qualname__
    )
    timer["cancelled"] = True
    timer["action"](timer["point"])


def _published_alert_state(manager: AlertManager):
    """Describe one publication without retaining its mutable snapshot."""
    snapshot = manager._last_public_snapshot
    statuses = {
        alert["id"]: "active"
        for alert in (*snapshot["alerts"], *snapshot["acknowledge"])
    }
    statuses.update({alert["id"]: "pending" for alert in snapshot["pending"]})
    return (
        manager._runtime_phase,
        snapshot["startup"]["in_progress"],
        statuses,
    )


async def _settle() -> None:
    """Let coalesced manager tasks finish on the fake event loop."""
    for _index in range(6):
        await asyncio.sleep(0)


async def _start_and_reconcile(manager: AlertManager, hass) -> None:
    """Move a restored manager through grace into its authoritative phase."""
    hass.state = CoreState.running
    manager._home_assistant_started(Event())
    assert manager._runtime_phase is RuntimePhase.STARTUP_GRACE
    _fire_startup_reconciliation(hass)
    await _settle()
    assert manager._runtime_phase is RuntimePhase.RUNNING


def test_startup_banner_follows_transactional_runtime_phase(hass, entry):
    """The public banner follows the real grace and reconciliation lifecycle."""

    async def scenario():
        hass.state = CoreState.starting
        manager = AlertManager(hass, entry)
        assert await manager.async_setup() is True
        assert manager._last_public_snapshot["startup"] == {
            "in_progress": True,
            "stabilization_until": None,
        }
        updates: list[bool] = []
        hass.dispatchers[SIGNAL_ALERTS_UPDATED].append(lambda: updates.append(True))

        hass.state = CoreState.running
        manager._home_assistant_started(Event())
        deadline = manager._startup_reconciliation_deadline
        assert deadline is not None
        assert manager._last_public_snapshot["startup"] == {
            "in_progress": True,
            "stabilization_until": deadline.isoformat(),
        }
        assert len(updates) == 1

        _fire_startup_reconciliation(hass)
        assert manager._last_public_snapshot["startup"] == {
            "in_progress": True,
            "stabilization_until": None,
        }
        assert len(updates) == 2
        await _settle()
        assert manager._last_public_snapshot["startup"] == {
            "in_progress": False,
            "stabilization_until": None,
        }
        assert len(updates) == 3

    asyncio.run(scenario())


@pytest.mark.parametrize("fresh_side", ["source", "target"])
def test_reconciliation_rename_collision_always_prefers_fresh_runtime(
    hass, entry, set_now, fresh_side
):
    """A true live occurrence wins on either side of a startup rename."""
    start = datetime(2026, 9, 4, 12, tzinfo=UTC)
    set_now(start)

    async def scenario():
        old_state = hass.states.set("sensor.old", "ok")
        new_state = hass.states.set("sensor.new", "ok")
        manager = AlertManager(hass, entry)
        assert await manager.async_setup() is True
        old_id = "unavailable:sensor.old"
        new_id = "unavailable:sensor.new"
        states = {"source": old_state, "target": new_state}
        ids = {"source": old_id, "target": new_id}
        restored_side = "target" if fresh_side == "source" else "source"

        restored = AlertRecord.pending(
            manager._details(
                states[restored_side],
                ids[restored_side],
                "unavailable",
                "Unavailable",
            ),
            0,
            start,
        )
        restored.status = AlertStatus.ACTIVE
        restored.active_since = start
        restored.details.value = "restored"
        manager._replace_records({ids[restored_side]: restored})
        manager._unverified_restored_alert_ids = {ids[restored_side]}
        transaction = StartupReconciliationTransaction.capture(
            manager.records, manager._unverified_restored_alert_ids
        )
        manager._startup_reconciliation_transaction = transaction
        manager._runtime_phase = RuntimePhase.RECONCILING

        fresh_at = start + timedelta(minutes=5)
        fresh = AlertRecord.pending(
            manager._details(
                states[fresh_side],
                ids[fresh_side],
                "unavailable",
                "Unavailable",
            ),
            0,
            fresh_at,
        )
        fresh.status = AlertStatus.ACTIVE
        fresh.active_since = fresh_at
        fresh.details.value = "fresh"
        manager._set_record(fresh)
        transaction.record_stored(ids[fresh_side], None)

        manager._pending_entity_renames["sensor.old"] = "sensor.new"
        assert manager._apply_pending_entity_renames() is True
        manager._inject_restored_entity_for_reconciliation("sensor.new")

        assert set(manager.records) == {new_id}
        assert manager.records[new_id].details.value == "fresh"
        assert manager.records[new_id].detected_at == fresh_at
        assert transaction.live_origin(new_id) is None

    asyncio.run(scenario())


@pytest.mark.parametrize("active_first", [True, False])
def test_reconciliation_equal_clock_collision_prefers_restored_active(
    hass, entry, set_now, active_first
):
    """An active restored lifecycle wins an equal clock in either Store order."""
    start = datetime(2026, 9, 4, 12, tzinfo=UTC)
    set_now(start)

    async def scenario():
        old_state = hass.states.set("sensor.old", "ok")
        new_state = hass.states.set("sensor.new", "ok")
        manager = AlertManager(hass, entry)
        assert await manager.async_setup() is True
        old_id = "unavailable:sensor.old"
        new_id = "unavailable:sensor.new"
        active = AlertRecord.pending(
            manager._details(old_state, old_id, "unavailable", "Unavailable"),
            0,
            start,
        )
        active.status = AlertStatus.ACTIVE
        active.active_since = start
        pending = AlertRecord.pending(
            manager._details(new_state, new_id, "unavailable", "Unavailable"),
            900,
            start,
        )
        stored_records = [(old_id, active), (new_id, pending)]
        if not active_first:
            stored_records.reverse()
        manager._replace_records(dict(stored_records))
        manager._unverified_restored_alert_ids = {old_id, new_id}
        transaction = StartupReconciliationTransaction.capture(
            manager.records, manager._unverified_restored_alert_ids
        )
        manager._startup_reconciliation_transaction = transaction
        manager._runtime_phase = RuntimePhase.RECONCILING

        manager._pending_entity_renames["sensor.old"] = "sensor.new"
        assert manager._apply_pending_entity_renames() is True
        hass.states.data.pop("sensor.old")
        hass.states.set("sensor.new", "unknown")
        await manager.async_evaluate_entity("sensor.new", save=False, publish=False)

        assert manager.records[new_id].status is AlertStatus.ACTIVE
        assert transaction.original_was_active(new_id) is True
        previous_records = transaction.reconciled_original_records()
        assert previous_records[new_id].status is AlertStatus.ACTIVE

        hass.bus.fired.clear()
        manager._commit_reconciliation_lifecycle(previous_records)
        assert not [
            event
            for event, _data in hass.bus.fired
            if event in (EVENT_ALERT_STARTED, EVENT_ALERT_RESOLVED)
        ]

    asyncio.run(scenario())


def test_reconciliation_collision_prefers_oldest_restored_clock(hass, entry, set_now):
    """Lifecycle status only breaks a tie between restored occurrence clocks."""
    start = datetime(2026, 9, 4, 12, tzinfo=UTC)
    set_now(start)

    async def scenario():
        old_state = hass.states.set("sensor.old", "ok")
        new_state = hass.states.set("sensor.new", "ok")
        manager = AlertManager(hass, entry)
        assert await manager.async_setup() is True
        old_id = "unavailable:sensor.old"
        new_id = "unavailable:sensor.new"
        newer_active = AlertRecord.pending(
            manager._details(old_state, old_id, "unavailable", "Unavailable"),
            0,
            start + timedelta(minutes=5),
        )
        newer_active.status = AlertStatus.ACTIVE
        newer_active.active_since = newer_active.detected_at
        older_pending = AlertRecord.pending(
            manager._details(new_state, new_id, "unavailable", "Unavailable"),
            900,
            start,
        )
        manager._replace_records({old_id: newer_active, new_id: older_pending})
        manager._unverified_restored_alert_ids = {old_id, new_id}
        manager._startup_reconciliation_transaction = (
            StartupReconciliationTransaction.capture(
                manager.records, manager._unverified_restored_alert_ids
            )
        )
        manager._runtime_phase = RuntimePhase.RECONCILING

        manager._pending_entity_renames["sensor.old"] = "sensor.new"
        assert manager._apply_pending_entity_renames() is True

        assert manager.records[new_id].status is AlertStatus.PENDING
        assert manager.records[new_id].detected_at == start
        assert manager._startup_reconciliation_transaction.live_origin(new_id) == new_id

    asyncio.run(scenario())


def test_restored_pending_unavailable_is_removed_by_unknown_scan(hass, entry):
    """Unknown cannot keep a pending automatic unavailable alert after startup."""

    async def scenario():
        hass.states.set("event.baby", "unavailable")
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        alert_id = "unavailable:event.baby"
        assert first.records[alert_id].status is AlertStatus.PENDING
        assert alert_id in hass.stores["alert_manager"]["alerts"]
        await first.async_unload()

        hass.state = CoreState.starting
        hass.states.set("event.baby", "unknown")
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True
        assert alert_id in restarted.records
        assert restarted.public_snapshot()["pending_count"] == 0

        await _start_and_reconcile(restarted, hass)

        assert alert_id not in restarted.records
        assert alert_id not in hass.stores["alert_manager"]["alerts"]
        assert restarted.public_snapshot()["pending_count"] == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("uncertain_state", [None, "unknown", "unavailable"])
def test_restored_custom_pending_keeps_clock_and_advances_when_due(
    hass, entry, set_now, uncertain_state
):
    """Indeterminate startup values neither reset nor permanently block a rule."""
    start = datetime(2026, 9, 4, 10, tzinfo=UTC)
    set_now(start)

    async def scenario():
        hass.states.set("binary_sensor.pool_filter", "on")
        first = AlertManager(hass, entry)
        await first.async_setup()
        rule = await first.async_create_rule(
            {
                "name": "Pool filtration over 24 hours",
                "entity_ids": ["binary_sensor.pool_filter"],
                "operator": "equals",
                "value": "on",
                "duration": 24 * 60 * 60,
            }
        )
        alert_id = f"rule:{rule['id']}:binary_sensor.pool_filter"
        detected_at = first.records[alert_id].detected_at
        due_at = first.records[alert_id].due_at
        await first.async_unload()

        hass.state = CoreState.starting
        set_now(start + timedelta(hours=2))
        if uncertain_state is None:
            hass.states.data.pop("binary_sensor.pool_filter")
        else:
            hass.states.set("binary_sensor.pool_filter", uncertain_state)
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        await _start_and_reconcile(restarted, hass)

        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.PENDING
        assert restored.detected_at == detected_at
        assert restored.due_at == due_at
        assert alert_id in restarted._unverified_restored_alert_ids

        set_now(due_at + timedelta(seconds=1))
        await restarted.async_evaluate_entity("binary_sensor.pool_filter")

        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.ACTIVE
        assert restored.detected_at == detected_at
        assert restored.due_at == due_at
        assert hass.stores["alert_manager"]["alerts"][alert_id]["status"] == "active"

    asyncio.run(scenario())


@pytest.mark.parametrize("uncertain_state", [None, "unknown", "unavailable"])
@pytest.mark.parametrize("duration", [0, 3600])
def test_runtime_custom_alert_is_not_granted_restored_protection(
    hass, entry, uncertain_state, duration
):
    """Only records loaded from Store survive an indeterminate observation."""

    async def scenario():
        matching_state = hass.states.set("binary_sensor.filter", "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(
            {
                "name": "Filter active",
                "entity_ids": ["binary_sensor.filter"],
                "operator": "equals",
                "value": "on",
                "duration": duration,
            }
        )
        alert_id = f"rule:{rule['id']}:binary_sensor.filter"
        assert alert_id in manager.records
        assert alert_id not in manager._unverified_restored_alert_ids

        if uncertain_state is None:
            hass.states.data.pop("binary_sensor.filter")
            new_state = None
        else:
            new_state = hass.states.set("binary_sensor.filter", uncertain_state)
        manager._state_changed(
            Event(
                {
                    "entity_id": "binary_sensor.filter",
                    "old_state": matching_state,
                    "new_state": new_state,
                }
            )
        )
        await _settle()

        assert alert_id not in manager.records

    asyncio.run(scenario())


def test_restored_active_unavailable_waits_for_authoritative_confirmation(hass, entry):
    """An active outage survives startup uncertainty but not later recovery."""

    async def scenario():
        hass.states.set("sensor.offline", "unavailable")
        first = AlertManager(hass, entry)
        await first.async_setup()
        await first.async_update_config({"automatic": {"unavailable": {"delay": 0}}})
        alert_id = "unavailable:sensor.offline"
        assert first.records[alert_id].status is AlertStatus.ACTIVE
        await first.async_unload()

        hass.state = CoreState.starting
        unknown_state = hass.states.set("sensor.offline", "unknown")
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        await _start_and_reconcile(restarted, hass)
        assert restarted.records[alert_id].status is AlertStatus.ACTIVE
        assert alert_id in restarted._unverified_restored_alert_ids

        unavailable_state = hass.states.set("sensor.offline", "unavailable")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "sensor.offline",
                    "old_state": unknown_state,
                    "new_state": unavailable_state,
                }
            )
        )
        await _settle()
        assert restarted.records[alert_id].status is AlertStatus.ACTIVE
        assert alert_id not in restarted._unverified_restored_alert_ids

        unknown_again = hass.states.set("sensor.offline", "unknown")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "sensor.offline",
                    "old_state": unavailable_state,
                    "new_state": unknown_again,
                }
            )
        )
        await _settle()
        assert alert_id not in restarted.records
        assert [
            data
            for event, data in hass.bus.fired
            if event == EVENT_ALERT_RESOLVED and data["id"] == alert_id
        ]

    asyncio.run(scenario())


def test_restored_battery_alert_survives_neutral_startup_states(hass, entry):
    """Pack-neutral unavailable/unknown states do not erase a restored battery."""

    async def scenario():
        hass.states.set(
            "sensor.remote_battery",
            "5",
            {ATTR_DEVICE_CLASS: "battery"},
        )
        first = AlertManager(hass, entry)
        await first.async_setup()
        await first.async_update_config({"automatic": {"battery": {"delay": 0}}})
        alert_id = "battery:sensor.remote_battery"
        assert first.records[alert_id].status is AlertStatus.ACTIVE
        await first.async_unload()

        hass.state = CoreState.starting
        unavailable_state = hass.states.set(
            "sensor.remote_battery",
            "unavailable",
            {ATTR_DEVICE_CLASS: "battery"},
        )
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        await _start_and_reconcile(restarted, hass)
        assert restarted.records[alert_id].status is AlertStatus.ACTIVE
        assert alert_id in restarted._unverified_restored_alert_ids

        unknown_state = hass.states.set(
            "sensor.remote_battery",
            "unknown",
            {ATTR_DEVICE_CLASS: "battery"},
        )
        restarted._state_changed(
            Event(
                {
                    "entity_id": "sensor.remote_battery",
                    "old_state": unavailable_state,
                    "new_state": unknown_state,
                }
            )
        )
        await _settle()
        assert restarted.records[alert_id].status is AlertStatus.ACTIVE

        healthy_state = hass.states.set(
            "sensor.remote_battery",
            "90",
            {ATTR_DEVICE_CLASS: "battery"},
        )
        restarted._state_changed(
            Event(
                {
                    "entity_id": "sensor.remote_battery",
                    "old_state": unknown_state,
                    "new_state": healthy_state,
                }
            )
        )
        await _settle()
        assert alert_id not in restarted.records

    asyncio.run(scenario())


def test_reconciliation_drains_recovery_during_store_write_before_publish(hass, entry):
    """The latest state wins even when it changes while reconciliation awaits I/O."""

    async def scenario():
        hass.states.set("event.baby", "idle")
        first = AlertManager(hass, entry)
        await first.async_setup()
        await first.async_unload()

        hass.state = CoreState.starting
        unavailable_state = hass.states.set("event.baby", "unavailable")
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())

        save_started = asyncio.Event()
        release_save = asyncio.Event()
        original_save = restarted.storage.async_save
        first_call = True

        async def blocked_save(*args, **kwargs):
            nonlocal first_call
            if first_call:
                first_call = False
                save_started.set()
                await release_save.wait()
            await original_save(*args, **kwargs)

        restarted.storage.async_save = blocked_save
        _fire_startup_reconciliation(hass)
        await save_started.wait()
        assert restarted._runtime_phase is RuntimePhase.RECONCILING

        unknown_state = hass.states.set("event.baby", "unknown")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "event.baby",
                    "old_state": unavailable_state,
                    "new_state": unknown_state,
                }
            )
        )
        assert restarted._queued_evaluation_entities == {"event.baby"}
        release_save.set()
        await _settle()

        alert_id = "unavailable:event.baby"
        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert alert_id not in restarted.records
        assert alert_id not in hass.stores["alert_manager"]["alerts"]
        assert restarted.public_snapshot()["pending_count"] == 0

    asyncio.run(scenario())


def test_reconciliation_drains_broad_jinja_change_during_store_write(hass, entry):
    """A broad Jinja dependency change is evaluated before startup publishes."""

    async def scenario():
        hass.states.set("binary_sensor.filter", "on")
        first = AlertManager(hass, entry)
        await first.async_setup()
        rule = await first.async_create_rule(
            {
                "name": "Dynamic filter gate",
                "entity_ids": ["binary_sensor.filter"],
                "operator": "equals",
                "value": "on",
                "condition_template": "{{ true }}",
                "duration": 0,
            }
        )
        alert_id = f"rule:{rule['id']}:binary_sensor.filter"
        assert first.records[alert_id].status is AlertStatus.ACTIVE
        await first.async_unload()

        hass.state = CoreState.starting
        old_gate_state = hass.states.set("sensor.dynamic_gate", "off")
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()

        def dynamic_render_info(_variables=None):
            matches = hass.states.get("sensor.dynamic_gate").state == "on"
            return SimpleNamespace(
                result=lambda: str(matches).lower(),
                entities=frozenset(),
                all_states=True,
                all_states_lifecycle=True,
                domains=frozenset(),
                domains_lifecycle=frozenset(),
                has_time=False,
                rate_limit=60,
                filter=lambda _entity_id: True,
                filter_lifecycle=lambda _entity_id: True,
            )

        restarted._rule_templates[rule["id"]].async_render_to_info = dynamic_render_info
        published_states = []
        original_publish = restarted._publish_if_changed

        def capture_publish(*args, **kwargs):
            original_publish(*args, **kwargs)
            published_states.append(_published_alert_state(restarted))

        restarted._publish_if_changed = capture_publish
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())

        save_started = asyncio.Event()
        release_save = asyncio.Event()
        original_save = restarted.storage.async_save
        first_call = True

        async def blocked_save(*args, **kwargs):
            nonlocal first_call
            if first_call:
                first_call = False
                save_started.set()
                await release_save.wait()
            await original_save(*args, **kwargs)

        restarted.storage.async_save = blocked_save
        _fire_startup_reconciliation(hass)
        await save_started.wait()
        assert alert_id not in restarted.records

        new_gate_state = hass.states.set("sensor.dynamic_gate", "on")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "sensor.dynamic_gate",
                    "old_state": old_gate_state,
                    "new_state": new_gate_state,
                }
            )
        )
        assert restarted._queued_evaluation_entities == {"binary_sensor.filter"}
        release_save.set()
        await _settle()

        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert restarted.records[alert_id].status is AlertStatus.ACTIVE
        assert hass.stores["alert_manager"]["alerts"][alert_id]["status"] == "active"
        assert published_states == [
            (RuntimePhase.STARTUP_GRACE, True, {alert_id: "active"}),
            (RuntimePhase.STARTUP_GRACE, True, {alert_id: "active"}),
            (RuntimePhase.RUNNING, False, {alert_id: "active"}),
        ]

    asyncio.run(scenario())


def test_reconciliation_rechecks_pending_due_crossed_during_store(hass, entry, set_now):
    """A Store write cannot make the first committed alert status stale."""
    start = datetime(2026, 9, 4, 12, tzinfo=UTC)
    set_now(start)

    async def scenario():
        entity_id = "binary_sensor.pool_filter"
        hass.states.set(entity_id, "on", {ATTR_FRIENDLY_NAME: "Pool filter"})
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        rule = await first.async_create_rule(
            {
                "name": "Pool filtration",
                "entity_ids": [entity_id],
                "operator": "equals",
                "value": "on",
                "duration": 60,
            }
        )
        alert_id = f"rule:{rule['id']}:{entity_id}"
        due_at = first.records[alert_id].due_at
        await first.async_unload()
        hass.bus.fired.clear()

        hass.state = CoreState.starting
        set_now(due_at - timedelta(seconds=1))
        hass.states.set(entity_id, "on", {ATTR_FRIENDLY_NAME: "Renamed filter"})
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())

        published_states = []
        original_publish = restarted._publish_if_changed

        def capture_publish(*args, **kwargs):
            original_publish(*args, **kwargs)
            published_states.append(_published_alert_state(restarted))

        restarted._publish_if_changed = capture_publish
        save_started = asyncio.Event()
        release_save = asyncio.Event()
        original_save = restarted.storage.async_save
        save_calls = 0

        async def blocked_save(*args, **kwargs):
            nonlocal save_calls
            save_calls += 1
            if save_calls == 1:
                save_started.set()
                await release_save.wait()
            await original_save(*args, **kwargs)

        restarted.storage.async_save = blocked_save
        _fire_startup_reconciliation(hass)
        await save_started.wait()
        assert restarted.records[alert_id].status is AlertStatus.PENDING

        set_now(due_at + timedelta(seconds=1))
        release_save.set()
        await _settle()

        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert restarted.records[alert_id].status is AlertStatus.ACTIVE
        assert hass.stores["alert_manager"]["alerts"][alert_id]["status"] == "active"
        assert save_calls == 2
        assert published_states == [
            (RuntimePhase.STARTUP_GRACE, True, {alert_id: "pending"}),
            (RuntimePhase.RUNNING, False, {alert_id: "active"}),
        ]
        assert [
            event for event, _data in hass.bus.fired if event == EVENT_ALERT_STARTED
        ] == [EVENT_ALERT_STARTED]

    asyncio.run(scenario())


def test_reconciliation_rechecks_jinja_minute_crossed_during_store(
    hass, entry, set_now
):
    """A time-aware template is authoritative at commit, not scan start."""
    start = datetime(2026, 9, 4, 12, 34, tzinfo=UTC)
    set_now(start)

    async def scenario():
        entity_id = "binary_sensor.pool_filter"
        hass.states.set(entity_id, "on")
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        rule = await first.async_create_rule(
            {
                "name": "Odd-minute filtration",
                "entity_ids": [entity_id],
                "operator": "equals",
                "value": "on",
                "condition_template": "{{ true }}",
                "duration": 0,
            }
        )
        alert_id = f"rule:{rule['id']}:{entity_id}"
        assert first.records[alert_id].status is AlertStatus.ACTIVE
        await first.async_unload()
        hass.bus.fired.clear()

        hass.state = CoreState.starting
        set_now(start.replace(second=59))
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True

        def time_render_info(_variables=None):
            matches = dt_util.now().minute % 2 == 1
            return SimpleNamespace(
                result=lambda: str(matches).lower(),
                entities=frozenset(),
                all_states=False,
                all_states_lifecycle=False,
                domains=frozenset(),
                domains_lifecycle=frozenset(),
                has_time=True,
                rate_limit=None,
                filter=lambda _entity_id: False,
                filter_lifecycle=lambda _entity_id: False,
            )

        restarted._rule_templates[rule["id"]].async_render_to_info = time_render_info
        published_states = []
        original_publish = restarted._publish_if_changed

        def capture_publish(*args, **kwargs):
            original_publish(*args, **kwargs)
            published_states.append(_published_alert_state(restarted))

        restarted._publish_if_changed = capture_publish
        save_started = asyncio.Event()
        release_save = asyncio.Event()
        original_save = restarted.storage.async_save
        save_calls = 0

        async def blocked_save(*args, **kwargs):
            nonlocal save_calls
            save_calls += 1
            if save_calls == 1:
                save_started.set()
                await release_save.wait()
            await original_save(*args, **kwargs)

        restarted.storage.async_save = blocked_save
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        _fire_startup_reconciliation(hass)
        await save_started.wait()
        assert alert_id not in restarted.records

        set_now(start.replace(minute=35, second=1))
        release_save.set()
        await _settle()

        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert restarted.records[alert_id].status is AlertStatus.ACTIVE
        assert hass.stores["alert_manager"]["alerts"][alert_id]["status"] == "active"
        assert save_calls == 2
        assert published_states == [
            (RuntimePhase.STARTUP_GRACE, True, {alert_id: "active"}),
            (RuntimePhase.STARTUP_GRACE, True, {alert_id: "active"}),
            (RuntimePhase.RUNNING, False, {alert_id: "active"}),
        ]
        assert not [
            event
            for event, _data in hass.bus.fired
            if event in (EVENT_ALERT_STARTED, EVENT_ALERT_RESOLVED)
        ]
        assert restarted._template_time_timer is not None

    asyncio.run(scenario())


@pytest.mark.parametrize("retained", ["original", "existing"])
def test_entity_rename_collision_keeps_provenance_of_retained_record(
    hass, entry, set_now, retained
):
    """A rename collision transfers provenance according to the chosen record."""
    now = datetime(2026, 9, 4, 12, tzinfo=UTC)
    set_now(now)

    async def scenario():
        old_state = hass.states.set("sensor.old", "ok")
        new_state = hass.states.set("sensor.new", "ok")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        old_id = "unavailable:sensor.old"
        new_id = "unavailable:sensor.new"
        if retained == "original":
            old_detected, new_detected = now, now + timedelta(minutes=1)
        else:
            old_detected, new_detected = now + timedelta(minutes=1), now
        original = AlertRecord.pending(
            manager._details(old_state, old_id, "unavailable", "Unavailable"),
            900,
            old_detected,
        )
        existing = AlertRecord.pending(
            manager._details(new_state, new_id, "unavailable", "Unavailable"),
            900,
            new_detected,
        )
        manager._set_record(original)
        manager._set_record(existing)
        if retained == "original":
            manager._unverified_restored_alert_ids = {old_id}
        else:
            manager._unverified_restored_alert_ids = {new_id}

        manager._pending_entity_renames["sensor.old"] = "sensor.new"
        assert manager._apply_pending_entity_renames() is True

        assert set(manager.records) == {new_id}
        assert manager.records[new_id].detected_at == min(old_detected, new_detected)
        assert manager._unverified_restored_alert_ids == {new_id}

    asyncio.run(scenario())


@pytest.mark.parametrize("active_side", ["source", "target"])
def test_runtime_rename_equal_clock_prefers_active_record(
    hass, entry, set_now, active_side
):
    """An equal-clock runtime rename never replaces active with pending."""
    now = datetime(2026, 9, 4, 12, tzinfo=UTC)
    set_now(now)

    async def scenario():
        old_state = hass.states.set("sensor.old", "ok")
        new_state = hass.states.set("sensor.new", "ok")
        manager = AlertManager(hass, entry)
        assert await manager.async_setup() is True
        old_id = "unavailable:sensor.old"
        new_id = "unavailable:sensor.new"
        old_record = AlertRecord.pending(
            manager._details(old_state, old_id, "unavailable", "Unavailable"),
            0 if active_side == "source" else 900,
            now,
        )
        new_record = AlertRecord.pending(
            manager._details(new_state, new_id, "unavailable", "Unavailable"),
            0 if active_side == "target" else 900,
            now,
        )
        active_record = old_record if active_side == "source" else new_record
        assert advance_record(active_record, now) is True
        manager._set_record(old_record)
        manager._set_record(new_record)

        manager._pending_entity_renames["sensor.old"] = "sensor.new"
        assert manager._apply_pending_entity_renames() is True

        assert set(manager.records) == {new_id}
        assert manager.records[new_id].status is AlertStatus.ACTIVE
        assert manager.records[new_id].active_since == now

    asyncio.run(scenario())


def test_shutdown_makes_due_timer_callback_inert(hass, entry):
    """A callback already handed to the loop cannot restart runtime after shutdown."""

    async def scenario():
        hass.states.set("sensor.offline", "unavailable")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        alert_id = "unavailable:sensor.offline"
        timer = next(
            timer
            for timer in hass.timers
            if not timer["cancelled"]
            and "_schedule_timer.<locals>.timer_due" in timer["action"].__qualname__
        )

        manager._begin_shutdown()
        hass.state = CoreState.stopping
        timer["action"](timer["point"])
        await _settle()

        assert manager._runtime_phase is RuntimePhase.STOPPING
        assert manager._queued_evaluation_entities == set()
        assert manager._evaluation_flush_scheduled is False
        assert manager.records[alert_id].status is AlertStatus.PENDING

    asyncio.run(scenario())


def test_restored_pending_unavailable_keeps_clock_when_outage_is_confirmed(
    hass, entry, set_now
):
    """A real outage keeps its old deadline, activates, then unknown resolves it."""
    start = datetime(2026, 9, 4, 12, tzinfo=UTC)
    set_now(start)

    async def scenario():
        hass.states.set("sensor.offline", "unavailable")
        first = AlertManager(hass, entry)
        await first.async_setup()
        alert_id = "unavailable:sensor.offline"
        detected_at = first.records[alert_id].detected_at
        due_at = first.records[alert_id].due_at
        await first.async_unload()

        hass.state = CoreState.starting
        set_now(start + timedelta(minutes=5))
        unavailable_state = hass.states.set("sensor.offline", "unavailable")
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        await _start_and_reconcile(restarted, hass)

        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.PENDING
        assert restored.detected_at == detected_at
        assert restored.due_at == due_at
        assert alert_id not in restarted._unverified_restored_alert_ids

        set_now(due_at + timedelta(seconds=1))
        await restarted.async_evaluate_entity("sensor.offline")
        assert restarted.records[alert_id].status is AlertStatus.ACTIVE

        unknown_state = hass.states.set("sensor.offline", "unknown")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "sensor.offline",
                    "old_state": unavailable_state,
                    "new_state": unknown_state,
                }
            )
        )
        await _settle()
        assert alert_id not in restarted.records

    asyncio.run(scenario())


@pytest.mark.parametrize("uncertain_state", [None, "unknown", "unavailable"])
def test_restored_active_custom_waits_for_authoritative_state(
    hass, entry, uncertain_state
):
    """A restored active rule survives uncertainty, then follows known states."""

    async def scenario():
        hass.states.set("binary_sensor.filter", "on")
        first = AlertManager(hass, entry)
        await first.async_setup()
        rule = await first.async_create_rule(
            {
                "name": "Filter active",
                "entity_ids": ["binary_sensor.filter"],
                "operator": "equals",
                "value": "on",
                "duration": 0,
            }
        )
        alert_id = f"rule:{rule['id']}:binary_sensor.filter"
        original = first.records[alert_id]
        detected_at = original.detected_at
        active_since = original.active_since
        await first.async_unload()

        hass.state = CoreState.starting
        if uncertain_state is None:
            hass.states.data.pop("binary_sensor.filter")
        else:
            hass.states.set("binary_sensor.filter", uncertain_state)
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        await _start_and_reconcile(restarted, hass)

        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.ACTIVE
        assert restored.detected_at == detected_at
        assert restored.active_since == active_since
        assert alert_id in restarted._unverified_restored_alert_ids

        indeterminate_state = hass.states.get("binary_sensor.filter")
        matching_state = hass.states.set("binary_sensor.filter", "on")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "binary_sensor.filter",
                    "old_state": indeterminate_state,
                    "new_state": matching_state,
                }
            )
        )
        await _settle()
        assert restarted.records[alert_id].status is AlertStatus.ACTIVE
        assert restarted.records[alert_id].detected_at == detected_at
        assert alert_id not in restarted._unverified_restored_alert_ids

        normal_state = hass.states.set("binary_sensor.filter", "off")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "binary_sensor.filter",
                    "old_state": matching_state,
                    "new_state": normal_state,
                }
            )
        )
        await _settle()
        assert alert_id not in restarted.records

    asyncio.run(scenario())


def test_state_change_during_startup_scan_is_drained_before_publish(hass, entry):
    """A state change after its scan turn is evaluated before startup publishes."""

    async def scenario():
        hass.states.set("event.baby", "idle")
        first = AlertManager(hass, entry)
        await first.async_setup()
        await first.async_unload()

        hass.state = CoreState.starting
        unavailable_state = hass.states.set("event.baby", "unavailable")
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())

        first_scan_complete = asyncio.Event()
        release_scan = asyncio.Event()
        catch_up_complete = asyncio.Event()
        original_evaluate = restarted.async_evaluate_entity
        blocked_once = False

        async def blocked_evaluate(entity_id, **kwargs):
            nonlocal blocked_once
            changed = await original_evaluate(entity_id, **kwargs)
            if entity_id != "event.baby":
                return changed
            if not blocked_once:
                blocked_once = True
                first_scan_complete.set()
                await release_scan.wait()
            else:
                catch_up_complete.set()
            return changed

        restarted.async_evaluate_entity = blocked_evaluate
        _fire_startup_reconciliation(hass)
        await first_scan_complete.wait()

        unknown_state = hass.states.set("event.baby", "unknown")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "event.baby",
                    "old_state": unavailable_state,
                    "new_state": unknown_state,
                }
            )
        )
        assert restarted._queued_evaluation_entities == {"event.baby"}
        release_scan.set()
        await catch_up_complete.wait()
        await _settle()

        alert_id = "unavailable:event.baby"
        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert alert_id not in restarted.records
        assert alert_id not in hass.stores["alert_manager"]["alerts"]
        assert restarted.public_snapshot()["pending_count"] == 0

    asyncio.run(scenario())


def test_shutdown_during_reconciliation_discards_queued_recovery(hass, entry):
    """A reconciliation task cannot return the manager to running after shutdown."""

    async def scenario():
        hass.states.set("event.baby", "idle")
        first = AlertManager(hass, entry)
        await first.async_setup()
        await first.async_unload()

        hass.state = CoreState.starting
        unavailable_state = hass.states.set("event.baby", "unavailable")
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())

        scan_complete = asyncio.Event()
        release_scan = asyncio.Event()
        original_evaluate = restarted.async_evaluate_entity
        blocked_once = False

        async def blocked_evaluate(entity_id, **kwargs):
            nonlocal blocked_once
            changed = await original_evaluate(entity_id, **kwargs)
            if entity_id == "event.baby" and not blocked_once:
                blocked_once = True
                scan_complete.set()
                await release_scan.wait()
            return changed

        restarted.async_evaluate_entity = blocked_evaluate
        _fire_startup_reconciliation(hass)
        await scan_complete.wait()
        alert_id = "unavailable:event.baby"
        assert alert_id in restarted.records

        unknown_state = hass.states.set("event.baby", "unknown")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "event.baby",
                    "old_state": unavailable_state,
                    "new_state": unknown_state,
                }
            )
        )
        assert restarted._queued_evaluation_entities == {"event.baby"}
        restarted._begin_shutdown()
        hass.state = CoreState.stopping
        release_scan.set()
        await _settle()
        await restarted.async_unload()

        assert restarted._runtime_phase is RuntimePhase.STOPPING
        assert alert_id not in restarted.records
        assert alert_id not in hass.stores["alert_manager"]["alerts"]
        assert restarted._queued_evaluation_entities == set()
        assert restarted._evaluation_flush_scheduled is False
        assert not [timer for timer in hass.timers if not timer["cancelled"]]

    asyncio.run(scenario())


def test_transient_startup_outage_has_no_lifecycle_side_effects(hass, entry):
    """Only the stable reconciliation result reaches events and history."""

    async def scenario():
        hass.states.set("event.baby", "idle")
        first = AlertManager(hass, entry)
        await first.async_setup()
        await first.async_update_config({"automatic": {"unavailable": {"delay": 0}}})
        await first.async_unload()

        hass.state = CoreState.starting
        unavailable_state = hass.states.set("event.baby", "unavailable")
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        hass.bus.fired.clear()

        active_created = asyncio.Event()
        release_scan = asyncio.Event()
        original_evaluate = restarted.async_evaluate_entity
        blocked_once = False

        async def blocked_evaluate(entity_id, **kwargs):
            nonlocal blocked_once
            changed = await original_evaluate(entity_id, **kwargs)
            if entity_id == "event.baby" and not blocked_once:
                blocked_once = True
                assert restarted.records["unavailable:event.baby"].status is (
                    AlertStatus.ACTIVE
                )
                active_created.set()
                await release_scan.wait()
            return changed

        restarted.async_evaluate_entity = blocked_evaluate
        _fire_startup_reconciliation(hass)
        await active_created.wait()
        frozen_snapshot = restarted.public_snapshot()
        assert restarted._runtime_phase is RuntimePhase.RECONCILING
        assert frozen_snapshot["active_count"] == 0
        assert frozen_snapshot["pending_count"] == 0

        unknown_state = hass.states.set("event.baby", "unknown")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "event.baby",
                    "old_state": unavailable_state,
                    "new_state": unknown_state,
                }
            )
        )
        release_scan.set()
        await _settle()

        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert "unavailable:event.baby" not in restarted.records
        assert restarted.history == []
        assert restarted._pending_history == []
        assert not [
            event
            for event, _data in hass.bus.fired
            if event in (EVENT_ALERT_STARTED, EVENT_ALERT_RESOLVED)
        ]

    asyncio.run(scenario())


@pytest.mark.parametrize("delay", [0, 15 * 60])
def test_shutdown_discards_unavailable_event_waiting_for_worker(hass, entry, delay):
    """A queued runtime worker cannot create an outage after shutdown starts."""

    async def scenario():
        old_state = hass.states.set("event.baby", "idle")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        await manager.async_update_config(
            {
                "entity_delays": {"event.baby": delay},
                "pending_display_delay": 0,
            }
        )

        unavailable_state = hass.states.set("event.baby", "unavailable")
        manager._state_changed(
            Event(
                {
                    "entity_id": "event.baby",
                    "old_state": old_state,
                    "new_state": unavailable_state,
                }
            )
        )
        assert manager._evaluation_flush_scheduled is True

        manager._begin_shutdown()
        hass.state = CoreState.stopping
        await _settle()
        await manager.async_unload()

        alert_id = "unavailable:event.baby"
        assert manager._runtime_phase is RuntimePhase.STOPPING
        assert alert_id not in manager.records
        assert alert_id not in hass.stores["alert_manager"]["alerts"]

    asyncio.run(scenario())


def test_side_worker_cannot_enter_reconciling_before_startup_owner(hass, entry):
    """RECONCILING starts only after its worker owns the mutation lock."""

    async def scenario():
        hass.states.set("event.baby", "idle")
        first = AlertManager(hass, entry)
        await first.async_setup()
        await first.async_unload()

        hass.state = CoreState.starting
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        restarted._registry_evaluation_dirty = True

        await restarted._config_mutation_lock.acquire()
        side_worker = asyncio.create_task(restarted._async_flush_registry_evaluation())
        _fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        assert restarted._runtime_phase is RuntimePhase.STARTUP_GRACE

        restarted._config_mutation_lock.release()
        await side_worker
        await _settle()

        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert restarted._registry_evaluation_dirty is False

    asyncio.run(scenario())


def test_registry_rename_during_scan_is_applied_and_saved(hass, entry):
    """A rename arriving during the scan is consumed before the first publish."""

    async def scenario():
        hass.states.set("binary_sensor.old_filter", "on")
        first = AlertManager(hass, entry)
        await first.async_setup()
        rule = await first.async_create_rule(
            {
                "name": "Filter active",
                "entity_ids": ["binary_sensor.old_filter"],
                "operator": "equals",
                "value": "on",
                "duration": 0,
            }
        )
        await first.async_unload()

        hass.state = CoreState.starting
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        hass.bus.fired.clear()

        old_scanned = asyncio.Event()
        release_scan = asyncio.Event()
        renamed_scan_started = asyncio.Event()
        release_renamed_scan = asyncio.Event()
        original_evaluate = restarted.async_evaluate_entity
        blocked_once = False

        async def blocked_evaluate(entity_id, **kwargs):
            nonlocal blocked_once
            changed = await original_evaluate(entity_id, **kwargs)
            if entity_id == "binary_sensor.old_filter" and not blocked_once:
                blocked_once = True
                old_scanned.set()
                await release_scan.wait()
            elif entity_id == "binary_sensor.new_filter":
                renamed_scan_started.set()
                await release_renamed_scan.wait()
            return changed

        restarted.async_evaluate_entity = blocked_evaluate
        _fire_startup_reconciliation(hass)
        await old_scanned.wait()

        hass.states.data.pop("binary_sensor.old_filter")
        hass.states.set("binary_sensor.new_filter", "on")
        restarted._registry_changed(
            Event(
                {
                    "action": "update",
                    "old_entity_id": "binary_sensor.old_filter",
                    "entity_id": "binary_sensor.new_filter",
                }
            )
        )
        release_scan.set()
        await renamed_scan_started.wait()
        assert restarted.config["rules"][0]["entity_ids"] == [
            "binary_sensor.new_filter"
        ]
        assert restarted.get_config()["rules"][0]["entity_ids"] == [
            "binary_sensor.old_filter"
        ]
        release_renamed_scan.set()
        await _settle()

        alert_id = f"rule:{rule['id']}:binary_sensor.new_filter"
        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert restarted.config["rules"][0]["entity_ids"] == [
            "binary_sensor.new_filter"
        ]
        assert alert_id in restarted.records
        assert hass.stores["alert_manager"]["config"]["rules"][0]["entity_ids"] == [
            "binary_sensor.new_filter"
        ]
        assert restarted.records[alert_id].status is AlertStatus.ACTIVE
        assert not [
            event
            for event, _data in hass.bus.fired
            if event in (EVENT_ALERT_STARTED, EVENT_ALERT_RESOLVED)
        ]

    asyncio.run(scenario())


def test_pack_change_during_scan_forces_a_second_authoritative_scan(hass, entry):
    """Pack availability changes cannot remain dirty after reconciliation."""

    async def scenario():
        hass.states.set("event.baby", "idle")
        first = AlertManager(hass, entry)
        await first.async_setup()
        await first.async_unload()

        hass.state = CoreState.starting
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())

        first_scan = asyncio.Event()
        release_scan = asyncio.Event()
        original_evaluate = restarted.async_evaluate_entity
        evaluation_count = 0
        refresh_count = 0
        original_replace = restarted._replace_pack_availability_snapshot

        async def blocked_evaluate(entity_id, **kwargs):
            nonlocal evaluation_count
            changed = await original_evaluate(entity_id, **kwargs)
            if entity_id == "event.baby":
                evaluation_count += 1
                if evaluation_count == 1:
                    first_scan.set()
                    await release_scan.wait()
            return changed

        def counted_replace():
            nonlocal refresh_count
            refresh_count += 1
            return original_replace()

        restarted.async_evaluate_entity = blocked_evaluate
        restarted._replace_pack_availability_snapshot = counted_replace
        _fire_startup_reconciliation(hass)
        await first_scan.wait()

        restarted._schedule_pack_availability_refresh()
        assert restarted._pack_refresh_dirty is True
        release_scan.set()
        await _settle()

        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert restarted._pack_refresh_dirty is False
        assert refresh_count == 1
        assert evaluation_count >= 2

    asyncio.run(scenario())


def test_running_transition_during_setup_starts_exactly_one_grace(hass, entry):
    """Finishing HA startup during setup cannot strand reconciliation."""

    async def scenario():
        hass.states.set("event.baby", "idle")
        first = AlertManager(hass, entry)
        await first.async_setup()
        await first.async_unload()

        hass.state = CoreState.starting
        hass.states.set("event.baby", "unknown")
        restarted = AlertManager(hass, entry)
        original_load = restarted._async_load_condition_translations

        async def finish_startup_during_load():
            await original_load()
            hass.state = CoreState.running

        restarted._async_load_condition_translations = finish_startup_during_load
        assert await restarted.async_setup() is True

        active_grace_timers = [
            timer
            for timer in hass.timers
            if not timer["cancelled"]
            and "_schedule_startup_reconciliation" in timer["action"].__qualname__
        ]
        assert restarted._runtime_phase is RuntimePhase.STARTUP_GRACE
        assert len(active_grace_timers) == 1

        _fire_startup_reconciliation(hass)
        await _settle()
        assert restarted._runtime_phase is RuntimePhase.RUNNING

    asyncio.run(scenario())


def test_setup_reaching_final_write_never_arms_runtime(hass, entry):
    """A terminal HA state during setup leaves no listeners or timers behind."""

    async def scenario():
        hass.state = CoreState.starting
        manager = AlertManager(hass, entry)
        translations_loaded = asyncio.Event()
        release_setup = asyncio.Event()
        original_load = manager._async_load_condition_translations

        async def blocked_translation_load():
            await original_load()
            translations_loaded.set()
            await release_setup.wait()

        manager._async_load_condition_translations = blocked_translation_load
        setup_task = asyncio.create_task(manager.async_setup())
        await translations_loaded.wait()

        hass.state = CoreState.final_write
        release_setup.set()
        assert await setup_task is False
        await manager.async_unload()

        assert manager._runtime_phase is RuntimePhase.STOPPING
        assert manager._unsubscribers == []
        assert hass.shutdown_jobs == []
        assert not any(hass.bus.listeners.values())
        assert not any(hass.dispatchers.values())
        assert not [timer for timer in hass.timers if not timer["cancelled"]]

    asyncio.run(scenario())


def test_shutdown_rollback_cannot_rearm_restored_template_timers(hass, entry):
    """Restoring Jinja dependency metadata during shutdown leaves no timer."""

    async def scenario():
        hass.states.set("binary_sensor.filter", "on")
        first = AlertManager(hass, entry)
        await first.async_setup()
        rule = await first.async_create_rule(
            {
                "name": "Filter active",
                "entity_ids": ["binary_sensor.filter"],
                "operator": "equals",
                "value": "on",
                "condition_template": "{{ true }}",
                "duration": 3600,
            }
        )
        await first.async_unload()

        hass.state = CoreState.starting
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        restarted._rule_template_render_info[(rule["id"], "binary_sensor.filter")] = (
            SimpleNamespace(
                entities=frozenset(),
                all_states=False,
                all_states_lifecycle=False,
                domains=frozenset(),
                domains_lifecycle=frozenset(),
                has_time=True,
                rate_limit=None,
            )
        )
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())

        scan_complete = asyncio.Event()
        release_scan = asyncio.Event()
        original_evaluate = restarted.async_evaluate_entity

        async def blocked_evaluate(entity_id, **kwargs):
            changed = await original_evaluate(entity_id, **kwargs)
            if entity_id == "binary_sensor.filter":
                scan_complete.set()
                await release_scan.wait()
            return changed

        restarted.async_evaluate_entity = blocked_evaluate
        _fire_startup_reconciliation(hass)
        await scan_complete.wait()

        restarted._begin_shutdown()
        hass.state = CoreState.stopping
        release_scan.set()
        await _settle()
        await restarted.async_unload()

        assert restarted._runtime_phase is RuntimePhase.STOPPING
        assert restarted._template_time_timer is None
        assert restarted._template_rate_limit_timers == {}
        assert not [timer for timer in hass.timers if not timer["cancelled"]]

    asyncio.run(scenario())


def test_failed_config_write_restores_startup_provenance(hass, entry):
    """Rollback restores both the alert and its indeterminate-state protection."""

    async def scenario():
        hass.states.set("binary_sensor.filter", "on")
        first = AlertManager(hass, entry)
        await first.async_setup()
        rule = await first.async_create_rule(
            {
                "name": "Filter active",
                "entity_ids": ["binary_sensor.filter"],
                "operator": "equals",
                "value": "on",
                "duration": 3600,
            }
        )
        alert_id = f"rule:{rule['id']}:binary_sensor.filter"
        await first.async_unload()

        hass.state = CoreState.starting
        hass.states.set("binary_sensor.filter", "unknown")
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        await _start_and_reconcile(restarted, hass)
        original_config = restarted.get_config()
        assert alert_id in restarted._unverified_restored_alert_ids

        hass.states.set("binary_sensor.filter", "off")

        async def failed_save(*_args, **_kwargs):
            raise OSError("storage unavailable")

        restarted.storage.async_save = failed_save
        with pytest.raises(OSError, match="storage unavailable"):
            await restarted.async_update_config(
                {"global_delay": original_config["global_delay"] + 1}
            )

        assert restarted.get_config() == original_config
        assert alert_id in restarted.records
        assert alert_id in restarted._unverified_restored_alert_ids

    asyncio.run(scenario())


def test_reconciliation_custom_pending_true_false_true_keeps_clock(
    hass, entry, set_now
):
    """Every provisional scan rebases on the immutable restored occurrence."""
    start = datetime(2026, 9, 4, 18, tzinfo=UTC)
    set_now(start)

    async def scenario():
        hass.states.set("binary_sensor.filter", "on")
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        rule = await first.async_create_rule(
            {
                "name": "Filter active",
                "entity_ids": ["binary_sensor.filter"],
                "operator": "equals",
                "value": "on",
                "duration": 24 * 60 * 60,
            }
        )
        alert_id = f"rule:{rule['id']}:binary_sensor.filter"
        original = deepcopy(first.records[alert_id])
        await first.async_unload()

        hass.state = CoreState.starting
        matching_state = hass.states.set("binary_sensor.filter", "on")
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        restarted._immediate_state_save_required = True

        original_save = restarted.storage.async_save
        first_save_started = asyncio.Event()
        release_first_save = asyncio.Event()
        second_save_started = asyncio.Event()
        release_second_save = asyncio.Event()
        save_calls = 0

        async def blocked_save(*args, **kwargs):
            nonlocal save_calls
            save_calls += 1
            if save_calls == 1:
                first_save_started.set()
                await release_first_save.wait()
            elif save_calls == 2:
                second_save_started.set()
                await release_second_save.wait()
            await original_save(*args, **kwargs)

        restarted.storage.async_save = blocked_save
        _fire_startup_reconciliation(hass)
        await first_save_started.wait()

        normal_state = hass.states.set("binary_sensor.filter", "off")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "binary_sensor.filter",
                    "old_state": matching_state,
                    "new_state": normal_state,
                }
            )
        )
        release_first_save.set()
        await second_save_started.wait()

        final_state = hass.states.set("binary_sensor.filter", "on")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "binary_sensor.filter",
                    "old_state": normal_state,
                    "new_state": final_state,
                }
            )
        )
        release_second_save.set()
        await _settle()

        assert restarted._runtime_phase is RuntimePhase.RUNNING
        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.PENDING
        assert restored.detected_at == original.detected_at
        assert restored.due_at == original.due_at
        assert alert_id not in restarted._unverified_restored_alert_ids
        persisted = hass.stores["alert_manager"]["alerts"][alert_id]
        assert persisted["detected_at"] == original.detected_at.isoformat()
        assert save_calls == 3

    asyncio.run(scenario())


def test_reconciliation_active_unavailable_recovered_then_unavailable_keeps_identity(
    hass, entry
):
    """A late outage revives the restored active occurrence, not a new one."""

    async def scenario():
        hass.states.set("sensor.gateway", "unavailable")
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        await first.async_update_config({"automatic": {"unavailable": {"delay": 0}}})
        alert_id = "unavailable:sensor.gateway"
        original = deepcopy(first.records[alert_id])
        await first.async_unload()

        hass.state = CoreState.starting
        recovered_state = hass.states.set("sensor.gateway", "on")
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())

        original_save = restarted.storage.async_save
        save_started = asyncio.Event()
        release_save = asyncio.Event()
        save_calls = 0

        async def blocked_save(*args, **kwargs):
            nonlocal save_calls
            save_calls += 1
            if save_calls == 1:
                save_started.set()
                await release_save.wait()
            await original_save(*args, **kwargs)

        restarted.storage.async_save = blocked_save
        hass.bus.fired.clear()
        _fire_startup_reconciliation(hass)
        await save_started.wait()
        assert alert_id not in restarted.records

        unavailable_state = hass.states.set("sensor.gateway", "unavailable")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "sensor.gateway",
                    "old_state": recovered_state,
                    "new_state": unavailable_state,
                }
            )
        )
        release_save.set()
        await _settle()

        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.ACTIVE
        assert restored.detected_at == original.detected_at
        assert restored.active_since == original.active_since
        assert alert_id not in restarted._unverified_restored_alert_ids
        assert save_calls == 2
        assert not [
            data
            for event, data in hass.bus.fired
            if event == EVENT_ALERT_RESOLVED and data["id"] == alert_id
        ]

    asyncio.run(scenario())


def test_reconciliation_confirmed_custom_then_unknown_restores_provenance(hass, entry):
    """An unknown state arriving during Store cannot consume restored identity."""

    async def scenario():
        hass.states.set("binary_sensor.filter", "on")
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        rule = await first.async_create_rule(
            {
                "name": "Filter active",
                "entity_ids": ["binary_sensor.filter"],
                "operator": "equals",
                "value": "on",
                "duration": 0,
            }
        )
        alert_id = f"rule:{rule['id']}:binary_sensor.filter"
        original = deepcopy(first.records[alert_id])
        await first.async_unload()

        hass.state = CoreState.starting
        matching_state = hass.states.set("binary_sensor.filter", "on")
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        restarted._immediate_state_save_required = True

        original_save = restarted.storage.async_save
        save_started = asyncio.Event()
        release_save = asyncio.Event()

        async def blocked_save(*args, **kwargs):
            save_started.set()
            await release_save.wait()
            await original_save(*args, **kwargs)

        restarted.storage.async_save = blocked_save
        _fire_startup_reconciliation(hass)
        await save_started.wait()
        # Runtime provenance is not consumed by a provisional scan.
        assert alert_id in restarted._unverified_restored_alert_ids

        unknown_state = hass.states.set("binary_sensor.filter", "unknown")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "binary_sensor.filter",
                    "old_state": matching_state,
                    "new_state": unknown_state,
                }
            )
        )
        release_save.set()
        await _settle()

        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.ACTIVE
        assert restored.detected_at == original.detected_at
        assert restored.active_since == original.active_since
        assert alert_id in restarted._unverified_restored_alert_ids

    asyncio.run(scenario())


def test_pending_unavailable_cannot_gain_restored_active_protection(
    hass, entry, set_now
):
    """A provisional due transition cannot protect a formerly pending outage."""
    start = datetime(2026, 9, 4, 18, tzinfo=UTC)
    set_now(start)

    async def scenario():
        hass.states.set("sensor.gateway", "unavailable")
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        alert_id = "unavailable:sensor.gateway"
        original = deepcopy(first.records[alert_id])
        assert original.status is AlertStatus.PENDING
        await first.async_unload()

        hass.state = CoreState.starting
        set_now(original.due_at + timedelta(seconds=1))
        unavailable_state = hass.states.set("sensor.gateway", "unavailable")
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())

        original_save = restarted.storage.async_save
        save_started = asyncio.Event()
        release_save = asyncio.Event()

        async def blocked_save(*args, **kwargs):
            save_started.set()
            await release_save.wait()
            await original_save(*args, **kwargs)

        restarted.storage.async_save = blocked_save
        _fire_startup_reconciliation(hass)
        await save_started.wait()
        assert restarted.records[alert_id].status is AlertStatus.ACTIVE

        unknown_state = hass.states.set("sensor.gateway", "unknown")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "sensor.gateway",
                    "old_state": unavailable_state,
                    "new_state": unknown_state,
                }
            )
        )
        release_save.set()
        await _settle()

        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert alert_id not in restarted.records
        assert alert_id not in hass.stores["alert_manager"]["alerts"]

    asyncio.run(scenario())


def test_rename_collision_revives_oldest_removed_restored_occurrence(
    hass, entry, set_now
):
    """A removed collision winner replaces a live record from another restore."""
    start = datetime(2026, 9, 4, 18, tzinfo=UTC)
    set_now(start)

    async def scenario():
        hass.states.set("sensor.old", "unavailable")
        hass.states.set("sensor.new", "unavailable")
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        old_id = "unavailable:sensor.old"
        new_id = "unavailable:sensor.new"
        oldest_detected_at = first.records[new_id].detected_at
        first.records[old_id].detected_at += timedelta(minutes=1)
        first.records[old_id].due_at += timedelta(minutes=1)
        first.records[old_id].visible_at += timedelta(minutes=1)
        await first._async_save_state()
        await first.async_unload()

        hass.state = CoreState.starting
        set_now(start + timedelta(minutes=2))
        hass.states.set("sensor.old", "unavailable")
        hass.states.set("sensor.new", "ok")
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())

        original_save = restarted.storage.async_save
        save_started = asyncio.Event()
        release_save = asyncio.Event()

        async def blocked_save(*args, **kwargs):
            if not save_started.is_set():
                save_started.set()
                await release_save.wait()
            await original_save(*args, **kwargs)

        restarted.storage.async_save = blocked_save
        _fire_startup_reconciliation(hass)
        await save_started.wait()
        assert new_id not in restarted.records

        hass.states.data.pop("sensor.old")
        hass.states.set("sensor.new", "unavailable")
        restarted._registry_changed(
            Event(
                {
                    "action": "update",
                    "old_entity_id": "sensor.old",
                    "entity_id": "sensor.new",
                }
            )
        )
        release_save.set()
        await _settle()

        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert set(restarted.records) == {new_id}
        assert restarted.records[new_id].detected_at == oldest_detected_at
        assert (
            hass.stores["alert_manager"]["alerts"][new_id]["detected_at"]
            == oldest_detected_at.isoformat()
        )

    asyncio.run(scenario())


def test_internal_reconciliation_cancellation_rearms_startup(hass, entry):
    """Cancellation inside the admitted worker rolls back before it is propagated."""

    async def scenario():
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        await first.async_unload()

        hass.state = CoreState.starting
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        restarted._cancel_startup_reconciliation()
        restarted._startup_reconciliation_scheduled = True

        original_evaluate_all = restarted.async_evaluate_all

        async def cancelled_evaluation(**_kwargs):
            raise asyncio.CancelledError

        restarted.async_evaluate_all = cancelled_evaluation
        with pytest.raises(asyncio.CancelledError):
            await restarted._async_finish_startup_reconciliation()

        active_timers = [
            timer
            for timer in hass.timers
            if not timer["cancelled"]
            and "_schedule_startup_reconciliation" in timer["action"].__qualname__
        ]
        assert restarted._runtime_phase is RuntimePhase.STARTUP_GRACE
        assert restarted._startup_reconciliation_snapshot is None
        assert restarted._startup_reconciliation_transaction is None
        assert restarted._startup_reconciliation_scheduled is False
        assert len(active_timers) == 1

        restarted.async_evaluate_all = original_evaluate_all
        await restarted.async_unload()

    asyncio.run(scenario())


def test_snapshot_failure_rearms_startup_reconciliation(hass, entry):
    """A failed transaction capture cannot strand the startup phase."""

    async def scenario():
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        await first.async_unload()

        hass.state = CoreState.starting
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        restarted._cancel_startup_reconciliation()
        restarted._startup_reconciliation_scheduled = True
        original_snapshot = restarted._configuration_snapshot

        def failed_snapshot():
            raise RuntimeError("snapshot failed")

        restarted._configuration_snapshot = failed_snapshot
        await restarted._async_finish_startup_reconciliation()

        active_timers = [
            timer
            for timer in hass.timers
            if not timer["cancelled"]
            and "_schedule_startup_reconciliation" in timer["action"].__qualname__
        ]
        assert restarted._runtime_phase is RuntimePhase.STARTUP_GRACE
        assert restarted._startup_reconciliation_snapshot is None
        assert restarted._startup_reconciliation_transaction is None
        assert restarted._startup_reconciliation_scheduled is False
        assert len(active_timers) == 1

        restarted._configuration_snapshot = original_snapshot
        await restarted.async_unload()

    asyncio.run(scenario())


def test_failed_reconciliation_compensates_speculative_store_before_retry(hass, entry):
    """A failed scan rewrites its pre-scan Store snapshot before it is retried."""

    async def scenario():
        hass.states.set("sensor.gateway", "ok")
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        await first.async_unload()
        before_store = deepcopy(hass.stores["alert_manager"])

        hass.state = CoreState.starting
        hass.states.set("sensor.gateway", "unavailable")
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        restarted._cancel_startup_reconciliation()
        restarted._startup_reconciliation_scheduled = True

        original_save = restarted.storage.async_save
        save_calls = 0

        async def fail_after_first_write(*args, **kwargs):
            nonlocal save_calls
            save_calls += 1
            await original_save(*args, **kwargs)
            if save_calls == 1:
                raise RuntimeError("failed after speculative write")

        restarted.storage.async_save = fail_after_first_write
        await restarted._async_finish_startup_reconciliation()

        active_timers = [
            timer
            for timer in hass.timers
            if not timer["cancelled"]
            and "_schedule_startup_reconciliation" in timer["action"].__qualname__
        ]
        assert save_calls == 2
        assert restarted.records == {}
        assert hass.stores["alert_manager"] == before_store
        assert restarted._runtime_phase is RuntimePhase.STARTUP_GRACE
        assert len(active_timers) == 1

        restarted.storage.async_save = original_save
        await restarted.async_unload()

    asyncio.run(scenario())


def test_second_scan_store_failure_compensates_first_speculative_write(hass, entry):
    """A failed catch-up Store cannot leave the prior provisional scan durable."""

    async def scenario():
        hass.states.set("sensor.gateway", "ok")
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        await first.async_unload()
        before_store = deepcopy(hass.stores["alert_manager"])

        hass.state = CoreState.starting
        unavailable_state = hass.states.set("sensor.gateway", "unavailable")
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        restarted._cancel_startup_reconciliation()
        restarted._startup_reconciliation_scheduled = True

        original_save = restarted.storage.async_save
        first_write_done = asyncio.Event()
        release_first_write = asyncio.Event()
        save_calls = 0

        async def fail_second_write(*args, **kwargs):
            nonlocal save_calls
            save_calls += 1
            if save_calls == 1:
                await original_save(*args, **kwargs)
                first_write_done.set()
                await release_first_write.wait()
                return
            if save_calls == 2:
                raise RuntimeError("catch-up write failed")
            await original_save(*args, **kwargs)

        restarted.storage.async_save = fail_second_write
        reconciliation_task = asyncio.create_task(
            restarted._async_finish_startup_reconciliation()
        )
        await first_write_done.wait()
        assert "unavailable:sensor.gateway" in hass.stores["alert_manager"]["alerts"]

        unknown_state = hass.states.set("sensor.gateway", "unknown")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "sensor.gateway",
                    "old_state": unavailable_state,
                    "new_state": unknown_state,
                }
            )
        )
        release_first_write.set()
        await reconciliation_task

        active_timers = [
            timer
            for timer in hass.timers
            if not timer["cancelled"]
            and "_schedule_startup_reconciliation" in timer["action"].__qualname__
        ]
        assert save_calls == 3
        assert restarted.records == {}
        assert hass.stores["alert_manager"] == before_store
        assert restarted._runtime_phase is RuntimePhase.STARTUP_GRACE
        assert restarted._startup_reconciliation_snapshot is None
        assert restarted._startup_reconciliation_transaction is None
        assert len(active_timers) == 1

        restarted.storage.async_save = original_save
        await restarted.async_unload()

    asyncio.run(scenario())


def test_cancelled_compensation_still_cleans_and_rearms(hass, entry):
    """Cancellation reported by compensation cannot skip lifecycle cleanup."""

    async def scenario():
        hass.states.set("sensor.gateway", "ok")
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        await first.async_unload()
        before_store = deepcopy(hass.stores["alert_manager"])

        hass.state = CoreState.starting
        hass.states.set("sensor.gateway", "unavailable")
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        restarted._cancel_startup_reconciliation()
        restarted._startup_reconciliation_scheduled = True

        original_save = restarted.storage.async_save
        save_calls = 0

        async def cancelled_after_write(*args, **kwargs):
            nonlocal save_calls
            save_calls += 1
            await original_save(*args, **kwargs)
            if save_calls == 1:
                raise RuntimeError("failed after speculative write")
            raise asyncio.CancelledError

        restarted.storage.async_save = cancelled_after_write
        with pytest.raises(asyncio.CancelledError):
            await restarted._async_finish_startup_reconciliation()

        active_timers = [
            timer
            for timer in hass.timers
            if not timer["cancelled"]
            and "_schedule_startup_reconciliation" in timer["action"].__qualname__
        ]
        assert save_calls == 2
        assert restarted.records == {}
        assert hass.stores["alert_manager"] == before_store
        assert restarted._runtime_phase is RuntimePhase.STARTUP_GRACE
        assert restarted._startup_reconciliation_snapshot is None
        assert restarted._startup_reconciliation_transaction is None
        assert restarted._startup_reconciliation_scheduled is False
        assert len(active_timers) == 1

        restarted.storage.async_save = original_save
        await restarted.async_unload()

    asyncio.run(scenario())


def test_restore_failure_still_cleans_and_rearms(hass, entry):
    """A defensive rollback failure cannot leave reconciliation half-open."""

    async def scenario():
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        await first.async_unload()

        hass.state = CoreState.starting
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        restarted._cancel_startup_reconciliation()
        restarted._startup_reconciliation_scheduled = True
        original_evaluate_all = restarted.async_evaluate_all
        original_restore = restarted._restore_configuration_snapshot

        async def failed_evaluation(**_kwargs):
            raise RuntimeError("evaluation failed")

        def failed_restore(_snapshot):
            raise RuntimeError("restore failed")

        restarted.async_evaluate_all = failed_evaluation
        restarted._restore_configuration_snapshot = failed_restore
        await restarted._async_finish_startup_reconciliation()

        active_timers = [
            timer
            for timer in hass.timers
            if not timer["cancelled"]
            and "_schedule_startup_reconciliation" in timer["action"].__qualname__
        ]
        assert restarted._runtime_phase is RuntimePhase.STARTUP_GRACE
        assert restarted._startup_reconciliation_snapshot is None
        assert restarted._startup_reconciliation_transaction is None
        assert restarted._startup_reconciliation_scheduled is False
        assert len(active_timers) == 1

        restarted.async_evaluate_all = original_evaluate_all
        restarted._restore_configuration_snapshot = original_restore
        await restarted.async_unload()

    asyncio.run(scenario())


def test_cancelled_config_before_transaction_keeps_restored_snapshot(hass, entry):
    """Cancellation before lock admission cannot mutate restored state."""

    async def scenario():
        hass.states.set("binary_sensor.filter", "on")
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        rule = await first.async_create_rule(
            {
                "name": "Filter active",
                "entity_ids": ["binary_sensor.filter"],
                "operator": "equals",
                "value": "on",
                "duration": 3600,
            }
        )
        alert_id = f"rule:{rule['id']}:binary_sensor.filter"
        await first.async_unload()

        hass.state = CoreState.starting
        hass.states.set("binary_sensor.filter", "unknown")
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True
        await _start_and_reconcile(restarted, hass)
        assert alert_id in restarted._unverified_restored_alert_ids

        before_config = restarted.get_config()
        before_records = deepcopy(restarted.records)
        before_provenance = set(restarted._unverified_restored_alert_ids)
        before_store = deepcopy(hass.stores["alert_manager"])
        await restarted._config_mutation_lock.acquire()
        update_task = asyncio.create_task(
            restarted.async_update_config(
                {"pending_display_delay": before_config["pending_display_delay"] + 1}
            )
        )
        await asyncio.sleep(0)
        assert not update_task.done()
        update_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await update_task
        restarted._config_mutation_lock.release()

        assert restarted.get_config() == before_config
        assert restarted.records == before_records
        assert restarted._unverified_restored_alert_ids == before_provenance

        await restarted.async_unload()
        assert hass.stores["alert_manager"] == before_store

    asyncio.run(scenario())


def test_cancelled_setup_unload_compensates_inflight_reconciliation(hass, entry):
    """Unload drains startup mutation and rewrites its rolled-back snapshot."""

    async def scenario():
        hass.states.set("sensor.gateway", "on")
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        await first.async_unload()
        before_store = deepcopy(hass.stores["alert_manager"])

        hass.states.set("sensor.gateway", "unavailable")
        restarted = AlertManager(hass, entry)
        setup_waiting = asyncio.Event()
        hold_setup = asyncio.Event()

        async def blocked_backup_initialization():
            setup_waiting.set()
            await hold_setup.wait()

        restarted._async_initialize_config_backups = blocked_backup_initialization
        setup_task = asyncio.create_task(restarted.async_setup())
        await setup_waiting.wait()
        assert restarted._runtime_phase is RuntimePhase.STARTUP_GRACE
        assert restarted._persistence_ready is True

        original_save = restarted.storage.async_save
        save_started = asyncio.Event()
        release_save = asyncio.Event()
        save_calls = 0

        async def blocked_save(*args, **kwargs):
            nonlocal save_calls
            save_calls += 1
            if save_calls == 1:
                save_started.set()
                await release_save.wait()
            await original_save(*args, **kwargs)

        restarted.storage.async_save = blocked_save
        _fire_startup_reconciliation(hass)
        await save_started.wait()
        assert "unavailable:sensor.gateway" in restarted.records

        setup_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await setup_task

        unload_task = asyncio.create_task(restarted.async_unload())
        await asyncio.sleep(0)
        assert not unload_task.done()
        assert restarted._runtime_phase is RuntimePhase.STOPPING

        release_save.set()
        await unload_task
        await _settle()

        assert save_calls == 3
        assert hass.stores["alert_manager"] == before_store
        assert restarted.records == {}
        assert restarted._startup_reconciliation_scheduled is False
        assert not [timer for timer in hass.timers if not timer["cancelled"]]

    asyncio.run(scenario())


def test_cancelled_unload_waits_for_reconciliation_and_compensates(hass, entry):
    """Caller cancellation cannot skip the final compensating Store write."""

    async def scenario():
        hass.states.set("sensor.gateway", "on")
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        await first.async_unload()
        before_store = deepcopy(hass.stores["alert_manager"])

        hass.states.set("sensor.gateway", "unavailable")
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True

        original_save = restarted.storage.async_save
        save_started = asyncio.Event()
        release_save = asyncio.Event()
        save_calls = 0

        async def blocked_save(*args, **kwargs):
            nonlocal save_calls
            save_calls += 1
            if save_calls == 1:
                save_started.set()
                await release_save.wait()
            await original_save(*args, **kwargs)

        restarted.storage.async_save = blocked_save
        _fire_startup_reconciliation(hass)
        await save_started.wait()
        assert "unavailable:sensor.gateway" in restarted.records

        unload_task = asyncio.create_task(restarted.async_unload())
        await asyncio.sleep(0)
        assert not unload_task.done()
        assert restarted._runtime_phase is RuntimePhase.STOPPING

        unload_task.cancel()
        await asyncio.sleep(0)
        assert not unload_task.done()

        release_save.set()
        with pytest.raises(asyncio.CancelledError):
            await unload_task
        await _settle()

        assert save_calls == 3
        assert hass.stores["alert_manager"] == before_store
        assert restarted.records == {}
        assert restarted._unsubscribers == []
        assert restarted._startup_reconciliation_scheduled is False
        assert not [timer for timer in hass.timers if not timer["cancelled"]]

    asyncio.run(scenario())
