"""Unknown-state neutrality regressions for every automatic pack."""

from __future__ import annotations

import asyncio

from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    STATE_HOME,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)

from custom_components.alert_manager.runtime_manager import AlertManager


def test_unknown_does_not_create_automatic_alerts(
    hass, entry, registry_entry, config_entry
):
    """Unknown alone must never open an occurrence for any automatic pack."""

    async def scenario():
        registry_entry(hass, "device_tracker.unifi_client", platform="unifi")
        config_entry(hass, "unifi")

        hass.states.set("sensor.generic", STATE_UNKNOWN)
        hass.states.set(
            "sensor.battery",
            STATE_UNKNOWN,
            {ATTR_DEVICE_CLASS: "battery"},
        )
        hass.states.set(
            "binary_sensor.connectivity",
            STATE_UNKNOWN,
            {ATTR_DEVICE_CLASS: "connectivity"},
        )
        hass.states.set(
            "device_tracker.unifi_client",
            STATE_UNKNOWN,
            {"source_type": "router"},
        )

        manager = AlertManager(hass, entry)
        await manager.async_setup()
        for pack_id in ("unavailable", "battery", "connectivity", "unifi"):
            manager.config["automatic"][pack_id]["enabled"] = True

        for entity_id in (
            "sensor.generic",
            "sensor.battery",
            "binary_sensor.connectivity",
            "device_tracker.unifi_client",
        ):
            changed = await manager.async_evaluate_entity(
                entity_id,
                save=False,
                publish=False,
            )
            assert not changed

        assert not manager.records

    asyncio.run(scenario())


def test_unknown_preserves_existing_occurrences_for_all_packs(
    hass, entry, registry_entry, config_entry
):
    """Pending automatic occurrences keep their identity and timer through unknown."""

    async def scenario():
        registry_entry(hass, "device_tracker.unifi_client", platform="unifi")
        config_entry(hass, "unifi")

        manager = AlertManager(hass, entry)
        await manager.async_setup()
        for pack_id in ("unavailable", "battery", "connectivity", "unifi"):
            manager.config["automatic"][pack_id]["enabled"] = True
            manager.config["automatic"][pack_id]["delay"] = 300

        cases = (
            (
                "unavailable",
                "sensor.generic",
                STATE_UNAVAILABLE,
                {},
                STATE_UNKNOWN,
                {},
                "ok",
                {},
            ),
            (
                "battery",
                "sensor.battery",
                "10",
                {ATTR_DEVICE_CLASS: "battery"},
                STATE_UNKNOWN,
                {ATTR_DEVICE_CLASS: "battery"},
                "80",
                {ATTR_DEVICE_CLASS: "battery"},
            ),
            (
                "connectivity",
                "binary_sensor.connectivity",
                "off",
                {ATTR_DEVICE_CLASS: "connectivity"},
                STATE_UNKNOWN,
                {},
                "on",
                {ATTR_DEVICE_CLASS: "connectivity"},
            ),
            (
                "unifi",
                "device_tracker.unifi_client",
                "not_home",
                {"source_type": "router"},
                STATE_UNKNOWN,
                {},
                STATE_HOME,
                {"source_type": "router"},
            ),
        )

        for (
            pack_id,
            entity_id,
            alert_state,
            alert_attributes,
            neutral_state,
            neutral_attributes,
            healthy_state,
            healthy_attributes,
        ) in cases:
            hass.states.set(entity_id, alert_state, alert_attributes)
            assert await manager.async_evaluate_entity(
                entity_id,
                save=False,
                publish=False,
            )

            alert_id = f"{pack_id}:{entity_id}"
            record = manager.records[alert_id]
            detected_at = record.detected_at
            due_at = record.due_at
            timer = manager._timers[alert_id]

            hass.states.set(entity_id, neutral_state, neutral_attributes)
            assert not await manager.async_evaluate_entity(
                entity_id,
                save=False,
                publish=False,
            )

            assert manager.records[alert_id] is record
            assert record.detected_at == detected_at
            assert record.due_at == due_at
            assert manager._timers[alert_id] is timer

            hass.states.set(entity_id, healthy_state, healthy_attributes)
            assert await manager.async_evaluate_entity(
                entity_id,
                save=False,
                publish=False,
            )
            assert alert_id not in manager.records

    asyncio.run(scenario())
