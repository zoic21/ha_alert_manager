"""New coherence findings, partial reports, shared scans and delivery routing."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.alert_manager import coherence
from custom_components.alert_manager.const import DATA_COHERENCE_RESULT, DATA_MANAGER
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.notifications import validate_notification_profiles


def finding(entity="sensor.missing", source="automations.yaml", **extra):
    return {
        "entity_id": entity,
        "file": source,
        "line": 12,
        "source_type": "automation",
        "source_name": "Friendly name",
        "link": {"type": "navigate", "path": "/config/automation/edit/stable_id"},
        **extra,
    }


def compare(rows, previous=None, *, scan_esphome=True, ignored=frozenset(), **extra):
    report = {"results": rows, **extra}
    new = coherence._compare_coherence_report(report, previous, scan_esphome, ignored)
    return report, new


def test_semantic_comparison_first_empty_mixed_and_reappearance():
    old = finding()
    report, new = compare([old, {**old, "line": 20}])
    assert new == [old | {"line": 20}]
    moved = old | {"line": 200, "source_name": "Renamed", "scanned_at": "later"}
    other = finding("sensor.other")
    report, new = compare([other, moved], report)
    assert new == [other]
    report, new = compare([moved], report)
    assert new == []
    report, new = compare([moved, other], report)
    assert new == [other]
    report, new = compare([], report)
    assert new == []
    assert compare([old], report)[1] == [old]


@pytest.mark.parametrize(
    "changes",
    [
        {"problem_type": "other_problem"},
        {"file": "scripts.yaml"},
        {"link": {"path": "/config/automation/edit/another_id"}},
    ],
)
def test_semantic_identity_distinguishes_problem_and_source(changes):
    old = finding()
    assert compare([old | changes], {"results": [old]})[1] == [old | changes]


def test_partial_scan_retains_only_failed_sources_and_survives_reload(hass):
    old = finding()
    removed = finding("sensor.removed", "scripts.yaml")
    partial, new = compare(
        [],
        {"results": [old, removed]},
        skipped_sources=["automations.yaml"],
        files_skipped=1,
    )
    assert new == []
    assert partial["unscanned_results"] == [old]
    # Repeated failed scans cannot erase the baseline fragment.
    partial, _ = compare(
        [], partial, skipped_sources=["automations.yaml"], files_skipped=1
    )
    partial.update(scanned_at="2026-09-08T00:00:00+00:00", missing_entity_count=0)
    hass.stores[coherence.COHERENCE_STORAGE_KEY] = deepcopy(partial)
    restored = asyncio.run(coherence.async_load_coherence_result(hass))
    report, new = compare([old, removed], restored)
    assert new == [removed]
    assert report["unscanned_results"] == []


def test_disabled_esphome_and_legacy_incomplete_reports_preserve_baseline():
    old = finding(source="esphome/device.yaml")
    partial, _ = compare([], {"results": [old]}, scan_esphome=False)
    assert partial["unscanned_results"] == [old]
    assert compare([old], partial)[1] == []
    partial, _ = compare([], {"results": [old]}, files_skipped=1)
    assert compare([old], partial)[1] == []
    partial, _ = compare(
        [], partial, ignored=frozenset({old["entity_id"]}), files_skipped=1
    )
    assert partial["unscanned_results"] == []


def test_failed_multidocument_source_does_not_publish_partial_findings(tmp_path):
    (tmp_path / "broken.yaml").write_text("entity_id: sensor.missing\n---\nbroken: [\n")
    report = coherence.scan_configuration(tmp_path, frozenset())
    assert report["results"] == []
    assert report["skipped_sources"] == ["broken.yaml"]
    assert report["files_skipped"] == 1


def test_exclusions_are_applied_before_comparison(tmp_path):
    (tmp_path / "config.yaml").write_text("entities: [sensor.missing, sensor.other]\n")
    report = coherence.scan_configuration(
        tmp_path, frozenset(), ignored_entity_references=frozenset({"sensor.missing"})
    )
    new = coherence._compare_coherence_report(report, None, True, frozenset())
    assert [item["entity_id"] for item in new] == ["sensor.other"]


@pytest.mark.parametrize("origin", ["ui", "entity", "schedule"])
def test_origins_and_manual_baseline(hass, monkeypatch, origin):
    notify = AsyncMock()
    hass.data[DATA_MANAGER] = SimpleNamespace(
        config={}, notification_runtime=SimpleNamespace(async_notify_coherence=notify)
    )
    rows = [finding()]

    async def scan(*_args, **_kwargs):
        return {"results": deepcopy(rows), "missing_entity_count": len(rows)}

    monkeypatch.setattr(coherence, "async_scan_configuration", scan)

    async def scenario():
        await coherence.async_run_coherence_scan(hass, origin=origin)
        assert notify.await_count == (origin != "ui")
        await coherence.async_run_coherence_scan(hass, origin="entity")
        assert notify.await_count == (origin != "ui")
        rows.append(finding("sensor.new"))
        await coherence.async_run_coherence_scan(hass, origin="schedule")
        notify.assert_awaited_with([rows[-1]])

    asyncio.run(scenario())


@pytest.mark.parametrize("first_origin", ["ui", "entity", "schedule"])
def test_overlapping_requests_notify_once_with_initiator_origin(
    hass, monkeypatch, first_origin
):
    notify = AsyncMock()
    hass.data[DATA_MANAGER] = SimpleNamespace(
        config={}, notification_runtime=SimpleNamespace(async_notify_coherence=notify)
    )

    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()

        async def scan(*_args, **_kwargs):
            started.set()
            await release.wait()
            return {"results": [finding()], "missing_entity_count": 1}

        spy = AsyncMock(side_effect=scan)
        monkeypatch.setattr(coherence, "async_scan_configuration", spy)
        first = asyncio.create_task(
            coherence.async_run_coherence_scan(hass, origin=first_origin)
        )
        await started.wait()
        others = [
            asyncio.create_task(coherence.async_run_coherence_scan(hass, origin=origin))
            for origin in ("ui", "entity", "schedule")
        ]
        await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        results = await asyncio.gather(*others)
        assert all(result is results[0] for result in results)
        assert spy.await_count == hass.store_save_count == 1
        assert notify.await_count == (first_origin != "ui")

    asyncio.run(scenario())


def test_failed_scan_preserves_report_and_never_sends(hass, monkeypatch):
    previous = {"results": [finding()]}
    hass.data[DATA_COHERENCE_RESULT] = previous
    notify = AsyncMock()
    hass.data[DATA_MANAGER] = SimpleNamespace(
        config={}, notification_runtime=SimpleNamespace(async_notify_coherence=notify)
    )
    monkeypatch.setattr(
        coherence,
        "async_scan_configuration",
        AsyncMock(side_effect=OSError("scan failed")),
    )
    with pytest.raises(OSError):
        asyncio.run(coherence.async_run_coherence_scan(hass, origin="entity"))
    assert hass.data[DATA_COHERENCE_RESULT] is previous
    assert notify.await_count == hass.store_save_count == 0


def profile(profile_id="owner", **extra):
    return {
        "id": profile_id,
        "name": profile_id,
        "enabled": True,
        "targets": ["notify.phone"],
        "label_ids": ["unrelated"],
        "default_policy": {
            "notify_on_start": False,
            "notify_on_resolved": False,
            "reminder_interval": None,
        },
        "exceptions": [],
        **extra,
    }


def test_profile_opt_in_validation():
    assert (
        validate_notification_profiles([profile()])[0]["notify_on_coherence"] is False
    )
    assert (
        validate_notification_profiles([profile(notify_on_coherence=True)])[0][
            "notify_on_coherence"
        ]
        is True
    )
    for invalid in ("true", 1, None, []):
        with pytest.raises(ValueError, match="notify_on_coherence"):
            validate_notification_profiles([profile(notify_on_coherence=invalid)])


def test_coherence_delivery_opt_in_isolation_accounting_and_no_alerts(hass, entry):
    manager = AlertManager(hass, entry)
    manager.config["notification_profiles"] = validate_notification_profiles(
        [
            profile("default"),
            profile("disabled", enabled=False, notify_on_coherence=True),
            profile("failed", notify_on_coherence=True),
            profile("exception", notify_on_coherence=True),
            profile("ok", notify_on_coherence=True),
        ]
    )
    send = AsyncMock(
        side_effect=[
            {"delivered_targets": []},
            RuntimeError("broken"),
            {"delivered_targets": ["notify.phone"]},
        ]
    )
    manager.notifications.async_send = send
    asyncio.run(manager.notification_runtime.async_notify_coherence([finding()]))
    assert send.await_count == 3
    assert send.call_args.kwargs["click_url"] == "/alert-manager/coherence"
    assert "1 new coherence issue" in send.call_args.kwargs["message"]
    assert manager.notification_runtime.usage_snapshot()["last_24h"] == {
        "default": 0,
        "disabled": 0,
        "failed": 0,
        "exception": 0,
        "ok": 1,
    }
    assert not manager.records
    assert not manager.notification_runtime._batches
    asyncio.run(manager.notification_runtime.async_notify_coherence([]))
    assert send.await_count == 3


def test_integration_identity_upgrades_legacy_report_then_distinguishes_entries():
    old = finding(source_type="integration")
    current = old | {"source_id": "entry1"}
    report, new = compare([current], {"results": [old]})
    assert new == []
    other = current | {"source_id": "entry2"}
    assert compare([current, other], report)[1] == [other]


def test_skipped_check_category_retains_its_baseline():
    old = finding(scan_category="integration_check")
    partial, _ = compare(
        [], {"results": [old]}, skipped_categories=["integration_check"]
    )
    assert partial["unscanned_results"] == [old]
    assert compare([old], partial)[1] == []


def test_invalid_dashboard_metadata_fails_instead_of_hiding_sources(tmp_path):
    storage = tmp_path / ".storage"
    storage.mkdir()
    (storage / "lovelace_dashboards").write_text("{broken")
    with pytest.raises(ValueError):
        coherence.scan_configuration(tmp_path, frozenset())
