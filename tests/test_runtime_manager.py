"""Loop-safety and event-coalescing tests for the runtime manager."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from homeassistant.const import ATTR_DEVICE_CLASS
from homeassistant.core import Event, State

from custom_components.alert_manager.const import EVENT_ALERT_RESOLVED
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertStatus
from custom_components.alert_manager.sensor import AlertManagerSensor


def run(coroutine):
    return asyncio.run(coroutine)


def make_manager(hass, entry):
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    return manager


def _rule(**changes):
    rule = {
        "name": "Runtime guard",
        "entity_ids": ["sensor.source"],
        "operator": "equals",
        "value": "on",
        "duration": 900,
        "source": "state",
    }
    rule.update(changes)
    return rule


def _state_event(entity_id, old_state, new_state):
    return Event(
        {
            "entity_id": entity_id,
            "old_state": old_state,
            "new_state": new_state,
        }
    )


def test_jinja_condition_rejects_alert_manager_entity(hass, entry):
    """A self-referential condition is rejected before configuration changes."""
    hass.states.set("sensor.source", "on")
    manager = make_manager(hass, entry)

    with pytest.raises(ValueError, match="cannot reference Alert Manager entities"):
        run(
            manager.async_create_rule(
                _rule(
                    condition_template=(
                        "{{ states('sensor.alert_manager_main_active') == '0' }}"
                    )
                )
            )
        )

    assert manager.config["rules"] == []


def test_jinja_message_rejects_renamed_alert_manager_entity(
    hass, entry, registry_entry
):
    """Registry-renamed integration entities are rejected in message Jinja too."""
    hass.states.set("sensor.source", "on")
    registry_entry(hass, "sensor.renamed_alert_count", platform="alert_manager")
    manager = make_manager(hass, entry)

    with pytest.raises(ValueError, match="sensor.renamed_alert_count"):
        run(
            manager.async_create_rule(
                _rule(message="Count: {{ states('sensor.renamed_alert_count') }}")
            )
        )


def test_plain_message_can_name_alert_manager_entity(hass, entry):
    """A plain message is not Jinja and therefore is not falsely rejected."""
    hass.states.set("sensor.source", "on")
    manager = make_manager(hass, entry)

    created = run(
        manager.async_create_rule(
            _rule(message="See sensor.alert_manager_main_active for details")
        )
    )

    assert created["message"] == "See sensor.alert_manager_main_active for details"


def test_explicit_message_edit_refreshes_active_alert_once(hass, entry):
    """Editing a rule refreshes its active message without tracking it afterward."""

    async def scenario():
        hass.states.set("sensor.source", "on")
        hass.states.set("binary_sensor.cloudflared_running", "off")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        created = await manager.async_create_rule(_rule(duration=0, message=None))
        alert_id = f"rule:{created['id']}:sensor.source"
        assert manager.records[alert_id].details.message is None

        await manager.async_update_rule(
            created["id"],
            {"message": ("Status {{ states('binary_sensor.cloudflared_running') }}")},
        )

        record = manager.records[alert_id]
        assert record.status is AlertStatus.ACTIVE
        assert record.details.message == "Status off"
        assert record.details.condition == "Status off"
        assert "binary_sensor.cloudflared_running" not in manager._template_dependents

        hass.states.set("binary_sensor.cloudflared_running", "on")
        manager._state_changed(
            Event({"entity_id": "binary_sensor.cloudflared_running"})
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert manager.records[alert_id].details.message == "Status off"

    asyncio.run(scenario())


def test_legacy_self_referential_rule_is_disabled(hass, entry):
    """Unsafe rules persisted by older versions are retained but disabled."""
    hass.states.set("sensor.source", "on")
    manager = make_manager(hass, entry)
    created = run(manager.async_create_rule(_rule()))
    manager.config["rules"][0]["condition_template"] = (
        "{{ states('sensor.alert_manager_main_pending') }}"
    )
    manager.config["rules"][0]["enabled"] = True

    assert manager._remove_own_rule_sources() is True
    assert manager.config["rules"][0]["id"] == created["id"]
    assert manager.config["rules"][0]["enabled"] is False


def test_own_state_change_never_schedules_evaluation(hass, entry):
    """Alert Manager publications cannot feed back into the detection engine."""
    manager = make_manager(hass, entry)
    before = list(entry.created_task_names)

    manager._state_changed(Event({"entity_id": "sensor.alert_manager_main_active"}))

    assert entry.created_task_names == before


def test_sensors_reuse_last_published_snapshot(hass, entry, monkeypatch):
    """Aggregate sensors consume the manager snapshot without rebuilding it."""
    manager = make_manager(hass, entry)
    calls = 0
    original = manager.public_snapshot

    def count_snapshot():
        nonlocal calls
        calls += 1
        return original()

    monkeypatch.setattr(manager, "public_snapshot", count_snapshot)
    sensor = AlertManagerSensor(
        manager,
        "main_active",
        "alert_manager_main_active",
        "mdi:alert-circle",
        "active_count",
        "alerts",
        "alerts",
    )
    snapshot = manager._last_public_snapshot
    sensor._last_written_partition = (
        manager.monitoring_enabled,
        snapshot["active_count"],
        snapshot["alerts"],
    )
    sensor._async_manager_updated()

    assert calls == 0


def test_ordinary_state_change_skips_unavailable_only_evaluation(hass, entry):
    """Normal value churn is ignored when only unavailable could match it."""

    async def scenario():
        hass.states.set("sensor.noisy", "1")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        old_state = hass.states.get("sensor.noisy")
        before = list(entry.created_task_names)

        hass.states.set("sensor.noisy", "2")
        new_state = hass.states.get("sensor.noisy")
        manager._state_changed(_state_event("sensor.noisy", old_state, new_state))

        assert entry.created_task_names == before
        assert manager._evaluation_flush_scheduled is False

    asyncio.run(scenario())


def test_unavailable_transition_remains_evaluated(hass, entry):
    """Entering unavailable still opens the automatic alert after filtering."""

    async def scenario():
        hass.states.set("sensor.noisy", "1")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        old_state = hass.states.get("sensor.noisy")

        hass.states.set("sensor.noisy", "unavailable")
        new_state = hass.states.get("sensor.noisy")
        manager._state_changed(_state_event("sensor.noisy", old_state, new_state))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert "unavailable:sensor.noisy" in manager.records

    asyncio.run(scenario())


def test_battery_pack_transition_remains_evaluated(hass, entry):
    """Relevant automatic pack sources are not dropped by the early filter."""

    async def scenario():
        attributes = {ATTR_DEVICE_CLASS: "battery"}
        hass.states.set("sensor.battery", "50", attributes)
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        old_state = hass.states.get("sensor.battery")

        hass.states.set("sensor.battery", "10", attributes)
        new_state = hass.states.get("sensor.battery")
        manager._state_changed(_state_event("sensor.battery", old_state, new_state))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert "battery:sensor.battery" in manager.records

    asyncio.run(scenario())


def test_new_entity_lifecycle_updates_automatic_tracking(hass, entry):
    """Entity creation remains relevant so tracked_count cannot become stale."""

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        before = manager._tracked_count()

        hass.states.set("sensor.new_source", "ok")
        new_state = hass.states.get("sensor.new_source")
        manager._state_changed(_state_event("sensor.new_source", None, new_state))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert manager._tracked_count() == before + 1
        assert manager._last_public_snapshot["tracked_count"] == before + 1

    asyncio.run(scenario())


def test_noop_jinja_batch_skips_publication(hass, entry, monkeypatch):
    """A dependency re-evaluation with no output change does not build a snapshot."""

    async def scenario():
        hass.states.set("sensor.source", "on")
        hass.states.set("binary_sensor.guard", "off")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        await manager.async_create_rule(
            _rule(condition_template="{{ is_state('binary_sensor.guard', 'on') }}")
        )
        publish_calls = 0

        def count_publish(*, force=False):
            nonlocal publish_calls
            publish_calls += 1

        monkeypatch.setattr(manager, "_publish_if_changed", count_publish)
        old_state = hass.states.get("binary_sensor.guard")
        hass.states.set("binary_sensor.guard", "off")
        new_state = hass.states.get("binary_sensor.guard")
        manager._state_changed(
            _state_event("binary_sensor.guard", old_state, new_state)
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert publish_calls == 0

    asyncio.run(scenario())


def test_pending_visibility_timer_still_publishes_without_store_change(hass, entry):
    """Presentation-only timers publish even when the record itself is unchanged."""

    async def scenario():
        hass.states.set("sensor.source", "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        created = await manager.async_create_rule(_rule())
        alert_id = f"rule:{created['id']}:sensor.source"
        record = manager.records[alert_id]
        assert manager._last_public_snapshot["pending_count"] == 0
        before_saves = hass.store_save_count

        record.visible_at = record.detected_at
        manager._timer_due(alert_id)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert hass.store_save_count == before_saves
        assert manager._last_public_snapshot["pending_count"] == 1

    asyncio.run(scenario())


def test_jinja_dependencies_are_reverse_indexed_and_batched(hass, entry):
    """One dependency event evaluates all sources with a single Store write."""

    async def scenario():
        hass.states.set("sensor.one", "on")
        hass.states.set("sensor.two", "on")
        hass.states.set("binary_sensor.guard", "off")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        await manager.async_create_rule(
            _rule(
                entity_ids=["sensor.one", "sensor.two"],
                condition_template="{{ is_state('binary_sensor.guard', 'on') }}",
            )
        )

        dependents = manager._template_dependents["binary_sensor.guard"]
        assert {dependency[2] for dependency in dependents} == {
            "sensor.one",
            "sensor.two",
        }
        assert manager._template_dynamic_infos == {}

        before_saves = hass.store_save_count
        hass.states.set("binary_sensor.guard", "on")
        manager._state_changed(Event({"entity_id": "binary_sensor.guard"}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        rule_id = manager.config["rules"][0]["id"]
        assert f"rule:{rule_id}:sensor.one" in manager.records
        assert f"rule:{rule_id}:sensor.two" in manager.records
        assert hass.store_save_count == before_saves + 1
        assert entry.created_task_names[-1] == "alert_manager state-change batch"

    asyncio.run(scenario())


def test_registry_changes_are_coalesced(hass, entry):
    """Multiple registry events before the worker runs schedule one full scan."""

    async def scenario():
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        before = len(entry.created_task_names)

        manager._registry_changed(Event())
        manager._registry_changed(Event())
        manager._registry_changed(Event())
        assert len(entry.created_task_names) == before + 1

        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert manager._registry_evaluation_scheduled is False

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
    """A now()/utcnow() dependency refreshes on the next minute boundary."""
    start = datetime(2026, 8, 27, 12, 34, 17, tzinfo=UTC)
    set_now(start)
    manager = make_manager(hass, entry)
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


def test_jinja_lifecycle_uses_the_lifecycle_filter_only(hass, entry):
    """Entity creation follows RenderInfo.filter_lifecycle, like Home Assistant."""
    manager = make_manager(hass, entry)
    manager._index_render_info(
        "condition",
        ("watched-domain", "sensor.source"),
        _render_info(
            domains_lifecycle=frozenset({"sensor"}),
            filter_lifecycle=lambda entity_id: entity_id.startswith("sensor."),
        ),
    )
    manager._index_render_info(
        "condition",
        ("states-only", "sensor.other"),
        _render_info(
            all_states=True,
            filter=lambda _entity_id: True,
            filter_lifecycle=lambda _entity_id: False,
        ),
    )
    queued = []
    manager._queue_entity_evaluations = (
        lambda entity_ids, restoring=False: queued.extend(entity_ids)
    )

    manager._state_changed(_state_event("sensor.new", None, State("sensor.new", "on")))

    assert "sensor.source" in queued
    assert "sensor.other" not in queued


def test_dynamic_jinja_rate_limit_queues_one_trailing_refresh(hass, entry, set_now):
    """Broad templates coalesce state churn until RenderInfo's limit expires."""
    start = datetime(2026, 8, 27, 12, tzinfo=UTC)
    set_now(start)
    manager = make_manager(hass, entry)
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

    assert not manager._dynamic_dependency_matches(
        dependency_key,
        info,
        "binary_sensor.changed",
        lifecycle=False,
    )
    assert dependency_key in manager._template_rate_limit_timers
    first_timer = hass.timers[-1]
    assert first_timer["point"] == start + timedelta(seconds=60)

    manager._dynamic_dependency_matches(
        dependency_key,
        info,
        "binary_sensor.changed_again",
        lifecycle=False,
    )
    assert len(manager._template_rate_limit_timers) == 1
    first_timer["action"](first_timer["point"])
    assert queued == ["sensor.source"]


def test_entity_rename_migrates_config_and_active_occurrence(hass, entry, set_now):
    """A registry rename preserves references and the current alert lifecycle."""

    async def scenario():
        start = datetime(2026, 8, 27, 12, tzinfo=UTC)
        set_now(start)
        hass.states.set("sensor.old", "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        created = await manager.async_create_rule(
            _rule(entity_ids=["sensor.old"], duration=0)
        )
        old_alert_id = f"rule:{created['id']}:sensor.old"
        await manager.async_acknowledge(old_alert_id, "Admin")
        await manager.async_update_config(
            {
                "entity_delays": {"sensor.old": 123},
                "excluded_entities": ["sensor.old"],
            }
        )
        original = manager.records[old_alert_id]
        detected_at = original.detected_at
        active_since = original.active_since

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
        assert manager.config["entity_delays"] == {"sensor.new": 123}
        assert manager.config["excluded_entities"] == ["sensor.new"]
        assert old_alert_id not in manager.records
        record = manager.records[new_alert_id]
        assert record.detected_at == detected_at
        assert record.active_since == active_since
        assert record.acknowledged_by == "Admin"

    asyncio.run(scenario())


def test_runtime_keeps_delay_recheck_semantics(hass, entry, set_now):
    """Changing a duration still rechecks an already active occurrence."""

    async def scenario():
        start = datetime(2026, 8, 27, 12, tzinfo=UTC)
        set_now(start)
        hass.states.set("sensor.source", "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        created = await manager.async_create_rule(_rule(duration=0))

        await manager.async_update_rule(created["id"], {"duration": 60})

        record = manager.records[f"rule:{created['id']}:sensor.source"]
        assert record.status is AlertStatus.PENDING
        assert record.due_at == start + timedelta(seconds=60)

    asyncio.run(scenario())


def test_runtime_rule_cleanup_remains_silent(hass, entry):
    """Disabling a rule is configuration cleanup, not condition recovery."""

    async def scenario():
        hass.states.set("sensor.source", "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        created = await manager.async_create_rule(_rule(duration=0))
        hass.bus.fired.clear()

        await manager.async_update_rule(created["id"], {"enabled": False})

        assert not [
            event for event, _data in hass.bus.fired if event == EVENT_ALERT_RESOLVED
        ]

    asyncio.run(scenario())
