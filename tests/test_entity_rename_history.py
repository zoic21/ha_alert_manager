"""Bounded entity rename history, independent of alert monitoring."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from homeassistant.core import Event

from custom_components.alert_manager import manager_runtime
from custom_components.alert_manager.const import (
    DATA_MANAGER,
    ENTITY_RENAME_HISTORY_LIMIT,
    ENTITY_RENAME_SAVE_DELAY_SECONDS,
    ENTITY_RENAME_STORAGE_KEY,
)
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.storage import EntityRenameHistoryStorage
from custom_components.alert_manager.websocket import websocket_entity_renames_list


def test_registry_records_only_id_changes_even_with_monitoring_disabled(
    hass, entry, registry_entry, monkeypatch
):
    """Metadata updates are ignored; every rename in a burst is retained."""
    now = datetime(2026, 10, 3, 12, tzinfo=UTC)
    monkeypatch.setattr(manager_runtime.dt_util, "utcnow", lambda: now)

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        manager.config["monitoring_enabled"] = False
        saves = hass.store_save_count
        for data in (
            {"action": "create", "entity_id": "sensor.new"},
            {"action": "update", "entity_id": "sensor.new", "changes": {"name": "Old"}},
            {
                "action": "update",
                "entity_id": "sensor.new",
                "old_entity_id": "sensor.new",
            },
            {"action": "remove", "entity_id": "sensor.new"},
        ):
            manager._registry_changed(Event(data))
        assert manager.entity_renames_snapshot() == {"renames": []}
        item = registry_entry(hass, "sensor.new")
        item.id = "registry-id"
        manager._registry_changed(
            Event(
                {
                    "action": "update",
                    "old_entity_id": "sensor.old",
                    "entity_id": "sensor.new",
                }
            )
        )
        manager._registry_changed(
            Event(
                {
                    "action": "update",
                    "old_entity_id": "sensor.new",
                    "entity_id": "sensor.final",
                }
            )
        )
        assert hass.store_save_count == saves
        assert ENTITY_RENAME_STORAGE_KEY not in hass.stores
        renames = manager.entity_rename_history.snapshot()
        assert [rename["new_entity_id"] for rename in renames] == [
            "sensor.final",
            "sensor.new",
        ]
        assert renames[1] == {
            "old_entity_id": "sensor.old",
            "new_entity_id": "sensor.new",
            "registry_entry_id": "registry-id",
            "renamed_at": now.isoformat(),
        }
        manager._begin_shutdown()
        manager._registry_changed(
            Event(
                {
                    "action": "update",
                    "old_entity_id": "sensor.final",
                    "entity_id": "sensor.late",
                }
            )
        )
        assert manager.entity_rename_history.snapshot() == renames
        await manager.async_unload()

    asyncio.run(scenario())


def test_burst_keeps_latest_500_and_immutable_worker_snapshot(hass):
    """Delay requests coalesce; a worker never sees a mutated payload."""
    history = EntityRenameHistoryStorage(hass)
    now = datetime(2026, 10, 3, 12, tzinfo=UTC)
    history.record("sensor.old", "sensor.first", "first-id", now)
    first_payload = history._store.delayed_save[0]()
    for index in range(ENTITY_RENAME_HISTORY_LIMIT + 1):
        history.record(f"sensor.old_{index}", f"sensor.new_{index}", None, now)
    assert len(first_payload["renames"]) == 1
    assert first_payload["renames"][0]["new_entity_id"] == "sensor.first"
    assert hass.store_save_count == 0
    callback, delay = history._store.delayed_save
    assert delay == ENTITY_RENAME_SAVE_DELAY_SECONDS
    payload = callback()
    assert len(payload["renames"]) == 500
    assert payload["renames"][0]["new_entity_id"] == "sensor.new_1"
    assert history.snapshot()[0]["new_entity_id"] == "sensor.new_500"
    assert hass.store_options[ENTITY_RENAME_STORAGE_KEY] == {
        "private": True,
        "atomic_writes": True,
        "serialize_in_event_loop": False,
    }
    asyncio.run(history._store.async_save(payload))
    assert hass.store_save_count == 1
    assert len(hass.stores[ENTITY_RENAME_STORAGE_KEY]["renames"]) == 500


def test_unload_flushes_pending_history_and_restart_restores_it(hass, entry):
    """An immediate unload retains the latest rename without waiting for the delay."""

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        manager.entity_rename_history.record(
            "sensor.old", "sensor.new", None, datetime.now(UTC)
        )
        await manager.async_unload()
        assert manager.entity_rename_history._store.delayed_save is None
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        assert (
            restarted.entity_rename_history.snapshot()
            == manager.entity_rename_history.snapshot()
        )
        saves = hass.store_save_count
        await restarted.entity_rename_history.async_flush()
        assert hass.store_save_count == saves
        await restarted.async_unload()

    asyncio.run(scenario())


def test_more_info_follows_registry_identity_after_further_renames(
    hass, entry, registry_entry
):
    """Historic IDs remain unchanged; deleted identities cannot target reused IDs."""
    manager = AlertManager(hass, entry)
    item = registry_entry(hass, "sensor.current")
    item.id = "stable-id"
    manager.entity_rename_history.record(
        "sensor.old", "sensor.intermediate", item.id, datetime.now(UTC)
    )
    result = manager.entity_renames_snapshot()
    assert result["renames"][0]["current_entity_id"] == "sensor.current"
    assert result["renames"][0]["new_entity_id"] == "sensor.intermediate"
    assert "current_entity_id" not in manager.entity_rename_history.snapshot()[0]
    del hass.entity_registry.entries["sensor.current"]
    registry_entry(hass, "sensor.intermediate").id = "different-id"
    assert manager.entity_renames_snapshot()["renames"][0]["current_entity_id"] is None


def test_rename_history_websocket_returns_snapshot(hass, entry):
    """The admin endpoint returns the history without a scan or disk read."""
    manager = AlertManager(hass, entry)
    manager.entity_rename_history.record(
        "sensor.old", "sensor.new", None, datetime.now(UTC)
    )
    hass.data[DATA_MANAGER] = manager
    results = []
    connection = SimpleNamespace(
        user=SimpleNamespace(is_admin=True),
        send_result=lambda message_id, result: results.append((message_id, result)),
    )
    asyncio.run(websocket_entity_renames_list(hass, connection, {"id": 42}))
    assert results == [(42, manager.entity_renames_snapshot())]
    assert hass.store_save_count == 0
