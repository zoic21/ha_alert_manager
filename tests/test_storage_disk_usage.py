"""On-demand disk usage, executor boundaries and shared cache behavior."""

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from custom_components.alert_manager import storage as storage_module
from custom_components.alert_manager.const import (
    COHERENCE_STORAGE_KEY,
    CONFIG_BACKUP_STORAGE_KEY,
    ENTITY_RENAME_STORAGE_KEY,
    HISTORY_STORAGE_KEY,
    NOTIFICATION_STORAGE_KEY,
    STORAGE_KEY,
)
from custom_components.alert_manager.storage import AlertManagerStorage


def test_disk_usage_counts_only_our_data_files_outside_the_event_loop(
    hass, tmp_path, monkeypatch, set_now
):
    storage_dir = tmp_path / ".storage"
    storage_dir.mkdir()
    hass.config.path = lambda *parts: str(tmp_path.joinpath(*parts))
    files = {
        STORAGE_KEY: 13,
        HISTORY_STORAGE_KEY: 21,
        COHERENCE_STORAGE_KEY: 34,
        CONFIG_BACKUP_STORAGE_KEY: 55,
        NOTIFICATION_STORAGE_KEY: 89,
        ENTITY_RENAME_STORAGE_KEY: 144,
    }
    for key, size in files.items():
        (storage_dir / key).write_bytes(b"x" * size)
    (storage_dir / "core.config_entries").write_bytes(b"x" * 1000)
    (storage_dir / f"{STORAGE_KEY}.tmp").write_bytes(b"x" * 2000)
    observed = []
    original_stat = Path.stat
    loop_thread = threading.get_ident()

    def stat(path, *args, **kwargs):
        observed.append((path.name, threading.get_ident()))
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    now = datetime(2026, 10, 3, 12, tzinfo=UTC)
    set_now(now)
    storage = AlertManagerStorage(hass)
    assert observed == []

    result = asyncio.run(storage.async_disk_usage())

    assert result == {"bytes": sum(files.values()), "measured_at": now.isoformat()}
    assert {name for name, _thread in observed} == files.keys()
    assert len(observed) == 6
    assert all(thread != loop_thread for _name, thread in observed)
    assert hass.store_save_count == 0
    assert hass.timers == []


@pytest.mark.parametrize("storage_exists", [False, True])
def test_missing_disk_files_count_as_zero(hass, tmp_path, storage_exists):
    hass.config.path = lambda *parts: str(tmp_path.joinpath(*parts))
    if storage_exists:
        (tmp_path / ".storage").mkdir()
    storage = AlertManagerStorage(hass)
    assert asyncio.run(storage.async_disk_usage())["bytes"] == 0


def test_disk_usage_cache_expires_only_on_request_and_uses_monotonic_time(
    hass, tmp_path, monkeypatch, set_now
):
    hass.config.path = lambda *parts: str(tmp_path.joinpath(*parts))
    storage_dir = tmp_path / ".storage"
    storage_dir.mkdir()
    data_file = storage_dir / STORAGE_KEY
    data_file.write_bytes(b"old")
    ticks = [100.0]
    monkeypatch.setattr(storage_module, "monotonic", lambda: ticks[0])
    measurements = []
    original_measure = storage_module._measure_storage_bytes

    def measure(path):
        measurements.append(path)
        return original_measure(path)

    monkeypatch.setattr(storage_module, "_measure_storage_bytes", measure)
    now = datetime(2026, 10, 3, 12, tzinfo=UTC)
    set_now(now)
    storage = AlertManagerStorage(hass)
    first = asyncio.run(storage.async_disk_usage())
    data_file.write_bytes(b"updated")
    ticks[0] += 299
    set_now(now + timedelta(days=1))
    assert asyncio.run(storage.async_disk_usage()) == first
    ticks[0] += 1
    set_now(now - timedelta(days=1))
    assert len(measurements) == 1
    refreshed = asyncio.run(storage.async_disk_usage())
    assert refreshed == {
        "bytes": 7,
        "measured_at": (now - timedelta(days=1)).isoformat(),
    }
    assert len(measurements) == 2
    assert hass.timers == []


def test_concurrent_disk_requests_share_one_measurement(hass, tmp_path):
    hass.config.path = lambda *parts: str(tmp_path.joinpath(*parts))
    original_executor = hass.async_add_executor_job
    storage = AlertManagerStorage(hass)

    async def scenario():
        entered = asyncio.Event()
        release = asyncio.Event()
        calls = []

        async def executor(target, *args):
            calls.append(target)
            entered.set()
            await release.wait()
            return await original_executor(target, *args)

        hass.async_add_executor_job = executor
        requests = [asyncio.create_task(storage.async_disk_usage()) for _ in range(8)]
        try:
            await entered.wait()
            await asyncio.sleep(0)
            assert len(calls) == 1
        finally:
            release.set()
        results = await asyncio.gather(*requests)
        assert all(result == results[0] for result in results)
        assert len(calls) == 1
        results[0]["bytes"] = 999
        assert results[1]["bytes"] == 0
        assert (await storage.async_disk_usage())["bytes"] == 0

    asyncio.run(scenario())


def test_inaccessible_file_makes_disk_usage_unavailable_and_caches_the_failure(
    hass, tmp_path, monkeypatch, caplog
):
    hass.config.path = lambda *parts: str(tmp_path.joinpath(*parts))
    storage_dir = tmp_path / ".storage"
    storage_dir.mkdir()
    (storage_dir / STORAGE_KEY).write_bytes(b"data")
    original_stat = Path.stat
    denied = [True]

    def stat(path, *args, **kwargs):
        if path.name == COHERENCE_STORAGE_KEY and denied[0]:
            raise PermissionError("not readable")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    ticks = [100.0]
    monkeypatch.setattr(storage_module, "monotonic", lambda: ticks[0])
    storage = AlertManagerStorage(hass)
    first = asyncio.run(storage.async_disk_usage())
    assert first["bytes"] is None
    denied[0] = False
    assert asyncio.run(storage.async_disk_usage()) == first
    assert len(caplog.records) == 1
    assert "Unable to measure Alert Manager storage size" in caplog.text
    ticks[0] += 300
    assert asyncio.run(storage.async_disk_usage())["bytes"] == 4
