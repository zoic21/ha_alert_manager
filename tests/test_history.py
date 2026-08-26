"""Persistent resolved-alert history, retention and isolation tests."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from custom_components.alert_manager.const import (
    DEFAULT_HISTORY_LIMIT,
    EVENT_ALERT_RESOLVED,
    HISTORY_STORAGE_KEY,
)
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertStatus
from custom_components.alert_manager.yaml_io import dump_config_yaml


def run(coroutine):
    return asyncio.run(coroutine)


def make_manager(hass, entry):
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    return manager


def _resolve_unavailable(manager, hass, set_now, at, entity_id="sensor.test"):
    set_now(at)
    hass.states.set(entity_id, "unavailable", {"friendly_name": "Archived name"})
    run(manager.async_evaluate_entity(entity_id))
    assert manager.records[f"unavailable:{entity_id}"].status is AlertStatus.ACTIVE
    set_now(at + timedelta(seconds=30))
    hass.states.set(entity_id, "ok", {"friendly_name": "Current name"})
    run(manager.async_evaluate_entity(entity_id))


def test_active_resolution_preserves_snapshot_acknowledgement_and_persists(
    hass, entry, set_now, registry_entry, device_entry
):
    """A resolved active rule freezes all useful data across a reload."""
    start = datetime(2026, 8, 26, 12, tzinfo=UTC)
    set_now(start)
    device = device_entry(hass, name="Rack probe", area_id="rack")
    hass.area_registry.entries["rack"] = type("Area", (), {"name": "Server room"})()
    registry_entry(
        hass,
        "sensor.rack_temperature",
        platform="mqtt",
        device_id=device.id,
    )
    hass.states.set(
        "sensor.rack_temperature",
        "34.5",
        {"friendly_name": "Rack temperature", "unit_of_measurement": "°C"},
    )
    manager = make_manager(hass, entry)
    rule = run(
        manager.async_create_rule(
            {
                "name": "Rack too hot",
                "entity_ids": ["sensor.rack_temperature"],
                "operator": "above",
                "value": 33,
                "duration": 0,
                "source": "state",
                "message": "Cool the rack",
            }
        )
    )
    alert_id = f"rule:{rule['id']}:sensor.rack_temperature"
    run(manager.async_acknowledge(alert_id, "Loïc"))
    set_now(start + timedelta(seconds=75))
    hass.states.set(
        "sensor.rack_temperature",
        "30",
        {"friendly_name": "Renamed later", "unit_of_measurement": "°C"},
    )
    run(manager.async_evaluate_entity("sensor.rack_temperature"))

    assert manager.records == {}
    assert len(manager.history) == 1
    event = manager.history_snapshot()["events"][0]
    assert event == hass.stores[HISTORY_STORAGE_KEY]["events"][0]
    assert event["id"] == alert_id
    assert event["rule_id"] == rule["id"]
    assert event["rule_name"] == "Rack too hot"
    assert event["entity_name"] == "Rack temperature"
    assert event["device_name"] == "Rack probe"
    assert event["area"] == "Server room"
    assert event["message"] == "Cool the rack"
    assert event["trigger_value"] == "34.5"
    assert event["source"] == "state"
    assert event["operator"] == "above"
    assert event["comparison_value"] == 33
    assert event["attribute"] is None
    assert event["final_status"] == "resolved"
    assert event["acknowledged"] is True
    assert event["acknowledged_by"] == "Loïc"
    assert event["acknowledged_at"] == start.isoformat()
    assert event["pending_duration_seconds"] == 0
    assert event["active_duration_seconds"] == 75
    assert event["total_duration_seconds"] == 75

    reloaded = make_manager(hass, entry)
    assert reloaded.history_snapshot()["events"] == [event]


def test_pending_cancellation_is_not_archived(hass, entry):
    """A condition recovered before activation creates no historical event."""
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)
    hass.states.set("sensor.test", "ok")
    run(manager.async_evaluate_entity("sensor.test"))
    assert manager.records == {}
    assert manager.history_snapshot()["events"] == []
    assert HISTORY_STORAGE_KEY not in hass.stores


def test_retention_default_limit_zero_and_deterministic_trimming(hass, entry, set_now):
    """Newest events win on insert and on an immediate limit reduction."""
    manager = make_manager(hass, entry)
    assert manager.get_history_config() == {
        "retention_limit": DEFAULT_HISTORY_LIMIT,
        "enabled": True,
    }
    run(manager.async_update_config({"automatic": {"unavailable": {"delay": 0}}}))
    start = datetime(2026, 8, 26, 10, tzinfo=UTC)
    for index in range(3):
        _resolve_unavailable(
            manager,
            hass,
            set_now,
            start + timedelta(minutes=index),
            f"sensor.test_{index}",
        )
    assert [event.id for event in manager.history] == [
        "unavailable:sensor.test_2",
        "unavailable:sensor.test_1",
        "unavailable:sensor.test_0",
    ]

    assert run(manager.async_set_history_limit(2))["retention_limit"] == 2
    assert [event.id for event in manager.history] == [
        "unavailable:sensor.test_2",
        "unavailable:sensor.test_1",
    ]
    run(manager.async_set_history_limit(1))
    assert [event.id for event in manager.history] == ["unavailable:sensor.test_2"]

    run(manager.async_set_history_limit(0))
    assert manager.history == []
    assert manager.get_history_config()["enabled"] is False
    _resolve_unavailable(
        manager,
        hass,
        set_now,
        start + timedelta(hours=1),
        "sensor.disabled_history",
    )
    assert manager.history == []
    assert hass.stores[HISTORY_STORAGE_KEY] == {"events": []}


def test_clear_history_preserves_all_runtime_partitions(hass, entry, set_now):
    """History deletion never changes active, pending or acknowledged alerts."""
    manager = make_manager(hass, entry)
    run(manager.async_update_config({"automatic": {"unavailable": {"delay": 0}}}))
    start = datetime(2026, 8, 26, 14, tzinfo=UTC)
    _resolve_unavailable(manager, hass, set_now, start, "sensor.archived")

    hass.states.set("sensor.active", "unavailable")
    run(manager.async_evaluate_entity("sensor.active"))
    hass.states.set("sensor.acknowledged", "unavailable")
    run(manager.async_evaluate_entity("sensor.acknowledged"))
    run(manager.async_acknowledge("unavailable:sensor.acknowledged", "Loïc"))
    run(manager.async_update_config({"entity_delays": {"sensor.pending": 900}}))
    hass.states.set("sensor.pending", "unavailable")
    run(manager.async_evaluate_entity("sensor.pending"))
    before = deepcopy(manager.records)

    result = run(manager.async_clear_history())
    assert result["events"] == []
    assert manager.records == before
    snapshot = manager.public_snapshot()
    assert snapshot["active_count"] == 1
    assert snapshot["acknowledge_count"] == 1
    assert snapshot["pending_count"] == 1


def test_history_write_failure_does_not_block_business_resolution(hass, entry, set_now):
    """The resolved event and runtime removal survive a history-store failure."""
    manager = make_manager(hass, entry)
    run(manager.async_update_config({"automatic": {"unavailable": {"delay": 0}}}))
    hass.states.set("sensor.test", "unavailable")
    run(manager.async_evaluate_entity("sensor.test"))

    async def fail_history(_entries):
        raise OSError("history unavailable")

    manager.history_storage.async_save = fail_history
    set_now(datetime(2026, 8, 26, 16, tzinfo=UTC))
    hass.states.set("sensor.test", "ok")
    run(manager.async_evaluate_entity("sensor.test"))

    assert manager.records == {}
    assert manager.history == []
    assert len(manager._pending_history) == 1
    assert any(event == EVENT_ALERT_RESOLVED for event, _data in hass.bus.fired)


def test_yaml_export_import_excludes_history_and_preserves_local_retention(hass, entry):
    """History data and retention are outside the V1.5 YAML interchange."""
    manager = make_manager(hass, entry)
    run(manager.async_set_history_limit(42))
    exported = manager.export_config_yaml()
    assert "history" not in exported
    assert "retention" not in exported
    imported = run(manager.async_import_config(dump_config_yaml(manager.get_config())))
    assert imported["config"]["history_limit"] == 42
    assert manager.get_history_config()["retention_limit"] == 42
