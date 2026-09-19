"""Clock, identity and reconciliation regressions found in the stable review."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import State
from test_transitions import edge, expire, run, setup

from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertDetails, AlertRecord, Rule
from custom_components.alert_manager.sequences import SequenceProgress
from custom_components.alert_manager.transactions import (
    StartupReconciliationTransaction,
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
