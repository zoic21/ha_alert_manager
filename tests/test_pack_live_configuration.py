"""Pack edits reconcile existing observations and administrative removals."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from homeassistant.helpers import entity_registry as er

from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertStatus


def run(coroutine):
    return asyncio.run(coroutine)


def test_pending_device_delay_edits_preserve_start_and_acknowledged_identity(
    hass, entry, set_now
):
    start = datetime(2026, 9, 12, tzinfo=UTC)
    set_now(start)
    device = "a" * 32
    er.async_get(hass).entries["sensor.a"] = SimpleNamespace(
        entity_id="sensor.a",
        device_id=device,
        labels=set(),
        disabled_by=None,
        platform="test",
        config_entry_id=None,
        area_id=None,
        name=None,
        original_name=None,
    )
    hass.states.set("sensor.a", "unavailable")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    run(
        manager.async_update_config(
            {
                "automatic": {
                    "unavailable": {
                        "delay": 120,
                        "device_overrides": {device: {"delay": 60}},
                    }
                }
            }
        )
    )
    alert_id = "unavailable:sensor.a"
    record = manager.records[alert_id]
    assert record.detected_at == start
    set_now(start + timedelta(seconds=30))
    run(
        manager.async_update_config(
            {
                "automatic": {
                    "unavailable": {"device_overrides": {device: {"delay": 180}}}
                }
            }
        )
    )
    assert manager.records[alert_id].detected_at == start
    assert manager.records[alert_id].status is AlertStatus.PENDING
    assert manager.records[alert_id].delay == 180
    run(
        manager.async_update_config(
            {
                "automatic": {
                    "unavailable": {"entity_overrides": {"sensor.a": {"delay": 0}}}
                }
            }
        )
    )
    assert manager.records[alert_id].status is AlertStatus.ACTIVE
    run(manager.async_acknowledge(alert_id, None))
    active = deepcopy(manager.records[alert_id])
    run(
        manager.async_update_config(
            {"automatic": {"unavailable": {"entity_overrides": {}}}}
        )
    )
    current = manager.records[alert_id]
    assert current.detected_at == active.detected_at
    assert current.active_since == active.active_since
    assert current.acknowledged_at == active.acknowledged_at
    assert current.status is AlertStatus.ACTIVE


def test_disabling_target_cancels_batch_reminder_and_records_administrative_reason(
    hass, entry, set_now
):
    from test_notifications import _profile

    async def scenario():
        set_now(datetime(2026, 9, 12, tzinfo=UTC))
        hass.states.set("sensor.a", "ok")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        profile = _profile()
        profile["label_ids"] = []
        profile["default_policy"]["reminder_interval"] = 60
        await manager.async_update_config(
            {
                "automatic": {"unavailable": {"delay": 0}},
                "notification_profiles": [profile],
            }
        )
        hass.states.set("sensor.a", "unavailable")
        await manager.async_evaluate_entity("sensor.a")
        alert_id = "unavailable:sensor.a"
        assert alert_id in manager.records
        await asyncio.sleep(0)
        from custom_components.alert_manager.const import EVENT_ALERT_STARTED

        await manager.notification_runtime._async_handle_event(
            EVENT_ALERT_STARTED, manager.records[alert_id].as_public_dict()
        )
        assert (
            alert_id in manager.notification_runtime._batches[("loic", "started")].items
        )
        events = list(hass.bus.fired)
        await manager.async_update_config(
            {
                "automatic": {
                    "unavailable": {
                        "entity_overrides": {"sensor.a": {"enabled": False}}
                    }
                }
            }
        )
        assert alert_id not in manager.records
        assert all(
            alert_id not in batch.items
            for batch in manager.notification_runtime._batches.values()
        )
        assert all(
            alert_id not in data
            for data in manager.notification_runtime._runtime.values()
        )
        history = next(item for item in manager.history if item.id == alert_id)
        assert history.condition_params["resolution_reason"] == "monitoring_disabled"
        assert hass.bus.fired == events
        assert alert_id not in manager._timers

    run(scenario())


def test_failed_disable_restores_execution_cycle_counters(hass, entry, monkeypatch):
    import pytest

    from custom_components.alert_manager.packs import execution_errors

    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    hass.states.set("automation.test", "on", {"current": 0})
    tracker = execution_errors._ExecutionTracker(consecutive_failures=2)
    hass.data[execution_errors._DATA_CYCLES] = {"automation.test": tracker}

    async def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(manager.storage, "async_save", fail)
    with pytest.raises(OSError, match="disk full"):
        run(
            manager.async_update_config(
                {"automatic": {"execution_errors": {"enabled": False}}}
            )
        )
    assert manager.config["automatic"]["execution_errors"]["enabled"] is True
    assert (
        hass.data[execution_errors._DATA_CYCLES]["automation.test"].consecutive_failures
        == 2
    )


def test_idless_legacy_import_reuses_unambiguous_unchanged_rule(hass, entry):
    import yaml

    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    rule = run(
        manager.async_create_rule(
            {
                "name": "High",
                "entity_ids": ["sensor.a"],
                "operator": "above",
                "value": 10,
                "duration": 0,
            }
        )
    )
    document = yaml.safe_load(run(manager.async_export_config_yaml()))
    document["rules"][0].pop("id")
    run(manager.async_import_config(yaml.safe_dump(document)))
    assert manager.config["rules"][0]["id"] == rule["id"]
