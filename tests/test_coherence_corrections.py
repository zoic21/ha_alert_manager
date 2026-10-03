"""Coherence fixes reuse rename identities and the selected replacement batch."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
import yaml
from test_entity_replacement import Dashboard, apply, write
from test_websocket import Connection

from custom_components.alert_manager.coherence import async_scan_configuration
from custom_components.alert_manager.const import DATA_COHERENCE_RESULT, DATA_MANAGER
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.websocket import (
    websocket_coherence_corrections_preview,
    websocket_coherence_get,
)


@pytest.fixture
def manager(hass, entry, tmp_path, registry_entry):
    hass.config.path = lambda *parts: str(tmp_path.joinpath(*parts))
    manager = AlertManager(hass, entry)
    hass.data[DATA_MANAGER] = manager
    for old, current, identity in (
        ("light.old", "light.current", "stable-light"),
        ("sensor.old", "sensor.current", "stable-sensor"),
    ):
        registry_entry(hass, current).id = identity
        hass.states.set(current, "on")
        manager.entity_rename_history.record(old, current, identity, datetime.now(UTC))
    return manager


async def report(manager):
    result = await async_scan_configuration(manager.hass)
    result["scanned_at"] = datetime.now(UTC).isoformat()
    manager.hass.data[DATA_COHERENCE_RESULT] = result
    return result


def test_report_resolves_final_name_and_only_editable_references(
    manager, tmp_path, monkeypatch
):
    from custom_components.alert_manager import entity_replacement as module

    manager.entity_rename_history.record(
        "light.original", "light.old", "stable-light", datetime.now(UTC)
    )
    write(
        tmp_path,
        "config.yaml",
        "entities: [light.original, light.old, light.deleted]\n",
    )
    write(tmp_path, "readonly.yaml", "entity_id: light.old\n")
    write(tmp_path, "symlink.yaml", "entity_id: light.old\n").unlink()
    (tmp_path / "symlink.yaml").symlink_to(tmp_path / "config.yaml")
    write(
        tmp_path,
        ".storage/core.config_entries",
        json.dumps(
            {
                "data": {
                    "entries": [{"domain": "test", "data": {"entity_id": "light.old"}}]
                }
            }
        ),
    )
    manager.entity_rename_history.record(
        "light.deleted", "light.reused", "deleted-identity", datetime.now(UTC)
    )
    manager.hass.states.set("light.reused", "on")
    real_access = module.os.access
    monkeypatch.setattr(
        module.os,
        "access",
        lambda path, mode: path.name != "readonly.yaml" and real_access(path, mode),
    )

    async def run():
        stored = await report(manager)
        original = deepcopy(stored)
        monkeypatch.setattr(
            module,
            "_discover_sources",
            lambda *_args, **_kwargs: pytest.fail(
                "Corrections must only read files with findings"
            ),
        )
        snapshot = await manager.async_coherence_snapshot(stored)
        correctable = [row for row in snapshot["results"] if "correction_target" in row]
        assert {row["entity_id"] for row in correctable} == {
            "light.original",
            "light.old",
        }
        assert {row["file"] for row in correctable} == {"config.yaml"}
        assert {row["correction_target"] for row in correctable} == {"light.current"}
        assert stored == original
        assert all("correction_target" not in row for row in stored["results"])

    asyncio.run(run())


def test_batch_edits_only_selected_lines_with_multiple_targets_in_one_file(
    manager, tmp_path, monkeypatch
):
    from custom_components.alert_manager import entity_replacement as module

    path = write(
        tmp_path,
        "config.yaml",
        "entities: [light.old, sensor.old, light.old]\nentity_id: light.old\n",
    )
    real_collect = module._replacement_file
    traversals = []

    def collect(source, *args):
        traversals.append(source.relative_path)
        return real_collect(source, *args)

    async def run():
        stored = await report(manager)
        monkeypatch.setattr(module, "_replacement_file", collect)
        indices = [
            index for index, row in enumerate(stored["results"]) if row["line"] == 1
        ]
        preview = await manager.async_preview_coherence_corrections(
            stored["scanned_at"], indices
        )
        assert traversals == ["config.yaml"]
        assert preview["replacement_count"] == 3
        assert preview["file_count"] == 1
        assert {row["new_entity_id"] for row in preview["replacements"]} == {
            "light.current",
            "sensor.current",
        }
        result = await apply(manager.entity_replacement, preview)
        assert result["replacement_count"] == 3
        assert yaml.safe_load(path.read_text()) == {
            "entities": ["light.current", "sensor.current", "light.current"],
            "entity_id": "light.old",
        }
        snapshot = await manager.async_coherence_snapshot(stored)
        assert [
            row["line"] for row in snapshot["results"] if "correction_target" in row
        ] == [2]

    asyncio.run(run())


def test_native_dashboard_selection_keeps_storage_line_numbers(manager, tmp_path):
    dashboard = Dashboard()
    dashboard.config = None
    dashboard.value = {
        "views": [
            {
                "title": "Office",
                "cards": [{"entity": "light.old"}, {"entity": "light.old"}],
            }
        ]
    }
    manager.hass.data["lovelace"] = SimpleNamespace(dashboards={"lovelace": dashboard})
    path = write(
        tmp_path,
        ".storage/lovelace",
        json.dumps({"version": 1, "data": {"config": dashboard.value}}, indent=2),
    )
    original = path.read_bytes()

    async def run():
        stored = await report(manager)
        assert len(stored["results"]) == 2
        assert stored["results"][0]["line"] != stored["results"][1]["line"]
        snapshot = await manager.async_coherence_snapshot(stored)
        assert all(
            row["correction_target"] == "light.current" for row in snapshot["results"]
        )
        preview = await manager.async_preview_coherence_corrections(
            stored["scanned_at"], [0]
        )
        assert preview["replacement_count"] == 1
        result = await apply(manager.entity_replacement, preview)
        assert not result["yaml_changed"]

    asyncio.run(run())
    assert dashboard.value["views"][0]["cards"] == [
        {"entity": "light.current"},
        {"entity": "light.old"},
    ]
    assert path.read_bytes() == original


def test_dashboard_changed_since_scan_is_not_correctable(manager, tmp_path):
    dashboard = Dashboard()
    dashboard.config = None
    manager.hass.data["lovelace"] = SimpleNamespace(dashboards={"lovelace": dashboard})
    write(
        tmp_path, ".storage/lovelace", json.dumps({"data": {"config": dashboard.value}})
    )

    async def run():
        stored = await report(manager)
        dashboard.value["views"][0]["cards"].append({"entity": "light.current"})
        snapshot = await manager.async_coherence_snapshot(stored)
        assert all("correction_target" not in row for row in snapshot["results"])
        with pytest.raises(ValueError, match="replacement_preview_stale"):
            await manager.async_preview_coherence_corrections(stored["scanned_at"], [0])
        assert not dashboard.saved

    asyncio.run(run())


def test_reused_old_identifier_and_deleted_newest_identity_disable_correction(
    manager, tmp_path
):
    write(tmp_path, "config.yaml", "entity_id: light.old\n")

    async def run():
        stored = await report(manager)
        manager.hass.states.set("light.old", "on")
        assert await manager.async_coherence_snapshot(stored) == stored
        manager.hass.states.data.pop("light.old")
        manager.entity_rename_history.record(
            "light.old", "light.deleted", "missing-identity", datetime.now(UTC)
        )
        assert await manager.async_coherence_snapshot(stored) == stored

    asyncio.run(run())


def test_batch_collision_and_deleted_target_leave_all_files_unchanged(
    manager, tmp_path
):
    first = write(tmp_path, "config.yaml", "entities: [light.old, sensor.old]\n")
    collision = write(
        tmp_path, "scene.yaml", "entities: {sensor.old: on, sensor.current: off}\n"
    )
    original = first.read_bytes(), collision.read_bytes()

    async def run():
        stored = await report(manager)
        indices = list(range(len(stored["results"])))
        preview = await manager.async_preview_coherence_corrections(
            stored["scanned_at"], indices
        )
        with pytest.raises(ValueError, match="replacement_yaml_invalid"):
            await apply(manager.entity_replacement, preview)
        assert (first.read_bytes(), collision.read_bytes()) == original
        collision.unlink()
        stored = await report(manager)
        preview = await manager.async_preview_coherence_corrections(
            stored["scanned_at"], list(range(len(stored["results"])))
        )
        manager.hass.entity_registry.entries.pop("sensor.current")
        manager.hass.states.data.pop("sensor.current")
        with pytest.raises(ValueError, match="replacement_entity_missing"):
            await apply(manager.entity_replacement, preview)

    asyncio.run(run())
    assert first.read_bytes() == original[0]


def test_correction_transport_enforces_permissions_and_report_identity(
    manager, tmp_path
):
    write(tmp_path, "config.yaml", "entity_id: light.old\n")

    async def run():
        stored = await report(manager)
        message = {"id": 12, "scanned_at": stored["scanned_at"], "row_indices": [0]}
        denied = Connection(admin=False)
        await websocket_coherence_corrections_preview(manager.hass, denied, message)
        assert denied.errors[0][1] == "unauthorized"
        allowed = Connection(admin=True)
        await websocket_coherence_get(manager.hass, allowed, {"id": 11})
        assert (
            allowed.results[0][1]["results"][0]["correction_target"] == "light.current"
        )
        await websocket_coherence_corrections_preview(
            manager.hass, allowed, {**message, "row_indices": [100]}
        )
        assert allowed.errors[-1][1] == "replacement_selection_invalid"
        await websocket_coherence_corrections_preview(
            manager.hass, allowed, {**message, "scanned_at": "stale"}
        )
        assert allowed.errors[-1][1] == "replacement_preview_stale"
        await websocket_coherence_corrections_preview(manager.hass, allowed, message)
        assert allowed.results[-1][1]["coherence_correction"]

    asyncio.run(run())
