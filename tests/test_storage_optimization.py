"""Selective persistence and off-loop serialization regression tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from custom_components.alert_manager.const import (
    CONFIG_BACKUP_STORAGE_KEY,
    HISTORY_STORAGE_KEY,
    NOTIFICATION_STORAGE_KEY,
    PENDING_PERSISTENCE_DELAY_SECONDS,
    STORAGE_KEY,
)
from custom_components.alert_manager.manager import AlertManager


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
