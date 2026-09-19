"""Publication invalidation preserves live data without rescanning idle alerts."""

import asyncio
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.core import Event
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util
from pack_test_helpers import automatic_settings
from test_rule_labels import payload
from test_transitions import edge, expire, run, setup

from custom_components.alert_manager.const import SIGNAL_ALERTS_UPDATED
from custom_components.alert_manager.manager import AlertManager


def test_unchanged_publication_does_not_walk_alerts_or_templates(
    hass, entry, monkeypatch
):
    """A large unchanged fleet does no snapshot work, even on full reevaluation."""
    for index in range(600):
        hass.states.set(f"sensor.source_{index}", "unavailable")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    run(manager.async_update_config(automatic_settings(delay=0)))
    assert manager._last_public_snapshot["active_count"] == 600
    build = Mock(wraps=manager._build_public_snapshot)
    cleanup = Mock(wraps=manager._remove_dependency_key)
    monkeypatch.setattr(manager, "_build_public_snapshot", build)
    monkeypatch.setattr(manager, "_remove_dependency_key", cleanup)
    for _ in range(10):
        manager._publish_if_changed()
    run(manager.async_evaluate_entity("sensor.source_0"))
    run(manager.async_evaluate_all())
    build.assert_not_called()
    cleanup.assert_not_called()

    # A forced refresh is still supported and publication has no template effects.
    manager._publish_if_changed(force=True)
    assert build.call_count == 1
    cleanup.assert_not_called()
    hass.states.set("sensor.source_0", "on")
    run(manager.async_evaluate_entity("sensor.source_0"))
    assert build.call_count == 2
    assert manager._last_public_snapshot["active_count"] == 599


@pytest.mark.parametrize("source", ["value", "transition"])
@pytest.mark.parametrize("live", [False, True])
def test_message_dependencies_follow_lifecycle_without_publication(
    hass, entry, set_now, monkeypatch, source, live
):
    """Even silent activation and resolution maintain all dependency indexes."""
    original_render = Template.async_render_to_info

    def render_with_time(self, variables=None):
        # The lightweight HA stub does not detect now(); emulate HA's RenderInfo.
        info = original_render(self, variables)
        info.has_time = True
        return info

    monkeypatch.setattr(Template, "async_render_to_info", render_with_time)
    hass.states.set("sensor.context", "warm")
    manager, key, rule = setup(
        hass,
        entry,
        source=source,
        operator="equals",
        value="B",
        duration=60,
        message="{{ states('sensor.context') }} {{ now() }}",
        update_message_when_active=live,
    )
    edge(manager, hass, "B")
    pair = (rule["id"], "sensor.edge")
    dependency = ("message", *pair)
    assert pair in manager._rule_message_render_info
    assert dependency in manager._template_time_dependencies
    set_now(manager.records[key].due_at)
    run(manager.async_evaluate_entity("sensor.edge", publish=False, emit_events=False))
    assert (pair in manager._rule_message_render_info) is live
    assert (dependency in manager._template_entities_by_key) is live
    assert (dependency in manager._template_time_dependencies) is live
    if live:
        run(
            manager.async_update_rule(rule["id"], {"update_message_when_active": False})
        )
        assert pair not in manager._rule_message_render_info
        run(manager.async_update_rule(rule["id"], {"update_message_when_active": True}))
        # Transitions render live messages on evaluation, as do ordinary rules.
        assert pair in manager._rule_message_render_info
    run(manager.async_delete_rule(rule["id"]))
    assert pair not in manager._rule_message_render_info
    assert dependency not in manager._template_entities_by_key
    assert dependency not in manager._template_time_dependencies
    assert manager._template_time_timer is None


def test_acknowledgement_notifications_and_labels_refresh_published_data(
    hass, entry, registry_entry
):
    async def scenario():
        hass.states.set("sensor.test", "on")
        entity = registry_entry(hass, "sensor.test")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(payload())
        key = f"rule:{rule['id']}:sensor.test"
        await manager.async_set_acknowledgements([key], True, "admin", duration=120)
        assert manager._last_public_snapshot["acknowledge_count"] == 1
        await manager.async_set_acknowledgements([key], False, "admin")
        assert manager._last_public_snapshot["active_count"] == 1
        assert manager._last_public_snapshot == manager.public_snapshot()

        await manager.async_update_rule(rule["id"], {"label_ids": ["rule_label"]})
        assert manager._last_public_snapshot["alerts"][0]["labels"] == ["rule_label"]
        entity.labels.add("entity_label")
        manager._registry_changed(
            Event({"action": "update", "entity_id": "sensor.test"})
        )
        for _ in range(5):
            await asyncio.sleep(0)
        assert manager._last_public_snapshot["alerts"][0]["labels"] == [
            "entity_label",
            "rule_label",
        ]

        record = manager.records[key]
        await manager._async_record_notification(
            [SimpleNamespace(alert_id=key, detected_at=record.detected_at.isoformat())],
            {"id": "profile", "name": "Phone"},
            "started",
            dt_util.now(),
        )
        await manager._async_flush_live_messages()
        published = manager._last_public_snapshot["alerts"][0]
        assert published["notifications"]["alert"]["count"] == 1
        assert manager._last_public_snapshot == manager.public_snapshot()

    run(scenario())


def test_failed_edit_does_not_publish_speculative_data(hass, entry, monkeypatch):
    hass.states.set("sensor.test", "on")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    rule = run(manager.async_create_rule(payload()))
    previous = deepcopy(manager._last_public_snapshot)
    updates = Mock()
    hass.dispatchers[SIGNAL_ALERTS_UPDATED].append(updates)
    monkeypatch.setattr(
        manager, "_async_save_state", AsyncMock(side_effect=OSError("disk"))
    )
    with pytest.raises(OSError):
        run(manager.async_update_rule(rule["id"], {"label_ids": ["speculative"]}))
    manager._publish_if_changed()
    assert manager._last_public_snapshot == previous
    updates.assert_not_called()
    build = Mock(wraps=manager._build_public_snapshot)
    monkeypatch.setattr(manager, "_build_public_snapshot", build)
    manager._publish_if_changed()
    build.assert_not_called()


def test_sequence_progress_and_repeated_transition_refresh_publication(
    hass, entry, set_now
):
    manager, key, _rule = setup(
        hass,
        entry,
        source="value_sequence",
        steps=[
            {"operator": "equals", "value": "1", "duration": 0},
            {"operator": "equals", "value": "2", "duration": 0},
            {"operator": "equals", "value": "3", "duration": 0},
        ],
    )
    for state in ("1", "2", "3"):
        edge(manager, hass, state)
        assert manager._last_public_snapshot == manager.public_snapshot()
    assert manager._last_public_snapshot["active_count"] == 1
    previous = deepcopy(manager._last_public_snapshot)
    set_now(dt_util.now() + timedelta(seconds=10))
    for state in ("1", "2", "3"):
        edge(manager, hass, state)
    assert manager._last_public_snapshot != previous
    assert manager._last_public_snapshot == manager.public_snapshot()
    set_now(manager.records[key].expires_at)
    expire(manager, key)
    assert manager._last_public_snapshot["active_count"] == 0


def test_live_message_flush_refreshes_publication(hass, entry):
    async def scenario():
        hass.states.set("sensor.test", "on")
        hass.states.set("sensor.context", "warm")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        await manager.async_create_rule(
            payload(
                message="{{ states('sensor.context') }}",
                update_message_when_active=True,
            )
        )
        hass.states.set("sensor.context", "cold")
        await manager.async_evaluate_entity("sensor.test")
        assert manager._last_public_snapshot["alerts"][0]["message"] == "warm"
        await manager._async_flush_live_messages()
        assert manager._last_public_snapshot["alerts"][0]["message"] == "cold"

    run(scenario())


def test_visibility_deadline_invalidates_before_timer_dispatch(
    hass, entry, set_now, monkeypatch
):
    """A concurrent refresh must reveal pending rows even if HA's timer is queued."""
    hass.states.set("sensor.test", "on")
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    rule = run(manager.async_create_rule(payload(duration=60)))
    record = manager.records[f"rule:{rule['id']}:sensor.test"]
    assert manager._last_public_snapshot["pending_count"] == 0
    build = Mock(wraps=manager._build_public_snapshot)
    monkeypatch.setattr(manager, "_build_public_snapshot", build)
    set_now(record.visible_at - timedelta(seconds=1))
    manager._publish_if_changed()
    build.assert_not_called()
    set_now(record.visible_at)
    manager._publish_if_changed()
    assert manager._last_public_snapshot["pending_count"] == 1
    assert build.call_count == 1
    manager._publish_if_changed()
    assert build.call_count == 1
