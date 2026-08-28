"""Tests for the on-demand coherence button and issue sensor."""

from __future__ import annotations

import asyncio
import importlib

from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.alert_manager.button import (
    AlertManagerCoherenceButton,
)
from custom_components.alert_manager.button import (
    async_setup_entry as setup_button,
)
from custom_components.alert_manager.const import (
    DATA_COHERENCE_RESULT,
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
        "results": [
            {"entity_id": "sensor.first"},
            {"entity_id": "sensor.first"},
            {"entity_id": "binary_sensor.second"},
        ],
    }
    hass.data[DATA_COHERENCE_RESULT] = result
    async_dispatcher_send(hass, SIGNAL_COHERENCE_UPDATED, result)

    assert sensor.native_value == 2
    assert sensor.writes == 1

    async_dispatcher_send(hass, SIGNAL_COHERENCE_UPDATED, result)
    assert sensor.writes == 1


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

    async def scan(_hass):
        return expected

    monkeypatch.setattr(coherence_module, "async_scan_configuration", scan)
    sensor = AlertManagerCoherenceIssueSensor()
    sensor.hass = hass
    run(sensor.async_added_to_hass())

    result = run(coherence_module.async_run_coherence_scan(hass))

    assert result is expected
    assert hass.data[DATA_COHERENCE_RESULT] is expected
    assert sensor.native_value == 2
    assert sensor.writes == 1
