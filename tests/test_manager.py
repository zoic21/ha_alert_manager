"""Alert Manager lifecycle, detection, persistence and exclusion tests."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, Event
from homeassistant.util import dt as dt_util

from custom_components.alert_manager.const import (
    ALERT_MANAGER_ENTITY_IDS,
    DATA_MANAGER,
    EVENT_ALERT_RESOLVED,
    EVENT_ALERT_STARTED,
    EVENT_DEVICE_ALERT_STARTED,
    MAX_RULES,
    SIGNAL_ALERTS_UPDATED,
    SIGNAL_NOTIFICATION_LIFECYCLE,
    STARTUP_RECONCILIATION_DELAY_SECONDS,
)
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import (
    AlertDetails,
    AlertRecord,
    AlertStatus,
    Rule,
)
from custom_components.alert_manager.runtime_phase import RuntimePhase
from custom_components.alert_manager.sensor import (
    AlertManagerCoherenceIssueSensor,
    AlertManagerSensor,
    _bounded_attributes,
    _compact_alert,
)
from custom_components.alert_manager.sensor import (
    async_setup_entry as async_setup_sensor,
)
from custom_components.alert_manager.transactions import (
    StartupReconciliationTransaction,
)


def run(coroutine):
    return asyncio.run(coroutine)


def make_manager(hass, entry):
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    return manager


def test_rule_creation_respects_the_configuration_limit(hass, entry):
    """The dedicated create API cannot bypass the complete-config rule limit."""
    manager = make_manager(hass, entry)
    manager.config["rules"] = [
        Rule(
            id=f"rule-{index}",
            name=f"Rule {index}",
            entity_ids=["sensor.test"],
            operator="equals",
            value="on",
            duration=0,
        ).as_dict()
        for index in range(MAX_RULES)
    ]

    with pytest.raises(ValueError, match=f"at most {MAX_RULES}"):
        run(
            manager.async_create_rule(
                {
                    "name": "One rule too many",
                    "entity_ids": ["sensor.test"],
                    "operator": "equals",
                    "value": "on",
                    "duration": 0,
                }
            )
        )


def assert_record_index(manager):
    """Assert the entity lookup cache is derived exactly from live records."""
    expected = {}
    for alert_id, record in manager.records.items():
        expected.setdefault(record.details.entity_id, set()).add(alert_id)
    assert manager._record_ids_by_entity == expected


def published_alert_state(manager):
    """Describe one publication without exposing a mutable snapshot reference."""
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


def fire_device_event_timers(hass):
    """Run every pending 10-second device-event debounce timer."""
    for timer in list(hass.timers):
        if timer["cancelled"]:
            continue
        if "_schedule_device_event_timer" not in timer["action"].__qualname__:
            continue
        timer["action"](timer["point"])


def fire_startup_reconciliation(hass):
    """Run the one-shot reconciliation after startup values settle."""
    timer = next(
        timer
        for timer in hass.timers
        if not timer["cancelled"]
        and "_schedule_startup_reconciliation" in timer["action"].__qualname__
    )
    timer["cancelled"] = True
    timer["action"](timer["point"])


def begin_shutdown(hass):
    """Run registered shutdown jobs before Home Assistant unloads integrations."""
    for hassjob, args in tuple(hass.shutdown_jobs):
        hassjob.job(*args)


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

        fire_startup_reconciliation(hass)
        assert manager._last_public_snapshot["startup"] == {
            "in_progress": True,
            "stabilization_until": None,
        }
        assert len(updates) == 2
        for _index in range(4):
            await asyncio.sleep(0)
        assert manager._last_public_snapshot["startup"] == {
            "in_progress": False,
            "stabilization_until": None,
        }
        assert len(updates) == 3

    run(scenario())


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
        assert not transaction.current_alert_ids_for_originals(
            {ids[restored_side]}, manager.records
        )

    run(scenario())


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

    run(scenario())


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

    run(scenario())


def test_creation_of_partitioned_sensors(hass, entry, registry_entry):
    """The sensor platform exposes alert partitions and coherence issues."""
    registry_entry(
        hass,
        "sensor.legacy_alerts",
        platform="alert_manager",
        unique_id="alert_manager",
    )
    manager = make_manager(hass, entry)
    hass.data[DATA_MANAGER] = manager
    entities = []
    run(async_setup_sensor(hass, entry, entities.extend))
    assert len(entities) == 5
    partition_sensors = [
        entity for entity in entities if isinstance(entity, AlertManagerSensor)
    ]
    coherence_sensor = next(
        entity
        for entity in entities
        if isinstance(entity, AlertManagerCoherenceIssueSensor)
    )
    assert len(partition_sensors) == 4
    assert {entity.entity_id for entity in entities} == {
        "sensor.alert_manager_coherence_issue",
        "sensor.alert_manager_main_active",
        "sensor.alert_manager_main_pending",
        "sensor.alert_manager_main_acknowledge",
        "sensor.alert_manager_device_main_active",
    }
    assert {entity._attr_unique_id for entity in entities} == {
        "alert_manager_coherence_issue",
        "alert_manager_main_active",
        "alert_manager_main_pending",
        "alert_manager_main_acknowledge",
        "alert_manager_device_main_active",
    }
    assert all(entity.native_value == 0 for entity in partition_sensors)
    assert coherence_sensor.native_value is None
    assert {
        entity.entity_id: entity.extra_state_attributes for entity in partition_sensors
    } == {
        "sensor.alert_manager_main_active": {
            "alerts": [],
            "history_revision": 0,
            "alerts_revision": 0,
            "runtime": {
                "tracked_count": 0,
                "startup": {
                    "in_progress": False,
                    "stabilization_until": None,
                },
            },
        },
        "sensor.alert_manager_main_pending": {"alerts": [], "alerts_revision": 0},
        "sensor.alert_manager_main_acknowledge": {"alerts": [], "alerts_revision": 0},
        "sensor.alert_manager_device_main_active": {"devices": []},
    }
    assert all(
        entity._attr_device_info["identifiers"] == {("alert_manager", "main")}
        for entity in entities
    )
    assert "sensor.legacy_alerts" not in hass.entity_registry.entries


def test_normal_to_pending_and_no_duplicate(hass, entry):
    """A first-install anomaly starts pending and repeated evaluation is idempotent."""
    hass.states.set("sensor.unas", "unavailable", {"friendly_name": "UNAS"})
    manager = make_manager(hass, entry)
    assert set(manager.records) == {"unavailable:sensor.unas"}
    assert manager.records["unavailable:sensor.unas"].status is AlertStatus.PENDING
    assert_record_index(manager)
    run(manager.async_evaluate_entity("sensor.unas"))
    assert len(manager.records) == 1
    assert_record_index(manager)


def test_record_index_avoids_full_scans_for_one_entity_evaluation(hass, entry):
    """State routing and evaluation use the entity cache, not all records."""

    class NoFullScanRecords(dict):
        def items(self):
            raise AssertionError("entity evaluation scanned every record")

        def values(self):
            raise AssertionError("state routing scanned every record")

    hass.states.set("sensor.unas", "unavailable")
    manager = make_manager(hass, entry)
    manager.records = NoFullScanRecords(manager.records)

    assert manager._state_event_affects_source(Event(), "sensor.unas") is True
    run(
        manager.async_evaluate_entity(
            "sensor.unas",
            save=False,
            publish=False,
        )
    )
    assert manager._record_ids_by_entity == {"sensor.unas": {"unavailable:sensor.unas"}}


def test_matching_updates_keep_the_original_trigger_value(hass, entry):
    """A still-abnormal value cannot overwrite the occurrence trigger snapshot."""
    hass.states.set("sensor.temperature", "11")
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "High temperature",
                "entity_ids": ["sensor.temperature"],
                "operator": "above",
                "value": 10,
                "duration": 900,
                "source": "state",
            }
        )
    )
    alert_id = f"rule:{rule['id']}:sensor.temperature"
    assert manager.records[alert_id].details.value == "11"

    hass.states.set("sensor.temperature", "12")
    run(manager.async_evaluate_entity("sensor.temperature"))

    assert manager.records[alert_id].details.value == "11"


def test_pending_cancellation(hass, entry):
    """A recovered condition before due_at returns to normal without an event."""
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)
    hass.states.set("sensor.test", "20")
    run(manager.async_evaluate_entity("sensor.test"))
    assert manager.records == {}
    assert_record_index(manager)
    assert not [item for item in hass.bus.fired if item[0] == EVENT_ALERT_RESOLVED]


def test_pending_to_active(hass, entry, set_now):
    """A still-true condition becomes active exactly when due."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)
    set_now(start + timedelta(seconds=900))
    run(manager.async_evaluate_entity("sensor.test"))
    record = manager.records["unavailable:sensor.test"]
    assert record.status is AlertStatus.ACTIVE
    assert record.active_since == record.due_at


def test_pending_alert_is_exposed_after_configured_display_delay(
    hass, entry, set_now, registry_entry, device_entry
):
    """Only the transient pending row waits for the presentation deadline."""
    start = datetime(2026, 8, 27, 10, tzinfo=UTC)
    set_now(start)
    device = device_entry(hass, name="Onduleur")
    registry_entry(hass, "sensor.ups", device_id=device.id)
    hass.states.set("sensor.ups", "unavailable")
    manager = make_manager(hass, entry)
    run(manager.async_update_config({"entity_delays": {"sensor.ups": 30}}))
    record = manager.records["unavailable:sensor.ups"]
    assert record.status is AlertStatus.PENDING
    assert record.visible_at == start + timedelta(seconds=10)
    assert manager.public_snapshot()["pending_count"] == 0

    set_now(start + timedelta(seconds=10))
    run(manager.async_evaluate_entity("sensor.ups"))
    assert manager.public_snapshot()["active_count"] == 0
    assert manager.public_snapshot()["pending_count"] == 1
    assert not [
        event for event, _data in hass.bus.fired if event == EVENT_DEVICE_ALERT_STARTED
    ]

    set_now(start + timedelta(seconds=30))
    run(manager.async_evaluate_entity("sensor.ups"))
    snapshot = manager.public_snapshot()
    assert record.status is AlertStatus.ACTIVE
    assert record.visible_at is None
    assert snapshot["active_count"] == 1
    assert snapshot["pending_count"] == 0
    assert snapshot["device_active_count"] == 1
    assert snapshot["active_devices"][0]["device_name"] == "Onduleur"
    assert snapshot["active_devices"][0]["alert_ids"] == ["unavailable:sensor.ups"]
    fire_device_event_timers(hass)
    events = [
        data for event, data in hass.bus.fired if event == EVENT_DEVICE_ALERT_STARTED
    ]
    assert len(events) == 1
    assert events[0]["device_ids"] == [device.id]
    assert "device_id" not in events[0]


def test_short_rule_delay_skips_pending_display_before_active(hass, entry, set_now):
    """A short rule becomes active without briefly exposing a pending row."""
    start = datetime(2026, 8, 27, 10, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "on")
    manager = make_manager(hass, entry)
    run(manager.async_update_config({"pending_display_delay": 10}))
    rule = run(
        manager.async_create_rule(
            {
                "name": "Short rule",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "on",
                "duration": 5,
            }
        )
    )
    record = manager.records[f"rule:{rule['id']}:sensor.test"]
    assert record.visible_at == start + timedelta(seconds=5)
    assert manager.public_snapshot()["pending_count"] == 0

    set_now(start + timedelta(seconds=5))
    run(manager.async_evaluate_entity("sensor.test"))
    assert record.visible_at is None
    assert manager.public_snapshot()["active_count"] == 1


def test_transient_pending_alert_never_reaches_public_lists(hass, entry, set_now):
    """A flapping condition that clears within ten seconds stays invisible."""
    start = datetime(2026, 8, 27, 10, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)

    for offset in (2, 6):
        set_now(start + timedelta(seconds=offset))
        hass.states.set("sensor.test", "ok")
        run(manager.async_evaluate_entity("sensor.test"))
        snapshot = manager.public_snapshot()
        assert snapshot["pending_count"] == 0
        assert snapshot["active_count"] == 0
        if offset == 2:
            set_now(start + timedelta(seconds=4))
            hass.states.set("sensor.test", "unavailable")
            run(manager.async_evaluate_entity("sensor.test"))

    assert not [
        event for event, _data in hass.bus.fired if event == EVENT_DEVICE_ALERT_STARTED
    ]


def test_pending_timer_runs_on_home_assistant_event_loop(hass, entry, set_now):
    """Timer jobs stay on the HA loop before creating config-entry tasks."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)
    timer = min(
        (timer for timer in hass.timers if not timer["cancelled"]),
        key=lambda item: item["point"],
    )
    assert timer["action"]._hass_callback is True

    async def fire_timer():
        set_now(start + timedelta(seconds=900))
        timer["action"](start + timedelta(seconds=900))
        await asyncio.sleep(0)

    run(fire_timer())
    record = manager.records["unavailable:sensor.test"]
    assert record.status is AlertStatus.ACTIVE
    assert entry.created_task_names == ["alert_manager state-change batch"]


def test_active_resolution_and_events(hass, entry, set_now):
    """Started/resolved events contain the structured documented timestamps."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable", {"friendly_name": "Test"})
    manager = make_manager(hass, entry)
    set_now(start + timedelta(seconds=901))
    run(manager.async_evaluate_entity("sensor.test"))
    hass.states.set("sensor.test", "ok")
    set_now(start + timedelta(seconds=1000))
    run(manager.async_evaluate_entity("sensor.test"))
    assert manager.records == {}
    started = [data for event, data in hass.bus.fired if event == EVENT_ALERT_STARTED]
    resolved = [data for event, data in hass.bus.fired if event == EVENT_ALERT_RESOLVED]
    assert len(started) == len(resolved) == 1
    assert started[0]["id"] == "unavailable:sensor.test"
    assert started[0]["condition"] == "État indisponible"
    assert started[0]["message"] == "État indisponible"
    assert started[0]["condition_key"] == "automatic.unavailable"
    assert started[0]["condition_params"] == {}
    assert "severity" not in started[0]
    assert "severity" not in resolved[0]
    assert "active_since" in started[0]
    assert "resolved_at" in resolved[0]


@pytest.mark.parametrize("delay", [0, 15 * 60])
def test_shutdown_discards_queued_unavailable_transition(hass, entry, delay):
    """A delayed worker cannot manufacture an outage after shutdown begins."""

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

        begin_shutdown(hass)
        hass.state = CoreState.stopping
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        alert_id = "unavailable:event.baby"
        assert manager._runtime_phase is RuntimePhase.STOPPING
        assert alert_id not in manager.records
        await manager.async_unload()
        assert alert_id not in hass.stores["alert_manager"]["alerts"]

    run(scenario())


def test_shutdown_cancels_registry_and_device_callbacks(
    hass, entry, registry_entry, device_entry
):
    """Registry and debounce callbacks are inert once shutdown has begun."""

    async def scenario():
        device = device_entry(hass, name="Baby")
        registry_entry(hass, "sensor.old", device_id=device.id)
        hass.states.set("sensor.old", "unavailable")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        await manager.async_update_config({"entity_delays": {"sensor.old": 0}})
        alert_id = "unavailable:sensor.old"
        assert manager.records[alert_id].status is AlertStatus.ACTIVE
        device_timer = next(
            timer
            for timer in hass.timers
            if not timer["cancelled"]
            and "_schedule_device_event_timer" in timer["action"].__qualname__
        )

        begin_shutdown(hass)
        hass.state = CoreState.stopping
        manager._registry_changed(
            Event(
                {
                    "action": "update",
                    "old_entity_id": "sensor.old",
                    "entity_id": "sensor.new",
                }
            )
        )
        device_timer["action"](device_timer["point"])
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert set(manager.records) == {alert_id}
        assert device_timer["cancelled"] is True
        assert not [
            event
            for event, _data in hass.bus.fired
            if event == EVENT_DEVICE_ALERT_STARTED
        ]

    run(scenario())


def test_unload_cleans_every_resource_when_final_save_fails(hass, entry):
    """A Store failure cannot leave a detached manager running in the background."""

    async def scenario():
        hass.states.set("sensor.test", "unavailable")
        manager = AlertManager(hass, entry)
        await manager.async_setup()

        async def failed_save(*_args, **_kwargs):
            raise OSError("disk unavailable")

        manager.storage.async_save = failed_save
        await manager.async_unload()

        assert manager._runtime_phase is RuntimePhase.STOPPING
        assert manager._unsubscribers == []
        assert manager._pack_entry_unsubscribers == {}
        assert manager.notification_runtime._unsubscribe == []
        assert hass.shutdown_jobs == []
        assert not any(hass.bus.listeners.values())
        assert not hass.dispatchers[SIGNAL_NOTIFICATION_LIFECYCLE]
        assert not [timer for timer in hass.timers if not timer["cancelled"]]

    run(scenario())


def test_cancelled_unload_still_cleans_every_runtime_resource(hass, entry):
    """Cancellation during the final Store write cannot skip teardown."""

    async def scenario():
        hass.states.set("sensor.test", "unavailable")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        save_started = asyncio.Event()
        release_save = asyncio.Event()

        async def blocked_save(*_args, **_kwargs):
            save_started.set()
            await release_save.wait()

        manager.storage.async_save = blocked_save
        unload_task = asyncio.create_task(manager.async_unload())
        await save_started.wait()
        unload_task.cancel()
        await asyncio.sleep(0)
        assert not unload_task.done()
        release_save.set()
        with pytest.raises(asyncio.CancelledError):
            await unload_task

        assert manager._runtime_phase is RuntimePhase.STOPPING
        assert manager._unsubscribers == []
        assert manager._pack_entry_unsubscribers == {}
        assert manager.notification_runtime._unsubscribe == []
        assert hass.shutdown_jobs == []
        assert not any(hass.bus.listeners.values())
        assert not hass.dispatchers[SIGNAL_NOTIFICATION_LIFECYCLE]
        assert not [timer for timer in hass.timers if not timer["cancelled"]]

    run(scenario())


def test_startup_transition_during_setup_cannot_strand_reconciliation(
    hass, entry, set_now
):
    """Becoming running during setup still starts exactly one bounded grace."""
    start = datetime(2026, 9, 4, 17, 50, 27, tzinfo=UTC)
    set_now(start)

    async def scenario():
        hass.states.set("event.baby", "unavailable")
        first = AlertManager(hass, entry)
        await first.async_setup()
        set_now(start + timedelta(minutes=6))
        await first._async_flush_mature_pending()
        await first.async_unload()

        hass.state = CoreState.starting
        hass.states.set("event.baby", "unknown")
        restarted = AlertManager(hass, entry)
        load_translations = restarted._async_load_condition_translations

        async def load_translations_while_starting_finishes():
            await load_translations()
            hass.state = CoreState.running

        restarted._async_load_condition_translations = (
            load_translations_while_starting_finishes
        )
        await restarted.async_setup()

        assert restarted._runtime_phase is RuntimePhase.STARTUP_GRACE
        assert restarted._startup_reconciliation_timer is not None
        assert restarted.public_snapshot()["pending_count"] == 0

        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        alert_id = "unavailable:event.baby"
        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert alert_id not in restarted.records
        assert alert_id not in hass.stores["alert_manager"]["alerts"]

    run(scenario())


def test_setup_reaching_final_write_never_arms_runtime(hass, entry):
    """A setup that misses the shutdown hook still observes terminal core state."""

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

    run(scenario())


def test_unload_while_setup_is_loading_cannot_add_late_listeners(hass, entry):
    """An explicit unload closes setup before any later resource registration."""

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
        await manager.async_unload()
        release_setup.set()

        assert await setup_task is False
        assert manager._unsubscribers == []
        assert hass.shutdown_jobs == []
        assert not any(hass.bus.listeners.values())
        assert not any(hass.dispatchers.values())
        assert not [timer for timer in hass.timers if not timer["cancelled"]]

    run(scenario())


def test_started_during_migration_save_cannot_be_missed(hass, entry):
    """The STARTED listener is armed before setup performs Store I/O."""

    async def scenario():
        hass.state = CoreState.starting
        manager = AlertManager(hass, entry)
        original_load = manager.storage.async_load
        original_save = manager.storage.async_save
        save_started = asyncio.Event()
        release_save = asyncio.Event()

        async def migrated_load():
            config, records, _migrated = await original_load()
            return config, records, True

        async def blocked_save(*args, **kwargs):
            save_started.set()
            await release_save.wait()
            await original_save(*args, **kwargs)

        manager.storage.async_load = migrated_load
        manager.storage.async_save = blocked_save
        setup_task = asyncio.create_task(manager.async_setup())
        await save_started.wait()

        started_listeners = hass.bus.listeners[EVENT_HOMEASSISTANT_STARTED]
        assert started_listeners
        hass.state = CoreState.running
        for listener in tuple(started_listeners):
            listener(Event())
        release_save.set()

        assert await setup_task is True
        assert manager._runtime_phase is RuntimePhase.STARTUP_GRACE
        assert manager._startup_reconciliation_timer is not None
        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert manager._runtime_phase is RuntimePhase.RUNNING

    run(scenario())


def test_shutdown_during_notification_setup_leaves_no_runtime(hass, entry):
    """Notification setup cannot subscribe or schedule work after unload starts."""

    async def scenario():
        manager = AlertManager(hass, entry)
        runtime_load_started = asyncio.Event()
        release_runtime_load = asyncio.Event()

        async def blocked_runtime_load():
            runtime_load_started.set()
            await release_runtime_load.wait()

        manager.notification_runtime._async_load_runtime = blocked_runtime_load
        setup_task = asyncio.create_task(manager.async_setup())
        await runtime_load_started.wait()

        begin_shutdown(hass)
        hass.state = CoreState.stopping
        unload_task = asyncio.create_task(manager.async_unload())
        await asyncio.sleep(0)
        release_runtime_load.set()
        await asyncio.gather(setup_task, unload_task)

        assert manager._runtime_phase is RuntimePhase.STOPPING
        assert manager.notification_runtime._unsubscribe == []
        assert not hass.dispatchers[SIGNAL_NOTIFICATION_LIFECYCLE]
        assert not [timer for timer in hass.timers if not timer["cancelled"]]

    run(scenario())


def test_recovery_during_inflight_save_is_persisted_after_the_save(
    hass, entry, set_now
):
    """A stale save cannot overwrite a newer unavailable recovery."""
    start = datetime(2026, 9, 4, 17, 50, 27, tzinfo=UTC)
    set_now(start)

    async def scenario():
        unavailable_state = hass.states.set("event.baby", "unavailable")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        set_now(start + timedelta(minutes=6))
        await manager._async_flush_mature_pending()

        save_started = asyncio.Event()
        release_save = asyncio.Event()
        original_save = manager.storage.async_save
        first_call = True

        async def blocked_save(*args, **kwargs):
            nonlocal first_call
            if first_call:
                first_call = False
                save_started.set()
                await release_save.wait()
            await original_save(*args, **kwargs)

        manager.storage.async_save = blocked_save
        save_task = asyncio.create_task(manager._async_flush_mature_pending())
        await save_started.wait()

        unknown_state = hass.states.set("event.baby", "unknown")
        manager._state_changed(
            Event(
                {
                    "entity_id": "event.baby",
                    "old_state": unavailable_state,
                    "new_state": unknown_state,
                }
            )
        )
        assert "unavailable:event.baby" in manager.records

        release_save.set()
        await save_task
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        alert_id = "unavailable:event.baby"
        assert alert_id not in manager.records
        assert manager.public_snapshot()["pending_count"] == 0
        assert alert_id not in hass.stores["alert_manager"]["alerts"]

    run(scenario())


def test_state_change_during_startup_reconciliation_save_precedes_first_publish(
    hass, entry, set_now
):
    """A recovery during the Store write is folded into the startup snapshot."""
    start = datetime(2026, 9, 4, 17, 50, 27, tzinfo=UTC)
    set_now(start)

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
        fire_startup_reconciliation(hass)
        await save_started.wait()
        assert restarted._runtime_phase is RuntimePhase.RECONCILING
        assert "unavailable:event.baby" in restarted.records
        assert restarted.public_snapshot()["pending_count"] == 0

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
        release_save.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        alert_id = "unavailable:event.baby"
        assert alert_id not in restarted.records
        assert alert_id not in hass.stores["alert_manager"]["alerts"]
        assert restarted.public_snapshot()["pending_count"] == 0

    run(scenario())


def test_state_change_during_startup_scan_is_reconciled_before_publish(hass, entry):
    """The final live value wins even when it changes after its scan turn."""

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
        fire_startup_reconciliation(hass)
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
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        alert_id = "unavailable:event.baby"
        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert alert_id not in restarted.records
        assert alert_id not in hass.stores["alert_manager"]["alerts"]
        assert restarted.public_snapshot()["pending_count"] == 0

    run(scenario())


def test_shutdown_during_startup_reconciliation_cannot_reopen_runtime(hass, entry):
    """A Store write completing after shutdown cannot return to RUNNING."""

    async def scenario():
        hass.states.set("event.baby", "idle")
        first = AlertManager(hass, entry)
        await first.async_setup()
        await first.async_unload()

        hass.state = CoreState.starting
        hass.states.set("event.baby", "unavailable")
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())

        save_started = asyncio.Event()
        release_save = asyncio.Event()
        original_save = restarted.storage.async_save

        async def blocked_save(*args, **kwargs):
            save_started.set()
            await release_save.wait()
            await original_save(*args, **kwargs)

        restarted.storage.async_save = blocked_save
        fire_startup_reconciliation(hass)
        await save_started.wait()

        begin_shutdown(hass)
        hass.state = CoreState.stopping
        release_save.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert restarted._runtime_phase is RuntimePhase.STOPPING
        assert [
            timer["action"].__qualname__
            for timer in hass.timers
            if not timer["cancelled"]
        ] == []

    run(scenario())


def test_startup_owner_enters_reconciling_only_after_acquiring_lock(hass, entry):
    """A pre-queued side worker cannot mutate the restored startup snapshot."""

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
        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)

        assert restarted._runtime_phase is RuntimePhase.STARTUP_GRACE
        assert restarted._startup_reconciliation_scheduled is True

        restarted._config_mutation_lock.release()
        await side_worker
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert restarted._registry_evaluation_dirty is False
        assert restarted._startup_reconciliation_scheduled is False

    run(scenario())


def test_transient_startup_outage_is_private_until_transaction_commits(hass, entry):
    """Speculative alerts cannot reach snapshots, notifications or lifecycle."""

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
        fire_startup_reconciliation(hass)
        await active_created.wait()

        assert restarted._runtime_phase is RuntimePhase.RECONCILING
        assert restarted.public_snapshot()["active_count"] == 0
        assert restarted.public_snapshot()["pending_count"] == 0
        assert restarted.notification_runtime._records_getter() == {}
        assert not [
            event
            for event, _data in hass.bus.fired
            if event in (EVENT_ALERT_STARTED, EVENT_ALERT_RESOLVED)
        ]

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
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert "unavailable:event.baby" not in restarted.records
        assert restarted.history == []
        assert restarted._pending_history == []
        assert not [
            event
            for event, _data in hass.bus.fired
            if event in (EVENT_ALERT_STARTED, EVENT_ALERT_RESOLVED)
        ]

    run(scenario())


def test_registry_rename_and_pack_change_during_scan_are_committed(hass, entry):
    """Registry and pack dirties force a stable second authoritative scan."""

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

        first_scan = asyncio.Event()
        release_scan = asyncio.Event()
        renamed_scan = asyncio.Event()
        original_evaluate = restarted.async_evaluate_entity
        original_replace = restarted._replace_pack_availability_snapshot
        refresh_count = 0
        blocked_once = False

        async def blocked_evaluate(entity_id, **kwargs):
            nonlocal blocked_once
            changed = await original_evaluate(entity_id, **kwargs)
            if entity_id == "binary_sensor.old_filter" and not blocked_once:
                blocked_once = True
                first_scan.set()
                await release_scan.wait()
            elif entity_id == "binary_sensor.new_filter":
                renamed_scan.set()
            return changed

        def counted_replace():
            nonlocal refresh_count
            refresh_count += 1
            return original_replace()

        restarted.async_evaluate_entity = blocked_evaluate
        restarted._replace_pack_availability_snapshot = counted_replace
        fire_startup_reconciliation(hass)
        await first_scan.wait()

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
        restarted._schedule_pack_availability_refresh()
        assert restarted.get_config()["rules"][0]["entity_ids"] == [
            "binary_sensor.old_filter"
        ]
        release_scan.set()
        await renamed_scan.wait()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        alert_id = f"rule:{rule['id']}:binary_sensor.new_filter"
        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert restarted.config["rules"][0]["entity_ids"] == [
            "binary_sensor.new_filter"
        ]
        assert restarted.records[alert_id].status is AlertStatus.ACTIVE
        assert hass.stores["alert_manager"]["config"]["rules"][0]["entity_ids"] == [
            "binary_sensor.new_filter"
        ]
        assert refresh_count == 1
        assert restarted._registry_evaluation_dirty is False
        assert restarted._pack_refresh_dirty is False
        assert not [
            event
            for event, _data in hass.bus.fired
            if event in (EVENT_ALERT_STARTED, EVENT_ALERT_RESOLVED)
        ]

    run(scenario())


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
            published_states.append(published_alert_state(restarted))

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
        fire_startup_reconciliation(hass)
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
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert restarted.records[alert_id].status is AlertStatus.ACTIVE
        assert hass.stores["alert_manager"]["alerts"][alert_id]["status"] == "active"
        assert published_states == [
            (RuntimePhase.STARTUP_GRACE, True, {alert_id: "active"}),
            (RuntimePhase.STARTUP_GRACE, True, {alert_id: "active"}),
            (RuntimePhase.RUNNING, False, {alert_id: "active"}),
        ]

    run(scenario())


def test_reconciliation_rechecks_pending_due_crossed_during_store(hass, entry, set_now):
    """A Store write cannot make the first committed alert status stale."""
    start = datetime(2026, 9, 4, 12, tzinfo=UTC)
    set_now(start)

    async def scenario():
        entity_id = "binary_sensor.pool_filter"
        hass.states.set(entity_id, "on", {"friendly_name": "Pool filter"})
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        rule = await first.async_create_rule(
            {
                "name": "Pool filtration",
                "entity_ids": [entity_id],
                "operator": "equals",
                "value": "on",
                "duration": 10 * 60,
            }
        )
        alert_id = f"rule:{rule['id']}:{entity_id}"
        due_at = first.records[alert_id].due_at
        set_now(start + timedelta(minutes=6))
        await first._async_flush_mature_pending()
        assert alert_id in hass.stores["alert_manager"]["alerts"]
        await first.async_unload()
        hass.bus.fired.clear()

        hass.state = CoreState.starting
        set_now(due_at - timedelta(seconds=1))
        hass.states.set(entity_id, "on", {"friendly_name": "Renamed filter"})
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())

        published_states = []
        original_publish = restarted._publish_if_changed

        def capture_publish(*args, **kwargs):
            original_publish(*args, **kwargs)
            published_states.append(published_alert_state(restarted))

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
        fire_startup_reconciliation(hass)
        await save_started.wait()
        assert restarted.records[alert_id].status is AlertStatus.PENDING

        set_now(due_at + timedelta(seconds=1))
        release_save.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

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

    run(scenario())


def test_reconciliation_resolves_expired_deadline_before_first_publish(
    hass, entry, set_now
):
    """A restored deadline that expires during Store I/O is never published stale."""
    start = datetime(2026, 9, 4, 12, tzinfo=UTC)
    expires_at = start + timedelta(minutes=2)
    set_now(start)

    async def scenario():
        entity_id = "sensor.gateway"
        alert_id = f"flapping:unavailable:{entity_id}"
        hass.states.set(entity_id, "ok", {"friendly_name": "Gateway"})
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        await first.async_update_config({"automatic": {"flapping": {"enabled": True}}})
        first._set_record(
            AlertRecord.active_until(
                AlertDetails(
                    id=alert_id,
                    type="flapping",
                    entity_id=entity_id,
                    name="Gateway",
                    value=3,
                    condition="Flapping detected",
                    condition_key="automatic.flapping",
                    source=f"unavailable:{entity_id}",
                ),
                start,
                expires_at,
            )
        )
        first._immediate_state_save_required = True
        await first._async_save_state()
        await first.async_unload()

        hass.state = CoreState.starting
        set_now(expires_at - timedelta(seconds=1))
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        hass.bus.fired.clear()

        published_states = []
        original_publish = restarted._publish_if_changed

        def capture_publish(*args, **kwargs):
            original_publish(*args, **kwargs)
            published_states.append(published_alert_state(restarted))

        restarted._publish_if_changed = capture_publish
        save_started = asyncio.Event()
        release_save = asyncio.Event()
        second_save_started = asyncio.Event()
        release_second_save = asyncio.Event()
        original_save = restarted.storage.async_save
        save_calls = 0

        async def blocked_save(*args, **kwargs):
            nonlocal save_calls
            save_calls += 1
            if save_calls == 1:
                save_started.set()
                await release_save.wait()
            elif save_calls == 2:
                second_save_started.set()
                await release_second_save.wait()
            await original_save(*args, **kwargs)

        restarted.storage.async_save = blocked_save
        restarted._immediate_state_save_required = True
        fire_startup_reconciliation(hass)
        await save_started.wait()
        assert restarted.records[alert_id].status is AlertStatus.ACTIVE

        set_now(expires_at + timedelta(seconds=1))
        release_save.set()
        await second_save_started.wait()
        assert alert_id not in restarted.records
        restarted._queue_entity_evaluations((entity_id,))
        release_second_save.set()
        for _index in range(6):
            await asyncio.sleep(0)

        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert alert_id not in restarted.records
        assert alert_id not in hass.stores["alert_manager"]["alerts"]
        assert published_states == [
            (RuntimePhase.STARTUP_GRACE, True, {alert_id: "active"}),
            (RuntimePhase.RUNNING, False, {}),
        ]
        assert save_calls == 3
        assert [
            event for event, _data in hass.bus.fired if event == EVENT_ALERT_RESOLVED
        ] == [EVENT_ALERT_RESOLVED]
        assert restarted.history[0].id == alert_id

    run(scenario())


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
        set_now(start + timedelta(minutes=6))
        await first._async_flush_mature_pending()
        assert alert_id in hass.stores["alert_manager"]["alerts"]
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
        hass.bus.fired.clear()
        fire_startup_reconciliation(hass)
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
        for _index in range(5):
            await asyncio.sleep(0)

        assert restarted._runtime_phase is RuntimePhase.RUNNING
        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.PENDING
        assert restored.detected_at == original.detected_at
        assert restored.due_at == original.due_at
        assert alert_id not in restarted._unverified_restored_alert_ids
        persisted = hass.stores["alert_manager"]["alerts"][alert_id]
        assert persisted["detected_at"] == original.detected_at.isoformat()
        assert save_calls == 3
        assert not [
            event
            for event, data in hass.bus.fired
            if event in (EVENT_ALERT_STARTED, EVENT_ALERT_RESOLVED)
            and data["id"] == alert_id
        ]

        restarted.storage.async_save = original_save
        await restarted.async_unload()

    run(scenario())


def test_reconciliation_pending_unavailable_advanced_then_unknown_is_removed(
    hass, entry, set_now
):
    """Only an originally active outage is protected from final unknown."""
    start = datetime(2026, 9, 4, 18, tzinfo=UTC)
    set_now(start)

    async def scenario():
        entity_id = "sensor.gateway"
        alert_id = f"unavailable:{entity_id}"
        hass.states.set(entity_id, "unavailable")
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        assert first.records[alert_id].status is AlertStatus.PENDING
        due_at = first.records[alert_id].due_at

        set_now(start + timedelta(minutes=6))
        await first._async_flush_mature_pending()
        assert alert_id in hass.stores["alert_manager"]["alerts"]
        await first.async_unload()

        set_now(due_at + timedelta(seconds=1))
        hass.state = CoreState.starting
        unavailable_state = hass.states.set(entity_id, "unavailable")
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
        hass.bus.fired.clear()
        fire_startup_reconciliation(hass)
        await save_started.wait()
        assert restarted.records[alert_id].status is AlertStatus.ACTIVE

        unknown_state = hass.states.set(entity_id, "unknown")
        restarted._state_changed(
            Event(
                {
                    "entity_id": entity_id,
                    "old_state": unavailable_state,
                    "new_state": unknown_state,
                }
            )
        )
        release_save.set()
        for _index in range(5):
            await asyncio.sleep(0)

        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert alert_id not in restarted.records
        assert alert_id not in hass.stores["alert_manager"]["alerts"]
        assert not [
            event
            for event, data in hass.bus.fired
            if event in (EVENT_ALERT_STARTED, EVENT_ALERT_RESOLVED)
            and data["id"] == alert_id
        ]

        restarted.storage.async_save = original_save
        await restarted.async_unload()

    run(scenario())


def test_reconciliation_active_unavailable_keeps_identity_ack_and_notification(
    hass, entry
):
    """A late outage revives one restored active occurrence without side effects."""

    async def scenario():
        profile = {
            "id": "profile",
            "name": "Profile",
            "enabled": True,
            "targets": ["notify.phone"],
            "label_ids": [],
            "default_policy": {
                "notify_on_start": True,
                "notify_on_resolved": True,
                "reminder_interval": 300,
            },
            "exceptions": [],
        }
        hass.states.set("sensor.gateway", "unavailable")
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        await first.async_update_config(
            {
                "automatic": {"unavailable": {"delay": 0}},
                "notification_profiles": [profile],
            }
        )
        alert_id = "unavailable:sensor.gateway"
        await first.async_acknowledge(alert_id, "tester")
        original = deepcopy(first.records[alert_id])
        await first.async_unload()

        hass.state = CoreState.starting
        recovered_state = hass.states.set("sensor.gateway", "on")
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True
        assert alert_id in restarted.notification_runtime._runtime["profile"]
        reminder_before = restarted.notification_runtime._runtime["profile"][
            alert_id
        ].next_reminder
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
        fire_startup_reconciliation(hass)
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
        for _index in range(5):
            await asyncio.sleep(0)

        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.ACTIVE
        assert restored.detected_at == original.detected_at
        assert restored.due_at == original.due_at
        assert restored.active_since == original.active_since
        assert restored.acknowledged is True
        assert restored.acknowledged_at == original.acknowledged_at
        assert restored.acknowledged_by == original.acknowledged_by
        assert alert_id not in restarted._unverified_restored_alert_ids
        assert save_calls == 2
        assert not [
            event
            for event, data in hass.bus.fired
            if event in (EVENT_ALERT_STARTED, EVENT_ALERT_RESOLVED)
            and data["id"] == alert_id
        ]
        assert (
            restarted.notification_runtime._runtime["profile"][alert_id].next_reminder
            == reminder_before
        )
        assert restarted.notification_runtime._batches == {}

        restarted.storage.async_save = original_save
        await restarted.async_unload()

    run(scenario())


def test_reconciliation_confirmed_custom_then_unknown_resolves(hass, entry):
    """A final unknown observation resolves the restored rule at the deadline."""

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
        hass.bus.fired.clear()
        fire_startup_reconciliation(hass)
        await save_started.wait()
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
        for _index in range(5):
            await asyncio.sleep(0)

        assert alert_id not in restarted.records
        assert alert_id not in restarted._unverified_restored_alert_ids
        assert alert_id not in hass.stores["alert_manager"]["alerts"]
        resolved = [
            data
            for event_type, data in hass.bus.fired
            if event_type == EVENT_ALERT_RESOLVED and data["id"] == alert_id
        ]
        assert len(resolved) == 1

        restarted.storage.async_save = original_save
        await restarted.async_unload()

    run(scenario())


def test_reconciliation_rebases_removed_shadow_through_entity_rename(
    hass, entry, set_now
):
    """A rename can revive a provisionally removed occurrence under its new id."""
    start = datetime(2026, 9, 4, 19, tzinfo=UTC)
    set_now(start)

    async def scenario():
        old_entity_id = "binary_sensor.old_filter"
        new_entity_id = "binary_sensor.new_filter"
        hass.states.set(old_entity_id, "on")
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        rule = await first.async_create_rule(
            {
                "name": "Filter active",
                "entity_ids": [old_entity_id],
                "operator": "equals",
                "value": "on",
                "duration": 24 * 60 * 60,
            }
        )
        old_alert_id = f"rule:{rule['id']}:{old_entity_id}"
        original = deepcopy(first.records[old_alert_id])
        set_now(start + timedelta(minutes=6))
        await first._async_flush_mature_pending()
        await first.async_unload()

        hass.state = CoreState.starting
        hass.states.set(old_entity_id, "off")
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
        fire_startup_reconciliation(hass)
        await save_started.wait()
        assert old_alert_id not in restarted.records

        hass.states.data.pop(old_entity_id)
        hass.states.set(new_entity_id, "on")
        restarted._registry_changed(
            Event(
                {
                    "action": "update",
                    "old_entity_id": old_entity_id,
                    "entity_id": new_entity_id,
                }
            )
        )
        release_save.set()
        for _index in range(6):
            await asyncio.sleep(0)

        new_alert_id = f"rule:{rule['id']}:{new_entity_id}"
        restored = restarted.records[new_alert_id]
        assert restored.detected_at == original.detected_at
        assert restored.due_at == original.due_at
        assert restarted.config["rules"][0]["entity_ids"] == [new_entity_id]
        assert old_alert_id not in restarted.records
        assert new_alert_id in hass.stores["alert_manager"]["alerts"]

        restarted.storage.async_save = original_save
        await restarted.async_unload()

    run(scenario())


def test_reconciliation_rename_collision_prefers_oldest_removed_shadow(
    hass, entry, set_now
):
    """A provisional removal cannot make a newer rename peer win identity."""
    start = datetime(2026, 9, 4, 19, tzinfo=UTC)
    set_now(start)

    async def scenario():
        old_entity_id = "sensor.old_gateway"
        new_entity_id = "sensor.new_gateway"
        old_alert_id = f"unavailable:{old_entity_id}"
        new_alert_id = f"unavailable:{new_entity_id}"
        hass.states.set(old_entity_id, "unavailable")
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        await first.async_update_config({"automatic": {"unavailable": {"delay": 0}}})
        oldest = deepcopy(first.records[old_alert_id])

        set_now(start + timedelta(minutes=5))
        hass.states.set(new_entity_id, "unavailable")
        await first.async_evaluate_entity(new_entity_id)
        assert first.records[new_alert_id].detected_at > oldest.detected_at
        await first.async_unload()

        hass.state = CoreState.starting
        hass.states.set(old_entity_id, "on")
        hass.states.set(new_entity_id, "unavailable")
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
        fire_startup_reconciliation(hass)
        await save_started.wait()
        assert old_alert_id not in restarted.records
        assert restarted.records[new_alert_id].detected_at > oldest.detected_at

        hass.states.data.pop(old_entity_id)
        restarted._registry_changed(
            Event(
                {
                    "action": "update",
                    "old_entity_id": old_entity_id,
                    "entity_id": new_entity_id,
                }
            )
        )
        release_save.set()
        for _index in range(6):
            await asyncio.sleep(0)

        retained = restarted.records[new_alert_id]
        assert retained.detected_at == oldest.detected_at
        assert retained.active_since == oldest.active_since
        assert old_alert_id not in restarted.records
        persisted = hass.stores["alert_manager"]["alerts"]
        assert persisted[new_alert_id]["detected_at"] == oldest.detected_at.isoformat()
        assert old_alert_id not in persisted

        restarted.storage.async_save = original_save
        await restarted.async_unload()

    run(scenario())


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
            published_states.append(published_alert_state(restarted))

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
        fire_startup_reconciliation(hass)
        await save_started.wait()
        assert alert_id not in restarted.records

        set_now(start.replace(minute=35, second=1))
        release_save.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

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

    run(scenario())


def test_shutdown_rollback_cannot_rearm_restored_template_timers(hass, entry):
    """Restoring Jinja metadata during shutdown leaves no callback armed."""

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
        fire_startup_reconciliation(hass)
        await scan_complete.wait()

        restarted._begin_shutdown()
        hass.state = CoreState.stopping
        release_scan.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await restarted.async_unload()

        assert restarted._runtime_phase is RuntimePhase.STOPPING
        assert restarted._template_time_timer is None
        assert restarted._template_rate_limit_timers == {}
        assert not [timer for timer in hass.timers if not timer["cancelled"]]

    run(scenario())


def test_cancelled_rule_write_restores_config_records_and_render_info(hass, entry):
    """A Store cancellation rolls back the whole transaction."""

    async def scenario():
        hass.states.set("binary_sensor.filter", "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        original_config = manager.get_config()
        original_records = dict(manager.records)
        original_condition_info = dict(manager._rule_template_render_info)
        original_message_info = dict(manager._rule_message_render_info)
        original_save = manager.storage.async_save

        async def blocked_save(*_args, **_kwargs):
            raise asyncio.CancelledError

        manager.storage.async_save = blocked_save
        with pytest.raises(asyncio.CancelledError):
            await manager.async_create_rule(
                {
                    "name": "Filter active",
                    "entity_ids": ["binary_sensor.filter"],
                    "operator": "equals",
                    "value": "on",
                    "condition_template": "{{ true }}",
                    "message": "{{ states(entity_id) }}",
                    "duration": 3600,
                }
            )

        assert manager.get_config() == original_config
        assert manager.records == original_records
        assert manager._rule_template_render_info == original_condition_info
        assert manager._rule_message_render_info == original_message_info
        assert manager._record_ids_by_entity == {}

        manager.storage.async_save = original_save
        await manager.async_unload()

    run(scenario())


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
        fire_startup_reconciliation(hass)
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
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert save_calls == 3
        assert hass.stores["alert_manager"] == before_store
        assert restarted.records == {}
        assert restarted._startup_reconciliation_scheduled is False
        assert not [timer for timer in hass.timers if not timer["cancelled"]]

    run(scenario())


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
        fire_startup_reconciliation(hass)
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
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert save_calls == 3
        assert hass.stores["alert_manager"] == before_store
        assert restarted.records == {}
        assert restarted._unsubscribers == []
        assert restarted.notification_runtime._unsubscribe == []
        assert restarted._pending_persistence_timer is None
        assert restarted._pending_persistence_deadline is None
        assert restarted._startup_reconciliation_scheduled is False
        assert not hass.dispatchers[SIGNAL_NOTIFICATION_LIFECYCLE]
        assert not [timer for timer in hass.timers if not timer["cancelled"]]

    run(scenario())


def test_fresh_pending_restarts_while_active_state_remains_durable(
    hass, entry, set_now
):
    """A fresh pending restarts its delay while active state remains durable."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable")

    async def scenario():
        first = AlertManager(hass, entry)
        await first.async_setup()
        alert_id = "unavailable:sensor.test"
        due = first.records[alert_id].due_at
        assert alert_id not in hass.stores["alert_manager"]["alerts"]
        await first.async_unload()

        set_now(start + timedelta(seconds=300))
        second = AlertManager(hass, entry)
        await second.async_setup()
        assert alert_id not in second.records
        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert second.records[alert_id].due_at == due + timedelta(seconds=300)
        assert_record_index(second)
        set_now(second.records[alert_id].due_at + timedelta(seconds=1))
        await second.async_evaluate_entity("sensor.test")
        started_before = len(
            [item for item in hass.bus.fired if item[0] == EVENT_ALERT_STARTED]
        )
        await second.async_unload()

        third = AlertManager(hass, entry)
        await third.async_setup()
        assert third.records[alert_id].status is AlertStatus.ACTIVE
        assert_record_index(third)
        started_after = len(
            [item for item in hass.bus.fired if item[0] == EVENT_ALERT_STARTED]
        )
        assert started_after == started_before

    run(scenario())


def test_persisted_pending_rule_survives_transient_startup_state(hass, entry, set_now):
    """Starting-state events cannot erase a persisted pending occurrence."""
    start = datetime(2026, 9, 4, 10, tzinfo=UTC)
    set_now(start)
    hass.states.set("binary_sensor.pool_filter", "on")

    async def scenario():
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
        set_now(start + timedelta(minutes=6))
        await first._async_flush_mature_pending()
        assert alert_id in hass.stores["alert_manager"]["alerts"]
        await first.async_unload()

        hass.state = CoreState.starting
        rebooted_at = start + timedelta(hours=2, minutes=36)
        set_now(rebooted_at)
        previous_state = hass.states.get("binary_sensor.pool_filter")
        transient_state = hass.states.set("binary_sensor.pool_filter", "off")
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()

        tasks_before = len(entry.created_task_names)
        restarted._state_changed(
            Event(
                {
                    "entity_id": "binary_sensor.pool_filter",
                    "old_state": previous_state,
                    "new_state": transient_state,
                }
            )
        )
        assert len(entry.created_task_names) == tasks_before
        assert restarted.records[alert_id].detected_at == detected_at
        assert restarted.records[alert_id].due_at == due_at

        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert restarted.records[alert_id].detected_at == detected_at
        assert restarted.records[alert_id].due_at == due_at

        matching_state = hass.states.set("binary_sensor.pool_filter", "on")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "binary_sensor.pool_filter",
                    "old_state": transient_state,
                    "new_state": matching_state,
                }
            )
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert restarted.records[alert_id].detected_at == detected_at
        assert restarted.records[alert_id].due_at == due_at

        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        normal_state = hass.states.set("binary_sensor.pool_filter", "off")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "binary_sensor.pool_filter",
                    "old_state": matching_state,
                    "new_state": normal_state,
                }
            )
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert alert_id not in restarted.records

    run(scenario())


@pytest.mark.parametrize("uncertain_state", [None, "unknown", "unavailable"])
def test_restored_pending_rule_follows_final_startup_state(
    hass, entry, set_now, uncertain_state
):
    """A restored pending rule is bounded unless unavailable remains authoritative."""
    start = datetime(2026, 9, 4, 10, tzinfo=UTC)
    set_now(start)
    hass.states.set("binary_sensor.pool_filter", "on")

    async def scenario():
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
        original = first.records[alert_id]
        detected_at = original.detected_at
        due_at = original.due_at
        set_now(start + timedelta(minutes=6))
        await first._async_flush_mature_pending()
        assert alert_id in hass.stores["alert_manager"]["alerts"]
        await first.async_unload()

        hass.state = CoreState.starting
        set_now(start + timedelta(hours=2, minutes=36))
        if uncertain_state is None:
            hass.states.data.pop("binary_sensor.pool_filter")
        else:
            hass.states.set("binary_sensor.pool_filter", uncertain_state)
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()

        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.PENDING
        assert restored.detected_at == detected_at
        assert restored.due_at == due_at
        assert alert_id in restarted._unverified_restored_alert_ids

        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        if uncertain_state in (None, "unknown"):
            assert alert_id not in restarted.records
            assert alert_id not in restarted._unverified_restored_alert_ids
            assert alert_id not in hass.stores["alert_manager"]["alerts"]
            assert not [
                data
                for event_type, data in hass.bus.fired
                if event_type == EVENT_ALERT_RESOLVED and data["id"] == alert_id
            ]
            return

        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.PENDING
        assert restored.detected_at == detected_at
        assert restored.due_at == due_at
        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert alert_id in restarted._unverified_restored_alert_ids

        set_now(due_at + timedelta(seconds=1))
        matching_due_timers = [
            timer
            for timer in hass.timers
            if not timer["cancelled"]
            and timer["point"] == due_at
            and "_schedule_timer.<locals>.timer_due" in timer["action"].__qualname__
        ]
        assert len(matching_due_timers) == 1
        due_timer = matching_due_timers[0]
        due_timer["action"](due_at)
        for _index in range(5):
            await asyncio.sleep(0)
        assert restarted._queued_evaluation_entities == set()
        assert restarted._evaluation_flush_scheduled is False
        assert alert_id in restarted._unverified_restored_alert_ids
        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.ACTIVE
        assert restored.detected_at == detected_at
        assert restored.due_at == due_at
        assert hass.stores["alert_manager"]["alerts"][alert_id]["status"] == "active"

        indeterminate_state = hass.states.get("binary_sensor.pool_filter")
        matching_state = hass.states.set("binary_sensor.pool_filter", "on")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "binary_sensor.pool_filter",
                    "old_state": indeterminate_state,
                    "new_state": matching_state,
                }
            )
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert restarted.records[alert_id].status is AlertStatus.ACTIVE
        assert restarted.records[alert_id].detected_at == detected_at

    run(scenario())


@pytest.mark.parametrize("uncertain_state", [None, "unknown", "unavailable"])
def test_new_pending_rule_is_not_protected_from_runtime_uncertainty(
    hass, entry, uncertain_state
):
    """Indeterminate-state protection applies only to records restored at startup."""

    async def scenario():
        matching_state = hass.states.set("binary_sensor.pool_filter", "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(
            {
                "name": "Pool filtration over 24 hours",
                "entity_ids": ["binary_sensor.pool_filter"],
                "operator": "equals",
                "value": "on",
                "duration": 24 * 60 * 60,
            }
        )
        alert_id = f"rule:{rule['id']}:binary_sensor.pool_filter"
        assert manager.records[alert_id].status is AlertStatus.PENDING

        if uncertain_state is None:
            hass.states.data.pop("binary_sensor.pool_filter")
            new_state = None
        else:
            new_state = hass.states.set("binary_sensor.pool_filter", uncertain_state)
        manager._state_changed(
            Event(
                {
                    "entity_id": "binary_sensor.pool_filter",
                    "old_state": matching_state,
                    "new_state": new_state,
                }
            )
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert alert_id not in manager.records

    run(scenario())


@pytest.mark.parametrize("uncertain_state", [None, "unknown", "unavailable"])
def test_new_active_rule_is_not_protected_from_runtime_uncertainty(
    hass, entry, uncertain_state
):
    """Only startup restoration grants protection from uncertain observations."""

    async def scenario():
        matching_state = hass.states.set("binary_sensor.pool_filter", "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(
            {
                "name": "Pool filtration active",
                "entity_ids": ["binary_sensor.pool_filter"],
                "operator": "equals",
                "value": "on",
                "duration": 0,
            }
        )
        alert_id = f"rule:{rule['id']}:binary_sensor.pool_filter"
        assert manager.records[alert_id].status is AlertStatus.ACTIVE

        if uncertain_state is None:
            hass.states.data.pop("binary_sensor.pool_filter")
            new_state = None
        else:
            new_state = hass.states.set("binary_sensor.pool_filter", uncertain_state)
        manager._state_changed(
            Event(
                {
                    "entity_id": "binary_sensor.pool_filter",
                    "old_state": matching_state,
                    "new_state": new_state,
                }
            )
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert alert_id not in manager.records

    run(scenario())


@pytest.mark.parametrize("recovered_state", ["auto", "unknown"])
def test_pending_unavailable_clears_on_startup_recovery_event(
    hass, entry, set_now, recovered_state
):
    """A startup recovery clears a pending outage after any unknown grace."""
    start = datetime(2026, 9, 4, 16, 47, 22, tzinfo=UTC)
    set_now(start)

    async def scenario():
        hass.states.set("select.camera_mode", "unavailable")
        first = AlertManager(hass, entry)
        await first.async_setup()
        alert_id = "unavailable:select.camera_mode"
        assert first.records[alert_id].status is AlertStatus.PENDING
        set_now(start + timedelta(minutes=6))
        await first._async_flush_mature_pending()
        assert alert_id in hass.stores["alert_manager"]["alerts"]
        await first.async_unload()

        hass.state = CoreState.starting
        unavailable_state = hass.states.set("select.camera_mode", "unavailable")
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        assert restarted.records[alert_id].status is AlertStatus.PENDING

        usable_state = hass.states.set("select.camera_mode", recovered_state)
        restarted._state_changed(
            Event(
                {
                    "entity_id": "select.camera_mode",
                    "old_state": unavailable_state,
                    "new_state": usable_state,
                }
            )
        )

        assert restarted.records[alert_id].status is AlertStatus.PENDING
        assert restarted.public_snapshot()["pending_count"] == 0

        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert restarted.records[alert_id].status is AlertStatus.PENDING
        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert alert_id not in restarted.records
        assert restarted.public_snapshot()["pending_count"] == 0
        assert not [
            event for event, _data in hass.bus.fired if event == EVENT_ALERT_RESOLVED
        ]
        assert hass.stores["alert_manager"]["alerts"] == {}

    run(scenario())


@pytest.mark.parametrize("recovered_state", ["auto", "unknown"])
def test_pending_unavailable_clears_from_current_startup_state(
    hass, entry, set_now, recovered_state
):
    """Initial evaluation clears a pending outage whose event was missed."""
    start = datetime(2026, 9, 4, 16, 47, 22, tzinfo=UTC)
    set_now(start)

    async def scenario():
        hass.states.set("select.camera_mode", "unavailable")
        first = AlertManager(hass, entry)
        await first.async_setup()
        alert_id = "unavailable:select.camera_mode"
        assert first.records[alert_id].status is AlertStatus.PENDING
        set_now(start + timedelta(minutes=6))
        await first._async_flush_mature_pending()
        assert alert_id in hass.stores["alert_manager"]["alerts"]
        await first.async_unload()

        hass.state = CoreState.starting
        hass.states.set("select.camera_mode", recovered_state)
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        assert restarted.records[alert_id].status is AlertStatus.PENDING

        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert restarted.records[alert_id].status is AlertStatus.PENDING
        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert alert_id not in restarted.records
        assert restarted.public_snapshot()["pending_count"] == 0
        assert hass.stores["alert_manager"]["alerts"] == {}

    run(scenario())


def test_pending_unavailable_clears_on_unknown_state(hass, entry):
    """Unknown never keeps an unavailable occurrence pending at runtime."""

    async def scenario():
        unavailable_state = hass.states.set("event.camera_sound", "unavailable")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        alert_id = "unavailable:event.camera_sound"
        assert manager.records[alert_id].status is AlertStatus.PENDING

        unknown_state = hass.states.set("event.camera_sound", "unknown")
        manager._state_changed(
            Event(
                {
                    "entity_id": "event.camera_sound",
                    "old_state": unavailable_state,
                    "new_state": unknown_state,
                }
            )
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert alert_id not in manager.records
        assert manager.public_snapshot()["pending_count"] == 0

    run(scenario())


def test_restored_pending_unavailable_keeps_clock_when_outage_is_confirmed(
    hass, entry, set_now
):
    """A real outage spanning a restart keeps its clock and activates once."""
    start = datetime(2026, 9, 4, 16, 30, tzinfo=UTC)
    set_now(start)

    async def scenario():
        hass.states.set("sensor.offline", "unavailable")
        first = AlertManager(hass, entry)
        await first.async_setup()
        alert_id = "unavailable:sensor.offline"
        original = first.records[alert_id]
        detected_at = original.detected_at
        due_at = original.due_at
        set_now(start + timedelta(minutes=6))
        await first._async_flush_mature_pending()
        await first.async_unload()

        hass.state = CoreState.starting
        set_now(start + timedelta(minutes=10))
        hass.states.set("sensor.offline", "unavailable")
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.PENDING
        assert restored.detected_at == detected_at
        assert restored.due_at == due_at

        set_now(due_at + timedelta(seconds=1))
        await restarted.async_evaluate_entity("sensor.offline")
        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.ACTIVE
        assert restored.detected_at == detected_at
        assert restored.due_at == due_at

        unavailable_state = hass.states.get("sensor.offline")
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
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert alert_id not in restarted.records

    run(scenario())


def test_active_unavailable_is_protected_until_unknown_startup_deadline(
    hass, entry, set_now
):
    """A restored active outage is protected only until the startup deadline."""
    start = datetime(2026, 9, 4, 12, tzinfo=UTC)
    set_now(start)

    async def scenario():
        hass.states.set("sensor.offline", "unavailable")
        first = AlertManager(hass, entry)
        await first.async_setup()
        await first.async_update_config({"automatic": {"unavailable": {"delay": 0}}})

        alert_id = "unavailable:sensor.offline"
        original = first.records[alert_id]
        assert original.status is AlertStatus.ACTIVE
        detected_at = original.detected_at
        active_since = original.active_since
        await first.async_unload()

        hass.state = CoreState.starting
        hass.states.set("sensor.offline", "unknown")
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()

        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.ACTIVE
        assert restored.detected_at == detected_at
        assert restored.active_since == active_since

        hass.bus.fired.clear()
        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert alert_id not in restarted.records
        assert alert_id not in restarted._unverified_restored_alert_ids
        resolved = [
            data
            for event_type, data in hass.bus.fired
            if event_type == EVENT_ALERT_RESOLVED and data["id"] == alert_id
        ]
        assert len(resolved) == 1

    run(scenario())


@pytest.mark.parametrize("uncertain_state", [None, "unknown", "unavailable"])
def test_restored_active_rule_follows_final_startup_state(hass, entry, uncertain_state):
    """A restored active rule is bounded unless unavailable remains authoritative."""

    async def scenario():
        hass.states.set("binary_sensor.pool_filter", "on")
        first = AlertManager(hass, entry)
        await first.async_setup()
        rule = await first.async_create_rule(
            {
                "name": "Pool filtration active",
                "entity_ids": ["binary_sensor.pool_filter"],
                "operator": "equals",
                "value": "on",
                "duration": 0,
            }
        )
        alert_id = f"rule:{rule['id']}:binary_sensor.pool_filter"
        original = first.records[alert_id]
        detected_at = original.detected_at
        active_since = original.active_since
        await first.async_unload()

        hass.state = CoreState.starting
        if uncertain_state is None:
            hass.states.data.pop("binary_sensor.pool_filter")
        else:
            hass.states.set("binary_sensor.pool_filter", uncertain_state)
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        if uncertain_state in (None, "unknown"):
            assert alert_id not in restarted.records
            assert alert_id not in restarted._unverified_restored_alert_ids
            return

        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.ACTIVE
        assert restored.detected_at == detected_at
        assert restored.active_since == active_since

        uncertain = hass.states.get("binary_sensor.pool_filter")
        matching = hass.states.set("binary_sensor.pool_filter", "on")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "binary_sensor.pool_filter",
                    "old_state": uncertain,
                    "new_state": matching,
                }
            )
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert restarted.records[alert_id].status is AlertStatus.ACTIVE
        assert restarted.records[alert_id].detected_at == detected_at

        normal = hass.states.set("binary_sensor.pool_filter", "off")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "binary_sensor.pool_filter",
                    "old_state": matching,
                    "new_state": normal,
                }
            )
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert alert_id not in restarted.records

    run(scenario())


def test_active_unavailable_alert_survives_transient_normal_startup_state(hass, entry):
    """A normal startup placeholder cannot recreate an unavailable alert."""

    async def scenario():
        hass.states.set("sensor.offline", "unavailable")
        first = AlertManager(hass, entry)
        await first.async_setup()
        await first.async_update_config({"automatic": {"unavailable": {"delay": 0}}})

        alert_id = "unavailable:sensor.offline"
        original = first.records[alert_id]
        assert original.status is AlertStatus.ACTIVE
        detected_at = original.detected_at
        due_at = original.due_at
        active_since = original.active_since
        await first.async_unload()

        hass.state = CoreState.starting
        unavailable_before_restart = hass.states.get("sensor.offline")
        transient_state = hass.states.set("sensor.offline", "ok")
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()

        restarted._state_changed(
            Event(
                {
                    "entity_id": "sensor.offline",
                    "old_state": unavailable_before_restart,
                    "new_state": transient_state,
                }
            )
        )
        assert restarted.records[alert_id].status is AlertStatus.ACTIVE

        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.ACTIVE
        assert restored.detected_at == detected_at
        assert restored.due_at == due_at
        assert restored.active_since == active_since

        unavailable_again = hass.states.set("sensor.offline", "unavailable")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "sensor.offline",
                    "old_state": transient_state,
                    "new_state": unavailable_again,
                }
            )
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.ACTIVE
        assert restored.detected_at == detected_at
        assert restored.due_at == due_at
        assert restored.active_since == active_since

        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        normal_state = hass.states.set("sensor.offline", "ok")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "sensor.offline",
                    "old_state": unavailable_again,
                    "new_state": normal_state,
                }
            )
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert alert_id not in restarted.records

    run(scenario())


def test_startup_reconciliation_removes_confirmed_recovery(hass, entry):
    """A restored alert is resolved once its settled source is normal."""

    async def scenario():
        hass.states.set("sensor.recovered", "unavailable")
        first = AlertManager(hass, entry)
        await first.async_setup()
        await first.async_update_config({"automatic": {"unavailable": {"delay": 0}}})

        alert_id = "unavailable:sensor.recovered"
        assert first.records[alert_id].status is AlertStatus.ACTIVE
        await first.async_unload()

        hass.state = CoreState.starting
        hass.states.set("sensor.recovered", "ok")
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()

        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert restarted.records[alert_id].status is AlertStatus.ACTIVE

        resolved_before = len(
            [event for event, _data in hass.bus.fired if event == EVENT_ALERT_RESOLVED]
        )
        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert alert_id not in restarted.records
        resolved_after = len(
            [event for event, _data in hass.bus.fired if event == EVENT_ALERT_RESOLVED]
        )
        assert resolved_after == resolved_before + 1

    run(scenario())


def test_transient_startup_unavailable_does_not_create_pending_alert(hass, entry):
    """A startup-only unavailable value must not create a visible occurrence."""

    async def scenario():
        hass.states.set("sensor.persisted", "unavailable")
        hass.states.set("sensor.temperature", "31")
        first = AlertManager(hass, entry)
        await first.async_setup()
        assert "unavailable:sensor.persisted" in first.records
        await first.async_unload()

        hass.state = CoreState.starting
        hass.states.set("sensor.temperature", "unavailable")
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()

        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        alert_id = "unavailable:sensor.temperature"
        assert alert_id not in restarted.records

        hass.states.set("sensor.temperature", "31")
        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert alert_id not in restarted.records
        assert restarted.public_snapshot()["pending_count"] == 0
        assert alert_id not in hass.stores["alert_manager"]["alerts"]

    run(scenario())


@pytest.mark.parametrize("unavailable_delay", [0, 15 * 60])
def test_late_startup_unknown_never_exposes_new_unavailable(
    hass, entry, set_now, unavailable_delay
):
    """A late setup rechecks a new outage even when its recovery event was missed."""
    start = datetime(2026, 9, 4, 15, 31, 34, tzinfo=UTC)
    set_now(start)
    entity_id = "event.baby_intelligent_detection"
    hass.states.set(entity_id, "idle")

    async def scenario():
        first = AlertManager(hass, entry)
        await first.async_setup()
        await first.async_update_config(
            {
                "pending_display_delay": 0,
                "automatic": {"unavailable": {"delay": unavailable_delay}},
            }
        )
        assert first.records == {}
        await first.async_unload()
        assert hass.stores["alert_manager"]["alerts"] == {}

        hass.states.set(entity_id, "unavailable")
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()

        alert_id = f"unavailable:{entity_id}"
        assert alert_id not in restarted.records
        assert restarted.public_snapshot()["pending_count"] == 0

        # Reproduce an integration recovery whose state event was missed.
        hass.states.set(entity_id, "unknown")
        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert alert_id not in restarted.records
        assert restarted.public_snapshot()["pending_count"] == 0
        assert hass.stores["alert_manager"]["alerts"] == {}

    run(scenario())


def test_settled_startup_unavailable_starts_normal_delay_after_grace(
    hass, entry, set_now
):
    """A settled startup outage starts the normal pending lifecycle at the scan."""
    start = datetime(2026, 9, 4, 14, tzinfo=UTC)
    set_now(start)

    async def scenario():
        hass.states.set("sensor.temperature", "31")
        first = AlertManager(hass, entry)
        await first.async_setup()
        await first.async_unload()

        hass.state = CoreState.starting
        hass.states.set("sensor.temperature", "unavailable")
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()

        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        alert_id = "unavailable:sensor.temperature"
        assert alert_id not in restarted.records

        reconciled_at = start + timedelta(seconds=STARTUP_RECONCILIATION_DELAY_SECONDS)
        set_now(reconciled_at)
        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        pending = restarted.records[alert_id]
        assert pending.status is AlertStatus.PENDING
        assert pending.detected_at == reconciled_at
        assert pending.visible_at == reconciled_at + timedelta(seconds=10)
        assert pending.due_at == reconciled_at + timedelta(minutes=15)
        snapshot, _device_groups = restarted._build_public_snapshot()
        assert snapshot["pending_count"] == 0
        assert alert_id not in {item["id"] for item in snapshot["pending"]}

        visibility_timer = next(
            timer
            for timer in hass.timers
            if not timer["cancelled"] and timer["point"] == pending.visible_at
        )
        set_now(pending.visible_at)
        visibility_timer["action"](pending.visible_at)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert restarted.public_snapshot()["pending_count"] == 1

        activation_timer = next(
            timer
            for timer in hass.timers
            if not timer["cancelled"] and timer["point"] == pending.due_at
        )
        set_now(pending.due_at)
        activation_timer["action"](pending.due_at)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert restarted.records[alert_id].status is AlertStatus.ACTIVE

    run(scenario())


def test_new_custom_occurrence_starts_only_after_startup_grace(hass, entry):
    """A new matching custom rule starts at the authoritative startup scan."""

    async def scenario():
        hass.states.set("binary_sensor.transient", "off")
        first = AlertManager(hass, entry)
        await first.async_setup()
        rule = await first.async_create_rule(
            {
                "name": "Transient input",
                "entity_ids": ["binary_sensor.transient"],
                "operator": "equals",
                "value": "on",
                "duration": 3600,
            }
        )
        alert_id = f"rule:{rule['id']}:binary_sensor.transient"
        assert alert_id not in first.records
        await first.async_unload()

        hass.state = CoreState.starting
        matching_state = hass.states.set("binary_sensor.transient", "on")
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()

        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert alert_id not in restarted.records

        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert restarted.records[alert_id].status is AlertStatus.PENDING

        normal_state = hass.states.set("binary_sensor.transient", "off")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "binary_sensor.transient",
                    "old_state": matching_state,
                    "new_state": normal_state,
                }
            )
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert alert_id not in restarted.records

    run(scenario())


def test_missed_startup_recovery_is_applied_by_authoritative_scan(hass, entry, set_now):
    """The final current state wins even when its recovery event was missed."""
    start = datetime(2026, 9, 4, 16, 33, 21, tzinfo=UTC)
    set_now(start)

    async def scenario():
        hass.state = CoreState.starting
        hass.states.set("sensor.online", "ok")
        manager = AlertManager(hass, entry)
        await manager.async_setup()

        hass.state = CoreState.running
        manager._home_assistant_started(Event())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        hass.states.set("sensor.online", "unavailable")
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        alert_id = "unavailable:sensor.online"
        assert alert_id not in manager.records

        hass.states.set("sensor.online", "ok")
        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert alert_id not in manager.records
        assert manager.public_snapshot()["pending_count"] == 0

    run(scenario())


@pytest.mark.parametrize("startup_state", [None, "unknown"])
def test_active_alert_is_reconciled_after_uncertain_startup_grace(
    hass, entry, set_now, startup_state
):
    """Missing and unknown protect an active alert only during startup grace."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)

    async def scenario():
        hass.states.set("sensor.test", "unavailable")
        first = AlertManager(hass, entry)
        await first.async_setup()
        await first.async_update_config({"automatic": {"unavailable": {"delay": 0}}})
        alert_id = "unavailable:sensor.test"
        original = first.records[alert_id]
        assert original.status is AlertStatus.ACTIVE
        detected_at = original.detected_at
        active_since = original.active_since
        await first.async_unload()

        hass.state = CoreState.starting
        if startup_state is None:
            hass.states.data.pop("sensor.test")
        else:
            hass.states.set("sensor.test", startup_state)
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        restored = restarted.records[alert_id]
        assert restored.status is AlertStatus.ACTIVE
        assert restored.detected_at == detected_at
        assert restored.active_since == active_since

        hass.bus.fired.clear()
        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert restarted.records == {}
        assert restarted._unverified_restored_alert_ids == set()
        resolved = [
            data
            for event_type, data in hass.bus.fired
            if event_type == EVENT_ALERT_RESOLVED and data["id"] == alert_id
        ]
        assert len(resolved) == 1

    run(scenario())


def test_unavailable_detection_does_not_duplicate_connectivity(hass, entry):
    """Unavailable wins over connectivity for the same entity."""
    hass.states.set(
        "binary_sensor.gateway",
        "unavailable",
        {"device_class": "connectivity"},
    )
    manager = make_manager(hass, entry)
    assert set(manager.records) == {"unavailable:binary_sensor.gateway"}


def test_unknown_is_not_an_unavailable_alert(hass, entry):
    """The unavailable pack deliberately excludes unknown states."""
    hass.states.set("automation.test", "unknown")
    assert make_manager(hass, entry).records == {}


def test_disabled_entity_and_device_are_ignored(
    hass, entry, registry_entry, device_entry
):
    """Both registry disablers suppress automatic and custom alerts."""
    registry_entry(hass, "sensor.disabled", disabled_by="user")
    hass.states.set("sensor.disabled", "unavailable")
    device = device_entry(hass, disabled_by="user")
    registry_entry(hass, "sensor.device_disabled", device_id=device.id)
    hass.states.set("sensor.device_disabled", "unavailable")
    manager = make_manager(hass, entry)
    assert manager.records == {}


def test_entity_label_exclusion(hass, entry, registry_entry):
    """The configured label on an entity excludes it."""
    hass.label_registry.labels["pas_d_alerte"] = SimpleNamespace(label_id="skip")
    registry_entry(hass, "sensor.test", labels={"skip"})
    hass.states.set("sensor.test", "unavailable")
    assert make_manager(hass, entry).records == {}


def test_device_label_exclusion(hass, entry, registry_entry, device_entry):
    """The configured label on an associated device excludes its entities."""
    hass.label_registry.labels["pas_d_alerte"] = SimpleNamespace(label_id="skip")
    device = device_entry(hass, labels={"skip"})
    registry_entry(hass, "sensor.test", device_id=device.id)
    hass.states.set("sensor.test", "unavailable")
    assert make_manager(hass, entry).records == {}


def test_connectivity_off(hass, entry):
    """A connectivity binary sensor at off becomes pending."""
    hass.states.set("binary_sensor.gateway", "off", {"device_class": "connectivity"})
    manager = make_manager(hass, entry)
    assert "connectivity:binary_sensor.gateway" in manager.records


def test_unifi_tracker_away(hass, entry, registry_entry, config_entry):
    """Only router-backed UniFi trackers away from home trigger UniFi detection."""
    config_entry(hass, "unifi")
    registry_entry(hass, "device_tracker.ap", platform="unifi")
    hass.states.set("device_tracker.ap", "not_home", {"source_type": "router"})
    manager = make_manager(hass, entry)
    assert "unifi:device_tracker.ap" in manager.records


def test_battery_global_threshold(hass, entry):
    """Battery device class uses the global category threshold."""
    hass.states.set("sensor.battery", "15", {"device_class": "battery"})
    manager = make_manager(hass, entry)
    assert manager.records["battery:sensor.battery"].details.value == 15.0


def test_automatic_pack_messages_follow_home_assistant_language(hass, entry):
    """Sensors and events receive localized pack messages, including English."""
    hass.config.language = "en"
    hass.states.set("sensor.offline", "unavailable")
    hass.states.set("sensor.battery", "10", {"device_class": "battery"})
    manager = make_manager(hass, entry)

    unavailable = manager.records["unavailable:sensor.offline"].details
    battery = manager.records["battery:sensor.battery"].details
    assert unavailable.condition == unavailable.message == "State is unavailable"
    assert battery.condition == battery.message == "Battery less than or equal to 15%"

    run(
        manager.async_update_config(
            {
                "entity_delays": {
                    "sensor.offline": 0,
                    "sensor.battery": 0,
                }
            }
        )
    )
    started_messages = {
        event["message"]
        for event_type, event in hass.bus.fired
        if event_type == EVENT_ALERT_STARTED
    }
    assert started_messages == {
        "State is unavailable",
        "Battery less than or equal to 15%",
    }
    device_messages = {
        message
        for device in manager.public_snapshot()["active_devices"]
        for message in device["messages"]
    }
    assert device_messages == started_messages


def test_battery_ignores_low_battery_level_attribute(hass, entry):
    """Only pack-owned global and device thresholds affect battery alerts."""
    hass.states.set(
        "sensor.battery",
        "20",
        {"device_class": "battery", "low_battery_level": 25},
    )
    manager = make_manager(hass, entry)
    assert "battery:sensor.battery" not in manager.records


def test_battery_device_threshold_overrides_entity_and_global_thresholds(
    hass, entry, registry_entry, device_entry
):
    """The battery pack owns a replaceable per-device threshold mapping."""
    device = device_entry(hass, name="Télécommande")
    registry_entry(hass, "sensor.remote_battery", device_id=device.id)
    hass.states.set(
        "sensor.remote_battery",
        "20",
        {"device_class": "battery", "low_battery_level": 10},
    )
    manager = make_manager(hass, entry)
    assert "battery:sensor.remote_battery" not in manager.records

    run(
        manager.async_update_config(
            {"automatic": {"battery": {"device_thresholds": {device.id: 25}}}}
        )
    )
    record = manager.records["battery:sensor.remote_battery"]
    assert "25 %" in record.details.condition

    run(
        manager.async_update_config(
            {"automatic": {"battery": {"device_thresholds": {}}}}
        )
    )
    assert manager.config["automatic"]["battery"]["device_thresholds"] == {}
    assert "battery:sensor.remote_battery" not in manager.records


def test_custom_rule_requires_its_optional_jinja_condition(hass, entry):
    """A tracked Jinja dependency can open and resolve a matching rule."""
    hass.states.set("sensor.source", "on")
    hass.states.set("input_boolean.guard", "off")

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(
            {
                "name": "Guarded rule",
                "entity_ids": ["sensor.source"],
                "operator": "equals",
                "value": "on",
                "duration": 0,
                "condition_template": "{{ is_state('input_boolean.guard', 'on') }}",
            }
        )
        alert_id = f"rule:{rule['id']}:sensor.source"
        assert alert_id not in manager.records

        hass.states.set("input_boolean.guard", "on")
        manager._state_changed(Event({"entity_id": "input_boolean.guard"}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert manager.records[alert_id].status is AlertStatus.ACTIVE

        hass.states.set("input_boolean.guard", "off")
        manager._state_changed(Event({"entity_id": "input_boolean.guard"}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert alert_id not in manager.records

    run(scenario())


def test_jinja_only_rule_uses_only_its_template_and_keeps_duration(
    hass, entry, set_now
):
    """A comparison-free rule follows Jinja while retaining pending timing."""
    start = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.source", "comparison-does-not-matter")
    hass.states.set("input_boolean.guard", "on")

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(
            {
                "name": "Pure Jinja",
                "entity_ids": ["sensor.source"],
                "source": "jinja",
                "duration": 60,
                "condition_template": "{{ is_state('input_boolean.guard', 'on') }}",
            }
        )
        alert_id = f"rule:{rule['id']}:sensor.source"
        record = manager.records[alert_id]
        assert record.status is AlertStatus.PENDING
        assert record.due_at == start + timedelta(seconds=60)
        assert record.details.condition_key == "rule.jinja"
        assert record.details.operator is None
        assert record.details.comparison_value is None

        hass.states.set("input_boolean.guard", "off")
        manager._state_changed(Event({"entity_id": "input_boolean.guard"}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert alert_id not in manager.records

    run(scenario())


def test_unchanged_rule_resets_for_state_and_attribute_updates(hass, entry, set_now):
    """No-change rules restart on either part of a Home Assistant state."""
    start = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.source", "idle", {"sequence": 1})

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(
            {
                "name": "No updates",
                "entity_ids": ["sensor.source"],
                "source": "unchanged",
                "duration": 60,
            }
        )
        alert_id = f"rule:{rule['id']}:sensor.source"
        record = manager.records[alert_id]
        assert record.detected_at == start
        assert record.due_at == start + timedelta(seconds=60)
        assert record.details.condition_key == "rule.unchanged"
        assert record.details.operator is None
        assert record.details.comparison_value is None

        attribute_update = start + timedelta(seconds=30)
        set_now(attribute_update)
        hass.states.set("sensor.source", "idle", {"sequence": 2})
        await manager.async_evaluate_entity("sensor.source")
        record = manager.records[alert_id]
        assert record.status is AlertStatus.PENDING
        assert record.detected_at == attribute_update
        assert record.due_at == attribute_update + timedelta(seconds=60)

        set_now(start + timedelta(seconds=45))
        hass.states.set(
            "sensor.source",
            "idle",
            {"sequence": 2},
            last_updated=attribute_update,
        )
        await manager.async_evaluate_entity("sensor.source")
        assert manager.records[alert_id].detected_at == attribute_update

        set_now(attribute_update + timedelta(seconds=61))
        await manager.async_evaluate_entity("sensor.source")
        assert manager.records[alert_id].status is AlertStatus.ACTIVE

        state_update = start + timedelta(seconds=100)
        set_now(state_update)
        hass.states.set("sensor.source", "running", {"sequence": 2})
        await manager.async_evaluate_entity("sensor.source")
        record = manager.records[alert_id]
        assert record.status is AlertStatus.PENDING
        assert record.detected_at == state_update
        assert record.due_at == state_update + timedelta(seconds=60)
        resolved = [
            data
            for event_type, data in hass.bus.fired
            if event_type == EVENT_ALERT_RESOLVED and data["id"] == alert_id
        ]
        assert len(resolved) == 1

    run(scenario())


def test_unchanged_rule_accepts_an_optional_jinja_filter(hass, entry, set_now):
    """Jinja can filter inactivity but is not required by validation."""
    start = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.source", "idle")
    hass.states.set("input_boolean.guard", "off")

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(
            {
                "name": "Filtered inactivity",
                "entity_ids": ["sensor.source"],
                "source": "unchanged",
                "duration": 60,
                "condition_template": ("{{ is_state('input_boolean.guard', 'on') }}"),
            }
        )
        alert_id = f"rule:{rule['id']}:sensor.source"
        assert alert_id not in manager.records

        set_now(start + timedelta(seconds=61))
        hass.states.set("input_boolean.guard", "on")
        manager._state_changed(Event({"entity_id": "input_boolean.guard"}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        record = manager.records[alert_id]
        assert record.status is AlertStatus.PENDING
        assert record.detected_at == start + timedelta(seconds=61)

        set_now(start + timedelta(seconds=122))
        await manager.async_evaluate_entity("sensor.source")
        assert manager.records[alert_id].status is AlertStatus.ACTIVE

    run(scenario())


def test_selected_state_unchanged_ignores_attribute_updates(hass, entry, set_now):
    """State no-change restarts only when the main state value changes."""
    start = datetime(2026, 8, 29, 11, 0, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.source", "idle", {"sequence": 1})

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(
            {
                "name": "Stable state",
                "entity_ids": ["sensor.source"],
                "source": "state",
                "operator": "unchanged",
                "duration": 60,
            }
        )
        alert_id = f"rule:{rule['id']}:sensor.source"
        assert manager.records[alert_id].detected_at == start

        set_now(start + timedelta(seconds=30))
        hass.states.set("sensor.source", "idle", {"sequence": 2})
        await manager.async_evaluate_entity("sensor.source")
        assert manager.records[alert_id].detected_at == start

        changed_at = start + timedelta(seconds=40)
        set_now(changed_at)
        hass.states.set("sensor.source", "running", {"sequence": 2})
        await manager.async_evaluate_entity("sensor.source")
        record = manager.records[alert_id]
        assert record.detected_at == changed_at
        assert record.details.value == "running"
        assert record.details.condition_key == "rule.selected_unchanged"
        assert record.details.comparison_value is None

    run(scenario())


def test_selected_attribute_unchanged_and_array_wildcard(hass, entry, set_now):
    """Attribute inactivity and wildcard comparisons use only extracted values."""
    start = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    set_now(start)
    hass.states.set(
        "sensor.pool",
        "ok",
        {
            "data": [
                {"code": "8.33", "key": "enjoy"},
                {"code": "8.34", "key": "redox"},
            ],
            "sequence": 1,
        },
    )

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        stable = await manager.async_create_rule(
            {
                "name": "Stable keys",
                "entity_ids": ["sensor.pool"],
                "source": "attribute",
                "attribute": "data.*.key",
                "operator": "unchanged",
                "duration": 60,
            }
        )
        matching = await manager.async_create_rule(
            {
                "name": "Redox present",
                "entity_ids": ["sensor.pool"],
                "source": "attribute",
                "attribute": "data.*.key",
                "operator": "equals",
                "value": ["redox", "flow"],
                "duration": 0,
            }
        )
        stable_id = f"rule:{stable['id']}:sensor.pool"
        matching_id = f"rule:{matching['id']}:sensor.pool"
        assert manager.records[stable_id].details.value == ["enjoy", "redox"]
        assert manager.records[matching_id].status is AlertStatus.ACTIVE

        set_now(start + timedelta(seconds=20))
        hass.states.set(
            "sensor.pool",
            "changed state",
            {
                "data": [
                    {"code": "new", "key": "enjoy"},
                    {"code": "new", "key": "redox"},
                ],
                "sequence": 2,
            },
        )
        await manager.async_evaluate_entity("sensor.pool")
        assert manager.records[stable_id].detected_at == start

        changed_at = start + timedelta(seconds=30)
        set_now(changed_at)
        hass.states.set(
            "sensor.pool",
            "changed state",
            {"data": [{"code": "8.35", "key": "ph"}]},
        )
        await manager.async_evaluate_entity("sensor.pool")
        assert manager.records[stable_id].detected_at == changed_at
        assert manager.records[stable_id].details.value == ["ph"]
        assert matching_id not in manager.records

    run(scenario())


def test_editing_to_selected_unchanged_starts_a_new_inactivity_window(
    hass, entry, set_now
):
    """Changing comparison semantics cannot reuse an older active occurrence."""
    start = datetime(2026, 8, 29, 13, 0, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.source", "on", {"sequence": 1})

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(
            {
                "name": "State rule",
                "entity_ids": ["sensor.source"],
                "source": "state",
                "operator": "equals",
                "value": "on",
                "duration": 0,
            }
        )
        alert_id = f"rule:{rule['id']}:sensor.source"
        assert manager.records[alert_id].status is AlertStatus.ACTIVE

        changed_at = start + timedelta(seconds=120)
        set_now(changed_at)
        await manager.async_update_rule(
            rule["id"],
            {
                "source": "attribute",
                "attribute": "sequence",
                "operator": "unchanged",
                "duration": 60,
            },
        )

        record = manager.records[alert_id]
        assert record.status is AlertStatus.PENDING
        assert record.detected_at == changed_at
        assert record.due_at == changed_at + timedelta(seconds=60)

    run(scenario())


def test_custom_rule_rejects_invalid_jinja_syntax(hass, entry):
    """Invalid templates never reach storage or runtime evaluation."""
    hass.states.set("sensor.source", "on")
    manager = make_manager(hass, entry)
    with pytest.raises(ValueError, match="Invalid rule condition_template"):
        run(
            manager.async_create_rule(
                {
                    "name": "Invalid Jinja",
                    "entity_ids": ["sensor.source"],
                    "operator": "equals",
                    "value": "on",
                    "duration": 0,
                    "condition_template": "{% if %}",
                }
            )
        )


def test_custom_rule_message_updates_pending_then_freezes_when_active(
    hass, entry, set_now
):
    """A Jinja message follows dependencies only until activation."""
    start = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.source", "on")
    hass.states.set("sensor.context", "warm")

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(
            {
                "name": "Templated message",
                "entity_ids": ["sensor.source"],
                "operator": "equals",
                "value": "on",
                "duration": 60,
                "message": (
                    "{{ entity_id }} vaut {{ value }} et le contexte est "
                    "{{ states('sensor.context') }}"
                ),
            }
        )
        alert_id = f"rule:{rule['id']}:sensor.source"
        expected = "sensor.source vaut on et le contexte est warm"
        record = manager.records[alert_id]
        condition = record.details.condition
        assert record.status is AlertStatus.PENDING
        assert record.details.message == expected
        assert condition != expected
        assert record.details.condition_key == "rule.generated"

        hass.states.set("sensor.context", "hot")
        manager._state_changed(Event({"entity_id": "sensor.context"}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        updated = "sensor.source vaut on et le contexte est hot"
        assert manager.records[alert_id].details.message == updated
        assert manager.records[alert_id].details.condition == condition

        set_now(start + timedelta(seconds=60))
        await manager.async_evaluate_entity("sensor.source")
        assert manager.records[alert_id].status is AlertStatus.ACTIVE

        hass.states.set("sensor.context", "cold")
        manager._state_changed(Event({"entity_id": "sensor.context"}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert manager.records[alert_id].details.message == updated
        assert manager.records[alert_id].details.condition == condition
        assert (
            hass.stores["alert_manager"]["alerts"][alert_id]["details"]["message"]
            == updated
        )

        await manager.async_unload()
        reloaded = AlertManager(hass, entry)
        await reloaded.async_setup()
        assert reloaded.records[alert_id].details.message == updated
        assert reloaded.records[alert_id].details.condition == condition

    run(scenario())


def test_custom_rule_can_keep_updating_message_while_active(hass, entry, set_now):
    """Live messages update in memory but batch Store and Recorder writes."""
    start = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.source", "on")
    hass.states.set("sensor.context", "warm")

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(
            {
                "name": "Live templated message",
                "entity_ids": ["sensor.source"],
                "operator": "equals",
                "value": "on",
                "duration": 0,
                "message": "Context: {{ states('sensor.context') }}",
                "update_message_when_active": True,
            }
        )
        alert_id = f"rule:{rule['id']}:sensor.source"
        record = manager.records[alert_id]
        assert record.status is AlertStatus.ACTIVE
        assert record.details.message == "Context: warm"
        assert (
            "message",
            rule["id"],
            "sensor.source",
        ) in manager._template_entities_by_key
        saves_before_update = hass.store_save_count
        updates = []
        hass.dispatchers[SIGNAL_ALERTS_UPDATED].append(lambda: updates.append(True))

        hass.states.set("sensor.context", "cold")
        manager._state_changed(Event({"entity_id": "sensor.context"}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert record.details.message == "Context: cold"
        assert record.details.condition != record.details.message
        assert record.details.condition_key == "rule.generated"
        assert hass.store_save_count == saves_before_update
        assert (
            hass.stores["alert_manager"]["alerts"][alert_id]["details"]["message"]
            == "Context: warm"
        )
        assert updates == []
        public_record = next(
            alert
            for alert in manager.public_snapshot()["alerts"]
            if alert["id"] == alert_id
        )
        assert public_record["message"] == "Context: cold"

        hass.states.set("sensor.context", "hot")
        manager._state_changed(Event({"entity_id": "sensor.context"}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert record.details.message == "Context: hot"
        assert hass.store_save_count == saves_before_update
        assert updates == []

        live_timer = next(
            timer
            for timer in reversed(hass.timers)
            if not timer["cancelled"]
            and timer["point"] == start + timedelta(seconds=30)
        )
        live_timer["action"](live_timer["point"])
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert hass.store_save_count == saves_before_update + 1
        assert (
            hass.stores["alert_manager"]["alerts"][alert_id]["details"]["message"]
            == "Context: hot"
        )
        assert updates == [True]

    run(scenario())


def test_custom_rule_rejects_invalid_message_jinja_syntax(hass, entry):
    """An invalid Jinja message is rejected before it reaches storage."""
    hass.states.set("sensor.source", "on")
    manager = make_manager(hass, entry)
    with pytest.raises(ValueError, match="Invalid rule message template"):
        run(
            manager.async_create_rule(
                {
                    "name": "Invalid message",
                    "entity_ids": ["sensor.source"],
                    "operator": "equals",
                    "value": "on",
                    "duration": 0,
                    "message": "{% if %}",
                }
            )
        )


@pytest.mark.parametrize(
    ("operator", "state", "expected"),
    [
        ("equals", "off", "off"),
        ("not_equals", "ERROR", "OL CHRG"),
        ("contains", "OL CHRG", ["ERROR", "CHRG"]),
        ("not_contains", "OL CHRG", ["ERROR", "WARN"]),
        ("above", "11.2", 9),
        ("below", "0.8", 1),
    ],
)
def test_custom_rule_operator(hass, entry, operator, state, expected):
    """Every custom-rule operator creates the stable rule alert id."""
    hass.states.set("sensor.test", state)
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "Rule",
                "entity_ids": ["sensor.test"],
                "operator": operator,
                "value": expected,
                "duration": 300,
                "enabled": True,
                "source": "state",
            }
        )
    )
    record = manager.records[f"rule:{rule['id']}:sensor.test"]
    assert record.details.rule_id == rule["id"]
    assert record.details.rule_name == "Rule"
    assert record.details.condition_key == "rule.generated"
    assert record.details.condition_params == {
        "source": "state",
        "attribute": None,
        "operator": operator,
        "expected": (
            " / ".join(str(value) for value in expected)
            if isinstance(expected, list)
            else str(expected)
        ),
        "unit": None,
        "duration": 300,
    }


def test_custom_rule_message_does_not_replace_condition(hass, entry):
    """A custom message remains separate from the structured rule condition."""
    hass.states.set("sensor.test", "on")
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "User rule",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "on",
                "duration": 0,
                "message": "My custom message",
            }
        )
    )
    details = manager.records[f"rule:{rule['id']}:sensor.test"].details
    assert details.message == "My custom message"
    assert details.condition != details.message
    assert details.condition_key == "rule.generated"
    assert details.condition_params == {
        "source": "state",
        "attribute": None,
        "operator": "equals",
        "expected": "on",
        "unit": None,
        "duration": 0,
    }


def test_editing_active_rule_message_preserves_condition(hass, entry):
    """Explicit message edits cannot overwrite an active alert condition."""
    hass.states.set("sensor.test", "on")
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "User rule",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "on",
                "duration": 0,
                "message": "Old message",
            }
        )
    )
    alert_id = f"rule:{rule['id']}:sensor.test"
    condition = manager.records[alert_id].details.condition

    run(manager.async_update_rule(rule["id"], {"message": "New message"}))

    details = manager.records[alert_id].details
    assert details.message == "New message"
    assert details.condition == condition
    assert details.condition_key == "rule.generated"


def test_delay_priority(hass, entry):
    """Entity, pack and global delays follow the documented priority."""
    hass.states.set("sensor.test", "unavailable")
    hass.states.set("sensor.custom", "on")
    manager = make_manager(hass, entry)
    run(
        manager.async_update_config(
            {
                "global_delay": 100,
                "automatic": {"unavailable": {"delay": 80}},
                "entity_delays": {"sensor.test": 20},
            }
        )
    )
    assert manager.records["unavailable:sensor.test"].delay == 20

    run(manager.async_update_config({"entity_delays": {}}))
    assert manager.records["unavailable:sensor.test"].delay == 80

    run(manager.async_update_config({"automatic": {"unavailable": {"delay": None}}}))
    assert manager.records["unavailable:sensor.test"].delay == 100

    run(manager.async_update_config({"entity_delays": {"sensor.custom": 1}}))
    rule = run(
        manager.async_create_rule(
            {
                "name": "Custom duration",
                "entity_ids": ["sensor.custom"],
                "operator": "equals",
                "value": "on",
                "duration": 10,
            }
        )
    )
    assert manager.records[f"rule:{rule['id']}:sensor.custom"].delay == 10


def test_shortened_automatic_delay_uses_real_activation_time(hass, entry, set_now):
    """A pending alert activated by a shorter delay starts at the config change."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)

    changed_at = start + timedelta(minutes=15)
    set_now(changed_at)
    run(manager.async_update_config({"automatic": {"unavailable": {"delay": 10}}}))

    record = manager.records["unavailable:sensor.test"]
    assert record.status is AlertStatus.ACTIVE
    assert record.due_at == start + timedelta(seconds=10)
    assert record.active_since == changed_at


def test_missing_rule_attribute_does_not_trigger_not_equals(hass, entry):
    """A missing attribute is not treated as an arbitrary comparison value."""
    hass.states.set("sensor.test", "ok", {})
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "Missing attribute",
                "entity_ids": ["sensor.test"],
                "source": "attribute",
                "attribute": "missing",
                "operator": "not_equals",
                "value": "ok",
                "duration": 60,
            }
        )
    )
    assert f"rule:{rule['id']}:sensor.test" not in manager.records


def test_unchanged_global_evaluation_does_not_publish(hass, entry):
    """Registry reevaluation does not cause a redundant sensor/Recorder write."""
    manager = make_manager(hass, entry)
    notifications = []
    hass.dispatchers["alert_manager_alerts_updated"].append(
        lambda: notifications.append(True)
    )
    run(manager.async_evaluate_all())
    assert notifications == []


def test_publication_groups_active_devices_once(hass, entry, monkeypatch):
    """One publication reuses device groups for the snapshot and event debounce."""
    manager = make_manager(hass, entry)
    original = manager._active_device_groups
    calls = 0

    def count_groups(active_records=None):
        nonlocal calls
        calls += 1
        return original(active_records)

    monkeypatch.setattr(manager, "_active_device_groups", count_groups)
    manager._publish_if_changed(force=True)

    assert calls == 1


def test_unavailable_monitors_every_domain_but_not_alert_manager(
    hass, entry, registry_entry
):
    """Unavailable applies to all domains while excluding the integration itself."""
    hass.states.set("automation.unrelated", "unavailable")
    hass.states.set("sensor.relevant", "unavailable")
    registry_entry(hass, "sensor.alert_manager_copy", platform="alert_manager")
    hass.states.set("sensor.alert_manager_copy", "unavailable")
    for entity_id in ALERT_MANAGER_ENTITY_IDS:
        hass.states.set(entity_id, "unavailable")
    manager = make_manager(hass, entry)
    assert set(manager.records) == {
        "unavailable:automation.unrelated",
        "unavailable:sensor.relevant",
    }


def test_custom_rules_reject_alert_manager_entities(hass, entry, registry_entry):
    """Visual and YAML-backed rule APIs cannot monitor the integration itself."""
    registry_entry(hass, "sensor.renamed_alerts", platform="alert_manager")
    manager = make_manager(hass, entry)
    payload = {
        "name": "Self monitoring",
        "entity_ids": ["sensor.alert_manager_main_active"],
        "operator": "above",
        "value": 0,
        "duration": 0,
        "enabled": True,
        "source": "state",
    }

    with pytest.raises(ValueError, match="Alert Manager entities"):
        run(manager.async_create_rule(payload))

    payload["entity_ids"] = ["sensor.renamed_alerts"]
    with pytest.raises(ValueError, match="Alert Manager entities"):
        run(manager.async_create_rule(payload))


def test_coherence_issue_sensor_is_a_loop_safe_custom_rule_source(hass, entry):
    """Only the coherence result sensor can feed a custom Alert Manager rule."""
    entity_id = "sensor.alert_manager_coherence_issue"
    hass.states.set(
        entity_id,
        "2",
        {"scanned_at": "2026-08-24T12:00:00+00:00"},
    )
    manager = make_manager(hass, entry)
    created = run(
        manager.async_create_rule(
            {
                "name": "Coherence issues",
                "entity_ids": [entity_id],
                "operator": "above",
                "value": 0,
                "duration": 0,
                "enabled": True,
                "source": "state",
                "message": "{{ states('sensor.alert_manager_coherence_issue') }}",
            }
        )
    )

    alert_id = f"rule:{created['id']}:{entity_id}"
    assert alert_id in manager.records
    assert manager.records[alert_id].status is AlertStatus.ACTIVE
    assert manager.records[alert_id].details.message == "2"
    assert f"unavailable:{entity_id}" not in manager.records


def test_coherence_schedule_is_replaced_and_cancelled_with_configuration(hass, entry):
    """Changing or disabling the schedule never leaves duplicate listeners."""
    manager = make_manager(hass, entry)
    assert manager.config["coherence_schedule"] == "none"
    assert not [timer for timer in hass.timers if "hour" in timer]

    run(manager.async_update_config({"coherence_schedule": "daily"}))
    first = next(timer for timer in hass.timers if "hour" in timer)
    assert first["cancelled"] is False
    assert hass.stores["alert_manager"]["config"]["coherence_schedule"] == "daily"

    run(manager.async_update_config({"coherence_schedule": "weekly"}))
    live = [
        timer for timer in hass.timers if "hour" in timer and not timer["cancelled"]
    ]
    assert first["cancelled"] is True
    assert len(live) == 1

    run(manager.async_update_config({"coherence_schedule": "none"}))
    assert live[0]["cancelled"] is True
    assert not [
        timer for timer in hass.timers if "hour" in timer and not timer["cancelled"]
    ]


def test_existing_self_rules_are_preserved_for_manual_recovery(hass, entry):
    """An obsolete invalid self-rule is preserved instead of being deleted."""
    stored = {
        "config": {
            "rules": [
                {
                    "id": "self-rule",
                    "name": "Self monitoring",
                    "entity_ids": ["sensor.alert_manager_main_pending"],
                    "operator": "above",
                    "value": 0,
                    "duration": 0,
                }
            ]
        },
        "alerts": {},
    }
    hass.stores["alert_manager"] = deepcopy(stored)

    manager = make_manager(hass, entry)

    assert manager.recovery_active is True
    assert manager.get_config()["rules"] == []
    assert hass.stores["alert_manager"] == stored


def test_state_listener_skips_irrelevant_entities(hass, entry):
    """Unrelated state events do not allocate config-entry evaluation tasks."""
    manager = make_manager(hass, entry)
    run(
        manager.async_update_config(
            {
                "automatic": {
                    "unavailable": {"enabled": False},
                    "connectivity": {"enabled": False},
                    "unifi": {"enabled": False},
                    "battery": {"enabled": False},
                    "execution_errors": {"enabled": False},
                }
            }
        )
    )
    entry.created_task_names.clear()

    async def fire_events():
        manager._state_changed(Event({"entity_id": "automation.unrelated"}))
        await asyncio.sleep(0)

    run(fire_events())
    assert entry.created_task_names == []


def test_rule_mutation_uses_one_atomic_storage_write(hass, entry):
    """A rule change and its immediate evaluation persist in one snapshot."""
    hass.states.set("sensor.test", "on")
    manager = make_manager(hass, entry)
    hass.store_save_count = 0
    run(
        manager.async_create_rule(
            {
                "name": "One write",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "on",
                "duration": 0,
            }
        )
    )
    assert hass.store_save_count == 1


def test_configuration_write_failure_restores_runtime_state(hass, entry):
    """A failed settings write leaves configuration, alerts and timers unchanged."""
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)
    before_config = manager.get_config()
    before_records = deepcopy(manager.records)

    async def fail_save(_config, _records, **_kwargs):
        raise OSError("storage unavailable")

    manager.storage.async_save = fail_save
    with pytest.raises(OSError, match="storage unavailable"):
        run(manager.async_update_config({"entity_delays": {"sensor.test": 0}}))
    assert manager.get_config() == before_config
    assert manager.records == before_records
    assert [timer for timer in hass.timers if not timer["cancelled"]]


def test_runtime_write_failure_is_retried_without_another_state_change(
    hass, entry, set_now
):
    """An unchanged evaluation persists a transition left dirty by a failed write."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)
    alert_id = "unavailable:sensor.test"
    set_now(manager.records[alert_id].due_at + timedelta(seconds=1))
    run(manager.async_evaluate_entity("sensor.test"))
    assert manager.records[alert_id].status is AlertStatus.ACTIVE

    original_save = manager.storage.async_save

    async def fail_save(_config, _records, **_kwargs):
        raise OSError("storage unavailable")

    manager.storage.async_save = fail_save
    hass.states.set("sensor.test", "on")
    with pytest.raises(OSError, match="storage unavailable"):
        run(manager.async_evaluate_entity("sensor.test"))
    assert alert_id not in manager.records
    assert alert_id in hass.stores["alert_manager"]["alerts"]
    assert manager._immediate_state_save_required is True
    assert (
        len([event for event, _data in hass.bus.fired if event == EVENT_ALERT_RESOLVED])
        == 1
    )

    manager.storage.async_save = original_save
    run(manager.async_evaluate_entity("sensor.test"))

    assert manager._immediate_state_save_required is False
    assert hass.stores["alert_manager"]["alerts"] == {}
    assert (
        len([event for event, _data in hass.bus.fired if event == EVENT_ALERT_RESOLVED])
        == 1
    )


def test_rule_write_failures_restore_create_update_and_delete(hass, entry):
    """Every rule mutation rolls back fully when persistence is unavailable."""
    hass.states.set("sensor.test", "on")
    manager = make_manager(hass, entry)
    payload = {
        "name": "Atomic rule",
        "entity_ids": ["sensor.test"],
        "operator": "equals",
        "value": "on",
        "duration": 60,
    }
    original_save = manager.storage.async_save

    async def fail_save(_config, _records, **_kwargs):
        raise OSError("storage unavailable")

    manager.storage.async_save = fail_save
    with pytest.raises(OSError, match="storage unavailable"):
        run(manager.async_create_rule(payload))
    assert manager.get_config()["rules"] == []
    assert manager.records == {}
    assert_record_index(manager)

    manager.storage.async_save = original_save
    rule = run(manager.async_create_rule(payload))
    before_config = manager.get_config()
    before_records = deepcopy(manager.records)
    manager.storage.async_save = fail_save

    with pytest.raises(OSError, match="storage unavailable"):
        run(manager.async_update_rule(rule["id"], {"duration": 0}))
    assert manager.get_config() == before_config
    assert manager.records == before_records
    assert_record_index(manager)

    with pytest.raises(OSError, match="storage unavailable"):
        run(manager.async_delete_rule(rule["id"]))
    assert manager.get_config() == before_config
    assert manager.records == before_records
    assert_record_index(manager)


def test_failed_rule_mutation_restores_startup_provenance(hass, entry, set_now):
    """Rollback keeps the marker that protects a restored pending occurrence."""
    start = datetime(2026, 9, 4, 10, tzinfo=UTC)
    set_now(start)
    hass.states.set("binary_sensor.pool_filter", "on")

    async def scenario():
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
        set_now(start + timedelta(minutes=6))
        await first._async_flush_mature_pending()
        await first.async_unload()

        hass.state = CoreState.starting
        hass.states.set("binary_sensor.pool_filter", "unknown")
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        assert alert_id in restarted._unverified_restored_alert_ids

        async def fail_save(*_args, **_kwargs):
            raise OSError("storage unavailable")

        restarted.storage.async_save = fail_save
        with pytest.raises(OSError, match="storage unavailable"):
            await restarted.async_delete_rule(rule["id"])

        assert alert_id in restarted.records
        assert alert_id in restarted._unverified_restored_alert_ids
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert alert_id in restarted.records
        assert alert_id in restarted._unverified_restored_alert_ids

    run(scenario())


def test_custom_rule_entities_have_independent_lifecycles(hass, entry, set_now):
    """Each rule/entity pair owns its pending clock, activation and resolution."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.one", "on", {"friendly_name": "Capteur un"})
    hass.states.set("sensor.two", "on", {"friendly_name": "Capteur deux"})
    hass.states.set("sensor.three", "off")
    manager = make_manager(hass, entry)
    run(manager.async_update_config({"pending_display_delay": 0}))
    rule = run(
        manager.async_create_rule(
            {
                "name": "Plusieurs sources",
                "entity_ids": ["sensor.one", "sensor.two", "sensor.three"],
                "operator": "equals",
                "value": "on",
                "duration": 60,
            }
        )
    )
    one_id = f"rule:{rule['id']}:sensor.one"
    two_id = f"rule:{rule['id']}:sensor.two"
    assert set(manager.records) == {one_id, two_id}
    assert manager.public_snapshot()["pending_count"] == 2
    assert manager.records[one_id].details.name == "Capteur un"

    set_now(start + timedelta(seconds=30))
    hass.states.set("sensor.one", "off")
    run(manager.async_evaluate_entity("sensor.one"))
    assert one_id not in manager.records
    assert manager.records[two_id].detected_at == start

    set_now(start + timedelta(seconds=60))
    run(manager.async_evaluate_entity("sensor.two"))
    assert manager.records[two_id].status is AlertStatus.ACTIVE
    snapshot = manager.public_snapshot()
    assert snapshot["active_count"] == 1
    assert snapshot["pending_count"] == 0

    hass.states.set("sensor.one", "on")
    run(manager.async_evaluate_entity("sensor.one"))
    assert manager.records[one_id].detected_at == start + timedelta(seconds=60)
    assert manager.records[one_id].status is AlertStatus.PENDING


def test_same_entity_can_belong_to_multiple_rules(hass, entry):
    """Rule ids keep two matching rules on the same source independent."""
    hass.states.set("sensor.test", "on")
    manager = make_manager(hass, entry)
    rules = [
        run(
            manager.async_create_rule(
                {
                    "name": name,
                    "entity_ids": ["sensor.test"],
                    "operator": "equals",
                    "value": "on",
                    "duration": 0,
                    "message": f"{name} message",
                }
            )
        )
        for name in ("First", "Second")
    ]
    assert set(manager.records) == {f"rule:{rule['id']}:sensor.test" for rule in rules}
    snapshot = manager.public_snapshot()
    assert snapshot["active_count"] == 2
    assert snapshot["active_devices"][0]["messages"] == [
        "First message",
        "Second message",
    ]
    assert snapshot["active_devices"][0]["rules"] == ["First", "Second"]


def test_device_event_debounces_new_alerts_and_includes_rule_message_arrays(
    hass, entry, registry_entry, device_entry
):
    """The device event waits for ten quiet seconds and emits the final group."""
    device = device_entry(hass, name="Baie")
    registry_entry(hass, "sensor.rack", device_id=device.id)
    hass.states.set("sensor.rack", "hot")
    manager = make_manager(hass, entry)

    first = run(
        manager.async_create_rule(
            {
                "name": "Temperature",
                "entity_ids": ["sensor.rack"],
                "operator": "equals",
                "value": "hot",
                "duration": 0,
                "message": "Rack hot",
            }
        )
    )
    first_timer = next(
        timer
        for timer in reversed(hass.timers)
        if not timer["cancelled"]
        and "_schedule_device_event_timer" in timer["action"].__qualname__
    )
    assert not [
        event for event, _data in hass.bus.fired if event == EVENT_DEVICE_ALERT_STARTED
    ]

    second = run(
        manager.async_create_rule(
            {
                "name": "Ventilation",
                "entity_ids": ["sensor.rack"],
                "operator": "equals",
                "value": "hot",
                "duration": 0,
                "message": "Fan stopped",
            }
        )
    )
    assert first_timer["cancelled"] is True
    fire_device_event_timers(hass)
    events = [
        data for event, data in hass.bus.fired if event == EVENT_DEVICE_ALERT_STARTED
    ]
    assert len(events) == 1
    assert set(events[0]["alert_ids"]) == {
        f"rule:{first['id']}:sensor.rack",
        f"rule:{second['id']}:sensor.rack",
    }
    assert events[0]["messages"] == ["Rack hot", "Fan stopped"]
    assert events[0]["rules"] == ["Temperature", "Ventilation"]


def test_device_sensor_keeps_messages_and_rules_inside_each_device():
    """The device sensor exposes no misleading global message/rule arrays."""
    devices = [
        {
            "device_id": "one",
            "device_ids": ["one"],
            "device_name": "UPS one",
            "area": "Garage",
            "alert_count": 2,
            "messages": ["Battery low", "Offline"],
            "rules": ["Battery", "Unavailable"],
        },
        {
            "device_id": "two",
            "device_ids": ["two"],
            "device_name": "UPS two",
            "area": "Office",
            "alert_count": 2,
            "messages": ["Offline", "Temperature high"],
            "rules": ["Unavailable", "Temperature"],
        },
    ]
    manager = SimpleNamespace(
        monitoring_enabled=True,
        public_snapshot=lambda: {
            "device_active_count": 2,
            "active_devices": devices,
        },
    )
    sensor = AlertManagerSensor(
        manager,
        "device_main_active",
        "alert_manager_device_main_active",
        "mdi:devices",
        "device_active_count",
        "active_devices",
        "devices",
    )

    assert sensor.extra_state_attributes == {
        "devices": [
            {
                "device_ids": ["one"],
                "device_name": "UPS one",
                "alert_count": 2,
                "messages": ["Battery low", "Offline"],
                "rules": ["Battery", "Unavailable"],
            },
            {
                "device_ids": ["two"],
                "device_name": "UPS two",
                "alert_count": 2,
                "messages": ["Offline", "Temperature high"],
                "rules": ["Unavailable", "Temperature"],
            },
        ]
    }


def test_lifecycle_sensor_attributes_are_compact_and_recorder_safe():
    """Large alert collections stay below Recorder's 16 KiB attribute limit."""
    alerts = [
        {
            "id": f"rule:identifier-{index}:sensor.long_entity_{index}",
            "type": "rule",
            "entity_id": f"sensor.long_entity_{index}",
            "name": f"Redundant friendly name {index}",
            "device_id": "a" * 32,
            "device_name": "Redundant device name",
            "area": "Redundant area",
            "integration": "mqtt",
            "unit": "%",
            "value": index,
            "condition": "Value is outside its configured range",
            "message": "x" * 1024,
            "rule_name": "Long rule",
            "detected_at": "2026-08-27T10:00:00+00:00",
            "due_at": "2026-08-27T10:15:00+00:00",
        }
        for index in range(100)
    ]
    manager = SimpleNamespace(
        monitoring_enabled=True,
        public_snapshot=lambda: {
            "pending_count": len(alerts),
            "pending": alerts,
        },
    )
    sensor = AlertManagerSensor(
        manager,
        "main_pending",
        "alert_manager_main_pending",
        "mdi:clock-alert-outline",
        "pending_count",
        "pending",
        "alerts",
    )

    attributes = sensor.extra_state_attributes
    encoded = json.dumps(attributes, ensure_ascii=False, default=str).encode()

    assert len(encoded) < 16_384
    assert attributes["alerts_omitted"] > 0
    assert attributes["alerts"]
    assert {
        "name",
        "device_id",
        "device_name",
        "area",
        "integration",
        "unit",
    }.isdisjoint(attributes["alerts"][0])


def test_linear_attribute_bounding_preserves_the_previous_output():
    """The linear size accounting keeps the exact established prefix contract."""
    alerts = [
        {
            "id": f"rule:{index}:sensor.source_{index}",
            "entity_id": f"sensor.source_{index}",
            "value": {"temperature": index, "labels": ["été", "garage"]},
            "condition": f"Condition {index}",
            "message": "é" * (index % 17),
            "detected_at": "2026-08-27T10:00:00+00:00",
            "due_at": "2026-08-27T10:15:00+00:00",
        }
        for index in range(400)
    ]

    expected = []
    for alert in alerts:
        candidate = [*expected, _compact_alert(alert)]
        omitted = len(alerts) - len(candidate)
        attributes = {"alerts": candidate}
        if omitted:
            attributes["alerts_omitted"] = omitted
        if (
            len(
                json.dumps(
                    attributes,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=str,
                ).encode()
            )
            > 15_000
        ):
            break
        expected = candidate

    result = _bounded_attributes("alerts", alerts, _compact_alert)

    assert result["alerts"] == expected
    assert result["alerts_omitted"] == len(alerts) - len(expected)


def test_sensor_skips_writes_when_its_partition_did_not_change():
    """A change in another lifecycle partition does not churn this sensor."""
    snapshot = {
        "active_count": 1,
        "alerts": [{"id": "active", "entity_id": "sensor.active"}],
        "pending_count": 0,
        "pending": [],
        "tracked_count": 2,
        "startup": {"in_progress": False, "stabilization_until": None},
    }
    manager = SimpleNamespace(
        monitoring_enabled=True,
        public_snapshot=lambda: deepcopy(snapshot),
    )
    sensor = AlertManagerSensor(
        manager,
        "main_active",
        "alert_manager_main_active",
        "mdi:alert-circle",
        "active_count",
        "alerts",
        "alerts",
    )
    writes = []
    sensor.async_write_ha_state = lambda: writes.append(True)

    sensor._async_manager_updated()
    snapshot["pending_count"] = 1
    snapshot["pending"] = [{"id": "pending", "entity_id": "sensor.pending"}]
    sensor._async_manager_updated()

    assert len(writes) == 1

    snapshot["startup"] = {
        "in_progress": True,
        "stabilization_until": "2026-09-04T10:02:00+00:00",
    }
    sensor._async_manager_updated()

    assert len(writes) == 2
    assert sensor.extra_state_attributes["runtime"] == {
        "tracked_count": 2,
        "startup": snapshot["startup"],
    }


def test_tracked_count_combines_custom_instances_and_automatic_entities(
    hass, entry, registry_entry
):
    """Tracked total counts rule/entity pairs plus unique automatic sources."""
    hass.label_registry.labels["pas_d_alerte"] = SimpleNamespace(label_id="skip")
    hass.states.set("sensor.one", "ok")
    hass.states.set("sensor.two", "ok")
    registry_entry(hass, "sensor.excluded", labels={"skip"})
    hass.states.set("sensor.excluded", "ok")
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "Two custom instances",
                "entity_ids": ["sensor.one", "sensor.excluded"],
                "operator": "equals",
                "value": "alert",
                "duration": 0,
            }
        )
    )

    # Two eligible automatic entities plus two configured custom instances.
    assert manager.public_snapshot()["tracked_count"] == 4

    run(manager.async_update_rule(rule["id"], {"enabled": False}))
    assert manager.public_snapshot()["tracked_count"] == 2


def test_rule_delay_update_can_activate_immediately(hass, entry, set_now):
    """A shortened duration is recalculated from the original detection time."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "on")
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "Delay",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "on",
                "duration": 900,
            }
        )
    )
    set_now(start + timedelta(seconds=600))
    run(manager.async_update_rule(rule["id"], {"duration": 300}))
    record = manager.records[f"rule:{rule['id']}:sensor.test"]
    assert record.status is AlertStatus.ACTIVE
    assert record.due_at == start + timedelta(seconds=300)
    assert record.active_since == start + timedelta(seconds=600)


def test_removing_entity_delay_replaces_the_complete_mapping(hass, entry):
    """Saving an empty entity-delay mapping really removes existing overrides."""
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)
    run(manager.async_update_config({"entity_delays": {"sensor.test": 20}}))
    assert manager.records["unavailable:sensor.test"].delay == 20

    run(manager.async_update_config({"entity_delays": {}}))

    assert manager.config["entity_delays"] == {}
    assert manager.records["unavailable:sensor.test"].delay == 900


def test_rule_delay_extension_rechecks_an_active_instance(hass, entry, set_now):
    """Extending a duration can return a just-active instance to pending."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "on")
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "Extended delay",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "on",
                "duration": 0,
            }
        )
    )
    hass.bus.fired.clear()
    run(manager.async_update_rule(rule["id"], {"duration": 60}))
    record = manager.records[f"rule:{rule['id']}:sensor.test"]
    assert record.status is AlertStatus.PENDING
    assert record.active_since is None
    assert record.due_at == start + timedelta(seconds=60)
    assert not [
        event for event, _data in hass.bus.fired if event == EVENT_ALERT_RESOLVED
    ]


def test_entity_delay_extension_returns_active_automatic_alert_to_pending(
    hass, entry, set_now
):
    """Automatic delay changes retain the id and original detection time."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)
    run(manager.async_update_config({"entity_delays": {"sensor.test": 0}}))
    record = manager.records["unavailable:sensor.test"]
    assert record.status is AlertStatus.ACTIVE
    assert record.detected_at == start

    hass.bus.fired.clear()
    run(manager.async_update_config({"entity_delays": {"sensor.test": 60}}))
    record = manager.records["unavailable:sensor.test"]
    assert record.details.id == "unavailable:sensor.test"
    assert record.detected_at == start
    assert record.due_at == start + timedelta(seconds=60)
    assert record.status is AlertStatus.PENDING
    assert record.active_since is None
    assert not [
        event for event, _data in hass.bus.fired if event == EVENT_ALERT_RESOLVED
    ]


def test_pack_availability_cleans_timers_and_preserves_enabled_choice(
    hass, entry, registry_entry, config_entry
):
    """An unavailable conditional pack is inert without changing its setting."""
    registry_entry(hass, "device_tracker.ap", platform="unifi")
    hass.states.set("device_tracker.ap", "not_home", {"source_type": "router"})
    manager = make_manager(hass, entry)
    metadata = {pack["id"]: pack for pack in manager.get_packs()}
    assert metadata["unavailable"]["available"] is True
    assert metadata["connectivity"]["available"] is True
    assert metadata["battery"]["available"] is True
    assert metadata["unifi"]["available"] is False
    assert manager.records == {}
    assert manager._timers == {}

    unifi_entry = config_entry(hass, "unifi")
    assert run(manager.async_refresh_pack_availability()) is True
    assert "unifi:device_tracker.ap" in manager.records
    assert manager.get_config()["automatic"]["unifi"]["enabled"] is True
    assert manager._timers

    unifi_entry.state = ConfigEntryState.NOT_LOADED
    assert run(manager.async_refresh_pack_availability()) is True
    assert manager.records == {}
    assert manager._timers == {}
    assert manager.get_config()["automatic"]["unifi"]["enabled"] is True

    unifi_entry.state = ConfigEntryState.LOADED
    assert run(manager.async_refresh_pack_availability()) is True
    assert "unifi:device_tracker.ap" in manager.records
    assert manager.get_config()["automatic"]["unifi"]["enabled"] is True


def test_pack_entry_state_listener_re_evaluates_automatically(
    hass, entry, registry_entry, config_entry
):
    """A prerequisite entry state transition schedules the availability refresh."""
    unifi_entry = config_entry(hass, "unifi")
    registry_entry(hass, "device_tracker.ap", platform="unifi")
    hass.states.set("device_tracker.ap", "not_home", {"source_type": "router"})

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        assert "unifi:device_tracker.ap" in manager.records

        unifi_entry.set_state(ConfigEntryState.NOT_LOADED)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert "unifi:device_tracker.ap" not in manager.records
        assert entry.created_task_names[-1] == "alert_manager pack-availability batch"

    run(scenario())


@pytest.mark.parametrize(
    ("state", "disabled_by", "source"),
    [
        (ConfigEntryState.NOT_LOADED, None, "user"),
        (ConfigEntryState.LOADED, "user", "user"),
        (ConfigEntryState.LOADED, None, "ignore"),
    ],
)
def test_unifi_pack_requires_a_usable_config_entry(
    hass, entry, config_entry, state, disabled_by, source
):
    """Unloaded, disabled and ignored UniFi entries do not enable the pack."""
    config_entry(
        hass,
        "unifi",
        state=state,
        disabled_by=disabled_by,
        source=source,
    )
    manager = make_manager(hass, entry)
    unifi = next(pack for pack in manager.get_packs() if pack["id"] == "unifi")
    assert unifi["available"] is False


def test_same_device_alerts_remain_individual_in_state_and_events(
    hass, entry, registry_entry, device_entry
):
    """Device grouping data never changes individual counters or events."""
    device = device_entry(hass, name="Onduleur")
    registry_entry(hass, "sensor.ups_status", device_id=device.id)
    registry_entry(hass, "sensor.ups_battery", device_id=device.id)
    hass.states.set("sensor.ups_status", "unavailable")
    hass.states.set("sensor.ups_battery", "unavailable")
    manager = make_manager(hass, entry)
    run(
        manager.async_update_config(
            {
                "entity_delays": {
                    "sensor.ups_status": 0,
                    "sensor.ups_battery": 60,
                },
                "pending_display_delay": 0,
            }
        )
    )

    snapshot = manager.public_snapshot()
    assert snapshot["active_count"] == 1
    assert snapshot["pending_count"] == 1
    assert len(snapshot["alerts"]) == len(snapshot["pending"]) == 1
    assert snapshot["alerts"][0]["device_id"] == device.id
    assert snapshot["pending"][0]["device_id"] == device.id
    assert snapshot["alerts"][0]["id"] != snapshot["pending"][0]["id"]

    run(
        manager.async_update_config(
            {
                "entity_delays": {
                    "sensor.ups_status": 0,
                    "sensor.ups_battery": 0,
                }
            }
        )
    )
    started = [data for event, data in hass.bus.fired if event == EVENT_ALERT_STARTED]
    assert {data["id"] for data in started} == {
        "unavailable:sensor.ups_status",
        "unavailable:sensor.ups_battery",
    }
    fire_device_event_timers(hass)
    device_started = [
        data for event, data in hass.bus.fired if event == EVENT_DEVICE_ALERT_STARTED
    ]
    assert len(device_started) == 1
    assert device_started[0]["device_ids"] == [device.id]
    assert "device_id" not in device_started[0]
    assert set(device_started[0]["alert_ids"]) <= {
        "unavailable:sensor.ups_status",
        "unavailable:sensor.ups_battery",
    }
    assert manager.public_snapshot()["active_count"] == 2

    hass.states.set("sensor.ups_status", "ok")
    hass.states.set("sensor.ups_battery", "ok")
    run(manager.async_evaluate_entity("sensor.ups_status"))
    run(manager.async_evaluate_entity("sensor.ups_battery"))
    resolved = [data for event, data in hass.bus.fired if event == EVENT_ALERT_RESOLVED]
    assert {data["id"] for data in resolved} == {
        "unavailable:sensor.ups_status",
        "unavailable:sensor.ups_battery",
    }


def test_devices_with_the_same_name_share_one_active_group(
    hass, entry, registry_entry, device_entry
):
    """Duplicate registry devices keep one counter and one lifecycle event."""
    first_device = device_entry(hass, "a" * 32, name="Onduleur")
    second_device = device_entry(hass, "b" * 32, name=" onduleur ")
    registry_entry(hass, "sensor.ups_one", device_id=first_device.id)
    registry_entry(hass, "sensor.ups_two", device_id=second_device.id)
    hass.states.set("sensor.ups_one", "unavailable")
    hass.states.set("sensor.ups_two", "ok")
    manager = make_manager(hass, entry)
    run(
        manager.async_update_config(
            {
                "entity_delays": {"sensor.ups_one": 0, "sensor.ups_two": 0},
                "pending_display_delay": 0,
            }
        )
    )

    initial = manager.public_snapshot()
    assert initial["device_active_count"] == 1
    assert initial["active_devices"][0]["device_ids"] == [first_device.id]
    fire_device_event_timers(hass)
    device_events = [
        data for event, data in hass.bus.fired if event == EVENT_DEVICE_ALERT_STARTED
    ]
    assert len(device_events) == 1
    assert device_events[0]["device_ids"] == [first_device.id]
    assert "device_id" not in device_events[0]

    hass.states.set("sensor.ups_two", "unavailable")
    run(manager.async_evaluate_entity("sensor.ups_two"))
    snapshot = manager.public_snapshot()
    assert snapshot["device_active_count"] == 1
    device = snapshot["active_devices"][0]
    assert device["device_id"] == first_device.id
    assert device["device_ids"] == [first_device.id, second_device.id]
    assert device["device_name"] == "Onduleur"
    assert device["alert_count"] == 2
    assert set(device["alert_ids"]) == {
        "unavailable:sensor.ups_one",
        "unavailable:sensor.ups_two",
    }
    assert device["messages"] == ["État indisponible"]
    assert device["rules"] == ["unavailable"]
    device_events = [
        data for event, data in hass.bus.fired if event == EVENT_DEVICE_ALERT_STARTED
    ]
    assert len(device_events) == 1

    hass.states.set("sensor.ups_one", "ok")
    run(manager.async_evaluate_entity("sensor.ups_one"))
    remaining = manager.public_snapshot()["active_devices"][0]
    assert remaining["device_id"] == second_device.id
    assert remaining["device_ids"] == [second_device.id]
    assert (
        len(
            [
                event
                for event, _data in hass.bus.fired
                if event == EVENT_DEVICE_ALERT_STARTED
            ]
        )
        == 1
    )


def test_entities_without_devices_are_counted_individually(hass, entry):
    """Each device-less entity acts as one stable fallback device."""
    hass.states.set("sensor.one", "unavailable", {"friendly_name": "Capteur un"})
    hass.states.set("sensor.two", "unavailable")
    manager = make_manager(hass, entry)
    run(
        manager.async_update_config(
            {
                "entity_delays": {"sensor.one": 0, "sensor.two": 0},
                "pending_display_delay": 0,
            }
        )
    )

    snapshot = manager.public_snapshot()
    assert snapshot["device_active_count"] == 2
    assert {
        (device["device_id"], device["device_name"])
        for device in snapshot["active_devices"]
    } == {
        ("sensor.one", "Capteur un"),
        ("sensor.two", "sensor.two"),
    }
    assert all(
        device["device_ids"] == [device["device_id"]]
        for device in snapshot["active_devices"]
    )
    fire_device_event_timers(hass)
    events = [
        data for event, data in hass.bus.fired if event == EVENT_DEVICE_ALERT_STARTED
    ]
    assert {tuple(event["device_ids"]) for event in events} == {
        ("sensor.one",),
        ("sensor.two",),
    }
    assert all("device_id" not in event for event in events)

    run(manager.async_evaluate_entity("sensor.one"))
    assert (
        len(
            [
                event
                for event, _data in hass.bus.fired
                if event == EVENT_DEVICE_ALERT_STARTED
            ]
        )
        == 2
    )


def test_rule_configuration_cleanup_is_silent(hass, entry):
    """Removing a source or disabling a rule emits no resolution notification."""
    hass.states.set("sensor.one", "on")
    hass.states.set("sensor.two", "on")
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "Cleanup",
                "entity_ids": ["sensor.one", "sensor.two"],
                "operator": "equals",
                "value": "on",
                "duration": 0,
            }
        )
    )
    hass.bus.fired.clear()
    run(manager.async_update_rule(rule["id"], {"entity_ids": ["sensor.one"]}))
    assert f"rule:{rule['id']}:sensor.two" not in manager.records
    assert not [
        event for event, _data in hass.bus.fired if event == EVENT_ALERT_RESOLVED
    ]

    run(manager.async_update_rule(rule["id"], {"enabled": False}))
    assert f"rule:{rule['id']}:sensor.one" not in manager.records
    assert not [
        event for event, _data in hass.bus.fired if event == EVENT_ALERT_RESOLVED
    ]


def test_custom_rules_ignore_selected_exclusion_labels(hass, entry, registry_entry):
    """An explicit rule still monitors a label-excluded source."""
    hass.label_registry.labels["pas_d_alerte"] = SimpleNamespace(label_id="skip")
    registry_entry(hass, "sensor.test", labels={"skip"})
    hass.states.set("sensor.test", "on")
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "Explicit",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "on",
                "duration": 0,
            }
        )
    )
    assert f"rule:{rule['id']}:sensor.test" in manager.records


def test_legacy_rule_and_label_configuration_migrate_idempotently(hass, entry):
    """V1 entity_id and exclusion-label names become V1.1 registry ids."""
    hass.label_registry.labels["pas_d_alerte"] = SimpleNamespace(label_id="skip")
    hass.states.set("sensor.test", "on", {"friendly_name": "Legacy sensor"})
    detected_at = datetime(2026, 8, 24, 12, tzinfo=UTC)
    hass.stores["alert_manager"] = {
        "config": {
            "exclusion_label": "pas_d_alerte",
            "active_display_delay": 7,
            "automatic": {"unavailable": {"domains": ["sensor"]}},
            "rules": [
                {
                    "id": "legacy",
                    "name": "Legacy",
                    "entity_id": "sensor.test",
                    "operator": "equals",
                    "value": "on",
                    "duration": 60,
                    "version": 1,
                }
            ],
        },
        "alerts": {
            "rule:legacy": {
                "details": {
                    "id": "rule:legacy",
                    "type": "rule",
                    "entity_id": "sensor.test",
                    "name": "Legacy sensor",
                    "value": "on",
                    "condition": "État égal à on",
                },
                "status": "pending",
                "detected_at": detected_at.isoformat(),
                "due_at": (detected_at + timedelta(seconds=60)).isoformat(),
                "delay": 60,
                "active_since": None,
            }
        },
    }
    manager = make_manager(hass, entry)
    rule = manager.get_config()["rules"][0]
    assert rule["entity_ids"] == ["sensor.test"]
    assert "entity_id" not in rule
    assert rule["version"] == 2
    assert manager.get_config()["excluded_labels"] == ["skip"]
    assert manager.get_config()["monitoring_enabled"] is True
    assert manager.get_config()["history_limit"] == 100
    assert manager.get_config()["coherence_scan_esphome"] is True
    assert manager.get_config()["coherence_ignored_entity_references"] == []
    assert manager.get_config()["pending_display_delay"] == 7
    assert "active_display_delay" not in manager.get_config()
    assert manager.history == []
    assert "domains" not in manager.get_config()["automatic"]["unavailable"]
    assert "rule:legacy:sensor.test" in manager.records
    assert manager.records["rule:legacy:sensor.test"].detected_at == detected_at
    assert manager.records["rule:legacy:sensor.test"].details.rule_id == "legacy"
    assert manager.records["rule:legacy:sensor.test"].details.rule_name == "Legacy"
    assert manager.records["rule:legacy:sensor.test"].details.source == "state"
    assert manager.records["rule:legacy:sensor.test"].details.operator == "equals"
    assert manager.records["rule:legacy:sensor.test"].details.comparison_value == "on"
    assert hass.stores["alert_manager"]["config"]["monitoring_enabled"] is True
    assert hass.stores["alert_manager"]["config"]["pending_display_delay"] == 7

    run(manager.async_unload())
    reloaded = make_manager(hass, entry)
    assert reloaded.get_config()["rules"] == [rule]
    assert reloaded.get_config()["excluded_labels"] == ["skip"]


def test_invalid_alerts_collection_is_ignored(hass, entry):
    """A malformed storage collection is removed during successful startup."""
    hass.stores["alert_manager"] = {"config": {}, "alerts": []}
    manager = make_manager(hass, entry)
    assert manager.records == {}
    assert hass.stores["alert_manager"]["alerts"] == {}


def test_invalid_stored_configuration_is_preserved_for_recovery(hass, entry):
    """A malformed stored rule is never overwritten by startup defaults."""
    stored = {
        "config": {"rules": [{"id": "incomplete"}]},
        "alerts": {},
    }
    hass.stores["alert_manager"] = deepcopy(stored)
    manager = make_manager(hass, entry)
    assert manager.recovery_active is True
    assert manager.get_config()["rules"] == []
    assert hass.stores["alert_manager"] == stored


def test_unload_reload_cleans_listeners_and_timers(hass, entry):
    """Unload cancels timers/listeners and a new manager reloads one clean set."""
    hass.states.set("sensor.test", "unavailable")

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        assert any(hass.bus.listeners.values())
        assert len(hass.dispatchers[SIGNAL_NOTIFICATION_LIFECYCLE]) == 1
        assert any(not timer["cancelled"] for timer in hass.timers)
        await manager.async_unload()
        assert all(not listeners for listeners in hass.bus.listeners.values())
        assert hass.dispatchers[SIGNAL_NOTIFICATION_LIFECYCLE] == []
        assert all(timer["cancelled"] for timer in hass.timers)

        reloaded = AlertManager(hass, entry)
        await reloaded.async_setup()
        assert reloaded.records == {}
        fire_startup_reconciliation(hass)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert reloaded.records
        assert sum(len(items) for items in hass.bus.listeners.values()) == 5
        assert len(hass.dispatchers[SIGNAL_NOTIFICATION_LIFECYCLE]) == 1

    run(scenario())


def test_history_marker_is_independent_of_alert_updates(hass, entry):
    """History signals reach the panel even with unchanged counts or monitoring off."""
    from homeassistant.helpers.dispatcher import async_dispatcher_send

    from custom_components.alert_manager.const import (
        SIGNAL_ALERTS_UPDATED,
        SIGNAL_HISTORY_UPDATED,
    )

    manager = make_manager(hass, entry)
    sensor = AlertManagerSensor(
        manager,
        "main_active",
        "alert_manager_main_active",
        "mdi:alert-circle",
        "active_count",
        "alerts",
        "alerts",
    )
    sensor.hass = hass
    run(sensor.async_added_to_hass())
    assert sensor.extra_state_attributes["history_revision"] == 0
    async_dispatcher_send(hass, SIGNAL_ALERTS_UPDATED)
    assert sensor.extra_state_attributes["history_revision"] == 0
    writes = sensor.writes
    async_dispatcher_send(hass, SIGNAL_HISTORY_UPDATED)
    assert sensor.writes == writes + 1
    assert sensor.extra_state_attributes["history_revision"] == 1
    run(manager.async_set_monitoring(False))
    assert sensor.extra_state_attributes["history_revision"] == 1
    run(manager.async_clear_history())
    assert sensor.extra_state_attributes["history_revision"] == 2
    run(manager.async_set_history_limit(200))
    assert sensor.extra_state_attributes["history_revision"] == 3
    for remove in sensor._removers:
        remove()
    async_dispatcher_send(hass, SIGNAL_HISTORY_UPDATED)
    assert sensor.extra_state_attributes["history_revision"] == 3


@pytest.mark.parametrize("partition", ["active", "pending", "acknowledge"])
@pytest.mark.parametrize("change", ["notification", "omitted_alert"])
def test_alert_revision_tracks_changes_hidden_by_compaction(partition, change):
    """Full-data changes invalidate the panel without growing sensor attributes."""
    from copy import deepcopy

    items_key = {
        "active": "alerts",
        "pending": "pending",
        "acknowledge": "acknowledge",
    }[partition]
    count_key = f"{partition}_count"
    alerts = [
        {"id": f"alert:{i}", "entity_id": f"sensor.test_{i}", "message": "x" * 1024}
        for i in range(100)
    ]
    snapshot = {
        count_key: len(alerts),
        items_key: alerts,
        "tracked_count": 100,
        "startup": {"in_progress": False, "stabilization_until": None},
    }
    manager = SimpleNamespace(monitoring_enabled=True, _last_public_snapshot=snapshot)
    sensor = AlertManagerSensor(
        manager,
        f"main_{partition}",
        f"alert_manager_main_{partition}",
        "mdi:alert-circle",
        count_key,
        items_key,
        "alerts",
    )
    sensor._async_manager_updated()
    before = sensor.extra_state_attributes
    assert before["alerts_omitted"] > 0
    updated = deepcopy(snapshot)
    if change == "notification":
        updated[items_key][0]["notifications"] = {"alert": {"count": 1}}
    else:
        updated[items_key][-1]["id"] = "replacement"
    manager._last_public_snapshot = updated
    sensor._async_manager_updated()
    after = sensor.extra_state_attributes
    assert sensor.native_value == 100
    assert after["alerts_revision"] == before["alerts_revision"] + 1
    assert {k: v for k, v in after.items() if k != "alerts_revision"} == {
        k: v for k, v in before.items() if k != "alerts_revision"
    }
    sensor._async_manager_updated()
    assert sensor.extra_state_attributes == after
