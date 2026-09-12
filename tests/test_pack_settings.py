"""Sparse pack exceptions preserve inheritance and deterministic precedence."""

from copy import deepcopy

from custom_components.alert_manager.pack_settings import resolve_settings


def test_fields_inherit_independently_and_zero_remains_explicit():
    config = {
        "enabled": True,
        "delay": 900,
        "threshold": 15,
        "device_overrides": {"device": {"delay": 1800, "enabled": False}},
        "entity_overrides": {"sensor.battery": {"threshold": 10, "enabled": True}},
    }
    before = deepcopy(config)
    values, origins = resolve_settings(config, "sensor.battery", "device")
    assert values == {"enabled": True, "delay": 1800, "threshold": 10}
    assert origins == {"enabled": "entity", "delay": "device", "threshold": "entity"}
    assert config == before
    config["entity_overrides"]["sensor.battery"]["delay"] = 0
    assert resolve_settings(config, "sensor.battery", "device")[0]["delay"] == 0
    del config["entity_overrides"]["sensor.battery"]["delay"]
    assert resolve_settings(config, "sensor.battery", "device")[0]["delay"] == 1800


def test_explicit_parent_equal_value_does_not_start_inheriting():
    config = {
        "enabled": True,
        "delay": 30,
        "entity_overrides": {"sensor.test": {"delay": 30}},
    }
    config["delay"] = 60
    assert resolve_settings(config, "sensor.test", None)[0]["delay"] == 30
    assert resolve_settings(config, "sensor.other", None)[0]["delay"] == 60


def test_disabled_pack_cannot_be_enabled_by_an_exception():
    config = {"enabled": False, "entity_overrides": {"sensor.test": {"enabled": True}}}
    values, origins = resolve_settings(config, "sensor.test", None)
    assert values["enabled"] is False
    assert origins["enabled"] == "pack"


def test_source_exceptions_are_isolated_with_field_by_field_priority():
    config = {
        "enabled": True,
        "occurrences": 5,
        "window": 7200,
        "recovery": 300,
        "device_overrides": {"device": {"window": 3600}},
        "entity_overrides": {"sensor.test": {"recovery": 100}},
        "source_packs": {
            "unavailable": {
                "occurrences": 8,
                "entity_overrides": {"sensor.test": {"occurrences": 10}},
            },
            "connectivity": {"occurrences": 6},
        },
    }
    unavailable, origins = resolve_settings(
        config, "sensor.test", "device", source_id="unavailable"
    )
    assert unavailable == {
        "enabled": True,
        "occurrences": 10,
        "window": 3600,
        "recovery": 100,
    }
    assert origins["occurrences"] == "source_entity"
    assert (
        resolve_settings(config, "sensor.test", "device", source_id="connectivity")[0][
            "occurrences"
        ]
        == 6
    )
    assert (
        resolve_settings(config, "sensor.test", "device", source_id="battery")[0][
            "enabled"
        ]
        is False
    )
