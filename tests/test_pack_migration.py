"""Legacy configuration converts once, or remains recoverable without data loss."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest
import yaml
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr

from custom_components.alert_manager.const import DEFAULT_CONFIG
from custom_components.alert_manager.pack_migration import async_migrate_exclusions
from custom_components.alert_manager.pack_settings import resolve_settings
from custom_components.alert_manager.storage import _migrate_config_shape
from custom_components.alert_manager.validation import validate_config
from custom_components.alert_manager.yaml_io import dump_config_yaml, parse_config_yaml


def legacy_config():
    return {
        "global_delay": 123,
        "entity_delays": {"sensor.battery": 0},
        "excluded_entities": ["sensor.battery"],
        "excluded_devices": ["a" * 32],
        "excluded_labels": ["existing"],
        "automatic": {
            "battery": {
                "enabled": False,
                "delay": None,
                "device_thresholds": {"a" * 32: 20},
            },
            "execution_errors": {"failure_thresholds": {"automation.test": 3}},
            "flapping": {
                "entity_overrides": {
                    "sensor.battery": {
                        "enabled": False,
                        "occurrences": 7,
                        "window": 120,
                        "recovery": 60,
                    }
                },
                "source_packs": {"unavailable": {"window": 300}},
            },
        },
    }


def add_targets(hass):
    er.async_get(hass).entries["sensor.battery"] = SimpleNamespace(
        labels={"keep"}, device_id="a" * 32
    )
    dr.async_get(hass).entries["a" * 32] = SimpleNamespace(labels={"device_keep"})


def test_conversion_preserves_effective_values_and_sparse_inheritance():
    raw = legacy_config()
    before = deepcopy(raw)
    converted, changed = _migrate_config_shape(raw)
    assert changed and raw == before
    for key in ("excluded_entities", "excluded_devices"):
        converted.pop(key)
    config = validate_config(converted)
    for pack_id, pack in config["automatic"].items():
        if pack_id == "flapping":
            continue
        assert pack["delay"] == (0 if pack_id == "execution_errors" else 123)
        assert pack["entity_overrides"]["sensor.battery"] == {"delay": 0}
    assert config["automatic"]["battery"]["device_overrides"]["a" * 32] == {
        "threshold": 20
    }
    assert config["automatic"]["execution_errors"]["entity_overrides"][
        "automation.test"
    ] == {"failure_threshold": 3}
    values, _ = resolve_settings(
        config["automatic"]["flapping"], "sensor.battery", None, source_id="unavailable"
    )
    assert values["window"] == 300
    assert values["enabled"] is False
    repeated, changed = _migrate_config_shape(config)
    assert repeated == config and not changed


def test_labels_are_additive_durable_and_idempotent(hass):
    add_targets(hass)
    converted, _ = _migrate_config_shape(legacy_config())
    config = asyncio.run(async_migrate_exclusions(hass, converted))
    label_id = config["excluded_labels"][-1]
    assert config["excluded_labels"][0] == "existing"
    assert "excluded_entities" not in config and "excluded_devices" not in config
    assert er.async_get(hass).entries["sensor.battery"].labels == {"keep", label_id}
    assert dr.async_get(hass).entries["a" * 32].labels == {"device_keep", label_id}
    for registry in (lr.async_get(hass), er.async_get(hass), dr.async_get(hass)):
        assert registry.saved is not None
    assert asyncio.run(async_migrate_exclusions(hass, converted)) == config
    assert len(lr.async_get(hass).labels) == 1
    assert parse_config_yaml(
        dump_config_yaml(validate_config(config))
    ) == validate_config(config)


@pytest.mark.parametrize("kind", ["entity", "device"])
def test_missing_registry_targets_fail_before_label_mutation(hass, kind):
    add_targets(hass)
    registry = er.async_get(hass) if kind == "entity" else dr.async_get(hass)
    registry.entries.clear()
    converted, _ = _migrate_config_shape(legacy_config())
    before = deepcopy(converted)
    with pytest.raises(ValueError, match=f"Cannot migrate excluded {kind}"):
        asyncio.run(async_migrate_exclusions(hass, converted))
    assert converted == before
    assert not lr.async_get(hass).labels


@pytest.mark.parametrize("stage", ["assign", "durability", "cancel"])
def test_failed_or_interrupted_label_conversion_retains_source_for_retry(
    hass, monkeypatch, stage
):
    add_targets(hass)
    converted, _ = _migrate_config_shape(legacy_config())
    before = deepcopy(converted)
    registry = dr.async_get(hass)
    if stage == "assign":

        def fail(*args, **kwargs):
            raise OSError("registry denied")

        monkeypatch.setattr(registry, "async_update_device", fail)
    else:

        async def fail(*args, **kwargs):
            if stage == "cancel":
                raise asyncio.CancelledError
            raise OSError("disk full")

        monkeypatch.setattr(registry._store, "async_save", fail)
    with pytest.raises(
        asyncio.CancelledError if stage == "cancel" else (ValueError, OSError)
    ):
        asyncio.run(async_migrate_exclusions(hass, converted))
    assert converted == before
    monkeypatch.undo()
    config = asyncio.run(async_migrate_exclusions(hass, converted))
    assert len(lr.async_get(hass).labels) == 1
    assert config["excluded_labels"][-1] in registry.entries["a" * 32].labels


def test_user_label_collision_is_not_adopted(hass):
    from custom_components.alert_manager.pack_migration import _MIGRATION_LABEL

    add_targets(hass)
    lr.async_get(hass).async_create(_MIGRATION_LABEL, description="user label")
    converted, _ = _migrate_config_shape(legacy_config())
    with pytest.raises(ValueError, match="already in use"):
        asyncio.run(async_migrate_exclusions(hass, converted))
    assert er.async_get(hass).entries["sensor.battery"].labels == {"keep"}


def test_old_yaml_uses_the_same_boundary_conversion(hass):
    add_targets(hass)
    raw = legacy_config()
    for pack in ("unavailable", "connectivity", "unifi"):
        raw["automatic"][pack] = {"enabled": True, "delay": None}
    imported = parse_config_yaml(
        yaml.safe_dump({"version": 1, "config": raw, "rules": []})
    )
    loaded, _ = _migrate_config_shape(raw)
    assert validate_config(
        asyncio.run(async_migrate_exclusions(hass, imported))
    ) == validate_config(asyncio.run(async_migrate_exclusions(hass, loaded)))


def test_canonical_ui_rejects_legacy_fields_and_duplicate_yaml_targets():
    for key, value in (
        ("global_delay", 20),
        ("entity_delays", {}),
        ("excluded_entities", ["sensor.a"]),
        ("excluded_devices", ["a" * 32]),
    ):
        with pytest.raises(ValueError):
            validate_config({**deepcopy(DEFAULT_CONFIG), key: value})
    with pytest.raises(ValueError):
        parse_config_yaml(
            "version: 2\nconfig:\n  automatic:\n    battery:\n"
            "      entity_overrides:\n        sensor.a: {threshold: 10}\n"
            "        sensor.a: {threshold: 20}\nrules: []\n"
        )


def test_failed_startup_migration_keeps_original_store_without_reconciliation(
    hass, entry
):
    from custom_components.alert_manager.manager import AlertManager

    original = {"config": legacy_config(), "alerts": {}}
    hass.stores["alert_manager"] = deepcopy(original)
    hass.states.set("sensor.battery", "unavailable")
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    assert manager.recovery_active
    assert not manager.records
    assert hass.stores["alert_manager"] == original
    assert not hass.bus.fired
