"""Update availability uses ordinary pack validation, events and lifecycle."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.core import Event

from custom_components.alert_manager.const import EVENT_ALERT_RESOLVED
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertStatus
from custom_components.alert_manager.packs.base import PackNeutral
from custom_components.alert_manager.packs.update_available import PACK
from custom_components.alert_manager.validation import validate_config
from custom_components.alert_manager.yaml_io import dump_config_yaml, parse_config_yaml

ENTITY = "update.core"
ALERT = f"update_available:{ENTITY}"


@pytest.mark.parametrize("state", ["unknown", "unavailable"])
def test_transient_states_are_neutral(hass, state):
    assert isinstance(
        PACK.evaluate(hass, hass.states.set(ENTITY, state), {}), PackNeutral
    )


@pytest.mark.parametrize(
    "settings",
    [
        {"entity_overrides": {ENTITY: {"enabled": True}}},
        {"entity_overrides": {ENTITY: {}}},
        {"entity_overrides": {ENTITY: {"enabled": False, "delay": 1}}},
        {"entity_overrides": {ENTITY: {"enabled": False, "label_ids": []}}},
        {"entity_overrides": {"sensor.test": {"enabled": False}}},
        {"device_overrides": {}},
        {"level": "information"},
    ],
)
def test_only_update_exclusions_are_accepted(settings):
    with pytest.raises(ValueError):
        validate_config({"automatic": {PACK.id: settings}})


def test_exclusions_and_pack_labels_round_trip():
    config = validate_config(
        {
            "automatic": {
                PACK.id: {
                    "entity_overrides": {ENTITY: {"enabled": False}},
                    "label_ids": ["maintenance"],
                }
            }
        }
    )
    assert config["automatic"][PACK.id]["delay"] == 0
    assert parse_config_yaml(dump_config_yaml(config)) == config


def test_event_routing_metadata_and_neutral_lifecycle(hass, entry):
    async def scenario():
        hass.states.set(ENTITY, "off")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        await manager.async_update_config(
            {"automatic": {PACK.id: {"label_ids": ["maintenance"]}}}
        )
        assert ALERT not in manager.records
        old = hass.states.get(ENTITY)
        new = hass.states.set(
            ENTITY, "on", {"latest_version": "2", "installed_version": "1"}
        )
        event = Event({"entity_id": ENTITY, "old_state": old, "new_state": new})
        assert manager._state_event_affects_source(event, ENTITY)
        manager._state_changed(event)
        for _ in range(3):
            await asyncio.sleep(0)
        record = manager.records[ALERT]
        assert record.status is AlertStatus.ACTIVE
        assert record.details.labels == ["maintenance"]
        start = record.detected_at
        await manager.async_acknowledge(ALERT, None)
        old = new
        new = hass.states.set(
            ENTITY, "on", {"latest_version": "3", "installed_version": "1"}
        )
        assert manager._state_event_affects_source(
            Event({"entity_id": ENTITY, "old_state": old, "new_state": new}), ENTITY
        )
        await manager.async_evaluate_entity(ENTITY)
        assert manager.records[ALERT].detected_at == start
        assert manager.records[ALERT].acknowledged_at is not None
        assert manager.records[ALERT].details.condition_params["latest_version"] == "3"
        for state in ("unknown", "unavailable"):
            hass.states.set(ENTITY, state)
            await manager.async_evaluate_entity(ENTITY)
            assert manager.records[ALERT].detected_at == start
        hass.states.set(ENTITY, "off")
        await manager.async_evaluate_entity(ENTITY)
        assert ALERT not in manager.records
        assert any(name == EVENT_ALERT_RESOLVED for name, _ in hass.bus.fired)
        await manager.async_unload()

    asyncio.run(scenario())


@pytest.mark.parametrize("delay", [0, 120])
def test_exclusion_removes_administratively_and_restores_monitoring(hass, entry, delay):
    async def scenario():
        hass.states.set(ENTITY, "off")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        await manager.async_update_config({"automatic": {PACK.id: {"delay": delay}}})
        hass.states.set(ENTITY, "on")
        await manager.async_evaluate_entity(ENTITY)
        assert manager.records[ALERT].status is (
            AlertStatus.PENDING if delay else AlertStatus.ACTIVE
        )
        events = list(hass.bus.fired)
        await manager.async_update_config(
            {
                "automatic": {
                    PACK.id: {
                        "entity_overrides": {ENTITY: {"enabled": False}},
                    }
                }
            }
        )
        assert ALERT not in manager.records
        assert not any(
            name == EVENT_ALERT_RESOLVED for name, _ in hass.bus.fired[len(events) :]
        )
        await manager.async_unload()
        restored = AlertManager(hass, entry)
        await restored.async_setup()
        assert restored.config["automatic"][PACK.id]["entity_overrides"] == {
            ENTITY: {"enabled": False}
        }
        assert ALERT not in restored.records
        await restored._async_finish_startup_reconciliation()
        await restored.async_update_config(
            {"automatic": {PACK.id: {"entity_overrides": {}}}}
        )
        assert ALERT in restored.records
        await restored.async_update_config({"automatic": {PACK.id: {"enabled": False}}})
        assert ALERT not in restored.records
        await restored.async_update_config({"automatic": {PACK.id: {"enabled": True}}})
        assert ALERT in restored.records
        await restored.async_unload()

    asyncio.run(scenario())


def test_pending_cancellation_and_activation(hass, entry, set_now):
    async def scenario():
        start = datetime(2026, 9, 14, tzinfo=UTC)
        set_now(start)
        hass.states.set(ENTITY, "off")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        await manager.async_update_config({"automatic": {PACK.id: {"delay": 60}}})
        hass.states.set(ENTITY, "on")
        await manager.async_evaluate_entity(ENTITY)
        assert manager.records[ALERT].status is AlertStatus.PENDING
        hass.states.set(ENTITY, "off")
        await manager.async_evaluate_entity(ENTITY)
        assert ALERT not in manager.records
        assert not manager.history
        hass.states.set(ENTITY, "on")
        await manager.async_evaluate_entity(ENTITY)
        set_now(start + timedelta(seconds=60))
        await manager.async_evaluate_entity(ENTITY)
        assert manager.records[ALERT].status is AlertStatus.ACTIVE
        await manager.async_unload()

    asyncio.run(scenario())


@pytest.mark.parametrize("state", ["unknown", "unavailable"])
def test_active_update_survives_restart_with_uncertain_availability(hass, entry, state):
    async def scenario():
        hass.states.set(ENTITY, "on")
        first = AlertManager(hass, entry)
        await first.async_setup()
        detected_at = first.records[ALERT].detected_at
        await first.async_unload()
        hass.states.set(ENTITY, state)
        restored = AlertManager(hass, entry)
        await restored.async_setup()
        await restored._async_finish_startup_reconciliation()
        assert restored.records[ALERT].detected_at == detected_at
        assert restored.records[ALERT].status is AlertStatus.ACTIVE
        await restored.async_unload()

    asyncio.run(scenario())


def test_exclusion_follows_registry_rename(hass, entry):
    async def scenario():
        hass.states.set(ENTITY, "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        await manager.async_update_config(
            {
                "automatic": {
                    PACK.id: {
                        "entity_overrides": {ENTITY: {"enabled": False}},
                    }
                }
            }
        )
        hass.states.data.pop(ENTITY)
        hass.states.set("update.renamed", "on")
        manager._registry_changed(
            Event(
                {
                    "action": "update",
                    "entity_id": "update.renamed",
                    "old_entity_id": ENTITY,
                    "changes": {"entity_id": "update.renamed"},
                }
            )
        )
        for _ in range(3):
            await asyncio.sleep(0)
        assert manager.config["automatic"][PACK.id]["entity_overrides"] == {
            "update.renamed": {"enabled": False},
        }
        assert not manager.records
        await manager.async_unload()

    asyncio.run(scenario())
