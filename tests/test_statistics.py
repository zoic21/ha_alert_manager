"""Bounded diagnostics, real transitions and measurement boundaries."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from pack_test_helpers import automatic_settings

from custom_components.alert_manager import manager_runtime
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import Rule
from custom_components.alert_manager.statistics import RuntimeStatistics


def test_hourly_aggregation_expiration_and_reuse(hass, set_now):
    now = datetime(2026, 10, 25, 0, 59, 59, tzinfo=UTC)
    set_now(now)
    stats = RuntimeStatistics()
    buckets = tuple(map(id, stats._buckets))
    stats.record_evaluation(2_000_000)
    stats.record_evaluation(8_000_000)
    stats.record_notification("phone")
    stats.record_activity("pending")
    set_now(now + timedelta(seconds=1))
    stats.record_evaluation(20_000_000)
    stats.record_notification("phone")
    stats.record_notification("tablet")
    result = stats.snapshot()
    assert result["evaluation_count"] == 3
    assert result["evaluation_total_ms"] == 30
    assert result["evaluation_average_ms"] == 10
    assert result["evaluation_max_ms"] == 20
    assert result["notification_profiles"] == {"phone": 2, "tablet": 1}
    assert result["notifications"] == 3
    assert result["observed_from"] == now.isoformat()
    # At hour +24 the first bucket is expired, even without another write.
    set_now(now.replace(minute=0, second=0) + timedelta(hours=24))
    result = stats.snapshot()
    assert result["evaluation_count"] == 1
    assert result["evaluation_total_ms"] == 20
    assert result["pending"] == 0
    stats.record_evaluation(1_000_000)
    assert stats.snapshot()["evaluation_average_ms"] == 10.5
    assert tuple(map(id, stats._buckets)) == buckets
    assert len(buckets) == 24
    set_now(now + timedelta(days=10))
    assert stats.snapshot()["notifications"] == 0
    assert stats.snapshot()["evaluation_max_ms"] == 0
    stats.record_notification("new")
    assert stats.snapshot()["notification_profiles"] == {"new": 1}
    assert (
        stats.snapshot()["observed_from"]
        == (now.replace(minute=0, second=0) + timedelta(days=10, hours=-23)).isoformat()
    )


def test_utc_hours_and_deleted_profiles(hass, set_now):
    from zoneinfo import ZoneInfo

    stats = RuntimeStatistics()
    first = datetime(2026, 10, 25, 2, 30, tzinfo=ZoneInfo("Europe/Paris"), fold=0)
    second = first.replace(fold=1)
    set_now(first)
    stats.record_notification("deleted")
    set_now(second)
    stats.record_notification("kept")
    assert len({b.hour for b in stats._buckets if b.hour is not None}) == 2
    stats.retain_profiles({"kept"})
    assert stats.snapshot()["notification_profiles"] == {"kept": 1}
    assert stats.snapshot()["notifications"] == 2
    # A backwards wall-clock jump must not include future buckets.
    set_now(first)
    assert stats.snapshot()["notifications"] == 1


def test_activity_transactions_keep_only_committed_transitions(hass):
    stats = RuntimeStatistics()
    with pytest.raises(ValueError), stats.activity_transaction():
        stats.record_activity("activations")
        with stats.activity_transaction():
            stats.record_activity("pending")
        raise ValueError("store failed")
    assert stats.snapshot()["activations"] == 0
    assert stats.snapshot()["pending"] == 0
    with stats.activity_transaction():
        stats.record_activity("pending")
    assert stats.snapshot()["pending"] == 1


def test_lifecycle_statistics_and_restart(hass, entry, set_now):
    async def scenario():
        start = datetime(2026, 9, 8, 10, tzinfo=UTC)
        set_now(start)
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        hass.states.set("sensor.test", "unavailable")
        await manager.async_evaluate_entity("sensor.test")
        await manager.async_evaluate_entity("sensor.test")
        assert manager.statistics.snapshot()["pending"] == 1
        set_now(start + timedelta(seconds=901))
        await manager.async_evaluate_entity("sensor.test")
        alert_id = "unavailable:sensor.test"
        assert manager.statistics.snapshot()["activations"] == 1
        await manager.async_acknowledge(alert_id, "Loïc")
        await manager.async_acknowledge(alert_id, "Loïc")
        await manager.async_set_acknowledgements([alert_id], True, "Loïc", duration=300)
        assert manager.statistics.snapshot()["acknowledgments"] == 1
        await manager.async_unacknowledge(alert_id, "Loïc")
        await manager.async_acknowledge(alert_id, "Loïc")
        assert manager.statistics.snapshot()["acknowledgments"] == 2
        await manager.async_unload()
        restored = AlertManager(hass, entry)
        await restored.async_setup()
        set_now(start + timedelta(seconds=1022))
        await restored._async_finish_startup_reconciliation()
        assert restored.statistics.snapshot()["activations"] == 0
        assert restored.statistics.snapshot()["pending"] == 0
        assert restored.statistics.snapshot()["acknowledgments"] == 0
        hass.states.set("sensor.test", "ok")
        await restored.async_evaluate_entity("sensor.test")
        await restored.async_evaluate_entity("sensor.test")
        assert restored.statistics.snapshot()["resolutions"] == 1
        await restored.async_update_config(automatic_settings(delay=0))
        hass.states.set("sensor.test", "unavailable")
        await restored.async_evaluate_entity("sensor.test")
        assert restored.statistics.snapshot()["activations"] == 1
        assert restored.statistics.snapshot()["pending"] == 0
        await restored.async_unload()

    asyncio.run(scenario())


def test_committed_pending_and_failed_configuration(hass, entry):
    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        await manager.async_set_monitoring(False)
        hass.states.set("sensor.test", "unavailable")
        await manager.async_set_monitoring(True)
        assert manager.statistics.snapshot()["pending"] == 1
        previous = deepcopy(manager.records)
        manager._emit_resume_events(previous)
        assert manager.statistics.snapshot()["pending"] == 1
        original = manager.storage.async_save

        async def fail(*args, **kwargs):
            raise OSError("store failed")

        manager.storage.async_save = fail
        with pytest.raises(OSError):
            await manager.async_update_config(automatic_settings(delay=0))
        assert manager.statistics.snapshot()["activations"] == 0
        manager.storage.async_save = original
        await manager.async_unload()

    asyncio.run(scenario())


def test_measurement_is_one_synchronous_live_rule_entity(hass, entry, monkeypatch):
    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        hass.states.set("sensor.test", "on")
        rule = Rule(
            id="test",
            name="Test",
            entity_ids=["sensor.test"],
            operator="equals",
            value="on",
            duration=0,
        )
        ticks = iter([100, 2_000_100, 50_000_000])
        monkeypatch.setattr(manager_runtime, "perf_counter_ns", lambda: next(ticks))
        state = hass.states.get("sensor.test")
        manager._evaluate_custom_rule(rule, state)
        result = manager.statistics.snapshot()
        assert result["evaluation_count"] == 1
        assert result["evaluation_total_ms"] == 2
        manager._evaluate_custom_rule(rule, state, dry_run=True)
        await asyncio.sleep(0)
        assert manager.statistics.snapshot()["evaluation_total_ms"] == 2
        assert manager.statistics.snapshot()["evaluation_count"] == 1
        await manager.async_unload()

    asyncio.run(scenario())


def test_silent_import_counts_transitions_without_replaying_events(hass, entry):
    from custom_components.alert_manager.yaml_io import dump_config_yaml

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        hass.states.set("sensor.test", "unavailable")
        config = deepcopy(manager.config)
        config["automatic"]["unavailable"]["delay"] = 0
        events = list(hass.bus.fired)
        await manager.async_import_config(dump_config_yaml(config))
        assert manager.statistics.snapshot()["activations"] == 1
        assert hass.bus.fired == events
        # Rebuilding the same active occurrence is not another activation.
        await manager.async_import_config(dump_config_yaml(config))
        assert manager.statistics.snapshot()["activations"] == 1
        assert hass.bus.fired == events
        hass.states.set("sensor.test", "ok")
        await manager.async_import_config(dump_config_yaml(config))
        assert manager.statistics.snapshot()["resolutions"] == 1
        assert hass.bus.fired == events
        await manager.async_unload()

    asyncio.run(scenario())
