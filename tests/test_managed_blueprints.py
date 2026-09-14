"""Managed blueprint maintenance shares normal configuration and alert lifecycle."""

import asyncio
import threading
from copy import deepcopy

import pytest
from test_blueprints import add_sensor, manager_for, run

from custom_components.alert_manager import manager_api
from custom_components.alert_manager.models import Rule


def create_managed(hass, entry, registry_entry):
    add_sensor(hass, registry_entry, "sensor.cpu", "processor_use")
    manager = manager_for(hass, entry)
    rule = run(manager.async_generate_rules(["system_cpu_usage"], managed=True))[0]
    return manager, rule


def apply(manager, row, entities=None, exclusions=None):
    return manager.async_apply_blueprint(
        row["rule_id"],
        row["token"],
        row["candidate"]["entity_ids"] if entities is None else entities,
        row["candidate"]["blueprint"]["excluded_entities"]
        if exclusions is None
        else exclusions,
    )


def test_explicit_membership_exclusions_and_detach(hass, entry, registry_entry):
    manager, original = create_managed(hass, entry, registry_entry)
    add_sensor(hass, registry_entry, "sensor.new", "processor_use", state="unavailable")
    before = deepcopy(manager.config)
    row = run(manager.async_reconcile_blueprints())[0]
    assert row["added"] == ["sensor.new"]
    assert manager.config == before
    updated = run(apply(manager, row, ["sensor.cpu"], ["sensor.new"]))
    assert updated["entity_ids"] == original["entity_ids"]
    assert not run(manager.async_reconcile_blueprints())[0]["update_available"]
    hass.states.set("sensor.new", "unknown", {"unit_of_measurement": "%"})
    assert not run(manager.async_reconcile_blueprints())[0]["update_available"]
    detached = run(manager.async_detach_blueprint(original["id"]))
    assert detached["blueprint"]["managed"] is False
    assert detached["entity_ids"] == updated["entity_ids"]
    assert run(manager.async_reconcile_blueprints()) == []
    run(manager.async_update_rule(original["id"], {"operator": "below"}))


def test_new_version_preserves_only_explicit_overrides(
    hass, entry, registry_entry, monkeypatch
):
    manager, rule = create_managed(hass, entry, registry_entry)
    run(
        manager.async_update_rule(
            rule["id"], {"value": 85, "name": "My CPU", "label_ids": ["mine"]}
        )
    )
    catalog = manager_api.load_blueprints()
    recipe = next(
        item for item in catalog if item["blueprint_id"] == "system_cpu_usage"
    )
    recipe["blueprint_version"] += 1
    recipe["rule"].update(value=92, duration=600, message="Updated message")
    monkeypatch.setattr(manager_api, "load_blueprints", lambda: catalog)
    row = run(manager.async_reconcile_blueprints())[0]
    assert row["version_available"]
    updated = run(apply(manager, row))
    assert updated["value"] == 85
    assert updated["duration"] == 600
    assert updated["message"] == "Updated message"
    assert updated["name"] == "My CPU"
    assert updated["label_ids"] == ["mine"]
    assert updated["blueprint"]["overrides"] == {"value": 85}
    assert Rule.from_dict(updated).as_dict() == updated


@pytest.mark.parametrize(
    "changes",
    [
        {"operator": "below"},
        {"entity_ids": ["sensor.other"]},
        {"message": "custom"},
        {"blueprint": None},
    ],
)
def test_owned_fields_reject_ordinary_edits(hass, entry, registry_entry, changes):
    manager, rule = create_managed(hass, entry, registry_entry)
    before = deepcopy(manager.config)
    with pytest.raises(ValueError, match="Detach"):
        run(manager.async_update_rule(rule["id"], changes))
    assert manager.config == before


def test_stale_and_invalid_proposals_cannot_commit(hass, entry, registry_entry):
    manager, rule = create_managed(hass, entry, registry_entry)
    row = run(manager.async_reconcile_blueprints())[0]
    run(manager.async_update_rule(rule["id"], {"name": "Concurrent edit"}))
    with pytest.raises(ValueError, match="Rules changed"):
        run(apply(manager, row))
    row = run(manager.async_reconcile_blueprints())[0]
    for entities, exclusions in [
        ([], []),
        (["sensor.invented"], []),
        (["sensor.cpu"], ["sensor.cpu"]),
    ]:
        with pytest.raises(ValueError):
            run(apply(manager, row, entities, exclusions))
    add_sensor(hass, registry_entry, "sensor.added_later", "processor_use")
    with pytest.raises(ValueError, match="Rules changed"):
        run(apply(manager, row))


@pytest.mark.parametrize("duration", [0, 300])
def test_sync_preserves_retained_alerts_and_rolls_back(
    hass, entry, registry_entry, monkeypatch, duration
):
    manager, rule = create_managed(hass, entry, registry_entry)
    run(manager.async_update_rule(rule["id"], {"duration": duration}))
    key = f"rule:{rule['id']}:sensor.cpu"
    record = deepcopy(manager.records[key])
    add_sensor(hass, registry_entry, "sensor.new", "processor_use")
    row = run(manager.async_reconcile_blueprints())[0]
    before = deepcopy(manager.config)
    save = manager._async_save_state

    async def fail():
        raise OSError("storage failure")

    monkeypatch.setattr(manager, "_async_save_state", fail)
    with pytest.raises(OSError, match="storage failure"):
        run(apply(manager, row))
    assert manager.config == before
    assert manager.records[key] == record
    monkeypatch.setattr(manager, "_async_save_state", save)
    updated = run(apply(manager, row))
    assert manager.records[key].detected_at == record.detected_at
    assert manager.records[key].status == record.status
    assert updated["id"] == rule["id"]
    row = run(manager.async_reconcile_blueprints())[0]
    run(apply(manager, row, ["sensor.new"], ["sensor.cpu"]))
    assert key not in manager.records


def test_discovery_is_shared_coalesced_off_loop_and_unload_safe(
    hass, entry, registry_entry, monkeypatch
):
    manager, rule = create_managed(hass, entry, registry_entry)
    original = manager_api.reconcile_blueprints
    entered = threading.Event()
    release = threading.Event()
    count = 0
    main_thread = threading.get_ident()

    def blocked(*args):
        nonlocal count
        count += 1
        assert threading.get_ident() != main_thread
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(manager_api, "reconcile_blueprints", blocked)

    async def scenario():
        tasks = [
            asyncio.create_task(manager.async_reconcile_blueprints()) for _ in range(5)
        ]
        assert await asyncio.to_thread(entered.wait, 5)
        tasks[0].cancel()
        with pytest.raises(asyncio.CancelledError):
            await tasks[0]
        # A cancelled client must not cancel a shared maintenance operation.
        release.set()
        rows = await asyncio.gather(*tasks[1:])
        assert all(result[0]["rule_id"] == rule["id"] for result in rows)
        assert count == 1
        entered.clear()
        release.clear()
        task = asyncio.create_task(manager.async_reconcile_blueprints())
        assert await asyncio.to_thread(entered.wait, 5)
        await manager.async_unload()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    run(scenario())


def test_exclusions_follow_registry_renames(hass, entry, registry_entry):
    manager, _rule = create_managed(hass, entry, registry_entry)
    add_sensor(hass, registry_entry, "sensor.excluded", "processor_use")
    row = run(manager.async_reconcile_blueprints())[0]
    run(apply(manager, row, ["sensor.cpu"], ["sensor.excluded"]))
    manager._pending_entity_renames["sensor.excluded"] = "sensor.renamed"
    assert manager._apply_pending_entity_renames()
    assert manager.config["rules"][0]["blueprint"]["excluded_entities"] == [
        "sensor.renamed"
    ]


def test_acknowledged_state_history_and_pending_deadline_survive(
    hass, entry, registry_entry
):
    manager, rule = create_managed(hass, entry, registry_entry)
    key = f"rule:{rule['id']}:sensor.cpu"
    pending = deepcopy(manager.records[key])
    add_sensor(hass, registry_entry, "sensor.new", "processor_use")
    row = run(manager.async_reconcile_blueprints())[0]
    run(apply(manager, row))
    assert manager.records[key].due_at == pending.due_at
    assert key in manager._timers
    run(manager.async_update_rule(rule["id"], {"duration": 0}))
    assert run(manager.async_acknowledge(key, "Loïc"))
    acknowledged = deepcopy(manager.records[key])
    history = deepcopy(manager.history)
    add_sensor(hass, registry_entry, "sensor.third", "processor_use")
    run(apply(manager, run(manager.async_reconcile_blueprints())[0]))
    assert manager.records[key].acknowledged_at == acknowledged.acknowledged_at
    assert manager.records[key].status == acknowledged.status
    assert manager.history == history


def test_unchanged_form_values_do_not_create_overrides(hass, entry, registry_entry):
    manager, rule = create_managed(hass, entry, registry_entry)
    updated = run(
        manager.async_update_rule(rule["id"], {"value": "90", "duration": 300})
    )
    assert updated["blueprint"]["overrides"] == {}
    assert run(manager.async_reconcile_blueprints())[0]["candidate"]["value"] == 90


def test_config_edit_during_comparison_is_rejected(
    hass, entry, registry_entry, monkeypatch
):
    manager, rule = create_managed(hass, entry, registry_entry)
    original = manager_api.reconcile_blueprints
    entered = threading.Event()
    release = threading.Event()

    def blocked(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(manager_api, "reconcile_blueprints", blocked)

    async def scenario():
        task = asyncio.create_task(manager.async_reconcile_blueprints())
        assert await asyncio.to_thread(entered.wait, 5)
        await manager.async_update_rule(rule["id"], {"name": "Edited while checking"})
        release.set()
        with pytest.raises(ValueError, match="Rules changed"):
            await task

    run(scenario())


def test_managed_settings_survive_restart(hass, entry, registry_entry):
    manager, rule = create_managed(hass, entry, registry_entry)
    run(manager.async_update_rule(rule["id"], {"duration": 60, "value": 75}))
    config = deepcopy(manager.config)
    run(manager.async_unload())
    restored = manager_for(hass, entry)
    assert restored.config["rules"] == config["rules"]
    assert not run(restored.async_reconcile_blueprints())[0]["update_available"]


def test_nonmatching_entities_are_only_removed_after_review(
    hass, entry, registry_entry
):
    manager, _rule = create_managed(hass, entry, registry_entry)
    add_sensor(hass, registry_entry, "sensor.new", "processor_use")
    hass.states.set("sensor.cpu", "95", {"unit_of_measurement": "MB"})
    row = run(manager.async_reconcile_blueprints())[0]
    assert row["removed"] == ["sensor.cpu"]
    assert manager.config["rules"][0]["entity_ids"] == ["sensor.cpu"]
    updated = run(apply(manager, row))
    assert updated["entity_ids"] == ["sensor.new"]


def test_same_blueprint_rules_share_one_discovery(hass, registry_entry, monkeypatch):
    from custom_components.alert_manager import blueprints

    add_sensor(hass, registry_entry, "sensor.cpu", "processor_use")
    catalog = blueprints.load_blueprints()
    installation = blueprints.snapshot_installation(hass, hass.entity_registry, set())
    recipe = next(
        item for item in catalog if item["blueprint_id"] == "system_cpu_usage"
    )
    rule = Rule.from_dict(
        {"id": "first", **blueprints.blueprint_payload(recipe, ["sensor.cpu"], {})}
    ).as_dict()
    rule["blueprint"]["managed"] = True
    duplicate = {**deepcopy(rule), "id": "second"}
    discover = blueprints.discover_blueprint
    calls = []

    def counted(*args):
        calls.append(args[0]["blueprint_id"])
        return discover(*args)

    monkeypatch.setattr(blueprints, "discover_blueprint", counted)
    rows = blueprints.reconcile_blueprints(catalog, installation, [rule, duplicate], {})
    assert len(rows) == 2
    assert calls == ["system_cpu_usage"]


def test_apply_only_rediscovers_the_selected_blueprint(
    hass, entry, registry_entry, monkeypatch
):
    manager, rule = create_managed(hass, entry, registry_entry)
    add_sensor(hass, registry_entry, "sensor.memory", "memory_use_percent")
    run(manager.async_generate_rules(["system_memory_usage"], managed=True))
    row = next(
        row
        for row in run(manager.async_reconcile_blueprints())
        if row["rule_id"] == rule["id"]
    )
    original = manager_api.reconcile_blueprints
    snapshots = []

    def capture(catalog, installation, rules, translations):
        snapshots.append(([item["blueprint_id"] for item in catalog], rules))
        return original(catalog, installation, rules, translations)

    monkeypatch.setattr(manager_api, "reconcile_blueprints", capture)
    run(apply(manager, row))
    assert len(snapshots) == 1
    assert snapshots[0][0] == ["system_cpu_usage"]
    assert [item["id"] for item in snapshots[0][1]] == [rule["id"]]


@pytest.mark.parametrize("payload", [None, [], "invalid", 1])
def test_create_rejects_non_object_rule_payloads(hass, entry, payload):
    manager = manager_for(hass, entry)
    with pytest.raises(ValueError, match="Rule must be an object"):
        run(manager.async_create_rule(payload))


def test_managed_yaml_partial_edits_preserve_structure(hass, entry, registry_entry):
    manager, rule = create_managed(hass, entry, registry_entry)
    raw = 'name: "My CPU"\nvalue: 82\nduration: 60\n'
    before = deepcopy(manager.config)
    validated = run(manager.async_validate_rule_yaml(raw, rule_id=rule["id"]))
    assert validated["blueprint"]["managed"] is True
    assert manager.config == before
    updated = run(manager.async_update_rule_yaml(rule["id"], raw))
    assert updated["name"] == "My CPU"
    assert updated["value"] == 82
    assert updated["duration"] == 60
    for key in ("id", "entity_ids", "source", "operator", "condition_template"):
        assert updated.get(key) == rule.get(key)
    assert updated["blueprint"]["overrides"] == {"value": 82, "duration": 60}
    renamed = run(manager.async_update_rule_yaml(rule["id"], 'name: "Renamed"'))
    assert renamed["value"] == 82
    assert renamed["duration"] == 60


@pytest.mark.parametrize(
    "raw",
    [
        "source: jinja",
        "entity_ids: [sensor.other]",
        "blueprint: null",
        "condition_template: '{{ false }}'",
        "operator: below",
    ],
)
def test_managed_yaml_rejects_structural_edits(hass, entry, registry_entry, raw):
    manager, rule = create_managed(hass, entry, registry_entry)
    before = deepcopy(manager.config)
    for request in (
        manager.async_validate_rule_yaml(raw, rule_id=rule["id"]),
        manager.async_update_rule_yaml(rule["id"], raw),
    ):
        with pytest.raises(ValueError, match="blueprint-owned"):
            run(request)
    assert manager.config == before


def test_managed_yaml_parsing_runs_in_executor(
    hass, entry, registry_entry, monkeypatch
):
    manager, rule = create_managed(hass, entry, registry_entry)
    original = manager_api.parse_rule_yaml_data
    threads = []

    def parse(*args, **kwargs):
        threads.append(threading.get_ident())
        return original(*args, **kwargs)

    monkeypatch.setattr(manager_api, "parse_rule_yaml_data", parse)
    main_thread = threading.get_ident()
    run(manager.async_validate_rule_yaml("duration: 42", rule_id=rule["id"]))
    run(manager.async_update_rule_yaml(rule["id"], "duration: 42"))
    assert len(threads) == 2
    assert all(thread != main_thread for thread in threads)


def test_managed_jinja_yaml_and_tester_keep_blueprint_templates(
    hass, entry, registry_entry
):
    registry_entry(
        hass,
        "sensor.backup",
        platform="backup",
        unique_id="last_successful_automatic_backup",
    )
    hass.states.set("sensor.backup", "2026-09-14T00:00:00+00:00")
    manager = manager_for(hass, entry)
    rule = run(
        manager.async_generate_rules(["home_assistant_backup_age"], managed=True)
    )[0]
    updated = run(manager.async_update_rule_yaml(rule["id"], 'name: "My backup"'))
    assert updated["condition_template"] == rule["condition_template"]
    assert updated["source"] == "jinja"
    assert updated["blueprint"]["managed"] is True
    before = deepcopy(manager.config)
    result = run(
        manager.async_test_rule(
            {"name": "Test backup", "duration": 0}, rule_id=rule["id"]
        )
    )
    assert len(result["results"]) == 1
    assert result["results"][0]["source"] == "jinja"
    assert manager.config == before
