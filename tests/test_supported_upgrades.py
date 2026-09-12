"""Keep the 2.2 upgrade boundary independent of current configuration defaults."""

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import Rule
from custom_components.alert_manager.storage import (
    AlertManagerConfigBackupStorage,
    AlertManagerStorage,
)
from custom_components.alert_manager.validation import validate_config
from custom_components.alert_manager.yaml_io import parse_config_yaml


def test_22_storage_yaml_and_backup_keep_the_same_configuration(hass):
    """Defaults copied from tag v2.2.0 still migrate through every saved entry point."""
    config = json.loads(
        (Path(__file__).parent / "fixtures/config_2_2.json").read_text()
    )
    config["excluded_labels"] = ["skip"]
    config["entity_delays"] = {"sensor.power": 42}
    config["rules"] = [
        {
            "id": "power",
            "name": "Power",
            "entity_ids": ["sensor.power"],
            "source": "attribute",
            "attribute": "power",
            "operator": "above",
            "value": 100,
            "duration": 30,
            "version": 2,
        }
    ]
    before = deepcopy(config)
    yaml_config = deepcopy(config)
    # The 2.2 exporter omits runtime history retention and internal rule versions.
    yaml_config.pop("history_limit")
    rules = yaml_config.pop("rules")
    for rule in rules:
        rule.pop("version")
    raw_yaml = yaml.safe_dump({"version": 1, "config": yaml_config, "rules": rules})
    hass.stores["alert_manager"] = {"config": config, "alerts": {}}

    async def scenario():
        storage = AlertManagerStorage(hass)
        loaded, records, changed = await storage.async_load()
        assert changed and records == {}
        normalized = validate_config(loaded)
        assert parse_config_yaml(raw_yaml) == normalized
        assert normalized["excluded_labels"] == ["skip"]
        assert normalized["rules"][0]["id"] == "power"
        assert normalized["rules"][0]["source"] == "value"
        assert normalized["rules"][0]["attribute"] == "power"
        assert normalized["automatic"]["unavailable"]["entity_overrides"] == {
            "sensor.power": {"delay": 42}
        }
        backups = AlertManagerConfigBackupStorage(hass)
        backup = await backups.async_create(
            raw_yaml, created_at=datetime(2026, 9, 8, tzinfo=UTC)
        )
        restored = await backups.async_get(backup["id"])
        assert parse_config_yaml(restored["yaml"]) == normalized
        await storage.async_save(normalized, records)
        reloaded, _, changed = await storage.async_load()
        assert reloaded == normalized
        assert changed is False

    asyncio.run(scenario())
    assert config == before


@pytest.mark.parametrize(
    "changes",
    [
        {"active_display_delay": 7},
        {"exclusion_label": "pas_d_alerte"},
        {"automatic": {"unavailable": {"domains": ["sensor"]}}},
    ],
)
def test_pre_22_configuration_is_rejected_without_overwriting_storage(
    hass, entry, changes
):
    """Both obsolete UI updates and unsupported stored data remain non-destructive."""

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        before = deepcopy(hass.stores["alert_manager"])
        with pytest.raises(ValueError, match="Unknown"):
            await manager.async_update_config(changes)
        assert hass.stores["alert_manager"] == before
        await manager.async_unload()
        unsupported = {"config": changes, "alerts": {}}
        hass.stores["alert_manager"] = deepcopy(unsupported)
        restarted = AlertManager(hass, entry)
        await restarted.async_setup()
        assert restarted.recovery_active
        assert hass.stores["alert_manager"] == unsupported
        await restarted.async_unload()

    asyncio.run(scenario())


def test_new_install_does_not_select_an_exclusion_label_by_name(hass):
    """Only explicitly selected label IDs control exclusions."""
    hass.label_registry.labels["pas_d_alerte"] = SimpleNamespace(label_id="skip")
    config, _, _ = asyncio.run(AlertManagerStorage(hass).async_load())
    assert config["excluded_labels"] == []


@pytest.mark.parametrize("version", [0, 1])
def test_obsolete_rule_versions_are_not_silently_upgraded(version):
    with pytest.raises(ValueError, match="version"):
        Rule.from_dict(
            {
                "id": "old",
                "name": "Old",
                "entity_ids": ["sensor.test"],
                "source": "state",
                "operator": "equals",
                "value": "on",
                "duration": 0,
                "version": version,
            }
        )
