"""Loop-safety and event-coalescing tests for the runtime manager."""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.const import ATTR_DEVICE_CLASS
from homeassistant.core import Event

from custom_components.alert_manager.models import AlertStatus
from custom_components.alert_manager.runtime_manager import AlertManager
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
