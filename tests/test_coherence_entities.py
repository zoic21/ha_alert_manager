"""Tests for the on-demand coherence button and issue sensor."""

from __future__ import annotations

import asyncio
import importlib
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.alert_manager.button import (
    AlertManagerCoherenceButton,
)
from custom_components.alert_manager.button import (
    async_setup_entry as setup_button,
)
from custom_components.alert_manager.const import (
    COHERENCE_STORAGE_KEY,
    DATA_COHERENCE_RESULT,
    DATA_MANAGER,
    SIGNAL_COHERENCE_UPDATED,
)
from custom_components.alert_manager.sensor import AlertManagerCoherenceIssueSensor


def run(coroutine):
    return asyncio.run(coroutine)


def test_button_platform_exposes_stable_entity_and_runs_scan(hass, entry, monkeypatch):
    """The native button launches the shared on-demand scan entry point."""
    entities = []
    run(setup_button(hass, entry, entities.extend))

    assert len(entities) == 1
    button = entities[0]
    assert isinstance(button, AlertManagerCoherenceButton)
    assert button.entity_id == "button.alert_manager_check_coherence"
    assert button._attr_unique_id == "alert_manager_check_coherence"
    button.hass = hass
    calls = []

    async def scan(scan_hass):
        calls.append(scan_hass)
        return {"missing_entity_count": 0, "results": []}

    button_module = importlib.import_module("custom_components.alert_manager.button")
    monkeypatch.setattr(button_module, "async_run_coherence_scan", scan)
    run(button.async_press())

    assert calls == [hass]


def test_button_rejects_non_admin_users_but_allows_internal_calls(
    hass, entry, monkeypatch
):
    """Entity permissions cannot let a non-admin bypass the panel restriction."""
    entities = []
    run(setup_button(hass, entry, entities.extend))
    button = entities[0]
    button.hass = hass
    calls = []

    async def scan(scan_hass):
        calls.append(scan_hass)
        return {"missing_entity_count": 0, "results": []}

    button_module = importlib.import_module("custom_components.alert_manager.button")
    monkeypatch.setattr(button_module, "async_run_coherence_scan", scan)
    hass.auth.users["regular-user"] = SimpleNamespace(is_admin=False)
    button._context = SimpleNamespace(user_id="regular-user")

    with pytest.raises(ServiceValidationError, match="administrator"):
        run(button.async_press())
    assert calls == []

    button._context = SimpleNamespace(user_id=None)
    run(button.async_press())
    assert calls == [hass]


def test_sensor_is_unknown_until_scan_then_tracks_distinct_issue_count(hass):
    """The issue sensor never reports a false zero before its first scan."""
    sensor = AlertManagerCoherenceIssueSensor()
    sensor.hass = hass
    run(sensor.async_added_to_hass())

    assert sensor.entity_id == "sensor.alert_manager_coherence_issue"
    assert sensor.native_value is None
    assert getattr(sensor, "writes", 0) == 0

    result = {
        "missing_entity_count": 2,
        "scanned_at": "2026-08-24T12:00:00+00:00",
        "results": [
            {"entity_id": "sensor.first"},
            {"entity_id": "sensor.first"},
            {"entity_id": "binary_sensor.second"},
        ],
    }
    hass.data[DATA_COHERENCE_RESULT] = result
    async_dispatcher_send(hass, SIGNAL_COHERENCE_UPDATED, result)

    assert sensor.native_value == 2
    assert sensor.extra_state_attributes == {"scanned_at": "2026-08-24T12:00:00+00:00"}
    assert sensor.writes == 1

    async_dispatcher_send(hass, SIGNAL_COHERENCE_UPDATED, result)
    assert sensor.writes == 1

    newer_result = {
        **result,
        "scanned_at": "2026-08-24T13:00:00+00:00",
        "results": [{"entity_id": "sensor.different"}],
    }
    async_dispatcher_send(hass, SIGNAL_COHERENCE_UPDATED, newer_result)
    assert sensor.native_value == 2
    assert sensor.extra_state_attributes == {"scanned_at": "2026-08-24T13:00:00+00:00"}
    assert sensor.writes == 2


def test_sensor_restores_latest_session_result_when_added(hass):
    """A sensor added after a panel scan immediately exposes that result."""
    hass.data[DATA_COHERENCE_RESULT] = {
        "missing_entity_count": 1,
        "results": [{"entity_id": "sensor.gone"}],
    }
    sensor = AlertManagerCoherenceIssueSensor()
    sensor.hass = hass

    run(sensor.async_added_to_hass())

    assert sensor.native_value == 1
    assert sensor.writes == 1


def test_shared_scan_entry_point_stores_result_and_updates_sensor(hass, monkeypatch):
    """Panel and button scans both publish through the same small entry point."""
    expected = {
        "missing_count": 3,
        "missing_entity_count": 2,
        "results": [
            {"entity_id": "sensor.first"},
            {"entity_id": "sensor.first"},
            {"entity_id": "sensor.second"},
        ],
    }
    coherence_module = importlib.import_module(
        "custom_components.alert_manager.coherence"
    )

    scan_options = {}

    async def scan(_hass, **options):
        scan_options.update(options)
        return expected

    monkeypatch.setattr(coherence_module, "async_scan_configuration", scan)
    hass.data[DATA_MANAGER] = SimpleNamespace(
        config={
            "coherence_scan_esphome": False,
            "coherence_ignored_entity_references": ["toto.plop"],
        }
    )
    sensor = AlertManagerCoherenceIssueSensor()
    sensor.hass = hass
    run(sensor.async_added_to_hass())

    result = run(coherence_module.async_run_coherence_scan(hass))

    assert result is expected
    assert result["scanned_at"] == "2026-08-24T12:00:00+00:00"
    assert hass.data[DATA_COHERENCE_RESULT] is expected
    assert hass.stores[COHERENCE_STORAGE_KEY] == expected
    assert hass.stores[COHERENCE_STORAGE_KEY] is not expected
    assert hass.store_options[COHERENCE_STORAGE_KEY]["serialize_in_event_loop"] is False
    assert hass.store_save_count == 1
    assert sensor.native_value == 2
    assert sensor.writes == 1
    assert scan_options == {
        "scan_esphome": False,
        "ignored_entity_references": frozenset({"toto.plop"}),
    }


def test_concurrent_scan_requests_share_one_scan_and_one_store_write(hass, monkeypatch):
    """Panel, button and schedule callers join the same in-flight operation."""
    coherence_module = importlib.import_module(
        "custom_components.alert_manager.coherence"
    )

    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def scan(_hass, **_options):
            nonlocal calls
            calls += 1
            started.set()
            await release.wait()
            return {"missing_entity_count": 0, "results": []}

        monkeypatch.setattr(coherence_module, "async_scan_configuration", scan)
        first = asyncio.create_task(coherence_module.async_run_coherence_scan(hass))
        for _ in range(10):
            if started.is_set():
                break
            await asyncio.sleep(0)
        assert started.is_set(), repr(first)
        second = asyncio.create_task(coherence_module.async_run_coherence_scan(hass))
        await asyncio.sleep(0)

        assert calls == 1
        release.set()
        first_result, second_result = await asyncio.gather(first, second)
        assert first_result is second_result
        assert hass.store_save_count == 1

    run(scenario())


def test_latest_scan_is_restored_from_storage_after_restart(hass):
    """The complete latest report survives the in-memory integration state."""
    stored = {
        "scanned_at": "2026-08-23T08:30:00+00:00",
        "missing_count": 3,
        "missing_entity_count": 2,
        "results": [
            {"entity_id": "sensor.first"},
            {"entity_id": "sensor.first"},
            {"entity_id": "sensor.second"},
        ],
    }
    hass.stores[COHERENCE_STORAGE_KEY] = stored
    coherence_module = importlib.import_module(
        "custom_components.alert_manager.coherence"
    )

    restored = run(coherence_module.async_load_coherence_result(hass))
    sensor = AlertManagerCoherenceIssueSensor()
    sensor.hass = hass
    run(sensor.async_added_to_hass())

    assert restored is stored
    assert hass.data[DATA_COHERENCE_RESULT] is stored
    assert sensor.native_value == 2


def test_invalid_stored_scan_is_ignored(hass):
    """A damaged storage record leaves the sensor unknown instead of crashing."""
    hass.stores[COHERENCE_STORAGE_KEY] = {
        "missing_entity_count": "not-a-number",
        "results": [],
        "scanned_at": "2026-08-23T08:30:00+00:00",
    }
    coherence_module = importlib.import_module(
        "custom_components.alert_manager.coherence"
    )

    assert run(coherence_module.async_load_coherence_result(hass)) is None
    assert DATA_COHERENCE_RESULT not in hass.data


def test_optional_coherence_schedules_run_only_on_their_due_date(hass, monkeypatch):
    """One daily time listener gates weekly and monthly scans without polling."""
    coherence_module = importlib.import_module(
        "custom_components.alert_manager.coherence"
    )
    calls = []

    async def scan(_hass):
        calls.append(True)
        return {"results": [], "missing_entity_count": 0}

    monkeypatch.setattr(coherence_module, "async_run_coherence_scan", scan)

    assert coherence_module.schedule_coherence_scans(hass, "none") is None
    assert hass.timers == []

    cancel = coherence_module.schedule_coherence_scans(hass, "weekly")
    timer = hass.timers[-1]
    assert (timer["hour"], timer["minute"], timer["second"]) == (3, 5, 0)
    run(timer["action"](datetime(2026, 8, 30, 3, 5, tzinfo=UTC)))
    assert calls == []
    run(timer["action"](datetime(2026, 8, 31, 3, 5, tzinfo=UTC)))
    assert calls == [True]
    cancel()
    assert timer["cancelled"] is True

    coherence_module.schedule_coherence_scans(hass, "monthly")
    timer = hass.timers[-1]
    run(timer["action"](datetime(2026, 9, 2, 3, 5, tzinfo=UTC)))
    assert calls == [True]
    run(timer["action"](datetime(2026, 10, 1, 3, 5, tzinfo=UTC)))
    assert calls == [True, True]

    coherence_module.schedule_coherence_scans(hass, "daily")
    timer = hass.timers[-1]
    run(timer["action"](datetime(2026, 10, 2, 3, 5, tzinfo=UTC)))
    assert calls == [True, True, True]
