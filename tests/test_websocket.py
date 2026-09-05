"""WebSocket permission and backend validation tests."""

from __future__ import annotations

import asyncio
import importlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from homeassistant.util import dt as dt_util

from custom_components.alert_manager.const import DATA_COHERENCE_RESULT, DATA_MANAGER
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.websocket import (
    websocket_alert_acknowledgements_update,
    websocket_alerts_list,
    websocket_coherence_get,
    websocket_coherence_scan,
    websocket_config_backup_download,
    websocket_config_backup_restore,
    websocket_config_export,
    websocket_config_get,
    websocket_config_import,
    websocket_config_import_validate,
    websocket_config_recovery_get,
    websocket_config_update,
    websocket_deleted_entities_list,
    websocket_history_clear,
    websocket_history_config_get,
    websocket_history_config_update,
    websocket_history_delete,
    websocket_history_list,
    websocket_notification_stats_get,
    websocket_packs_list,
    websocket_rule_create,
    websocket_rule_delete,
    websocket_rule_test,
    websocket_rule_update,
    websocket_rule_yaml_validate,
    websocket_rules_list,
)
from custom_components.alert_manager.yaml_io import dump_config_yaml


class Connection:
    def __init__(self, *, admin):
        self.user = SimpleNamespace(is_admin=admin, name="Loïc")
        self.errors = []
        self.results = []

    def send_error(self, message_id, code, message):
        self.errors.append((message_id, code, message))

    def send_result(self, message_id, result=None):
        self.results.append((message_id, result))


def test_timed_acknowledgement_websocket_validates_and_forwards_duration(hass, entry):
    manager = AlertManager(hass, entry)
    hass.states.set("sensor.test", "unavailable")
    asyncio.run(manager.async_setup())
    asyncio.run(manager.async_update_config({"global_delay": 0}))
    hass.data[DATA_MANAGER] = manager
    connection = Connection(admin=True)
    message = {
        "id": 1,
        "alert_ids": ["unavailable:sensor.test"],
        "acknowledged": True,
        "duration": 1800,
    }
    asyncio.run(websocket_alert_acknowledgements_update(hass, connection, message))
    record = manager.records["unavailable:sensor.test"]
    assert record.acknowledged_until == record.acknowledged_at + timedelta(minutes=30)
    assert connection.errors == []
    for duration in [0, -1, True, "900", 1.5, 31536001]:
        asyncio.run(
            websocket_alert_acknowledgements_update(
                hass, connection, {**message, "duration": duration}
            )
        )
        assert connection.errors[-1][1] == "invalid_format"
    unauthorized = Connection(admin=False)
    asyncio.run(websocket_alert_acknowledgements_update(hass, unauthorized, message))
    assert unauthorized.errors[-1][1] == "unauthorized"


def test_websocket_non_admin_is_refused(hass, entry):
    """Every mutating command is protected by the Home Assistant admin decorator."""
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    hass.data[DATA_MANAGER] = manager
    connection = Connection(admin=False)
    asyncio.run(
        websocket_config_update(
            hass,
            connection,
            {"id": 1, "type": "alert_manager/config/update", "config": {}},
        )
    )
    assert connection.errors == [(1, "unauthorized", "Unauthorized")]
    assert connection.results == []


def test_websocket_invalid_frontend_data_gets_readable_error(hass, entry):
    """Invalid durations are rejected server-side even for administrators."""
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    hass.data[DATA_MANAGER] = manager
    connection = Connection(admin=True)
    asyncio.run(
        websocket_config_update(
            hass,
            connection,
            {
                "id": 2,
                "type": "alert_manager/config/update",
                "config": {"global_delay": -1},
            },
        )
    )
    assert connection.results == []
    assert connection.errors[0][1] == "invalid_format"
    assert "between" in connection.errors[0][2]


def test_bulk_acknowledgement_websocket_uses_one_transaction(hass, entry):
    """The panel can update several alerts through one backend write."""
    for entity_id in ("sensor.one", "sensor.two"):
        hass.states.set(entity_id, "unavailable")
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    asyncio.run(manager.async_update_config({"global_delay": 0}))
    hass.data[DATA_MANAGER] = manager
    connection = Connection(admin=True)
    alert_ids = ["unavailable:sensor.one", "unavailable:sensor.two"]
    saves = hass.store_save_count

    asyncio.run(
        websocket_alert_acknowledgements_update(
            hass,
            connection,
            {"id": 25, "alert_ids": alert_ids, "acknowledged": True},
        )
    )

    assert connection.errors == []
    assert connection.results == [(25, {"updated": alert_ids})]
    assert hass.store_save_count == saves + 1
    assert all(
        manager.records[alert_id].acknowledged_by == "Loïc" for alert_id in alert_ids
    )


def test_websocket_exposes_backend_pack_metadata(hass, entry):
    """The panel gets pack labels and availability from the backend registry."""
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    hass.data[DATA_MANAGER] = manager
    connection = Connection(admin=True)

    asyncio.run(
        websocket_packs_list(
            hass,
            connection,
            {"id": 8, "type": "alert_manager/packs/list"},
        )
    )

    packs = connection.results[-1][1]
    assert [pack["id"] for pack in packs] == [
        "unavailable",
        "connectivity",
        "unifi",
        "battery",
        "execution_errors",
        "flapping",
    ]
    assert all(pack["translation_key"] == pack["id"] for pack in packs)
    assert all("name" not in pack and "description" not in pack for pack in packs)
    assert next(pack for pack in packs if pack["id"] == "unifi") == {
        "id": "unifi",
        "translation_key": "unifi",
        "prerequisites": ["unifi"],
        "available": False,
    }
    battery = next(pack for pack in packs if pack["id"] == "battery")
    assert [field["id"] for field in battery["config_fields"]] == [
        "threshold",
        "device_thresholds",
    ]
    assert battery["config_fields"][1]["type"] == "device_number_map"
    execution_errors = next(pack for pack in packs if pack["id"] == "execution_errors")
    assert execution_errors["config_fields"] == [
        {
            "id": "failure_thresholds",
            "type": "entity_number_map",
            "translation_key": "failure_thresholds",
            "default": {},
            "minimum": 1,
            "maximum": 100,
            "step": 1,
            "entity_domains": ["automation", "script"],
        }
    ]


def test_websocket_rule_actions_create_update_and_delete(hass, entry):
    """The complete mutating rule API works with panel-shaped payloads."""
    hass.states.set("todo.liste_d_achats", "0")
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    hass.data[DATA_MANAGER] = manager
    connection = Connection(admin=True)
    payload = {
        "name": "Liste vide",
        "entity_ids": ["todo.liste_d_achats"],
        "enabled": True,
        "source": "state",
        "attribute": None,
        "operator": "equals",
        "value": "0",
        "duration": 900,
        "message": None,
    }

    asyncio.run(
        websocket_rule_create(
            hass,
            connection,
            {"id": 3, "type": "alert_manager/rules/create", "rule": payload},
        )
    )
    assert connection.errors == []
    created = connection.results[-1][1]
    assert created["name"] == "Liste vide"
    assert manager.get_config()["rules"] == [created]

    asyncio.run(
        websocket_rule_update(
            hass,
            connection,
            {
                "id": 4,
                "type": "alert_manager/rules/update",
                "rule_id": created["id"],
                "rule": {"enabled": False, "name": "Liste désactivée"},
            },
        )
    )
    updated = connection.results[-1][1]
    assert updated["enabled"] is False
    assert updated["name"] == "Liste désactivée"

    asyncio.run(
        websocket_rule_delete(
            hass,
            connection,
            {
                "id": 5,
                "type": "alert_manager/rules/delete",
                "rule_id": created["id"],
            },
        )
    )
    assert connection.results[-1] == (5, {"deleted": True})
    assert manager.get_config()["rules"] == []


def test_websocket_rule_test_is_admin_only_and_returns_draft_result(hass, entry):
    """The dedicated endpoint evaluates a complete unsaved draft."""
    hass.states.set("sensor.temperature", "18.2")
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    hass.data[DATA_MANAGER] = manager
    connection = Connection(admin=True)
    payload = {
        "name": "Temperature",
        "entity_ids": ["sensor.temperature"],
        "enabled": False,
        "source": "state",
        "operator": "below",
        "value": "19",
        "duration": 600,
    }

    asyncio.run(
        websocket_rule_test(
            hass,
            connection,
            {"id": 55, "type": "alert_manager/rules/test", "rule": payload},
        )
    )

    assert connection.errors == []
    assert connection.results[0][0] == 55
    assert connection.results[0][1]["matched_count"] == 1
    assert manager.config["rules"] == []


def test_all_panel_websocket_reads_and_sensitive_paths_are_admin_only(hass, entry):
    """Read, YAML, history and import/export APIs all inherit the admin guard."""
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    hass.data[DATA_MANAGER] = manager
    connection = Connection(admin=False)
    for command, message in (
        (websocket_config_get, {"id": 6}),
        (websocket_alerts_list, {"id": 7}),
        (
            websocket_alert_acknowledgements_update,
            {
                "id": 24,
                "alert_ids": ["unavailable:sensor.test"],
                "acknowledged": True,
            },
        ),
        (websocket_packs_list, {"id": 8}),
        (websocket_rules_list, {"id": 9}),
        (websocket_notification_stats_get, {"id": 27}),
        (
            websocket_rule_test,
            {
                "id": 26,
                "rule": {
                    "name": "Test",
                    "entity_ids": ["sensor.test"],
                    "source": "state",
                    "operator": "equals",
                    "value": "on",
                    "duration": 0,
                },
            },
        ),
        (websocket_rule_yaml_validate, {"id": 10, "yaml": "name: test"}),
        (websocket_config_export, {"id": 11}),
        (websocket_config_import_validate, {"id": 12, "yaml": "version: 1"}),
        (websocket_config_import, {"id": 13, "yaml": "version: 1", "confirmed": True}),
        (websocket_history_list, {"id": 14}),
        (websocket_history_config_get, {"id": 15}),
        (websocket_history_config_update, {"id": 16, "retention_limit": 10}),
        (websocket_history_clear, {"id": 17, "confirmed": True}),
        (
            websocket_history_delete,
            {"id": 18, "event_ids": ["event"], "confirmed": True},
        ),
        (websocket_coherence_get, {"id": 18}),
        (websocket_coherence_scan, {"id": 19}),
        (websocket_deleted_entities_list, {"id": 23}),
        (websocket_config_recovery_get, {"id": 20}),
        (websocket_config_backup_download, {"id": 21, "backup_id": "one"}),
        (
            websocket_config_backup_restore,
            {"id": 22, "backup_id": "one", "confirmed": True},
        ),
    ):
        asyncio.run(command(hass, connection, message))
    assert [error[1] for error in connection.errors] == ["unauthorized"] * 22
    assert connection.results == []


def test_notification_stats_websocket_is_separate_from_configuration(hass, entry):
    """The panel reads recent usage through its dedicated admin endpoint."""
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    profile = {
        "id": "profile",
        "name": "Profile",
        "enabled": True,
        "targets": ["notify.phone"],
        "label_ids": [],
        "default_policy": {
            "notify_on_start": True,
            "notify_on_resolved": True,
            "reminder_interval": None,
        },
        "exceptions": [],
    }
    asyncio.run(manager.async_update_config({"notification_profiles": [profile]}))
    bucket = int(dt_util.now().timestamp()) // 3600
    manager.notification_runtime._usage = {"profile": {bucket: 2}}
    hass.data[DATA_MANAGER] = manager
    connection = Connection(admin=True)

    asyncio.run(websocket_notification_stats_get(hass, connection, {"id": 28}))

    assert connection.errors == []
    assert connection.results == [(28, {"last_24h": {"profile": 2}})]
    assert "usage" not in manager.get_config()


def test_coherence_scan_websocket_returns_on_demand_result(hass, entry, monkeypatch):
    """The admin-only endpoint returns the isolated scanner payload unchanged."""
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    hass.data[DATA_MANAGER] = manager
    connection = Connection(admin=True)
    expected = {
        "results": [],
        "missing_count": 0,
        "files_scanned": 3,
        "files_skipped": 0,
        "references_checked": 7,
        "duration_ms": 4,
    }

    async def scan(_hass):
        return expected

    websocket_module = importlib.import_module(
        "custom_components.alert_manager.websocket"
    )
    monkeypatch.setattr(websocket_module, "async_run_coherence_scan", scan)
    asyncio.run(websocket_coherence_scan(hass, connection, {"id": 40}))

    assert connection.errors == []
    assert connection.results == [(40, expected)]


def test_deleted_entities_websocket_returns_newest_fifty(hass, entry):
    """The registry remains the only source of retained deleted entities."""
    base = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    hass.entity_registry.deleted_entities = {
        ("sensor", "test", str(index)): SimpleNamespace(
            entity_id=f"sensor.deleted_{index}",
            name=f"Deleted {index}" if index % 2 else None,
            platform="test",
            modified_at=base + timedelta(minutes=index),
        )
        for index in range(52)
    }
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    hass.data[DATA_MANAGER] = manager
    connection = Connection(admin=True)

    asyncio.run(websocket_deleted_entities_list(hass, connection, {"id": 43}))

    result = connection.results[-1][1]
    assert len(result["entities"]) == 50
    assert result["entities"][0] == {
        "entity_id": "sensor.deleted_51",
        "name": "Deleted 51",
        "platform": "test",
        "deleted_at": "2026-08-24T12:51:00+00:00",
    }
    assert result["entities"][-1]["entity_id"] == "sensor.deleted_2"


def test_admin_recovery_websockets_list_download_and_restore_one_backup(hass, entry):
    """The shared automatic backup endpoints expose YAML and explicit restore."""
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    hass.data[DATA_MANAGER] = manager
    connection = Connection(admin=True)

    asyncio.run(websocket_config_recovery_get(hass, connection, {"id": 50}))
    status = connection.results[-1][1]
    assert status["active"] is False
    assert len(status["backups"]) == 1
    backup_id = status["backups"][0]["id"]

    asyncio.run(
        websocket_config_backup_download(
            hass, connection, {"id": 51, "backup_id": backup_id}
        )
    )
    assert connection.results[-1][1]["content"] == manager.export_config_yaml()

    asyncio.run(
        websocket_config_backup_restore(
            hass,
            connection,
            {"id": 52, "backup_id": backup_id, "confirmed": True},
        )
    )
    assert connection.errors == []
    assert connection.results[-1][1]["config"] == manager.get_config()


def test_coherence_get_websocket_restores_last_result_without_scanning(hass, entry):
    """Opening the panel retrieves the retained report without a new scan."""
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    hass.data[DATA_MANAGER] = manager
    connection = Connection(admin=True)

    asyncio.run(websocket_coherence_get(hass, connection, {"id": 41}))
    assert connection.results == [(41, None)]

    expected = {
        "scanned_at": "2026-08-24T12:00:00+00:00",
        "missing_entity_count": 1,
        "results": [{"entity_id": "sensor.gone"}],
    }
    hass.data[DATA_COHERENCE_RESULT] = expected
    asyncio.run(websocket_coherence_get(hass, connection, {"id": 42}))

    assert connection.results[-1] == (42, expected)


def test_history_websocket_configuration_and_clear(hass, entry):
    """History reads, bounded updates and clearing use dedicated admin APIs."""
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    hass.data[DATA_MANAGER] = manager
    connection = Connection(admin=True)

    asyncio.run(websocket_history_config_get(hass, connection, {"id": 30}))
    assert connection.results[-1] == (
        30,
        {"retention_limit": 100, "enabled": True},
    )
    asyncio.run(
        websocket_history_config_update(
            hass,
            connection,
            {"id": 31, "retention_limit": 0},
        )
    )
    assert connection.results[-1] == (
        31,
        {"retention_limit": 0, "enabled": False},
    )
    asyncio.run(
        websocket_history_config_update(
            hass,
            connection,
            {"id": 34, "retention_limit": 1001},
        )
    )
    assert connection.errors[-1][1] == "invalid_format"
    asyncio.run(websocket_history_list(hass, connection, {"id": 32}))
    assert connection.results[-1][1]["events"] == []
    asyncio.run(
        websocket_history_clear(hass, connection, {"id": 33, "confirmed": True})
    )
    assert connection.results[-1][1]["events"] == []


def test_configuration_export_validation_and_import_round_trip(hass, entry):
    """The WebSocket flow validates before the explicit replacement request."""
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    hass.data[DATA_MANAGER] = manager
    connection = Connection(admin=True)

    asyncio.run(websocket_config_export(hass, connection, {"id": 20}))
    exported = connection.results[-1][1]["yaml"]
    assert exported.startswith("version: 1\n")

    asyncio.run(
        websocket_config_import_validate(
            hass,
            connection,
            {"id": 21, "yaml": exported},
        )
    )
    assert connection.results[-1][1]["rules"] == 0

    asyncio.run(
        websocket_config_import(
            hass,
            connection,
            {
                "id": 22,
                "yaml": dump_config_yaml(manager.get_config()),
                "confirmed": True,
            },
        )
    )
    assert connection.results[-1][1]["config"] == manager.get_config()


def test_history_delete_websocket_returns_updated_snapshot(hass, entry):
    """The transport forwards occurrence IDs and returns the updated history."""
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    hass.data[DATA_MANAGER] = manager
    connection = Connection(admin=True)
    received = []
    snapshot = {"events": [], "count": 0, "retention_limit": 100, "enabled": True}

    async def delete_history(event_ids):
        received.extend(event_ids)
        return snapshot

    manager.async_delete_history = delete_history
    asyncio.run(
        websocket_history_delete(
            hass, connection, {"id": 40, "event_ids": ["occurrence"], "confirmed": True}
        )
    )
    assert received == ["occurrence"]
    assert connection.results == [(40, snapshot)]
