"""Rule recipes use normal rules and on-demand deterministic discovery."""

import asyncio
from copy import deepcopy

import pytest
import yaml

from custom_components.alert_manager.blueprints import (
    discover_blueprint,
    discovery_attributes,
    explain_match,
    load_blueprints,
    snapshot_installation,
    validate_discovery,
)
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import Rule
from custom_components.alert_manager.yaml_io import dump_rule_yaml, parse_rule_yaml


def run(coro):
    return asyncio.run(coro)


def add_sensor(hass, registry_entry, entity_id, key, unit="%", state="95", **kwargs):
    entity = registry_entry(
        hass, entity_id, platform="systemmonitor", unique_id=key, **kwargs
    )
    hass.states.set(entity_id, state, {"unit_of_measurement": unit})
    return entity


def manager_for(hass, entry):
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    return manager


def test_catalog_is_valid_and_localized():
    import json
    from pathlib import Path

    catalog = load_blueprints()
    assert len(catalog) == 4
    for blueprint in catalog:
        assert "error" not in blueprint
        assert blueprint["schema_version"] == 1
        assert blueprint["blueprint_version"] == (
            2 if blueprint["category"] == "system" else 1
        )
        for language in ("en", "fr"):
            data = json.loads(
                (
                    Path("custom_components/alert_manager/translations")
                    / f"{language}.json"
                ).read_text()
            )["config_panel"]
            for field in ("name_key", "description_key"):
                value = data
                for key in blueprint[field].split("."):
                    value = value[key]
                assert value
            assert data["generator"]["categories"][blueprint["category"]]


def test_discovery_renamed_unavailable_disabled_and_units(hass, registry_entry):
    add_sensor(
        hass, registry_entry, "sensor.z_renamed", "processor_use", state="unavailable"
    )
    add_sensor(hass, registry_entry, "sensor.a_renamed", "processor_use")
    add_sensor(
        hass, registry_entry, "sensor.disabled", "processor_use", disabled_by="user"
    )
    add_sensor(hass, registry_entry, "sensor.wrong_unit", "processor_use", unit="MB")
    add_sensor(hass, registry_entry, "sensor.memory", "memory_use_percent")
    recipe = next(
        b for b in load_blueprints() if b["blueprint_id"] == "system_cpu_usage"
    )
    snapshot = snapshot_installation(hass, hass.entity_registry, set())
    result = discover_blueprint(recipe, snapshot)
    assert result == {
        "status": "available",
        "entity_ids": ["sensor.a_renamed", "sensor.z_renamed"],
    }
    snapshot["entities"].reverse()
    assert discover_blueprint(recipe, snapshot) == result
    hass.states.set("sensor.z_renamed", "unknown", {"unit_of_measurement": "%"})
    assert (
        discover_blueprint(
            recipe, snapshot_installation(hass, hass.entity_registry, set())
        )
        == result
    )


def test_requirements_lifecycle_limits_and_explanation():
    recipe = next(
        b for b in load_blueprints() if b["blueprint_id"] == "storage_disk_usage"
    )
    empty = {"integrations": set(), "entities": []}
    assert discover_blueprint(recipe, empty)["status"] == "missing_integration"
    empty["integrations"].add("systemmonitor")
    assert discover_blueprint(recipe, empty)["status"] == "no_entities"
    assert (
        discover_blueprint(
            {**recipe, "requirements": {"entity_domains": ["sensor"]}}, empty
        )["status"]
        == "missing_domain"
    )
    assert (
        discover_blueprint({**recipe, "deprecated": True, "replaced_by": "new"}, empty)[
            "replaced_by"
        ]
        == "new"
    )
    expr = {
        "all": [
            {"field": "domain", "equals": "sensor"},
            {
                "any": [
                    {"field": "device_class", "in": ["temperature"]},
                    {"field": "entity_id", "glob": "sensor.cpu_*"},
                ]
            },
            {"not": {"field": "attributes.error", "exists": True}},
        ]
    }
    validate_discovery(expr)
    entity = {"domain": "sensor", "entity_id": "sensor.cpu_1"}
    explanation = explain_match(expr, entity)
    assert explanation["matched"]
    assert not explanation["criteria"][1]["criteria"][0]["matched"]
    assert not explain_match(expr, {**entity, "attributes.error": False})["matched"]
    installation = {
        "integrations": {"systemmonitor"},
        "entities": [{**entity, "entity_id": f"sensor.cpu_{i}"} for i in range(51)],
    }
    assert (
        discover_blueprint({**recipe, "discovery": expr}, installation)["status"]
        == "too_many_entities"
    )


@pytest.mark.parametrize(
    "expression",
    [
        {},
        {"any": []},
        {"field": "bogus", "equals": 1},
        {"field": "domain", "regex": ".*"},
        {"field": "domain", "in": "sensor"},
        {"field": "domain", "exists": "yes"},
        {"all": [], "extra": True},
    ],
)
def test_unknown_discovery_fails_closed(expression):
    with pytest.raises(ValueError):
        validate_discovery(expression)


def test_loader_isolates_bad_files_and_duplicate_ids(tmp_path):
    valid = load_blueprints()[0]
    (tmp_path / "valid.yaml").write_text(yaml.safe_dump(valid))
    (tmp_path / "broken.yaml").write_text("discovery: [")
    loaded = load_blueprints(tmp_path)
    assert len(loaded) == 2
    assert sum("error" in b for b in loaded) == 1
    (tmp_path / "duplicate.yaml").write_text(yaml.safe_dump(valid))
    assert all("error" in b for b in load_blueprints(tmp_path))


def test_generation_batch_edit_yaml_and_duplicates(hass, entry, registry_entry):
    add_sensor(hass, registry_entry, "sensor.cpu", "processor_use")
    add_sensor(hass, registry_entry, "sensor.memory", "memory_use_percent")
    manager = manager_for(hass, entry)
    created = run(
        manager.async_generate_rules(["system_memory_usage", "system_cpu_usage"])
    )
    assert len(created) == 2
    assert len(manager.config["rules"]) == 2
    rule = created[0]
    assert rule["name"] == "Système : utilisation CPU élevée"
    assert rule["blueprint"] == {
        "id": "system_cpu_usage",
        "version": 2,
        "managed": False,
    }
    updated = run(
        manager.async_update_rule(rule["id"], {"name": "Renamed", "value": 70})
    )
    assert updated["blueprint"] == rule["blueprint"]
    assert parse_rule_yaml(dump_rule_yaml(updated)).blueprint == rule["blueprint"]
    updated = run(manager.async_update_rule_yaml(rule["id"], dump_rule_yaml(updated)))
    assert updated["blueprint"] == rule["blueprint"]
    rows = run(manager.async_list_rule_blueprints())
    assert all("rule" not in row for row in rows)
    assert {
        row["status"]
        for row in rows
        if row["blueprint_id"] in {"system_cpu_usage", "system_memory_usage"}
    } == {"already_generated"}
    with pytest.raises(ValueError, match="no longer available"):
        run(manager.async_generate_rules(["system_cpu_usage"]))
    assert len(manager.config["rules"]) == 2


def test_matching_manual_rule_and_atomic_invalid_selection(hass, entry, registry_entry):
    add_sensor(hass, registry_entry, "sensor.cpu", "processor_use")
    manager = manager_for(hass, entry)
    before = deepcopy(manager.config)
    with pytest.raises(ValueError, match="no longer available"):
        run(manager.async_generate_rules(["system_cpu_usage", "unknown"]))
    assert manager.config == before
    recipe = next(
        b for b in load_blueprints() if b["blueprint_id"] == "system_cpu_usage"
    )
    run(
        manager.async_create_rule(
            {**recipe["rule"], "entity_ids": ["sensor.cpu"], "name": "Manual"}
        )
    )
    row = next(
        row
        for row in run(manager.async_list_rule_blueprints())
        if row["blueprint_id"] == "system_cpu_usage"
    )
    assert row["status"] == "matching_rule"


def test_batch_save_failure_rolls_back(hass, entry, registry_entry, monkeypatch):
    add_sensor(hass, registry_entry, "sensor.cpu", "processor_use")
    add_sensor(hass, registry_entry, "sensor.memory", "memory_use_percent")
    manager = manager_for(hass, entry)
    before_config = deepcopy(manager.config)
    before_records = deepcopy(manager.records)

    async def fail():
        raise OSError("disk full")

    monkeypatch.setattr(manager, "_async_save_state", fail)
    with pytest.raises(OSError, match="disk full"):
        run(manager.async_generate_rules(["system_cpu_usage", "system_memory_usage"]))
    assert manager.config == before_config
    assert manager.records == before_records
    assert not manager.rules


def test_concurrent_generation_rechecks_duplicates(hass, entry, registry_entry):
    add_sensor(hass, registry_entry, "sensor.cpu", "processor_use")
    manager = manager_for(hass, entry)

    async def generate():
        return await asyncio.gather(
            manager.async_generate_rules(["system_cpu_usage"]),
            manager.async_generate_rules(["system_cpu_usage"]),
            return_exceptions=True,
        )

    results = run(generate())
    assert sum(isinstance(result, ValueError) for result in results) == 1
    assert len(manager.config["rules"]) == 1


@pytest.mark.parametrize(
    "provenance",
    [
        "cpu",
        {},
        {"id": "x", "version": True, "managed": False},
        {"id": "x", "version": 1, "managed": True},
    ],
)
def test_invalid_provenance_rejected(provenance):
    with pytest.raises(ValueError, match="provenance"):
        Rule.from_dict(
            {
                "id": "x",
                "name": "Test",
                "entity_ids": ["sensor.x"],
                "operator": "above",
                "value": 90,
                "duration": 0,
                "blueprint": provenance,
            }
        )


def test_provenance_survives_config_roundtrip_and_reload(hass, entry, registry_entry):
    from custom_components.alert_manager.yaml_io import (
        dump_config_yaml,
        parse_config_yaml,
    )

    add_sensor(hass, registry_entry, "sensor.cpu", "processor_use")
    manager = manager_for(hass, entry)
    rule = run(manager.async_generate_rules(["system_cpu_usage"]))[0]
    exported = parse_config_yaml(dump_config_yaml(manager.config))
    assert exported["rules"][0]["blueprint"] == rule["blueprint"]
    restored = manager_for(hass, entry)
    assert restored.config["rules"][0]["blueprint"] == rule["blueprint"]
    # Adding another matching entity does not manage or rewrite the original rule.
    add_sensor(hass, registry_entry, "sensor.cpu_new", "processor_use")
    run(restored.async_list_rule_blueprints())
    assert restored.config["rules"][0]["entity_ids"] == ["sensor.cpu"]


def test_snapshot_copies_only_requested_attributes(hass, registry_entry):
    class Uncopyable:
        def __deepcopy__(self, memo):
            raise AssertionError("Unrelated attributes must not be copied")

    add_sensor(hass, registry_entry, "sensor.cpu", "processor_use")
    wanted = [1, 2]
    hass.states.set("sensor.cpu", "95", {"wanted": wanted, "large": Uncopyable()})
    catalog = [
        {
            "discovery": {
                "all": [
                    {"field": "domain", "equals": "sensor"},
                    {"not": {"field": "attributes.wanted", "exists": False}},
                    {"any": [{"field": "attributes.missing", "exists": False}]},
                ]
            }
        },
        {"error": "Invalid recipe"},
    ]
    attributes = discovery_attributes(catalog)
    assert attributes == {"wanted", "missing"}
    snapshot = snapshot_installation(hass, hass.entity_registry, attributes)
    entity = next(e for e in snapshot["entities"] if e["entity_id"] == "sensor.cpu")
    assert entity["attributes.wanted"] == [1, 2]
    wanted.append(3)
    assert entity["attributes.wanted"] == [1, 2]
    assert "attributes.large" not in entity
    assert "attributes.missing" not in entity


def test_equivalent_blueprints_in_batch_are_rejected_atomically(
    hass, entry, registry_entry, monkeypatch
):
    from custom_components.alert_manager import manager_api

    add_sensor(hass, registry_entry, "sensor.cpu", "processor_use")
    recipe = next(
        b for b in load_blueprints() if b["blueprint_id"] == "system_cpu_usage"
    )
    duplicate = deepcopy(recipe)
    duplicate["blueprint_id"] = "duplicate_cpu"
    duplicate["rule"]["value"] = str(recipe["rule"]["value"])
    monkeypatch.setattr(manager_api, "load_blueprints", lambda: [recipe, duplicate])
    manager = manager_for(hass, entry)
    before = deepcopy(manager.config)
    with pytest.raises(ValueError, match="equivalent rules"):
        run(manager.async_generate_rules(["system_cpu_usage", "duplicate_cpu"]))
    assert manager.config == before
    assert not manager.rules
    assert not manager.records


@pytest.mark.parametrize(
    ("blueprint_id", "unit", "entity_ids"),
    [
        (
            "system_cpu_usage",
            "%",
            [
                "sensor.dream_machine_pro_cpu_utilization",
                "sensor.u5g_backup_cpu_utilization",
                "sensor.u7_outdoor_cpu_utilization",
                "sensor.u7_pro_xg_etage_cpu_utilization",
                "sensor.unas_cpu_usage",
                "sensor.ups_2u_cpu_utilization",
                "sensor.usw_24_poe_1_cpu_utilization",
                "sensor.usw_24_poe_2_cpu_utilization",
                "sensor.usw_flex_cpu_utilization",
            ],
        ),
        (
            "system_memory_usage",
            "%",
            [
                "sensor.dream_machine_pro_memory_utilization",
                "sensor.u5g_backup_memory_utilization",
                "sensor.u7_outdoor_memory_utilization",
                "sensor.u7_pro_xg_etage_memory_utilization",
                "sensor.unvr_memory_utilization",
                "sensor.ups_2u_memory_utilization",
                "sensor.usw_24_poe_1_memory_utilization",
                "sensor.usw_24_poe_2_memory_utilization",
                "sensor.usw_flex_memory_utilization",
            ],
        ),
        (
            "system_cpu_temperature",
            "°C",
            [
                "sensor.dream_machine_pro_dream_machine_pro_cpu_temperature",
                "sensor.system_monitor_temperature_du_processeur",
                "sensor.unvr_temperature_du_processeur",
            ],
        ),
    ],
)
def test_device_discovery_excludes_addons_and_wrong_units(
    hass, registry_entry, blueprint_id, unit, entity_ids
):
    """Discover the supplied device names without System Monitor installed."""
    recipe = next(b for b in load_blueprints() if b["blueprint_id"] == blueprint_id)
    for entity_id in entity_ids:
        registry_entry(hass, entity_id, platform="unifi")
        hass.states.set(entity_id, "unavailable", {"unit_of_measurement": unit})
        # Supervisor entities must be excluded even with a matching English name.
        addon_id = entity_id.replace("sensor.", "sensor.addon_")
        registry_entry(hass, addon_id, platform="hassio")
        hass.states.set(addon_id, "95", {"unit_of_measurement": unit})
        wrong_id = entity_id.replace("sensor.", "sensor.wrong_unit_")
        hass.states.set(wrong_id, "95", {"unit_of_measurement": "MB"})
    for suffix in ("pourcentage_du_processeur", "pourcentage_de_memoire"):
        for app in ("advanced_ssh_web_terminal", "browser"):
            entity_id = f"sensor.{app}_{suffix}"
            registry_entry(hass, entity_id, platform="hassio")
            hass.states.set(entity_id, "0", {"unit_of_measurement": "%"})
    # Similar names are not sufficient: CPU frequency, free memory and unrelated
    # temperatures must never enter these rules.
    for suffix in ("cpu_frequency", "memory_free", "disk_temperature"):
        hass.states.set(f"sensor.device_{suffix}", "95", {"unit_of_measurement": unit})
    result = discover_blueprint(
        recipe, snapshot_installation(hass, hass.entity_registry, set())
    )
    assert result == {"status": "available", "entity_ids": sorted(entity_ids)}


def test_device_discovery_supports_unregistered_sensors(hass):
    """Template/REST device metrics need no integration or registry identity."""
    hass.states.set("sensor.unas_cpu_usage", "4", {"unit_of_measurement": "%"})
    hass.states.set("sensor.unas_memory_usage", "40", {"unit_of_measurement": "%"})
    snapshot = snapshot_installation(hass, hass.entity_registry, set())
    for metric in ("cpu", "memory"):
        recipe = next(
            b
            for b in load_blueprints()
            if b["blueprint_id"] == f"system_{metric}_usage"
        )
        assert discover_blueprint(recipe, snapshot) == {
            "status": "available",
            "entity_ids": [f"sensor.unas_{metric}_usage"],
        }


def test_regeneration_preserves_identity_and_rediscovers(hass, entry, registry_entry):
    add_sensor(hass, registry_entry, "sensor.cpu", "processor_use")
    manager = manager_for(hass, entry)
    original = run(manager.async_generate_rules(["system_cpu_usage"]))[0]
    run(manager.async_update_rule(original["id"], {"name": "Custom", "value": 70}))
    add_sensor(hass, registry_entry, "sensor.new_cpu", "processor_use")
    result = run(manager.async_generate_rules(["system_cpu_usage"], overwrite=True))[0]
    assert result["id"] == original["id"]
    assert result["name"] == original["name"]
    assert result["value"] == original["value"]
    assert result["entity_ids"] == ["sensor.cpu", "sensor.new_cpu"]
    assert len(manager.config["rules"]) == 1


def test_regeneration_failure_rolls_back_mixed_batch(
    hass, entry, registry_entry, monkeypatch
):
    add_sensor(hass, registry_entry, "sensor.cpu", "processor_use")
    add_sensor(hass, registry_entry, "sensor.memory", "memory_use_percent")
    manager = manager_for(hass, entry)
    original = run(manager.async_generate_rules(["system_cpu_usage"]))[0]
    run(manager.async_update_rule(original["id"], {"value": 70}))
    before = deepcopy(manager.config)
    records = deepcopy(manager.records)

    async def fail():
        raise OSError("disk full")

    monkeypatch.setattr(manager, "_async_save_state", fail)
    with pytest.raises(OSError, match="disk full"):
        run(
            manager.async_generate_rules(
                ["system_cpu_usage", "system_memory_usage"], overwrite=True
            )
        )
    assert manager.config == before
    assert manager.records == records


def test_regeneration_still_requires_compatible_entities(hass, entry, registry_entry):
    add_sensor(hass, registry_entry, "sensor.cpu", "processor_use")
    manager = manager_for(hass, entry)
    run(manager.async_generate_rules(["system_cpu_usage"]))
    hass.states.set("sensor.cpu", "95", {"unit_of_measurement": "MB"})
    with pytest.raises(ValueError, match="no longer available"):
        run(manager.async_generate_rules(["system_cpu_usage"], overwrite=True))


def test_regeneration_does_not_choose_between_duplicated_rules(
    hass, entry, registry_entry
):
    add_sensor(hass, registry_entry, "sensor.cpu", "processor_use")
    manager = manager_for(hass, entry)
    original = run(manager.async_generate_rules(["system_cpu_usage"]))[0]
    run(
        manager.async_create_rule(
            {
                key: value
                for key, value in original.items()
                if key not in {"id", "version"}
            }
        )
    )
    before = deepcopy(manager.config)
    row = next(
        row
        for row in run(manager.async_list_rule_blueprints())
        if row["blueprint_id"] == "system_cpu_usage"
    )
    assert row["status"] == "multiple_generated"
    with pytest.raises(ValueError, match="no longer available"):
        run(manager.async_generate_rules(["system_cpu_usage"], overwrite=True))
    assert manager.config == before
