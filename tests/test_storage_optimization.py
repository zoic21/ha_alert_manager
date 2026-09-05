"""Selective persistence and off-loop serialization regression tests."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.core import CoreState, Event

from custom_components.alert_manager import storage as storage_module
from custom_components.alert_manager.const import (
    CONFIG_BACKUP_STORAGE_KEY,
    HISTORY_STORAGE_KEY,
    NOTIFICATION_STORAGE_KEY,
    PENDING_PERSISTENCE_DELAY_SECONDS,
    STORAGE_KEY,
)
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import (
    AlertDetails,
    AlertRecord,
    AlertStatus,
    advance_record,
)
from custom_components.alert_manager.runtime_phase import RuntimePhase
from custom_components.alert_manager.storage import AlertManagerStorage
from custom_components.alert_manager.transactions import (
    StartupReconciliationTransaction,
)


def run(coroutine):
    return asyncio.run(coroutine)


def test_short_pending_round_trip_performs_no_runtime_write(hass, entry):
    """A transient pending record never changes the durable main snapshot."""
    hass.states.set("sensor.test", "ok")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    before = hass.store_save_count

    hass.states.set("sensor.test", "unavailable")
    run(manager.async_evaluate_entity("sensor.test"))
    assert "unavailable:sensor.test" in manager.records
    assert hass.stores[STORAGE_KEY]["alerts"] == {}
    assert hass.store_save_count == before

    hass.states.set("sensor.test", "ok")
    run(manager.async_evaluate_entity("sensor.test"))
    assert manager.records == {}
    assert hass.stores[STORAGE_KEY]["alerts"] == {}
    assert hass.store_save_count == before
    assert not any(
        not timer["cancelled"] and "pending_persistence" in timer["action"].__qualname__
        for timer in hass.timers
    )


def test_config_write_does_not_capture_a_fresh_pending(hass, entry):
    """An unrelated durable change cannot accidentally store a fresh pending."""
    hass.states.set("sensor.test", "unavailable")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())

    run(manager.async_update_config({"pending_display_delay": 5}))

    assert "unavailable:sensor.test" in manager.records
    assert hass.stores[STORAGE_KEY]["alerts"] == {}
    assert hass.stores[STORAGE_KEY]["config"]["pending_display_delay"] == 5


def test_long_pending_is_persisted_once_and_resumes_after_reload(hass, entry, set_now):
    """The shared deadline makes a long pending durable without polling."""

    async def scenario():
        start = datetime(2026, 8, 24, 12, tzinfo=UTC)
        set_now(start)
        hass.states.set("sensor.test", "unavailable")
        first = AlertManager(hass, entry)
        await first.async_setup()
        alert_id = "unavailable:sensor.test"
        due_at = first.records[alert_id].due_at
        assert alert_id not in hass.stores[STORAGE_KEY]["alerts"]

        timer = next(
            item
            for item in hass.timers
            if not item["cancelled"]
            and "pending_persistence" in item["action"].__qualname__
        )
        expected = start + timedelta(seconds=PENDING_PERSISTENCE_DELAY_SECONDS)
        assert timer["point"] == expected
        before = hass.store_save_count
        set_now(expected)
        timer["action"](expected)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert hass.store_save_count == before + 1
        assert alert_id in hass.stores[STORAGE_KEY]["alerts"]
        await first.async_unload()

        set_now(expected + timedelta(seconds=30))
        second = AlertManager(hass, entry)
        await second.async_setup()
        assert second.records[alert_id].due_at == due_at

    run(scenario())


def test_existing_pending_remains_persisted_for_backward_compatibility(
    hass, entry, set_now
):
    """A pending record written by an older release is retained immediately."""
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable")
    first = AlertManager(hass, entry)
    run(first.async_setup())
    alert_id = "unavailable:sensor.test"
    hass.stores[STORAGE_KEY]["alerts"][alert_id] = first.records[
        alert_id
    ].as_storage_dict()

    restarted = AlertManager(hass, entry)
    run(restarted.async_setup())
    run(restarted._async_save_state())

    assert alert_id in restarted.storage.persisted_alert_ids
    assert alert_id in hass.stores[STORAGE_KEY]["alerts"]


def test_startup_rename_transfers_pending_durability_and_rollback(hass, entry, set_now):
    """A fresh legacy pending follows its identity and rolls back atomically."""

    async def scenario():
        start = datetime(2026, 9, 4, 12, tzinfo=UTC)
        set_now(start)
        hass.states.set("sensor.old", "unavailable")
        manager = AlertManager(hass, entry)
        assert await manager.async_setup() is True
        old_id = "unavailable:sensor.old"
        new_id = "unavailable:sensor.new"
        await manager.storage.async_save(
            manager.config,
            manager.records,
            include_all_pending=True,
        )
        manager._unverified_restored_alert_ids = {old_id}
        snapshot = manager._configuration_snapshot()
        transaction = StartupReconciliationTransaction.capture(
            manager.records,
            manager._unverified_restored_alert_ids,
        )
        manager._startup_reconciliation_snapshot = snapshot
        manager._startup_reconciliation_transaction = transaction
        manager._runtime_phase = RuntimePhase.RECONCILING

        hass.states.data.pop("sensor.old")
        hass.states.set("sensor.new", "unavailable")
        manager._pending_entity_renames["sensor.old"] = "sensor.new"
        assert manager._apply_pending_entity_renames() is True
        await manager._async_save_main_store()

        assert set(hass.stores[STORAGE_KEY]["alerts"]) == {new_id}
        assert manager.storage.persisted_alert_ids == {new_id}

        manager._restore_configuration_snapshot(snapshot)
        manager._runtime_phase = RuntimePhase.STARTUP_GRACE
        await manager._async_save_main_store()

        assert set(hass.stores[STORAGE_KEY]["alerts"]) == {old_id}
        assert manager.storage.persisted_alert_ids == {old_id}

    run(scenario())


def test_runtime_rename_retries_with_transferred_pending_durability(
    hass, entry, set_now
):
    """A failed rename write retains the new durable identity for its retry."""

    async def scenario():
        set_now(datetime(2026, 9, 4, 12, tzinfo=UTC))
        hass.states.set("sensor.old", "unavailable")
        manager = AlertManager(hass, entry)
        assert await manager.async_setup() is True
        old_id = "unavailable:sensor.old"
        new_id = "unavailable:sensor.new"
        await manager.storage.async_save(
            manager.config,
            manager.records,
            include_all_pending=True,
        )
        before_store = deepcopy(hass.stores[STORAGE_KEY])

        hass.states.data.pop("sensor.old")
        hass.states.set("sensor.new", "unavailable")
        manager._pending_entity_renames["sensor.old"] = "sensor.new"
        assert manager._apply_pending_entity_renames() is True
        assert manager.storage.effective_durable_alert_ids == {new_id}

        original_save = manager.storage._store.async_save
        fail_write = True

        async def fail_once(payload):
            nonlocal fail_write
            if fail_write:
                fail_write = False
                raise RuntimeError("rename write failed")
            await original_save(payload)

        manager.storage._store.async_save = fail_once
        with pytest.raises(RuntimeError, match="rename write failed"):
            await manager._async_save_state()

        assert hass.stores[STORAGE_KEY] == before_store
        assert manager.storage.persisted_alert_ids == {old_id}
        assert manager.storage.effective_durable_alert_ids == {new_id}

        await manager._async_save_state()
        assert set(hass.stores[STORAGE_KEY]["alerts"]) == {new_id}
        assert manager.storage.persisted_alert_ids == {new_id}
        assert manager.storage.effective_durable_alert_ids == {new_id}

    run(scenario())


@pytest.mark.parametrize("active_side", ["source", "target"])
def test_runtime_rename_equal_clock_keeps_active_durable_collision(
    hass, entry, set_now, active_side
):
    """An equal-clock rename retains the active lifecycle and its durability."""

    async def scenario():
        now = datetime(2026, 9, 4, 12, tzinfo=UTC)
        set_now(now)
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
        active_id = old_id if active_side == "source" else new_id
        await manager.storage.async_save(
            manager.config,
            {active_id: active_record},
            include_all_pending=True,
        )

        manager._pending_entity_renames["sensor.old"] = "sensor.new"
        assert manager._apply_pending_entity_renames() is True

        assert set(manager.records) == {new_id}
        assert manager.records[new_id].status is AlertStatus.ACTIVE
        assert manager.storage.effective_durable_alert_ids == {new_id}

        await manager._async_save_state()
        assert set(hass.stores[STORAGE_KEY]["alerts"]) == {new_id}
        assert hass.stores[STORAGE_KEY]["alerts"][new_id]["status"] == "active"

    run(scenario())


def test_startup_multiscan_keeps_a_fresh_previously_durable_pending(
    hass, entry, set_now
):
    """A speculative clear cannot revoke pending durability before commit."""

    async def scenario():
        start = datetime(2026, 9, 4, 12, tzinfo=UTC)
        set_now(start)
        unavailable_state = hass.states.set("sensor.test", "unavailable")
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        alert_id = "unavailable:sensor.test"
        original = first.records[alert_id].as_storage_dict()
        await first.async_unload()
        hass.stores[STORAGE_KEY]["alerts"][alert_id] = deepcopy(original)

        clear_state = hass.states.set("sensor.test", "ok")
        hass.state = CoreState.starting
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True
        assert alert_id in restarted.storage.persisted_alert_ids
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        restarted._cancel_startup_reconciliation()
        restarted._startup_reconciliation_scheduled = True

        original_save = restarted.storage.async_save
        first_write_done = asyncio.Event()
        release_first_write = asyncio.Event()
        save_calls = 0

        async def block_after_first_write(*args, **kwargs):
            nonlocal save_calls
            save_calls += 1
            await original_save(*args, **kwargs)
            if save_calls == 1:
                first_write_done.set()
                await release_first_write.wait()

        restarted.storage.async_save = block_after_first_write
        reconcile = asyncio.create_task(
            restarted._async_finish_startup_reconciliation()
        )
        await first_write_done.wait()
        assert alert_id not in hass.stores[STORAGE_KEY]["alerts"]

        unavailable_state = hass.states.set("sensor.test", "unavailable")
        restarted._state_changed(
            Event(
                {
                    "entity_id": "sensor.test",
                    "old_state": clear_state,
                    "new_state": unavailable_state,
                }
            )
        )
        release_first_write.set()
        await reconcile

        assert save_calls == 2
        assert (
            restarted.records[alert_id].detected_at.isoformat()
            == original["detected_at"]
        )
        assert hass.stores[STORAGE_KEY]["alerts"][alert_id] == original
        assert alert_id in restarted.storage.persisted_alert_ids
        restarted.storage.async_save = original_save
        await restarted.async_unload()

    run(scenario())


def test_storage_payload_is_detached_and_duplicate_writes_are_skipped(hass, entry):
    """Executor serialization sees immutable data and unchanged saves are omitted."""

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        config = {"nested": {"value": 1}}
        manager.storage.variation_baselines = {"reference": 2.0}
        manager.storage.pack_runtime = {"pack": {"values": [3]}}
        before = hass.store_save_count

        await manager.storage.async_save(config, {})
        assert hass.store_save_count == before + 1
        await manager.storage.async_save(config, {})
        assert hass.store_save_count == before + 1

        config["nested"]["value"] = 9
        manager.storage.variation_baselines["reference"] = 9.0
        manager.storage.pack_runtime["pack"]["values"].append(9)
        stored = hass.stores[STORAGE_KEY]
        assert stored["config"]["nested"]["value"] == 1
        assert stored["variation_baselines"] == {"reference": 2.0}
        assert stored["pack_runtime"] == {"pack": {"values": [3]}}

    run(scenario())


def test_runtime_stores_serialize_outside_the_event_loop(hass, entry):
    """Every runtime JSON store opts into executor serialization."""
    manager = AlertManager(hass, entry)
    assert manager.storage._store.options["serialize_in_event_loop"] is False
    assert manager.history_storage._store.options["serialize_in_event_loop"] is False
    assert (
        manager.config_backup_storage._store.options["serialize_in_event_loop"] is False
    )
    assert (
        manager.notification_runtime._store.options["serialize_in_event_loop"] is False
    )
    assert set(hass.store_options) == {
        STORAGE_KEY,
        HISTORY_STORAGE_KEY,
        CONFIG_BACKUP_STORAGE_KEY,
        NOTIFICATION_STORAGE_KEY,
    }


def pending_record(alert_id, now):
    """Build a long pending occurrence without manager setup or timers."""
    return AlertRecord.pending(
        AlertDetails(
            id=alert_id,
            type="unavailable",
            entity_id="sensor.test",
            name="Test",
            value="unavailable",
            condition="Unavailable",
        ),
        900,
        now,
    )


def test_fresh_pending_is_filtered_before_serialization(hass, monkeypatch):
    """Only eligible records pay the cost of building detached dictionaries."""
    now = datetime(2026, 9, 5, 12, tzinfo=UTC)
    storage = AlertManagerStorage(hass)
    records = {
        "fresh": pending_record("fresh", now),
        "mature": pending_record("mature", now - timedelta(minutes=10)),
        "active": pending_record("active", now - timedelta(minutes=20)),
    }
    assert advance_record(records["active"], now)
    serialized = []
    original = AlertRecord.as_storage_dict

    def serialize(record):
        serialized.append(record.details.id)
        return original(record)

    monkeypatch.setattr(AlertRecord, "as_storage_dict", serialize)
    cutoff = now - timedelta(seconds=PENDING_PERSISTENCE_DELAY_SECONDS)
    run(storage.async_save({}, records, pending_before=cutoff))

    assert serialized == ["mature", "active"]
    assert set(hass.stores[STORAGE_KEY]["alerts"]) == {"mature", "active"}


def test_unchanged_sections_are_reused_and_nested_changes_retry(hass, monkeypatch):
    """Reuse needs no invalidation flags and a failed write cannot poison it."""

    async def scenario():
        storage = AlertManagerStorage(hass)
        config = {"nested": {"values": [1]}}
        storage.pack_runtime = {"pack": {"values": [2]}}
        storage.variation_baselines = {"reference": 3.0}
        await storage.async_save(config, {})
        original_payload = hass.stores[STORAGE_KEY]
        copied = []

        def copy_section(value):
            copied.append(value)
            return deepcopy(value)

        monkeypatch.setattr(storage_module, "deepcopy", copy_section)
        # A real alert change must reuse all three unchanged sections.
        now = datetime(2026, 9, 5, 12, tzinfo=UTC)
        record = pending_record("test", now)
        records = {"test": record}
        await storage.async_save(config, records, include_all_pending=True)
        assert copied == []
        persisted = hass.stores[STORAGE_KEY]
        for key in ("config", "pack_runtime", "variation_baselines"):
            assert persisted[key] is original_payload[key]

        config["nested"]["values"].append(4)
        storage.pack_runtime["pack"]["values"].append(5)
        storage.variation_baselines["reference"] = 6.0
        original_save = storage._store.async_save

        async def fail_save(payload):
            raise OSError("disk full")

        monkeypatch.setattr(storage._store, "async_save", fail_save)
        with pytest.raises(OSError, match="disk full"):
            await storage.async_save(config, records)
        assert storage._save_requests == 0
        assert hass.stores[STORAGE_KEY] is persisted
        assert persisted["config"]["nested"]["values"] == [1]
        assert persisted["pack_runtime"]["pack"]["values"] == [2]
        assert persisted["variation_baselines"] == {"reference": 3.0}

        monkeypatch.setattr(storage._store, "async_save", original_save)
        await storage.async_save(config, records)
        updated = hass.stores[STORAGE_KEY]
        assert updated["config"] == config
        assert updated["pack_runtime"] == storage.pack_runtime
        assert updated["variation_baselines"] == storage.variation_baselines
        before = hass.store_save_count
        await storage.async_save(config, records)
        assert hass.store_save_count == before

    run(scenario())


@pytest.mark.parametrize("cancel_waiter", [False, True])
def test_queued_save_keeps_new_pending_durability_and_detached_input(
    hass, monkeypatch, cancel_waiter
):
    """A waiting save retains newly durable pending and call-time values."""

    async def scenario():
        storage = AlertManagerStorage(hass)
        now = datetime(2026, 9, 5, 12, tzinfo=UTC)
        record = pending_record("test", now)
        records = {"test": record}
        config = {"nested": {"value": 1}}
        storage.pack_runtime = {"pack": {"values": [1]}}
        storage.variation_baselines = {"reference": 1.0}
        entered = asyncio.Event()
        release = asyncio.Event()
        original_save = storage._store.async_save

        async def slow_save(payload):
            entered.set()
            await release.wait()
            await original_save(payload)

        monkeypatch.setattr(storage._store, "async_save", slow_save)
        first = asyncio.create_task(
            storage.async_save(config, records, include_all_pending=True)
        )
        await entered.wait()
        record.details.message = "queued"
        config["nested"]["value"] = 2
        storage.pack_runtime["pack"]["values"].append(2)
        storage.variation_baselines["reference"] = 2.0
        second = asyncio.create_task(storage.async_save(config, records))
        await asyncio.sleep(0)
        assert storage._save_requests == 2
        record.details.message = "later"
        config["nested"]["value"] = 3
        storage.pack_runtime["pack"]["values"].append(3)
        storage.variation_baselines["reference"] = 3.0
        if cancel_waiter:
            second.cancel()
            with pytest.raises(asyncio.CancelledError):
                await second
        release.set()
        await first
        if not cancel_waiter:
            await second
        stored = hass.stores[STORAGE_KEY]
        assert "test" in stored["alerts"]
        expected = 1 if cancel_waiter else 2
        assert stored["config"]["nested"]["value"] == expected
        assert stored["variation_baselines"]["reference"] == expected
        assert stored["pack_runtime"]["pack"]["values"] == list(range(1, expected + 1))
        assert stored["alerts"]["test"]["details"].get("message") == (
            None if cancel_waiter else "queued"
        )
        assert storage._save_requests == 0

    run(scenario())
