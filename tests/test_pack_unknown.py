"""Each automatic detector owns unknown handling; custom rules keep their gate."""

import asyncio

import pytest
from homeassistant.core import Event

from custom_components.alert_manager.const import EVENT_ALERT_RESOLVED
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertStatus
from custom_components.alert_manager.packs import (
    PACKS_BY_ID,
    PackNeutral,
    execution_errors,
)


@pytest.mark.parametrize("delay", [0, 120])
@pytest.mark.parametrize("keep_attributes", [False, True])
@pytest.mark.parametrize(
    "pack_id,entity_id,bad,good,attributes",
    [
        ("battery", "sensor.battery", "10", "90", {"device_class": "battery"}),
        (
            "connectivity",
            "binary_sensor.link",
            "off",
            "on",
            {"device_class": "connectivity"},
        ),
        (
            "unifi",
            "device_tracker.router",
            "not_home",
            "home",
            {"source_type": "router"},
        ),
        ("update_available", "update.core", "on", "off", {}),
    ],
)
def test_live_unknown_preserves_pack_occurrence(
    hass,
    entry,
    registry_entry,
    config_entry,
    delay,
    keep_attributes,
    pack_id,
    entity_id,
    bad,
    good,
    attributes,
):
    async def scenario():
        if pack_id == "connectivity":
            registered = registry_entry(hass, entity_id)
            registered.original_device_class = "connectivity"
        if pack_id == "unifi":
            registry_entry(hass, entity_id, platform="unifi")
            config_entry(hass, "unifi")
        hass.states.set(entity_id, good, attributes)
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        await manager.async_update_config({"automatic": {pack_id: {"delay": delay}}})
        alert_id = f"{pack_id}:{entity_id}"
        old = hass.states.set(entity_id, bad, attributes)
        await manager.async_evaluate_entity(entity_id)
        before = manager.records[alert_id].as_public_dict()
        if not delay:
            await manager.async_acknowledge(alert_id, None)
        unknown = hass.states.set(
            entity_id, "unknown", attributes if keep_attributes else {}
        )
        manager._state_changed(
            Event({"entity_id": entity_id, "old_state": old, "new_state": unknown})
        )
        for _ in range(3):
            await asyncio.sleep(0)
        record = manager.records[alert_id]
        assert record.detected_at.isoformat() == before["detected_at"]
        assert record.status is (AlertStatus.PENDING if delay else AlertStatus.ACTIVE)
        if not delay:
            assert record.acknowledged_at is not None
        assert not any(n == EVENT_ALERT_RESOLVED for n, _ in hass.bus.fired)
        hass.states.set(entity_id, good, attributes)
        await manager.async_evaluate_entity(entity_id)
        assert alert_id not in manager.records
        await manager.async_unload()

    asyncio.run(scenario())


def test_unknown_does_not_create_alerts(hass, entry, registry_entry, config_entry):
    async def scenario():
        registry_entry(hass, "device_tracker.router", platform="unifi")
        config_entry(hass, "unifi")
        for entity_id, attrs in [
            ("sensor.battery", {"device_class": "battery"}),
            ("binary_sensor.link", {"device_class": "connectivity"}),
            ("device_tracker.router", {"source_type": "router"}),
            ("update.core", {}),
            ("automation.test", {"current": 0}),
        ]:
            hass.states.set(entity_id, "unknown", attrs)
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        assert not manager.records
        await manager.async_unload()

    asyncio.run(scenario())


def test_pack_can_resolve_unknown_while_another_preserves_it(hass, entry):
    async def scenario():
        hass.states.set("update.core", "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        await manager.async_update_config({"automatic": {"unavailable": {"delay": 0}}})
        hass.states.set("update.core", "unavailable")
        await manager.async_evaluate_entity("update.core")
        assert "unavailable:update.core" in manager.records
        assert "update_available:update.core" in manager.records
        hass.states.set("update.core", "unknown")
        await manager.async_evaluate_entity("update.core")
        assert "unavailable:update.core" not in manager.records
        assert "update_available:update.core" in manager.records
        await manager.async_unload()

    asyncio.run(scenario())


def test_execution_unknown_cannot_consume_a_stale_current_attribute(hass):
    pack = PACKS_BY_ID["execution_errors"]
    old = hass.states.set("automation.test", "on", {"current": 1})
    unknown = hass.states.set("automation.test", "unknown", {"current": 0})
    config = pack.default_config()
    assert pack.should_evaluate(hass, old, unknown, config) is False
    assert isinstance(pack.evaluate(hass, unknown, config), PackNeutral)
    assert execution_errors._DATA_CYCLES not in hass.data


def test_custom_rules_keep_existing_unknown_resolution(hass, entry):
    async def scenario():
        hass.states.set("update.core", "on")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(
            {
                "name": "Existing custom semantics",
                "enabled": True,
                "entity_ids": ["update.core"],
                "source": "state",
                "operator": "equals",
                "value": "on",
                "duration": 0,
            }
        )
        rule_id = f"rule:{rule['id']}:update.core"
        assert rule_id in manager.records
        hass.states.set("update.core", "unknown")
        await manager.async_evaluate_entity("update.core")
        assert rule_id not in manager.records
        assert "update_available:update.core" in manager.records
        await manager.async_unload()

    asyncio.run(scenario())
