"""Scoped configuration editors reuse validation without mutating runtime state."""

import asyncio
from copy import deepcopy

import pytest
import yaml

from custom_components.alert_manager.const import DEFAULT_CONFIG
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.packs import PACKS_BY_ID
from custom_components.alert_manager.yaml_io import parse_configuration_field_yaml


@pytest.mark.parametrize(
    ("field", "pack", "value"),
    [
        (
            "entity_overrides",
            "unavailable",
            {"sensor.b": {"delay": 0}, "sensor.a": {"delay": 86400}},
        ),
        (
            "device_overrides",
            "battery",
            {
                "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb": {"threshold": 15},
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": {"threshold": 20},
            },
        ),
        (
            "entity_overrides",
            "execution_errors",
            {"automation.test": {"failure_threshold": 3}},
        ),
        (
            "entity_overrides",
            "flapping",
            {
                "sensor.b": {
                    "enabled": False,
                    "occurrences": 5,
                    "window": 7200,
                    "recovery": 3600,
                },
                "sensor.a": {
                    "enabled": True,
                    "occurrences": 3,
                    "window": 300,
                    "recovery": 600,
                },
            },
        ),
        (
            "source_packs",
            "flapping",
            {
                "connectivity": {"occurrences": None, "window": 300, "recovery": None},
                "unavailable": {"occurrences": 3, "window": None, "recovery": 600},
            },
        ),
    ],
)
def test_scoped_yaml_preserves_values_and_order(field, pack, value):
    raw = yaml.safe_dump({field: value}, sort_keys=False)
    result = parse_configuration_field_yaml(raw, field, pack)
    assert result == value
    assert list(result) == list(value)


def test_every_declared_pack_drawer_accepts_its_default():
    for pack in PACKS_BY_ID.values():
        for field in pack.config_fields:
            if field.type.endswith("_map"):
                assert (
                    parse_configuration_field_yaml(
                        yaml.safe_dump({field.id: field.default}), field.id, pack.id
                    )
                    == field.default
                )


@pytest.mark.parametrize(
    ("raw", "field", "pack"),
    [
        ("entity_delays: [", "entity_delays", None),
        ("", "entity_delays", None),
        ("[]", "entity_delays", None),
        ("entity_delays: null", "entity_delays", None),
        ("entity_delays: {}\nrules: []", "entity_delays", None),
        ("entity_delays: {}\nentity_delays: {}", "entity_delays", None),
        ("entity_delays: {sensor.a: 1, sensor.a: 2}", "entity_delays", None),
        ("entity_delays: {sensor.a: -1}", "entity_delays", None),
        ("entity_delays: {sensor.a: 1.5}", "entity_delays", None),
        ("entity_delays: {sensor.a: 31536001}", "entity_delays", None),
        ("entity_delays: {sensor.alert_manager_main_active: 5}", "entity_delays", None),
        ("excluded_entities: [bad]", "excluded_entities", None),
        ("excluded_devices: [null]", "excluded_devices", None),
        (
            "device_thresholds: {aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa: 1000000001}",
            "device_thresholds",
            "battery",
        ),
        (
            "device_thresholds: {aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa: .nan}",
            "device_thresholds",
            "battery",
        ),
        ("failure_thresholds: {sensor.a: 2}", "failure_thresholds", "execution_errors"),
        ("source_packs: {unknown: {}}", "source_packs", "flapping"),
        ("source_packs: {unavailable: {typo: 5}}", "source_packs", "flapping"),
        (
            "entity_overrides: {sensor.a: {enabled: nope}}",
            "entity_overrides",
            "flapping",
        ),
        ("{}", "entity_delays", None),
        ("rules: []", "rules", None),
        ("enabled: false", "enabled", "battery"),
        ("threshold: 20", "threshold", "battery"),
        ("device_thresholds: {}", "device_thresholds", "unknown"),
    ],
)
def test_scoped_yaml_rejects_invalid_or_out_of_scope_data(raw, field, pack):
    with pytest.raises(ValueError):
        parse_configuration_field_yaml(raw, field, pack)


def test_scoped_yaml_validation_runs_in_executor_without_mutation(
    hass, entry, monkeypatch
):
    manager = AlertManager(hass, entry)
    manager.config = deepcopy(DEFAULT_CONFIG)
    original_config = deepcopy(manager.config)
    calls = []
    original_executor = hass.async_add_executor_job

    async def executor(target, *args):
        calls.append(target)
        return await original_executor(target, *args)

    monkeypatch.setattr(hass, "async_add_executor_job", executor)
    result = asyncio.run(
        manager.async_validate_configuration_field_yaml(
            "entity_overrides: {sensor.a: {delay: 120}}",
            "entity_overrides",
            "unavailable",
        )
    )
    assert result == {"sensor.a": {"delay": 120}}
    assert manager.config == original_config
    assert calls == [parse_configuration_field_yaml]
