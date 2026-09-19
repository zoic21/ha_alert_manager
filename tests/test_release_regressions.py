"""Clock, identity and reconciliation regressions found in the stable review."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import State
from homeassistant.util import dt as dt_util
from test_transitions import edge, expire, run, setup

from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertDetails, AlertRecord, Rule
from custom_components.alert_manager.sequences import SequenceProgress
from custom_components.alert_manager.transactions import (
    StartupReconciliationTransaction,
)
from custom_components.alert_manager.yaml_io import dump_config_yaml


@pytest.mark.parametrize("via_import", [False, True])
def test_source_edit_discards_previous_transition_deadline(
    hass, entry, set_now, via_import
):
    manager, key, rule = setup(hass, entry)
    edge(manager, hass, "B")
    old_deadline = manager.records[key].expires_at
    stale_timer = next(
        timer for timer in reversed(hass.timers) if not timer["cancelled"]
    )
    changes = {"source": "value", "operator": "equals", "value": ["B"], "duration": 0}
    if via_import:
        config = manager.get_config()
        config["rules"][0].update(changes)
        run(manager.async_import_config(dump_config_yaml(config)))
    else:
        run(manager.async_update_rule(rule["id"], changes))
    assert manager.records[key].expires_at is None
    set_now(old_deadline)
    stale_timer["action"](old_deadline)
    run(manager._async_flush_queued_evaluations())
    assert key in manager.records
    assert not manager.history


@pytest.mark.parametrize("change", ["remove", "disable", "entity"])
@pytest.mark.parametrize("paused", [False, True])
def test_import_removes_invalid_transition_instances(hass, entry, change, paused):
    manager, key, _ = setup(hass, entry)
    edge(manager, hass, "B")
    if paused:
        run(manager.async_set_monitoring(False))
    config = manager.get_config()
    if change == "remove":
        config["rules"] = []
    elif change == "disable":
        config["rules"][0]["enabled"] = False
    else:
        hass.states.set("sensor.replacement", "B")
        config["rules"][0]["entity_ids"] = ["sensor.replacement"]
    run(manager.async_import_config(dump_config_yaml(config)))
    assert key not in manager.records
    assert key not in manager._timers
    assert not manager.history


@pytest.mark.parametrize("change", ["attribute", "condition_template"])
def test_import_resets_only_incompatible_variation_baselines(hass, entry, change):
    async def scenario():
        hass.states.set("sensor.value", "10", {"a": 10, "b": 100})
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(
            {
                "name": "Variation",
                "entity_ids": ["sensor.value"],
                "source": "value_variation",
                "attribute": "a",
                "condition_template": "{{ true }}",
                "operator": "above",
                "value": 5,
                "duration": 0,
            }
        )
        baseline_key = f"{rule['id']}:sensor.value"
        original = deepcopy(manager._variation_baselines[baseline_key])
        config = manager.get_config()
        # An unrelated import must preserve the observation window.
        config["rules"][0]["name"] = "Renamed"
        await manager.async_import_config(dump_config_yaml(config))
        assert manager._variation_baselines[baseline_key] == original
        config["rules"][0][change] = "b" if change == "attribute" else "true"
        hass.states.set("sensor.value", "20", {"a": 20, "b": 100})
        await manager.async_import_config(dump_config_yaml(config))
        assert f"rule:{rule['id']}:sensor.value" not in manager.records
        assert manager._variation_baselines[baseline_key] != original
        assert not manager.history

    run(scenario())


def test_temporary_acknowledgement_uses_elapsed_time(hass, entry, set_now, dst_start):
    set_now(dst_start)
    manager, key, _ = setup(hass, entry, auto_resolve=7200)
    edge(manager, hass, "B")
    run(manager.async_set_acknowledgements([key], True, None, duration=60))
    record = manager.records[key]
    expected = dst_start.astimezone(UTC) + timedelta(seconds=60)
    assert record.acknowledged_until.astimezone(UTC) == expected
    deadline = record.acknowledged_until
    set_now((expected - timedelta(seconds=1)).astimezone(dst_start.tzinfo))
    run(manager._async_expire_acknowledgement(record, deadline))
    assert record.acknowledged
    set_now(expected.astimezone(dst_start.tzinfo))
    run(manager._async_expire_acknowledgement(record, deadline))
    assert not record.acknowledged


def test_pending_pause_and_delay_edits_use_elapsed_time(
    hass, entry, set_now, dst_start
):
    set_now(dst_start)
    hass.states.set("sensor.pending", "unavailable")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    run(manager.async_update_config({"pending_display_delay": 120}))
    key = "unavailable:sensor.pending"
    record = manager.records[key]
    initial_due = record.due_at.astimezone(UTC)
    initial_visible = record.visible_at.astimezone(UTC)
    run(manager.async_set_monitoring(False))
    resumed = dst_start.astimezone(UTC) + timedelta(seconds=60)
    set_now(resumed.astimezone(dst_start.tzinfo))
    run(manager.async_set_monitoring(True))
    record = manager.records[key]
    assert record.due_at.astimezone(UTC) == initial_due + timedelta(seconds=60)
    assert record.visible_at.astimezone(UTC) == initial_visible + timedelta(seconds=60)
    run(
        manager.async_update_config(
            {
                "pending_display_delay": 180,
                "automatic": {"unavailable": {"delay": 1200}},
            }
        )
    )
    record = manager.records[key]
    assert record.due_at.astimezone(UTC) == dst_start.astimezone(UTC) + timedelta(
        seconds=1260
    )
    assert record.visible_at.astimezone(UTC) == dst_start.astimezone(UTC) + timedelta(
        seconds=240
    )


def test_rule_metadata_enrichment_scans_rule_definitions_once(hass, entry):
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    manager._rules = [
        Rule.from_dict(
            {
                "id": str(i),
                "name": str(i),
                "entity_ids": [f"sensor.x{i}"],
                "source": "value",
                "operator": "equals",
                "value": ["on"],
                "duration": 0,
            }
        )
        for i in range(300)
    ]
    for rule in manager._rules:
        key = f"rule:{rule.id}:{rule.entity_ids[0]}"
        manager.records[key] = AlertRecord.pending(
            AlertDetails(
                id=key,
                type="rule",
                entity_id=rule.entity_ids[0],
                name="x",
                value="on",
                condition="x",
            ),
            60,
            dt_util.now(),
        )

    class CountedRules(list):
        visits = 0

        def __iter__(self):
            for rule in super().__iter__():
                self.visits += 1
                yield rule

    manager._rules = CountedRules(manager._rules)
    manager._enrich_rule_metadata()
    assert manager._rules.visits == len(manager._rules)
    assert all(
        record.details.rule_id is not None for record in manager.records.values()
    )


@pytest.fixture(params=[(3, 29, 1), (10, 25, 2)])
def dst_start(request):
    month, day, hour = request.param
    return datetime(2026, month, day, hour, 59, 30, tzinfo=ZoneInfo("Europe/Paris"))


def test_transition_expiration_across_dst(hass, entry, set_now, dst_start):
    set_now(dst_start)
    manager, key, _ = setup(hass, entry, auto_resolve=60)
    edge(manager, hass, "B")
    deadline = dst_start.astimezone(UTC) + timedelta(seconds=60)
    assert manager.records[key].expires_at == deadline
    set_now(deadline.astimezone(dst_start.tzinfo))
    expire(manager, key)
    assert key not in manager.records


@pytest.mark.parametrize("outgoing_first", [False, True])
def test_sequence_hold_across_dst(dst_start, outgoing_first):
    rule = Rule.from_dict(
        {
            "id": "s",
            "name": "s",
            "entity_ids": ["sensor.x"],
            "source": "value_sequence",
            "steps": [
                {"operator": "equals", "value": "A", "duration": 60},
                {"operator": "equals", "value": "B"},
            ],
        }
    )
    progress = SequenceProgress(rule)
    previous = State("sensor.x", "A")
    progress.observe(previous, dst_start)
    deadline = dst_start.astimezone(UTC) + timedelta(seconds=60)
    assert progress.deadline() == deadline
    now = deadline.astimezone(dst_start.tzinfo)
    if not outgoing_first:
        assert progress.observe(previous, now) is None
        assert progress.index == 1
    evidence = progress.observe(State("sensor.x", "B"), now, previous=previous)
    assert evidence is not None and len(evidence) == 2


@pytest.mark.parametrize("duration", [0, 60])
def test_variation_baseline_survives_entity_rename(hass, entry, duration):
    async def scenario():
        hass.states.set("sensor.old", "10")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(
            {
                "name": "variation",
                "entity_ids": ["sensor.old"],
                "source": "value_variation",
                "operator": "above",
                "value": 5,
                "duration": duration,
                "condition_template": "{{ true }}",
            }
        )
        hass.states.set("sensor.old", "20")
        await manager.async_evaluate_entity("sensor.old")
        old_key = f"rule:{rule['id']}:sensor.old"
        before = (manager.records[old_key].detected_at, manager.records[old_key].status)
        hass.states.set("sensor.new", "20")
        manager._pending_entity_renames["sensor.old"] = "sensor.new"
        manager._apply_pending_entity_renames()
        await manager.async_evaluate_entity("sensor.new")
        record = manager.records[f"rule:{rule['id']}:sensor.new"]
        assert (record.detected_at, record.status) == before
        assert old_key not in manager.records
        assert not manager.history
        await manager.async_unload()

    run(scenario())


def test_reconciliation_visits_records_linearly(monkeypatch):
    """Count identity visits instead of depending on machine timing."""
    records = {}
    for i in range(300):
        key = f"unavailable:sensor.x{i}"
        records[key] = AlertRecord.pending(
            AlertDetails(
                id=key,
                type="unavailable",
                entity_id=f"sensor.x{i}",
                name="x",
                value="unavailable",
                condition="unavailable",
            ),
            60,
            datetime(2026, 9, 19, tzinfo=UTC),
        )
    visits = 0
    original = StartupReconciliationTransaction._record_entity_id

    def counted(self, record):
        nonlocal visits
        visits += 1
        return original(self, record)

    monkeypatch.setattr(StartupReconciliationTransaction, "_record_entity_id", counted)
    transaction = StartupReconciliationTransaction.capture(records, set(records))
    for entity in transaction.entity_ids:
        retained = transaction.records_for_entity(entity)
        assert len(retained) == 1
        live = transaction.live_alert_ids_for_entity(entity)
        assert live == set(retained)
        transaction.stage_unverified(entity, live)
    assert set(transaction.reconciled_original_records()) == set(records)
    assert visits <= len(records) * 3
