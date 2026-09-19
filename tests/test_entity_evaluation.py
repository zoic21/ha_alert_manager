"""Entity evaluation preserves persistence and resolution policies across helpers."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from custom_components.alert_manager.const import (
    EVENT_ALERT_RESOLVED,
    EVENT_ALERT_STARTED,
)
from custom_components.alert_manager.manager import AlertManager


@pytest.mark.parametrize("live_first", [False, True])
def test_immediate_candidate_is_not_delayed_by_live_message_update(
    hass, entry, live_first
):
    """Candidate order must not lose an earlier immediate-save requirement."""

    async def scenario():
        hass.states.set("sensor.source", "5")
        hass.states.set("sensor.context", "warm")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        live = {
            "name": "Live",
            "entity_ids": ["sensor.source"],
            "operator": "above",
            "value": 0,
            "duration": 0,
            "message": "{{ states('sensor.context') }}",
            "update_message_when_active": True,
        }
        immediate = {**live, "name": "Immediate", "value": 10}
        keys = {}
        for rule in [live, immediate] if live_first else [immediate, live]:
            created = await manager.async_create_rule(rule)
            keys[rule["name"]] = f"rule:{created['id']}:sensor.source"
        saves = hass.store_save_count
        hass.bus.fired.clear()
        hass.states.set("sensor.source", "15")
        hass.states.set("sensor.context", "cold")
        occurrences = []
        assert await manager.async_evaluate_entity(
            "sensor.source", _new_occurrences=occurrences
        )
        assert hass.store_save_count == saves + 1
        assert len(occurrences) == 1
        assert occurrences[0].source.id == keys["Immediate"]
        assert [
            data["id"] for event, data in hass.bus.fired if event == EVENT_ALERT_STARTED
        ] == [keys["Immediate"]]
        alerts = {item["id"]: item for item in manager._last_public_snapshot["alerts"]}
        assert len(alerts) == 2
        assert alerts[keys["Live"]]["message"] == "cold"
        assert manager.records[keys["Live"]].details.value == "5"
        assert not manager._live_message_flush_pending

    asyncio.run(scenario())


@pytest.mark.parametrize("pending", [False, True])
@pytest.mark.parametrize("emit_events", [False, True])
@pytest.mark.parametrize("archive_resolutions", [False, True])
def test_missing_candidate_preserves_resolution_policies(
    hass, entry, monkeypatch, pending, emit_events, archive_resolutions
):
    """Removing pending/active records keeps archival and event flags independent."""

    async def scenario():
        hass.states.set("sensor.source", "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(
            {
                "name": "Source",
                "entity_ids": ["sensor.source"],
                "operator": "equals",
                "value": "on",
                "duration": 60 if pending else 0,
            }
        )
        key = f"rule:{rule['id']}:sensor.source"
        save_state = AsyncMock(wraps=manager._async_save_state)
        monkeypatch.setattr(manager, "_async_save_state", save_state)
        saves = hass.store_save_count
        hass.bus.fired.clear()
        hass.states.set("sensor.source", "off")
        assert await manager.async_evaluate_entity(
            "sensor.source",
            emit_events=emit_events,
            archive_resolutions=archive_resolutions,
        )
        assert key not in manager.records
        assert key not in manager._timers
        assert manager._last_public_snapshot["active_count"] == 0
        assert manager._last_public_snapshot["pending_count"] == 0
        save_state.assert_awaited_once()
        # Fresh pending records were never durable; Store suppresses that write.
        if pending:
            assert hass.store_save_count == saves
        else:
            assert hass.store_save_count > saves
        assert len(manager.history) == int(not pending and archive_resolutions)
        assert [
            data["id"]
            for event, data in hass.bus.fired
            if event == EVENT_ALERT_RESOLVED
        ] == ([key] if not pending and emit_events else [])

    asyncio.run(scenario())
