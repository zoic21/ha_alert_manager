"""Regression tests for the high-severity audit findings."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from homeassistant.core import Event, State

from custom_components.alert_manager.const import (
    DEFAULT_CONFIG,
    EVENT_ALERT_RESOLVED,
    EVENT_ALERT_STARTED,
)
from custom_components.alert_manager.models import AlertStatus
from custom_components.alert_manager.runtime_manager import AlertManager
from custom_components.alert_manager.yaml_io import dump_config_yaml


def _rule(**changes):
    rule = {
        "name": "High severity regression",
        "entity_ids": ["sensor.source"],
        "operator": "equals",
        "value": "on",
        "duration": 0,
        "source": "state",
    }
    rule.update(changes)
    return rule


def _events(hass, event_type):
    return [data for kind, data in hass.bus.fired if kind == event_type]


def test_active_occurrence_keeps_lifecycle_when_rule_delay_increases(
    hass, entry, set_now
):
    """An already active occurrence never goes back to pending on a delay edit."""

    async def scenario():
        start = datetime(2026, 8, 27, 12, tzinfo=UTC)
        set_now(start)
        hass.states.set("sensor.source", "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        created = await manager.async_create_rule(_rule())
        alert_id = f"rule:{created['id']}:sensor.source"
        await manager.async_acknowledge(alert_id, "Admin")
        active_since = manager.records[alert_id].active_since
        starts = len(_events(hass, EVENT_ALERT_STARTED))

        set_now(start + timedelta(seconds=10))
        await manager.async_update_rule(created["id"], {"duration": 3600})

        record = manager.records[alert_id]
        assert record.status is AlertStatus.ACTIVE
        assert record.active_since == active_since
        assert record.delay == 0
        assert record.acknowledged is True
        assert record.acknowledged_by == "Admin"
        assert len(_events(hass, EVENT_ALERT_STARTED)) == starts

        set_now(start + timedelta(seconds=20))
        hass.states.set("sensor.source", "off")
        await manager.async_evaluate_entity("sensor.source")
        history = next(event for event in manager.history if event.id == alert_id)
        assert history.pending_duration_seconds == 0
        assert history.active_at == active_since

    asyncio.run(scenario())


def test_failed_activation_save_rolls_back_and_emits_no_start(hass, entry, set_now):
    """A failed Store write cannot expose an activation that was not persisted."""

    async def scenario():
        start = datetime(2026, 8, 27, 12, tzinfo=UTC)
        set_now(start)
        hass.states.set("sensor.source", "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        created = await manager.async_create_rule(_rule(duration=30))
        alert_id = f"rule:{created['id']}:sensor.source"
        assert manager.records[alert_id].status is AlertStatus.PENDING
        starts = len(_events(hass, EVENT_ALERT_STARTED))

        async def fail_save(_config, _records):
            raise OSError("disk full")

        manager.storage.async_save = fail_save
        set_now(start + timedelta(seconds=31))
        with pytest.raises(OSError, match="disk full"):
            await manager.async_evaluate_entity("sensor.source")

        record = manager.records[alert_id]
        assert record.status is AlertStatus.PENDING
        assert record.active_since is None
        assert len(_events(hass, EVENT_ALERT_STARTED)) == starts

    asyncio.run(scenario())


def test_failed_resolution_save_rolls_back_and_emits_no_resolution(
    hass, entry, set_now
):
    """A failed Store write keeps the active occurrence and suppresses resolution."""

    async def scenario():
        start = datetime(2026, 8, 27, 12, tzinfo=UTC)
        set_now(start)
        hass.states.set("sensor.source", "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        created = await manager.async_create_rule(_rule())
        alert_id = f"rule:{created['id']}:sensor.source"
        resolutions = len(_events(hass, EVENT_ALERT_RESOLVED))

        async def fail_save(_config, _records):
            raise OSError("disk full")

        manager.storage.async_save = fail_save
        hass.states.set("sensor.source", "off")
        with pytest.raises(OSError, match="disk full"):
            await manager.async_evaluate_entity("sensor.source")

        assert manager.records[alert_id].status is AlertStatus.ACTIVE
        assert len(_events(hass, EVENT_ALERT_RESOLVED)) == resolutions
        assert not manager.history

    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["disable", "delete"])
def test_rule_removal_resolves_active_occurrence(hass, entry, set_now, operation):
    """Disabling or deleting a rule closes active instances with normal lifecycle."""

    async def scenario():
        start = datetime(2026, 8, 27, 12, tzinfo=UTC)
        set_now(start)
        hass.states.set("sensor.source", "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        created = await manager.async_create_rule(_rule())
        alert_id = f"rule:{created['id']}:sensor.source"
        before = len(_events(hass, EVENT_ALERT_RESOLVED))
        set_now(start + timedelta(seconds=15))

        if operation == "disable":
            await manager.async_update_rule(created["id"], {"enabled": False})
        else:
            await manager.async_delete_rule(created["id"])

        assert alert_id not in manager.records
        assert len(_events(hass, EVENT_ALERT_RESOLVED)) == before + 1
        matching_history = [event for event in manager.history if event.id == alert_id]
        assert len(matching_history) == 1
        assert matching_history[0].resolved_at == start + timedelta(seconds=15)

    asyncio.run(scenario())


def test_import_emits_durable_lifecycle_delta_while_monitoring_stays_on(
    hass, entry, set_now
):
    """A full import emits resolve/start events even without toggling monitoring."""

    async def scenario():
        start = datetime(2026, 8, 27, 12, tzinfo=UTC)
        set_now(start)
        hass.states.set("sensor.source", "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        created = await manager.async_create_rule(_rule(name="Old rule"))
        old_alert_id = f"rule:{created['id']}:sensor.source"
        starts = len(_events(hass, EVENT_ALERT_STARTED))
        resolutions = len(_events(hass, EVENT_ALERT_RESOLVED))

        imported = deepcopy(DEFAULT_CONFIG)
        imported["rules"] = [
            {
                "id": "export-only-id",
                **_rule(name="Imported rule"),
            }
        ]
        await manager.async_import_config(dump_config_yaml(imported))

        new_rule_id = manager.config["rules"][0]["id"]
        new_alert_id = f"rule:{new_rule_id}:sensor.source"
        assert new_rule_id != created["id"]
        assert old_alert_id not in manager.records
        assert manager.records[new_alert_id].status is AlertStatus.ACTIVE
        assert len(_events(hass, EVENT_ALERT_RESOLVED)) == resolutions + 1
        assert len(_events(hass, EVENT_ALERT_STARTED)) == starts + 1
        assert any(event.id == old_alert_id for event in manager.history)

    asyncio.run(scenario())


def test_entity_rename_preserves_active_occurrence_and_acknowledgement(
    hass, entry, set_now
):
    """Registry renames migrate rule and record identity without lifecycle restart."""

    async def scenario():
        start = datetime(2026, 8, 27, 12, tzinfo=UTC)
        set_now(start)
        hass.states.set("sensor.old", "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        created = await manager.async_create_rule(_rule(entity_ids=["sensor.old"]))
        old_alert_id = f"rule:{created['id']}:sensor.old"
        await manager.async_acknowledge(old_alert_id, "Admin")
        old_record = deepcopy(manager.records[old_alert_id])
        starts = len(_events(hass, EVENT_ALERT_STARTED))
        resolutions = len(_events(hass, EVENT_ALERT_RESOLVED))

        renamed_state = hass.states.data.pop("sensor.old")
        renamed_state.entity_id = "sensor.new"
        hass.states.data["sensor.new"] = renamed_state
        manager._registry_changed(
            Event(
                {
                    "action": "update",
                    "entity_id": "sensor.new",
                    "old_entity_id": "sensor.old",
                    "changes": {"entity_id": "sensor.new"},
                }
            )
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        new_alert_id = f"rule:{created['id']}:sensor.new"
        assert manager.config["rules"][0]["entity_ids"] == ["sensor.new"]
        assert old_alert_id not in manager.records
        record = manager.records[new_alert_id]
        assert record.status is AlertStatus.ACTIVE
        assert record.detected_at == old_record.detected_at
        assert record.active_since == old_record.active_since
        assert record.acknowledged is True
        assert record.acknowledged_by == "Admin"
        assert len(_events(hass, EVENT_ALERT_STARTED)) == starts
        assert len(_events(hass, EVENT_ALERT_RESOLVED)) == resolutions

    asyncio.run(scenario())


def test_entity_rename_migrates_config_even_while_monitoring_disabled(
    hass, entry, set_now
):
    """Rules, delays and exclusions follow a registry rename while suspended."""

    async def scenario():
        set_now(datetime(2026, 8, 27, 12, tzinfo=UTC))
        hass.states.set("sensor.old", "off")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        await manager.async_create_rule(_rule(entity_ids=["sensor.old"]))
        await manager.async_update_config(
            {
                "entity_delays": {"sensor.old": 123},
                "excluded_entities": ["sensor.old"],
            }
        )
        await manager.async_set_monitoring(False)

        renamed_state = hass.states.data.pop("sensor.old")
        renamed_state.entity_id = "sensor.new"
        hass.states.data["sensor.new"] = renamed_state
        manager._registry_changed(
            Event(
                {
                    "action": "update",
                    "entity_id": "sensor.new",
                    "old_entity_id": "sensor.old",
                    "changes": {"entity_id": "sensor.new"},
                }
            )
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert manager.config["rules"][0]["entity_ids"] == ["sensor.new"]
        assert manager.config["entity_delays"] == {"sensor.new": 123}
        assert manager.config["excluded_entities"] == ["sensor.new"]
        stored = hass.stores["alert_manager"]["config"]
        assert stored["entity_delays"] == {"sensor.new": 123}
        assert stored["excluded_entities"] == ["sensor.new"]

    asyncio.run(scenario())


def _render_info(**changes):
    values = {
        "entities": frozenset(),
        "all_states": False,
        "all_states_lifecycle": False,
        "domains": frozenset(),
        "domains_lifecycle": frozenset(),
        "has_time": False,
        "rate_limit": None,
        "filter": lambda _entity_id: False,
        "filter_lifecycle": lambda _entity_id: False,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_jinja_time_dependency_refreshes_at_next_minute(hass, entry, set_now):
    """RenderInfo.has_time creates the same minute-level refresh used by HA."""
    start = datetime(2026, 8, 27, 12, 34, 17, tzinfo=UTC)
    set_now(start)
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    dependency_key = ("condition", "rule-id", "sensor.source")
    manager._index_render_info(
        "condition",
        ("rule-id", "sensor.source"),
        _render_info(has_time=True),
    )

    assert dependency_key in manager._template_time_dependencies
    timer = hass.timers[-1]
    assert timer["point"] == datetime(2026, 8, 27, 12, 35, tzinfo=UTC)
    queued = []
    manager._queue_entity_evaluations = (
        lambda entity_ids, restoring=False: queued.extend(entity_ids)
    )
    timer["action"](timer["point"])
    assert queued == ["sensor.source"]


def test_jinja_lifecycle_dependency_uses_filter_lifecycle(hass, entry):
    """Entity additions/removals trigger templates that watch domain lifecycle."""
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    manager._index_render_info(
        "condition",
        ("rule-id", "sensor.source"),
        _render_info(
            domains_lifecycle=frozenset({"sensor"}),
            filter_lifecycle=lambda entity_id: entity_id.startswith("sensor."),
        ),
    )
    queued = []
    manager._queue_entity_evaluations = (
        lambda entity_ids, restoring=False: queued.extend(entity_ids)
    )

    manager._state_changed(
        Event(
            {
                "entity_id": "sensor.new",
                "old_state": None,
                "new_state": State("sensor.new", "on"),
            }
        )
    )

    assert "sensor.source" in queued


def test_dynamic_jinja_rate_limit_defers_broad_re_evaluation(hass, entry, set_now):
    """Broad all-state templates are coalesced using RenderInfo.rate_limit."""
    start = datetime(2026, 8, 27, 12, tzinfo=UTC)
    set_now(start)
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    info = _render_info(
        all_states=True,
        rate_limit=60,
        filter=lambda _entity_id: True,
    )
    dependency_key = ("condition", "rule-id", "sensor.source")
    manager._index_render_info("condition", ("rule-id", "sensor.source"), info)
    queued = []
    manager._queue_entity_evaluations = (
        lambda entity_ids, restoring=False: queued.extend(entity_ids)
    )

    assert (
        manager._dynamic_dependency_matches(
            dependency_key,
            info,
            "binary_sensor.changed",
            lifecycle=False,
        )
        is False
    )
    assert queued == []
    assert dependency_key in manager._template_rate_limit_timers
    timer = hass.timers[-1]
    assert timer["point"] == start + timedelta(seconds=60)
    timer["action"](timer["point"])
    assert queued == ["sensor.source"]


def test_concurrent_mutations_are_serialized_without_lost_config_updates(hass, entry):
    """Two simultaneous writes never overlap or restore over each other."""

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        original_save = manager.storage.async_save
        in_flight = 0
        max_in_flight = 0

        async def slow_save(config, records):
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            try:
                await asyncio.sleep(0.01)
                await original_save(config, records)
            finally:
                in_flight -= 1

        manager.storage.async_save = slow_save
        await asyncio.gather(
            manager.async_update_config({"global_delay": 120}),
            manager.async_update_config({"pending_display_delay": 7}),
        )

        assert max_in_flight == 1
        assert manager.config["global_delay"] == 120
        assert manager.config["pending_display_delay"] == 7
        stored = hass.stores["alert_manager"]["config"]
        assert stored["global_delay"] == 120
        assert stored["pending_display_delay"] == 7

    asyncio.run(scenario())
