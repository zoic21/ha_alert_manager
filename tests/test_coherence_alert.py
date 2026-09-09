"""Aggregate coherence source, report coverage and ordinary alert lifecycle."""

import asyncio
from copy import deepcopy
from datetime import timedelta

import pytest
from homeassistant.util import dt as dt_util

from custom_components.alert_manager import coherence
from custom_components.alert_manager.coherence_alert import (
    COHERENCE_ALERT_ID as ALERT_ID,
)
from custom_components.alert_manager.coherence_alert import (
    COHERENCE_ENTITY_ID,
    prepare_alert_report,
)
from custom_components.alert_manager.const import (
    DATA_COHERENCE_RESULT,
    DATA_MANAGER,
    EVENT_ALERT_RESOLVED,
    EVENT_ALERT_STARTED,
)
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertStatus
from custom_components.alert_manager.validation import validate_config
from custom_components.alert_manager.yaml_io import dump_config_yaml, parse_config_yaml


def report(count=1, *, complete=True):
    return {
        "scanned_at": dt_util.now().isoformat(),
        "results": [
            {"entity_id": f"sensor.missing_{i}", "file": "a.yaml"} for i in range(count)
        ],
        "missing_count": count,
        "missing_entity_count": count,
        "files_skipped": 0,
        "alert_complete": complete,
    }


def events(hass, kind):
    return [
        data
        for event, data in hass.bus.fired
        if event == kind and data["id"] == ALERT_ID
    ]


async def setup(hass, entry):
    manager = AlertManager(hass, entry)
    await manager.async_setup()
    hass.data[DATA_MANAGER] = manager
    return manager


async def drain():
    for _ in range(8):
        await asyncio.sleep(0)


def profile():
    return {
        "id": "coherence-test",
        "name": "All alerts",
        "enabled": True,
        "targets": ["notify.phone"],
        "label_ids": [],
        "exceptions": [],
        "default_policy": {
            "notify_on_start": True,
            "notify_on_resolved": True,
            "reminder_interval": 300,
        },
    }


def test_enable_update_acknowledge_recover_and_new_episode(hass, entry, set_now):
    async def scenario():
        manager = await setup(hass, entry)
        hass.data[DATA_COHERENCE_RESULT] = report(3)
        await manager.async_update_config({"coherence_alert_enabled": True})
        first = manager.records[ALERT_ID]
        assert first.status is AlertStatus.ACTIVE
        assert first.delay == 0
        assert manager.public_snapshot()["pending_count"] == 0
        assert first.details.value == 3
        assert len(events(hass, EVENT_ALERT_STARTED)) == 1
        await manager.async_acknowledge(ALERT_ID, "Loïc")
        hass.data[DATA_COHERENCE_RESULT] = report(5)
        await manager.async_reconcile_coherence_alert()
        assert manager.records[ALERT_ID] is first
        assert first.acknowledged and first.details.value == 5
        assert "5" in first.details.message
        await manager.async_evaluate_all()
        assert len(events(hass, EVENT_ALERT_STARTED)) == 1
        assert manager.public_snapshot()["acknowledge_count"] == 1
        hass.data[DATA_COHERENCE_RESULT] = report(0)
        await manager.async_reconcile_coherence_alert()
        assert ALERT_ID not in manager.records
        assert len(events(hass, EVENT_ALERT_RESOLVED)) == 1
        await manager._async_flush_history()
        assert len(manager.history) == 1
        assert manager.history[0].acknowledged
        set_now(dt_util.now() + timedelta(minutes=1))
        hass.data[DATA_COHERENCE_RESULT] = report(2)
        await manager.async_reconcile_coherence_alert()
        assert manager.records[ALERT_ID].detected_at != first.detected_at
        assert len(events(hass, EVENT_ALERT_STARTED)) == 2

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "invalid", [None, {}, {"results": None}, report(0, complete=False)]
)
def test_unknown_report_never_recovers_an_acknowledged_alert(hass, entry, invalid):
    async def scenario():
        manager = await setup(hass, entry)
        hass.data[DATA_COHERENCE_RESULT] = report()
        await manager.async_update_config({"coherence_alert_enabled": True})
        await manager.async_acknowledge(ALERT_ID, "test")
        original = deepcopy(manager.records[ALERT_ID])
        hass.data[DATA_COHERENCE_RESULT] = invalid
        await manager.async_reconcile_coherence_alert()
        await manager.async_evaluate_all()
        assert manager.records[ALERT_ID] == original
        assert not events(hass, EVENT_ALERT_RESOLVED)

    asyncio.run(scenario())


def test_enable_without_report_and_administrative_disable(hass, entry):
    async def scenario():
        manager = await setup(hass, entry)
        await manager.async_update_config({"notification_profiles": [profile()]})
        await manager.async_update_config({"coherence_alert_enabled": True})
        assert ALERT_ID not in manager.records
        hass.data[DATA_COHERENCE_RESULT] = report()
        await manager.async_reconcile_coherence_alert()
        await drain()
        runtime = manager.notification_runtime
        assert runtime._batches[("coherence-test", "started")].items[ALERT_ID]
        assert runtime._runtime["coherence-test"][ALERT_ID].next_reminder
        await manager.async_update_config({"coherence_alert_enabled": False})
        await drain()
        assert ALERT_ID not in manager.records
        assert not runtime._batches
        assert ALERT_ID not in runtime._runtime["coherence-test"]
        assert not manager.history and not manager._pending_history
        assert not events(hass, EVENT_ALERT_RESOLVED)
        # Existing report immediately reactivates via ordinary profile routing.
        await manager.async_update_config({"coherence_alert_enabled": True})
        await drain()
        assert runtime._batches[("coherence-test", "started")].items[ALERT_ID]
        await runtime._async_flush_batch("coherence-test", "started")
        hass.data[DATA_COHERENCE_RESULT] = report(0)
        await manager.async_reconcile_coherence_alert()
        await drain()
        assert runtime._batches[("coherence-test", "resolved")].items[ALERT_ID]

    asyncio.run(scenario())


@pytest.mark.parametrize("complete", [True, False])
def test_restart_preserves_episode_and_acknowledgment(hass, entry, complete):
    async def scenario():
        first = await setup(hass, entry)
        hass.data[DATA_COHERENCE_RESULT] = report()
        await first.async_update_config({"coherence_alert_enabled": True})
        await first.async_acknowledge(ALERT_ID, "test")
        original = deepcopy(first.records[ALERT_ID])
        await first.async_unload()
        if not complete:
            hass.data[DATA_COHERENCE_RESULT] = report(0, complete=False)
        hass.bus.fired.clear()
        restarted = await setup(hass, entry)
        await restarted._async_finish_startup_reconciliation()
        assert restarted.records[ALERT_ID] == original
        assert not events(hass, EVENT_ALERT_STARTED)
        assert not events(hass, EVENT_ALERT_RESOLVED)
        hass.data[DATA_COHERENCE_RESULT] = report(0)
        await restarted.async_reconcile_coherence_alert()
        assert ALERT_ID not in restarted.records

    asyncio.run(scenario())


def test_scan_overlap_and_failure_use_one_reconciliation(hass, entry, monkeypatch):
    async def scenario():
        manager = await setup(hass, entry)
        await manager.async_update_config({"coherence_alert_enabled": True})
        entered, release = asyncio.Event(), asyncio.Event()
        calls = 0

        async def scan(*args, **kwargs):
            nonlocal calls
            calls += 1
            entered.set()
            await release.wait()
            return report()

        monkeypatch.setattr(coherence, "async_scan_configuration", scan)
        first = asyncio.create_task(coherence.async_run_coherence_scan(hass))
        await entered.wait()
        second = asyncio.create_task(coherence.async_run_coherence_scan(hass))
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(first, second)
        assert calls == 1
        assert len(events(hass, EVENT_ALERT_STARTED)) == 1
        original = deepcopy(manager.records[ALERT_ID])

        async def failed(*args, **kwargs):
            raise OSError("scan failed")

        monkeypatch.setattr(coherence, "async_scan_configuration", failed)
        with pytest.raises(OSError, match="scan failed"):
            await coherence.async_run_coherence_scan(hass)
        assert manager.records[ALERT_ID] == original

    asyncio.run(scenario())


def test_report_coverage_survives_successive_skipped_categories():
    previous = report(2)
    previous["results"][0]["reference_type"] = "zha_device_ieee"
    previous["results"][1]["file"] = "esphome/node.yaml"
    for _ in range(3):
        partial = report(0)
        partial["checks"] = {"zha_device_ieee": "not_loaded"}
        prepare_alert_report(partial, previous, False)
        assert not partial["alert_complete"]
        assert partial["alert_required_checks"] == ["zha_device_ieee"]
        assert partial["alert_requires_esphome"]
        previous = partial
    completed = report(0)
    completed["checks"] = {"zha_device_ieee": "executed"}
    prepare_alert_report(completed, previous, True)
    assert completed["alert_complete"]


def test_skipped_file_and_malformed_yaml_cannot_claim_recovery(tmp_path):
    (tmp_path / "a.yaml").write_text("entity_id: sensor.missing\n---\nbad: [")
    result = coherence.scan_configuration(tmp_path, frozenset())
    prepare_alert_report(result, report(), True)
    assert result["files_skipped"] == 1
    assert not result["alert_complete"]
    assert result["results"] == []


def test_option_is_strict_persisted_yaml_and_disabled_by_default():
    config = validate_config({})
    assert config["coherence_alert_enabled"] is False
    config["coherence_alert_enabled"] = True
    assert (
        parse_config_yaml(dump_config_yaml(config))["coherence_alert_enabled"] is True
    )
    for value in ("true", 1, None):
        with pytest.raises(ValueError, match="coherence_alert_enabled"):
            validate_config({"coherence_alert_enabled": value})


def test_pause_resume_and_failed_enable_preserve_durable_state(
    hass, entry, monkeypatch
):
    async def scenario():
        manager = await setup(hass, entry)
        hass.data[DATA_COHERENCE_RESULT] = report()
        original_save = manager.storage.async_save

        async def fail(*args, **kwargs):
            raise OSError("disk error")

        monkeypatch.setattr(manager.storage, "async_save", fail)
        with pytest.raises(OSError, match="disk error"):
            await manager.async_update_config({"coherence_alert_enabled": True})
        assert not manager.config["coherence_alert_enabled"]
        assert ALERT_ID not in manager.records
        monkeypatch.setattr(manager.storage, "async_save", original_save)
        await manager.async_update_config({"coherence_alert_enabled": True})
        await manager.async_set_monitoring(False)
        hass.data[DATA_COHERENCE_RESULT] = report(0)
        await manager.async_reconcile_coherence_alert()
        assert ALERT_ID in manager.records
        await manager.async_set_monitoring(True)
        assert ALERT_ID not in manager.records

    asyncio.run(scenario())


def test_registry_rename_cannot_change_aggregate_identity(hass, entry):
    from custom_components.alert_manager.transactions import (
        StartupReconciliationTransaction,
    )

    async def scenario():
        manager = await setup(hass, entry)
        hass.data[DATA_COHERENCE_RESULT] = report()
        await manager.async_update_config({"coherence_alert_enabled": True})
        transaction = StartupReconciliationTransaction.capture(
            manager.records, {ALERT_ID}
        )
        transaction.record_entity_renames({COHERENCE_ENTITY_ID: "sensor.renamed"})
        restored = transaction.reconciled_original_records()
        assert set(restored) == {ALERT_ID}
        assert restored[ALERT_ID].details.entity_id == COHERENCE_ENTITY_ID
        manager._pending_entity_renames[COHERENCE_ENTITY_ID] = "sensor.renamed"
        manager._apply_pending_entity_renames()
        assert ALERT_ID in manager.records
        assert manager.records[ALERT_ID].details.entity_id == COHERENCE_ENTITY_ID

    asyncio.run(scenario())
