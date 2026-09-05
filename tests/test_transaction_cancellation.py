"""Atomic cancellation boundaries for serialized manager mutations."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.core import CoreState, Event
from homeassistant.util import dt as dt_util

from custom_components.alert_manager.const import STORAGE_KEY
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertHistoryEntry
from custom_components.alert_manager.runtime_phase import RuntimePhase
from custom_components.alert_manager.yaml_io import dump_config_yaml


async def _active_rule_manager(hass, entry) -> tuple[AlertManager, str]:
    """Return a running manager with one active custom-rule occurrence."""
    hass.states.set("binary_sensor.filter", "on")
    manager = AlertManager(hass, entry)
    assert await manager.async_setup() is True
    rule = await manager.async_create_rule(
        {
            "name": "Filter active",
            "entity_ids": ["binary_sensor.filter"],
            "operator": "equals",
            "value": "on",
            "duration": 0,
        }
    )
    return manager, f"rule:{rule['id']}:binary_sensor.filter"


async def _seed_history(manager: AlertManager, alert_id: str) -> None:
    """Persist two completed occurrences without changing the live record."""
    record = manager.records[alert_id]
    now = dt_util.now()
    manager.history = [
        AlertHistoryEntry.resolved(deepcopy(record), now + timedelta(seconds=2)),
        AlertHistoryEntry.resolved(deepcopy(record), now + timedelta(seconds=1)),
    ]
    await manager.history_storage.async_save(manager.history)


def _active_reconciliation_timers(hass) -> list[dict]:
    """Return every live startup reconciliation timer."""
    return [
        timer
        for timer in hass.timers
        if not timer["cancelled"]
        and "_schedule_startup_reconciliation" in timer["action"].__qualname__
    ]


async def _restart_in_startup_grace(hass, entry) -> AlertManager:
    """Persist a clean snapshot and return a restarted manager ready to admit."""
    first = AlertManager(hass, entry)
    assert await first.async_setup() is True
    await first.async_update_config({"automatic": {"unavailable": {"delay": 0}}})
    await first.async_unload()

    hass.state = CoreState.starting
    restarted = AlertManager(hass, entry)
    assert await restarted.async_setup() is True
    hass.state = CoreState.running
    restarted._home_assistant_started(Event())
    restarted._cancel_startup_reconciliation()
    restarted._startup_reconciliation_scheduled = True
    return restarted


def test_cancellation_before_mutation_lock_changes_nothing(hass, entry):
    """Cancellation before transaction admission cannot mutate memory or Store."""

    async def scenario() -> None:
        manager = AlertManager(hass, entry)
        assert await manager.async_setup() is True
        before_config = manager.get_config()
        before_store = deepcopy(hass.stores["alert_manager"])

        await manager._config_mutation_lock.acquire()
        update_task = asyncio.create_task(
            manager.async_update_config(
                {"global_delay": before_config["global_delay"] + 1}
            )
        )
        await asyncio.sleep(0)
        update_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await update_task
        manager._config_mutation_lock.release()

        assert manager.get_config() == before_config
        assert hass.stores["alert_manager"] == before_store
        await manager.async_unload()

    asyncio.run(scenario())


def test_cancelled_admitted_reconciliation_finishes_without_unload(hass, entry):
    """Caller cancellation cannot interrupt an admitted startup transaction."""

    async def scenario() -> None:
        hass.states.set("sensor.gateway", "on")
        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        await first.async_update_config({"automatic": {"unavailable": {"delay": 0}}})
        await first.async_unload()

        hass.state = CoreState.starting
        hass.states.set("sensor.gateway", "unavailable")
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        restarted._cancel_startup_reconciliation()
        restarted._startup_reconciliation_scheduled = True

        original_save = restarted.storage.async_save
        save_started = asyncio.Event()
        release_save = asyncio.Event()

        async def blocked_save(*args, **kwargs):
            save_started.set()
            await release_save.wait()
            await original_save(*args, **kwargs)

        restarted.storage.async_save = blocked_save
        reconciliation_task = asyncio.create_task(
            restarted._async_finish_startup_reconciliation()
        )
        await save_started.wait()
        assert restarted._runtime_phase is RuntimePhase.RECONCILING

        reconciliation_task.cancel()
        await asyncio.sleep(0)
        assert not reconciliation_task.done()

        release_save.set()
        with pytest.raises(asyncio.CancelledError):
            await reconciliation_task

        alert_id = "unavailable:sensor.gateway"
        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert alert_id in restarted.records
        assert alert_id in hass.stores["alert_manager"]["alerts"]
        restarted.storage.async_save = original_save
        await restarted.async_unload()

    asyncio.run(scenario())


def test_cancelled_reconciliation_before_lock_is_rearmed(hass, entry):
    """Cancellation before admission leaves one usable reconciliation timer."""

    async def scenario() -> None:
        hass.states.set("sensor.gateway", "on")
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

        await restarted._config_mutation_lock.acquire()
        reconciliation_task = asyncio.create_task(
            restarted._async_finish_startup_reconciliation()
        )
        await asyncio.sleep(0)
        reconciliation_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reconciliation_task

        active_timers = [
            timer
            for timer in hass.timers
            if not timer["cancelled"]
            and "_schedule_startup_reconciliation" in timer["action"].__qualname__
        ]
        assert restarted._runtime_phase is RuntimePhase.STARTUP_GRACE
        assert restarted._startup_reconciliation_scheduled is False
        assert len(active_timers) == 1

        restarted._config_mutation_lock.release()
        await restarted.async_unload()

    asyncio.run(scenario())


def test_internal_reconciliation_cancellation_rearms_startup(hass, entry):
    """An internal cancellation rolls back, cleans up and schedules one retry."""

    async def scenario() -> None:
        restarted = await _restart_in_startup_grace(hass, entry)
        original_evaluate_all = restarted.async_evaluate_all

        async def cancelled_evaluation(**_kwargs):
            raise asyncio.CancelledError

        restarted.async_evaluate_all = cancelled_evaluation
        with pytest.raises(asyncio.CancelledError):
            await restarted._async_finish_startup_reconciliation()

        assert restarted._runtime_phase is RuntimePhase.STARTUP_GRACE
        assert restarted._startup_reconciliation_snapshot is None
        assert restarted._startup_reconciliation_transaction is None
        assert restarted._startup_reconciliation_scheduled is False
        assert len(_active_reconciliation_timers(hass)) == 1

        restarted.async_evaluate_all = original_evaluate_all
        await restarted.async_unload()

    asyncio.run(scenario())


def test_snapshot_failure_rearms_startup_reconciliation(hass, entry):
    """A failed transaction capture cannot strand the startup phase."""

    async def scenario() -> None:
        restarted = await _restart_in_startup_grace(hass, entry)
        original_snapshot = restarted._configuration_snapshot

        def failed_snapshot():
            raise RuntimeError("snapshot failed")

        restarted._configuration_snapshot = failed_snapshot
        await restarted._async_finish_startup_reconciliation()

        assert restarted._runtime_phase is RuntimePhase.STARTUP_GRACE
        assert restarted._startup_reconciliation_snapshot is None
        assert restarted._startup_reconciliation_transaction is None
        assert restarted._startup_reconciliation_scheduled is False
        assert len(_active_reconciliation_timers(hass)) == 1

        restarted._configuration_snapshot = original_snapshot
        await restarted.async_unload()

    asyncio.run(scenario())


def test_failed_reconciliation_compensates_speculative_store_before_retry(hass, entry):
    """A failed scan rewrites its pre-scan Store snapshot before retrying."""

    async def scenario() -> None:
        hass.states.set("sensor.gateway", "ok")
        restarted = await _restart_in_startup_grace(hass, entry)
        before_store = deepcopy(hass.stores["alert_manager"])
        hass.states.set("sensor.gateway", "unavailable")

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

        assert save_calls == 2
        assert restarted.records == {}
        assert hass.stores["alert_manager"] == before_store
        assert restarted._runtime_phase is RuntimePhase.STARTUP_GRACE
        assert len(_active_reconciliation_timers(hass)) == 1

        restarted.storage.async_save = original_save
        await restarted.async_unload()

    asyncio.run(scenario())


def test_second_scan_store_failure_compensates_first_speculative_write(hass, entry):
    """A failed catch-up Store cannot leave a prior provisional scan durable."""

    async def scenario() -> None:
        hass.states.set("sensor.gateway", "ok")
        restarted = await _restart_in_startup_grace(hass, entry)
        before_store = deepcopy(hass.stores["alert_manager"])
        unavailable_state = hass.states.set("sensor.gateway", "unavailable")

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

        assert save_calls == 3
        assert restarted.records == {}
        assert hass.stores["alert_manager"] == before_store
        assert restarted._runtime_phase is RuntimePhase.STARTUP_GRACE
        assert restarted._startup_reconciliation_snapshot is None
        assert restarted._startup_reconciliation_transaction is None
        assert len(_active_reconciliation_timers(hass)) == 1

        restarted.storage.async_save = original_save
        await restarted.async_unload()

    asyncio.run(scenario())


def test_fresh_durable_pending_rollback_restores_store_and_membership(
    hass, entry, set_now
):
    """Rollback restores a fresh pending payload and its durability identity."""

    async def scenario() -> None:
        start = datetime(2026, 9, 4, 12, tzinfo=UTC)
        set_now(start)
        hass.states.set("sensor.test", "unavailable")
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
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        restarted._cancel_startup_reconciliation()
        restarted._startup_reconciliation_scheduled = True
        before_store = deepcopy(hass.stores[STORAGE_KEY])

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
                raise RuntimeError("catch-up write failed before Store")
            await original_save(*args, **kwargs)

        restarted.storage.async_save = fail_second_write
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

        assert save_calls == 3
        assert (
            restarted.records[alert_id].detected_at.isoformat()
            == original["detected_at"]
        )
        assert hass.stores[STORAGE_KEY] == before_store
        assert alert_id in restarted.storage.persisted_alert_ids
        assert restarted._runtime_phase is RuntimePhase.STARTUP_GRACE
        assert len(_active_reconciliation_timers(hass)) == 1

        restarted.storage.async_save = original_save
        await restarted.async_unload()

    asyncio.run(scenario())


def test_cancelled_compensation_still_cleans_and_rearms(hass, entry):
    """Cancellation from compensation cannot skip transaction cleanup."""

    async def scenario() -> None:
        hass.states.set("sensor.gateway", "ok")
        restarted = await _restart_in_startup_grace(hass, entry)
        before_store = deepcopy(hass.stores["alert_manager"])
        hass.states.set("sensor.gateway", "unavailable")

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

        assert save_calls == 2
        assert restarted.records == {}
        assert hass.stores["alert_manager"] == before_store
        assert restarted._runtime_phase is RuntimePhase.STARTUP_GRACE
        assert restarted._startup_reconciliation_snapshot is None
        assert restarted._startup_reconciliation_transaction is None
        assert restarted._startup_reconciliation_scheduled is False
        assert len(_active_reconciliation_timers(hass)) == 1

        restarted.storage.async_save = original_save
        await restarted.async_unload()

    asyncio.run(scenario())


def test_restore_failure_still_cleans_and_rearms(hass, entry):
    """A defensive rollback failure cannot leave reconciliation half-open."""

    async def scenario() -> None:
        restarted = await _restart_in_startup_grace(hass, entry)
        original_evaluate_all = restarted.async_evaluate_all
        original_restore = restarted._restore_configuration_snapshot

        async def failed_evaluation(**_kwargs):
            raise RuntimeError("evaluation failed")

        def failed_restore(_snapshot):
            raise RuntimeError("restore failed")

        restarted.async_evaluate_all = failed_evaluation
        restarted._restore_configuration_snapshot = failed_restore
        await restarted._async_finish_startup_reconciliation()

        assert restarted._runtime_phase is RuntimePhase.STARTUP_GRACE
        assert restarted._startup_reconciliation_snapshot is None
        assert restarted._startup_reconciliation_transaction is None
        assert restarted._startup_reconciliation_scheduled is False
        assert len(_active_reconciliation_timers(hass)) == 1

        restarted.async_evaluate_all = original_evaluate_all
        restarted._restore_configuration_snapshot = original_restore
        await restarted.async_unload()

    asyncio.run(scenario())


def test_cancellation_during_primary_config_store_finishes_commit(hass, entry):
    """A started primary write finishes before cancellation reaches its caller."""

    async def scenario() -> None:
        manager = AlertManager(hass, entry)
        assert await manager.async_setup() is True
        new_delay = manager.config["global_delay"] + 1
        original_save = manager.storage.async_save
        save_started = asyncio.Event()
        release_save = asyncio.Event()

        async def blocked_save(*args, **kwargs):
            save_started.set()
            await release_save.wait()
            await original_save(*args, **kwargs)

        manager.storage.async_save = blocked_save
        update_task = asyncio.create_task(
            manager.async_update_config({"global_delay": new_delay})
        )
        await save_started.wait()
        update_task.cancel()
        await asyncio.sleep(0)
        assert not update_task.done()

        release_save.set()
        with pytest.raises(asyncio.CancelledError):
            await update_task

        assert manager.config["global_delay"] == new_delay
        assert hass.stores["alert_manager"]["config"]["global_delay"] == new_delay
        manager.storage.async_save = original_save
        await manager.async_unload()

    asyncio.run(scenario())


def test_cancellation_after_primary_store_keeps_committed_snapshot(hass, entry):
    """Cancellation during history flush cannot roll memory behind durable state."""

    async def scenario() -> None:
        manager = AlertManager(hass, entry)
        assert await manager.async_setup() is True
        new_delay = manager.config["global_delay"] + 1
        original_flush = manager._async_flush_history
        flush_started = asyncio.Event()
        release_flush = asyncio.Event()

        async def blocked_flush() -> None:
            flush_started.set()
            await release_flush.wait()

        manager._async_flush_history = blocked_flush
        update_task = asyncio.create_task(
            manager.async_update_config({"global_delay": new_delay})
        )
        await flush_started.wait()
        assert hass.stores["alert_manager"]["config"]["global_delay"] == new_delay

        update_task.cancel()
        await asyncio.sleep(0)
        assert not update_task.done()
        release_flush.set()
        with pytest.raises(asyncio.CancelledError):
            await update_task

        assert manager.config["global_delay"] == new_delay
        assert hass.stores["alert_manager"]["config"]["global_delay"] == new_delay
        manager._async_flush_history = original_flush
        await manager.async_unload()

    asyncio.run(scenario())


def test_cancelled_acknowledgement_commits_memory_and_record_store(hass, entry):
    """Runtime-record mutations share the same non-interruptible boundary."""

    async def scenario() -> None:
        manager, alert_id = await _active_rule_manager(hass, entry)
        original_save = manager.storage.async_save
        save_started = asyncio.Event()
        release_save = asyncio.Event()

        async def blocked_save(*args, **kwargs):
            save_started.set()
            await release_save.wait()
            await original_save(*args, **kwargs)

        manager.storage.async_save = blocked_save
        acknowledge_task = asyncio.create_task(
            manager.async_acknowledge(alert_id, "test-user")
        )
        await save_started.wait()
        acknowledge_task.cancel()
        await asyncio.sleep(0)
        assert not acknowledge_task.done()

        release_save.set()
        with pytest.raises(asyncio.CancelledError):
            await acknowledge_task

        assert manager.records[alert_id].acknowledged is True
        assert hass.stores["alert_manager"]["alerts"][alert_id]["acknowledged"] is True
        manager.storage.async_save = original_save
        await manager.async_unload()

    asyncio.run(scenario())


@pytest.mark.parametrize("blocked_store", ["history", "primary"])
def test_cancelled_history_limit_finishes_both_stores(hass, entry, blocked_store: str):
    """Retention updates cannot stop between their history and config writes."""

    async def scenario() -> None:
        manager, alert_id = await _active_rule_manager(hass, entry)
        await _seed_history(manager, alert_id)
        write_started = asyncio.Event()
        release_write = asyncio.Event()
        original_history_save = manager.history_storage.async_save
        original_primary_save = manager.storage.async_save

        async def blocked_history_save(*args, **kwargs):
            write_started.set()
            await release_write.wait()
            await original_history_save(*args, **kwargs)

        async def blocked_primary_save(*args, **kwargs):
            write_started.set()
            await release_write.wait()
            await original_primary_save(*args, **kwargs)

        if blocked_store == "history":
            manager.history_storage.async_save = blocked_history_save
        else:
            manager.storage.async_save = blocked_primary_save

        limit_task = asyncio.create_task(manager.async_set_history_limit(1))
        await write_started.wait()
        limit_task.cancel()
        await asyncio.sleep(0)
        assert not limit_task.done()

        release_write.set()
        with pytest.raises(asyncio.CancelledError):
            await limit_task

        assert manager.config["history_limit"] == 1
        assert len(manager.history) == 1
        assert hass.stores["alert_manager"]["config"]["history_limit"] == 1
        assert len(hass.stores["alert_manager.history"]["events"]) == 1
        manager.history_storage.async_save = original_history_save
        manager.storage.async_save = original_primary_save
        await manager.async_unload()

    asyncio.run(scenario())


def test_cancelled_import_between_stores_finishes_complete_import(hass, entry):
    """A cancelled import cannot leave cleared history with the old config."""

    async def scenario() -> None:
        manager, alert_id = await _active_rule_manager(hass, entry)
        await _seed_history(manager, alert_id)
        candidate = manager.get_config()
        candidate["global_delay"] += 1
        raw_yaml = dump_config_yaml(candidate)
        new_delay = candidate["global_delay"]
        original_history_save = manager.history_storage.async_save
        history_cleared = asyncio.Event()
        release_import = asyncio.Event()

        async def blocked_after_history_save(*args, **kwargs):
            await original_history_save(*args, **kwargs)
            history_cleared.set()
            await release_import.wait()

        manager.history_storage.async_save = blocked_after_history_save
        import_task = asyncio.create_task(manager.async_import_config(raw_yaml))
        await history_cleared.wait()
        assert hass.stores["alert_manager.history"]["events"] == []
        assert hass.stores["alert_manager"]["config"]["global_delay"] != new_delay

        import_task.cancel()
        await asyncio.sleep(0)
        assert not import_task.done()
        release_import.set()
        with pytest.raises(asyncio.CancelledError):
            await import_task

        assert manager.config["global_delay"] == new_delay
        assert manager.history == []
        assert hass.stores["alert_manager"]["config"]["global_delay"] == new_delay
        assert hass.stores["alert_manager.history"]["events"] == []
        manager.history_storage.async_save = original_history_save
        await manager.async_unload()

    asyncio.run(scenario())
