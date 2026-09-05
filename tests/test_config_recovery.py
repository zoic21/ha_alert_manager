"""Configuration backup, startup recovery and explicit restore tests."""

from __future__ import annotations

import asyncio
import threading
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.alert_manager import manager_api as manager_api_module
from custom_components.alert_manager import storage as storage_module
from custom_components.alert_manager.const import (
    CONFIG_BACKUP_STORAGE_KEY,
    RECOVERY_NOTIFICATION_ID,
)
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.storage import AlertManagerConfigBackupStorage
from custom_components.alert_manager.validation import validate_config
from custom_components.alert_manager.yaml_io import dump_config_yaml, parse_config_yaml


def run(coroutine):
    """Run one manager operation in these isolated Home Assistant doubles."""
    return asyncio.run(coroutine)


def rule_payload(name: str = "Target on") -> dict:
    """Return one complete custom rule accepted by the public API."""
    return {
        "name": name,
        "entity_ids": ["sensor.target"],
        "enabled": True,
        "source": "state",
        "attribute": None,
        "operator": "equals",
        "value": "on",
        "duration": 0,
        "message": None,
        "update_message_when_active": False,
        "condition_template": None,
    }


def test_valid_export_creates_daily_backup_with_manual_export_representation(
    hass, entry
):
    """The automatic backup is the existing deterministic full YAML export."""
    manager = AlertManager(hass, entry)
    run(manager.async_setup())

    status = run(manager.async_get_recovery_status())
    assert status["active"] is False
    assert len(status["backups"]) == 1
    backup = status["backups"][0]
    downloaded = run(manager.async_get_config_backup_download(backup["id"]))
    assert downloaded["content"] == run(manager.async_export_config_yaml())
    assert parse_config_yaml(downloaded["content"])["rules"] == []
    assert backup["rules"] == 0


def test_backup_listing_reuses_metadata_without_parsing(hass, monkeypatch):
    """Opening the panel does not parse backup YAML on the event loop."""
    storage = AlertManagerConfigBackupStorage(hass)
    raw_yaml = dump_config_yaml(validate_config({}))
    backup = run(
        storage.async_create(raw_yaml, created_at=datetime(2026, 8, 28, 3, tzinfo=UTC))
    )

    def fail_parse(_raw_yaml):
        raise AssertionError("backup listing must not parse YAML")

    monkeypatch.setattr(storage_module, "parse_config_yaml", fail_parse)

    assert run(storage.async_list()) == [backup]


def test_backup_yaml_parsing_runs_in_executor(hass, monkeypatch):
    """Creation and selected-backup validation never block the event loop."""
    storage = AlertManagerConfigBackupStorage(hass)
    raw_yaml = dump_config_yaml(validate_config({}))
    event_loop_thread = threading.get_ident()
    parser_threads = []
    original_parser = storage_module.parse_config_yaml

    def tracked_parse(candidate):
        parser_threads.append(threading.get_ident())
        return original_parser(candidate)

    monkeypatch.setattr(storage_module, "parse_config_yaml", tracked_parse)
    backup = run(
        storage.async_create(raw_yaml, created_at=datetime(2026, 8, 28, 3, tzinfo=UTC))
    )
    assert run(storage.async_get(backup["id"])) is not None

    assert parser_threads
    assert all(thread_id != event_loop_thread for thread_id in parser_threads)


def test_config_import_parsing_runs_in_executor(hass, entry, monkeypatch):
    """A backup restore cannot reintroduce YAML parsing on the event loop."""
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    raw_yaml = run(manager.async_export_config_yaml())
    event_loop_thread = threading.get_ident()
    parser_threads = []
    original_parser = manager_api_module.parse_config_yaml

    def tracked_parse(candidate):
        parser_threads.append(threading.get_ident())
        return original_parser(candidate)

    monkeypatch.setattr(manager_api_module, "parse_config_yaml", tracked_parse)
    run(manager.async_import_config(raw_yaml))

    assert parser_threads
    assert all(thread_id != event_loop_thread for thread_id in parser_threads)


def test_invalid_export_never_enters_rotation_or_overwrites_valid_backups(hass):
    """Validation happens before the atomic backup-store write."""
    storage = AlertManagerConfigBackupStorage(hass)
    valid_yaml = dump_config_yaml(validate_config({}))
    first = run(
        storage.async_create(
            valid_yaml, created_at=datetime(2026, 8, 28, 3, tzinfo=UTC)
        )
    )
    before = deepcopy(hass.stores[CONFIG_BACKUP_STORAGE_KEY])

    with pytest.raises(ValueError):
        run(
            storage.async_create(
                "version: 1\nconfig: broken\n",
                created_at=datetime(2026, 8, 29, 3, tzinfo=UTC),
            )
        )

    assert hass.stores[CONFIG_BACKUP_STORAGE_KEY] == before
    assert run(storage.async_list()) == [first]


def test_backup_rotation_keeps_exactly_three_newest_valid_exports(hass):
    """A fourth daily backup removes only the oldest valid export."""
    storage = AlertManagerConfigBackupStorage(hass)
    raw_yaml = dump_config_yaml(validate_config({}))
    created = []
    for day in range(27, 31):
        created.append(
            run(
                storage.async_create(
                    raw_yaml,
                    created_at=datetime(2026, 8, day, 3, tzinfo=UTC),
                )
            )
        )

    backups = run(storage.async_list())
    assert [item["id"] for item in backups] == [
        created[3]["id"],
        created[2]["id"],
        created[1]["id"],
    ]


def test_invalid_startup_preserves_main_store_and_enters_manual_recovery(hass, entry):
    """An obsolete invalid rule can never be replaced by DEFAULT_CONFIG."""
    hass.states.set("sensor.unavailable_target", "unavailable")
    backup_storage = AlertManagerConfigBackupStorage(hass)
    backup = run(
        backup_storage.async_create(
            dump_config_yaml(validate_config({})),
            created_at=datetime(2026, 8, 30, 3, tzinfo=UTC),
        )
    )
    faulty_store = {
        "config": {"rules": [{"id": "old-rule-new-version-cannot-validate"}]},
        "alerts": {},
    }
    hass.stores["alert_manager"] = deepcopy(faulty_store)

    manager = AlertManager(hass, entry)
    run(manager.async_setup())

    assert manager.recovery_active is True
    assert manager.monitoring_enabled is True
    assert hass.stores["alert_manager"] == faulty_store
    assert hass.notifications[RECOVERY_NOTIFICATION_ID]
    assert (
        "configuration par défaut"
        in hass.notifications[RECOVERY_NOTIFICATION_ID]["message"]
    )
    status = run(manager.async_get_recovery_status())
    assert status["active"] is True
    assert status["backups"] == [backup]
    assert manager.get_config() == validate_config({})
    assert manager.records
    assert run(manager.async_get_recovery_status())["backups"] == [backup]


def test_invalid_startup_without_backup_does_not_create_one(hass, entry):
    """A rejected current configuration is never copied into backup rotation."""
    hass.stores["alert_manager"] = {
        "config": {"rules": [{"id": "incomplete"}]},
        "alerts": {},
    }
    manager = AlertManager(hass, entry)
    run(manager.async_setup())

    assert manager.recovery_active is True
    assert CONFIG_BACKUP_STORAGE_KEY not in hass.stores


def test_main_store_read_error_starts_recovery_without_writing_defaults(hass, entry):
    """An I/O failure remains recoverable and never creates a replacement store."""
    manager = AlertManager(hass, entry)

    async def fail_load():
        raise OSError("storage unavailable")

    manager.storage.async_load = fail_load
    run(manager.async_setup())

    assert manager.recovery_active is True
    assert "alert_manager" not in hass.stores
    assert CONFIG_BACKUP_STORAGE_KEY not in hass.stores
    assert RECOVERY_NOTIFICATION_ID in hass.notifications
    status = run(manager.async_get_recovery_status())
    assert status == {"active": True, "backups": []}


def test_home_assistant_silent_corrupt_store_fallback_is_not_treated_as_first_start(
    hass, entry
):
    """Store returning None after corruption cannot trigger a default config save."""
    manager = AlertManager(hass, entry)

    async def corrupt_snapshot():
        return '{"version": 1, "data": {broken json'

    manager.storage._async_read_store_snapshot = corrupt_snapshot
    run(manager.async_setup())

    assert manager.recovery_active is True
    assert "alert_manager" not in hass.stores
    assert manager.get_config() == validate_config({})


def test_explicit_backup_restore_uses_import_and_clears_recovery_notification(
    hass, entry
):
    """The default fallback persists only until an administrator restores a backup."""
    backup_storage = AlertManagerConfigBackupStorage(hass)
    backup_yaml = dump_config_yaml(validate_config({}))
    backup = run(
        backup_storage.async_create(
            backup_yaml, created_at=datetime(2026, 8, 30, 3, tzinfo=UTC)
        )
    )
    faulty_store = {
        "config": {"rules": [{"id": "incomplete"}]},
        "alerts": {},
    }
    hass.stores["alert_manager"] = deepcopy(faulty_store)
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    called_with = []
    original_import = manager.async_import_config

    async def tracked_import(raw_yaml):
        called_with.append(raw_yaml)
        return await original_import(raw_yaml)

    manager.async_import_config = tracked_import
    result = run(manager.async_restore_config_backup(backup["id"]))

    assert called_with == [backup_yaml]
    assert result["config"] == manager.get_config()
    assert manager.recovery_active is False
    assert RECOVERY_NOTIFICATION_ID not in hass.notifications
    assert hass.stores["alert_manager"]["config"] == manager.get_config()
    assert run(manager.async_get_recovery_status())["backups"] == [backup]


def test_backup_restore_regenerates_rule_ids_resets_runtime_and_reevaluates(
    hass, entry
):
    """A complete restore keeps functional config, not stale engine state."""
    hass.states.set("sensor.target", "on")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    created_rule = run(manager.async_create_rule(rule_payload()))
    backup_yaml = run(manager.async_export_config_yaml())
    backup = run(
        manager.config_backup_storage.async_create(
            backup_yaml,
            created_at=datetime(2026, 8, 25, 12, tzinfo=UTC),
        )
    )

    hass.states.set("sensor.target", "off")
    run(manager.async_evaluate_entity("sensor.target"))
    assert manager.history
    hass.states.set("sensor.other", "unavailable")
    run(manager.async_evaluate_entity("sensor.other"))
    assert any("sensor.other" in alert_id for alert_id in manager.records)

    hass.states.set("sensor.target", "on")
    hass.states.set("sensor.other", "ok")
    run(manager.async_restore_config_backup(backup["id"]))

    restored_rule = manager.get_config()["rules"][0]
    assert restored_rule["id"] != created_rule["id"]
    assert run(manager.async_export_config_yaml()) == backup_yaml
    assert manager.history == []
    assert manager._pending_history == []
    assert manager._variation_baselines == {}
    assert any("sensor.target" in alert_id for alert_id in manager.records)
    assert all("sensor.other" not in alert_id for alert_id in manager.records)


def test_invalid_backup_is_refused_without_changing_current_config_or_rotation(
    hass, entry
):
    """A damaged selected backup cannot affect live config or sibling backups."""
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    before_config = manager.get_config()
    selected = run(
        manager.config_backup_storage.async_create(
            run(manager.async_export_config_yaml()),
            created_at=datetime(2026, 8, 25, 12, tzinfo=UTC),
        )
    )
    before_store = deepcopy(hass.stores[CONFIG_BACKUP_STORAGE_KEY])
    backup_id = selected["id"]
    selected_item = next(
        item
        for item in hass.stores[CONFIG_BACKUP_STORAGE_KEY]["backups"]
        if item["id"] == backup_id
    )
    selected_item["yaml"] = "invalid"
    corrupted = deepcopy(hass.stores[CONFIG_BACKUP_STORAGE_KEY])
    assert len(before_store["backups"]) == 2

    with pytest.raises(ValueError, match="Unknown or invalid"):
        run(manager.async_restore_config_backup(backup_id))

    assert manager.get_config() == before_config
    assert hass.stores[CONFIG_BACKUP_STORAGE_KEY] == corrupted


def test_restart_catches_up_when_latest_valid_backup_is_older_than_one_day(hass, entry):
    """A missed deadline creates a fresh backup during the next valid startup."""
    storage = AlertManagerConfigBackupStorage(hass)
    old = run(
        storage.async_create(
            dump_config_yaml(validate_config({})),
            created_at=datetime(2026, 8, 22, 12, tzinfo=UTC),
        )
    )
    manager = AlertManager(hass, entry)
    run(manager.async_setup())

    backups = run(storage.async_list())
    assert len(backups) == 2
    assert backups[0]["id"] != old["id"]
    assert datetime.fromisoformat(backups[0]["created_at"]) - datetime.fromisoformat(
        old["created_at"]
    ) >= timedelta(days=1)
