"""Complete, read-only entity exports and their administrator-only transport."""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import UTC, datetime
from types import MappingProxyType, SimpleNamespace

import pytest
from homeassistant.helpers.entity import entity_sources
from test_websocket import Connection

from custom_components.alert_manager.const import DATA_MANAGER
from custom_components.alert_manager.entity_export import async_export_entities
from custom_components.alert_manager.websocket import (
    async_register_websocket_commands,
    websocket_entities_export,
)

REDACTED = "**REDACTED**"


def test_export_preserves_inventory_states_and_registry_flags(
    hass, registry_entry, device_entry, config_entry
):
    integration = config_entry(hass, "zha")
    device = device_entry(hass, "device", disabled_by="user", area_id="salon")
    device.config_entry_id = integration.entry_id
    device.manufacturer = "Fabricant"
    device.labels = {"important"}
    device_entry(hass, "empty")
    hass.area_registry.entries["salon"] = SimpleNamespace(id="salon", name="Salon")
    hass.area_registry.entries["bureau"] = SimpleNamespace(id="bureau", name="Bureau")
    hass.label_registry.labels["important"] = SimpleNamespace(
        label_id="important", name="Important"
    )
    hidden = registry_entry(
        hass, "sensor.hidden", platform="zha", device_id="device", area_id="bureau"
    )
    hidden.hidden_by = "user"
    hidden.entity_category = "diagnostic"
    registry_entry(hass, "sensor.disabled", device_id="device", disabled_by="device")
    registry_entry(hass, "switch.off", device_id="device")
    registry_entry(hass, "sensor.not_loaded")
    registry_entry(hass, "sensor.orphan", device_id="missing_device")
    hass.entity_registry.deleted_entities["old"] = SimpleNamespace(
        entity_id="sensor.deleted"
    )
    now = datetime(2026, 9, 30, 9, 46, 44, tzinfo=UTC)
    attributes = {
        "friendly_name": "Température <salon>",
        "unit_of_measurement": "°C",
        "nested": {"list": [1, True, None], "date": now},
        "supported_modes": {"auto"},
    }
    hass.states.set("sensor.hidden", "21.5", attributes)
    hass.states.set("switch.off", "off")
    hass.states.set("sensor.unavailable", "unavailable")
    hass.states.set("sensor.unknown", "unknown")
    hass.states.set("sensor.yaml", "42")
    entity_sources(hass)["sensor.yaml"] = {
        "domain": "template",
        "config_entry": "template-entry",
    }

    payload = asyncio.run(async_export_entities(hass))
    result = json.loads(payload["content"])
    assert payload["filename"].endswith("Z.json")
    assert payload["content_type"] == "application/json;charset=utf-8"
    assert result["schema_version"] == 1
    assert result["home_assistant_version"] == "2026.9.0"
    assert result["counts"] == {
        "devices": 2,
        "entities": 8,
        "entities_without_device": 5,
    }
    exported_device = result["devices"][0]
    assert exported_device["device_id"] == "device"
    assert exported_device["disabled"] is True
    assert exported_device["disabled_by"] == "user"
    assert exported_device["hidden"] is None
    assert exported_device["hidden_by"] is None
    assert exported_device["integrations"] == ["zha"]
    assert exported_device["labels"] == [{"id": "important", "name": "Important"}]
    assert result["devices"][1]["entities"] == []
    items = {
        item["entity_id"]: item
        for item in exported_device["entities"] + result["entities_without_device"]
    }
    disabled = items["sensor.disabled"]
    assert disabled["disabled"] is True
    assert disabled["disabled_by"] == "device"
    assert disabled["state"] is None and disabled["attributes"] is None
    assert disabled["effective_area"] == {"id": "salon", "name": "Salon"}
    hidden = items["sensor.hidden"]
    assert hidden["hidden"] is True and hidden["hidden_by"] == "user"
    assert hidden["disabled"] is False
    assert (
        hidden["area"] == hidden["effective_area"] == {"id": "bureau", "name": "Bureau"}
    )
    assert hidden["state"] == "21.5"
    assert hidden["attributes"]["nested"] == {
        "list": [1, True, None],
        "date": now.isoformat(),
    }
    assert hidden["attributes"]["supported_modes"] == ["auto"]
    assert hidden["name"] == "Température <salon>"
    assert hidden["last_changed"] and hidden["last_updated"] and hidden["last_reported"]
    assert items["switch.off"]["state"] == "off"
    assert items["switch.off"]["disabled"] is False
    assert items["switch.off"]["hidden"] is False
    assert items["sensor.not_loaded"]["state"] is None
    assert items["sensor.not_loaded"]["disabled"] is False
    assert items["sensor.unavailable"]["state"] == "unavailable"
    assert items["sensor.unavailable"]["integration"] is None
    assert items["sensor.unavailable"]["disabled"] is None
    assert items["sensor.unknown"]["state"] == "unknown"
    assert items["sensor.yaml"]["integration"] == "template"
    assert items["sensor.yaml"]["config_entry_id"] == "template-entry"
    assert items["sensor.yaml"]["registered"] is False
    assert items["sensor.orphan"]["device_id"] == "missing_device"
    assert "sensor.deleted" not in items
    assert hass.store_save_count == 0 and hass.services.calls == []


def test_export_captures_before_worker_and_does_not_read_live_registries(
    hass, registry_entry, device_entry, monkeypatch
):
    registry_entry(hass, "sensor.one", device_id="device")
    device_entry(hass, "device", name="Before")
    hass.states.set("sensor.one", "1")
    main_thread = threading.get_ident()
    captured_reported = hass.states.get("sensor.one").last_reported

    async def executor(target, *args):
        hass.states.get("sensor.one").last_reported = datetime(
            2026, 9, 30, 20, tzinfo=UTC
        )
        hass.states.set("sensor.one", "2")
        hass.states.set("sensor.new", "3")
        hass.entity_registry.entries.clear()
        hass.device_registry.entries.clear()

        def work():
            assert threading.get_ident() != main_thread
            return target(*args)

        return await asyncio.to_thread(work)

    monkeypatch.setattr(hass, "async_add_executor_job", executor)
    result = json.loads(asyncio.run(async_export_entities(hass))["content"])
    assert result["counts"]["entities"] == 1
    assert result["devices"][0]["name"] == "Before"
    assert result["devices"][0]["entities"][0]["state"] == "1"
    assert (
        result["devices"][0]["entities"][0]["last_reported"]
        == captured_reported.isoformat()
    )


@pytest.mark.parametrize("child_area", [None, "garden"])
def test_export_includes_children_with_native_names_and_effective_areas(
    hass, registry_entry, device_entry, monkeypatch, child_area
):
    class ChildDevice(SimpleNamespace):
        def __getattr__(self, name):
            if name in {
                "manufacturer",
                "model",
                "sw_version",
                "hw_version",
                "via_device_id",
            }:
                pytest.fail(f"Read hardware-only attribute on a child device: {name}")
            raise AttributeError(name)

    parent = device_entry(hass, "parent", area_id="garage", name="Power strip")
    parent.manufacturer = "Manufacturer"
    parent.config_entry_id = "entry"
    child = ChildDevice(
        id="child",
        name="Outlet",
        name_by_user=None,
        parent_device_id="parent",
        area_id=child_area,
        config_entry_id="entry",
        labels=set(),
        disabled_by=None,
    )
    hass.device_registry.entries["child"] = child
    # Recent HA exposes separate collections, not a mapping of all devices.
    hass.device_registry.devices = (parent,)
    hass.device_registry.child_devices = (child,)
    for area_id, name in [
        ("garage", "Garage"),
        ("garden", "Garden"),
        ("office", "Office"),
    ]:
        hass.area_registry.entries[area_id] = SimpleNamespace(id=area_id, name=name)
    inherited = registry_entry(hass, "switch.child", device_id="child")
    inherited.name = "Power strip Outlet Switch"
    registry_entry(hass, "sensor.override", device_id="child", area_id="office")
    hass.states.set("switch.child", "off", {"friendly_name": "Legacy name"})

    async def executor(target, *args):
        hass.entity_registry.entries["switch.child"] = SimpleNamespace(
            **{**vars(inherited), "name": "Changed after capture"}
        )
        hass.device_registry.entries["child"] = SimpleNamespace(
            **{**vars(child), "area_id": "office"}
        )
        hass.device_registry.entries.clear()
        return await asyncio.to_thread(target, *args)

    monkeypatch.setattr(hass, "async_add_executor_job", executor)
    result = json.loads(asyncio.run(async_export_entities(hass))["content"])
    assert result["counts"] == {
        "devices": 2,
        "entities": 2,
        "entities_without_device": 0,
    }
    exported = {device["device_id"]: device for device in result["devices"]}
    assert exported["parent"]["manufacturer"] == "Manufacturer"
    assert exported["parent"]["parent_device_id"] is None
    child = exported["child"]
    assert child["parent_device_id"] == "parent"
    assert child["manufacturer"] is None
    assert child["area"] == (
        None if child_area is None else {"id": "garden", "name": "Garden"}
    )
    expected_area = (
        {"id": "garden", "name": "Garden"}
        if child_area
        else {"id": "garage", "name": "Garage"}
    )
    assert child["effective_area"] == expected_area
    entities = {item["entity_id"]: item for item in child["entities"]}
    assert entities["switch.child"]["name"] == "Power strip Outlet Switch"
    assert entities["switch.child"]["effective_area"] == expected_area
    assert entities["sensor.override"]["effective_area"] == {
        "id": "office",
        "name": "Office",
    }


def test_export_endpoint_requires_admin_and_loaded_manager(hass):
    connection = Connection(admin=False)
    asyncio.run(websocket_entities_export(hass, connection, {"id": 1}))
    assert connection.errors[0][1] == "unauthorized"
    connection = Connection(admin=True)
    asyncio.run(websocket_entities_export(hass, connection, {"id": 2}))
    assert connection.errors[0][1] == "not_loaded"
    assert connection.results == []
    hass.data[DATA_MANAGER] = object()
    asyncio.run(websocket_entities_export(hass, connection, {"id": 3}))
    assert json.loads(connection.results[0][1]["content"])["counts"]["entities"] == 0
    async_register_websocket_commands(hass)
    assert websocket_entities_export in hass.commands


def test_export_does_not_silently_drop_unserializable_private_attributes(hass):
    hass.data[DATA_MANAGER] = object()
    hass.states.set("sensor.bad", "1", {"private_token": object()})
    connection = Connection(admin=True)
    asyncio.run(websocket_entities_export(hass, connection, {"id": 1}))
    assert connection.results == []
    assert connection.errors == [(1, "entity_export_failed", "entity_export_failed")]


@pytest.mark.parametrize("domain", ["person", "device_tracker", "sensor"])
def test_export_masks_known_sensitive_attributes_without_mutating_states(hass, domain):
    """Known secrets and location/network fields cannot leak, even when nested."""
    attributes = {
        "access_token": "access-secret",
        "refresh_token": "refresh-secret",
        "entity_picture": "/api/image/serve/person?token=picture-secret",
        "entity_picture_local": "/local/person.jpg",
        "latitude": 48.8566,
        "longitude": 2.3522,
        "gps": [48.8566, 2.3522],
        "mac": "aa:bb:cc:dd:ee:ff",
        "ip": "192.168.1.10",
        "friendly_name": "Source",
        "battery_level": 75,
        "nested": {
            "password": "password-secret",
            "entries": [
                {"api_key": "api-secret", "mac_address": "11:22:33:44:55:66"},
                {"ip_address": "2001:db8::1", "mode": "home"},
            ],
        },
    }
    entity_id = f"{domain}.source"
    hass.states.set(entity_id, "home", attributes)
    payload = asyncio.run(async_export_entities(hass))
    result = json.loads(payload["content"])
    item = result["entities_without_device"][0]
    exported = item["attributes"]
    assert item["name"] == "Source" and item["state"] == "home"
    assert exported["battery_level"] == 75
    for key in (
        "access_token",
        "refresh_token",
        "entity_picture",
        "entity_picture_local",
        "latitude",
        "longitude",
        "gps",
        "mac",
        "ip",
    ):
        assert exported[key] == REDACTED
    assert exported["nested"] == {
        "password": REDACTED,
        "entries": [
            {"api_key": REDACTED, "mac_address": REDACTED},
            {"ip_address": REDACTED, "mode": "home"},
        ],
    }
    for sensitive in ("access-secret", "picture-secret", "192.168.1.10", "48.8566"):
        assert sensitive not in payload["content"]
    assert hass.states.get(entity_id).attributes == attributes


def test_export_redacts_unserializable_known_secret_before_encoding(hass):
    """A known secret is replaced before JSON serialization ever sees it."""
    secret = object()
    hass.states.set("sensor.source", "1", {"access_token": secret})
    result = json.loads(asyncio.run(async_export_entities(hass))["content"])
    assert result["entities_without_device"][0]["attributes"] == {
        "access_token": REDACTED
    }
    assert hass.states.get("sensor.source").attributes["access_token"] is secret


def test_export_masks_secrets_inside_read_only_mappings_and_tuples(hass):
    """HA attribute containers retain safe values without requiring diagnostics."""
    nested = MappingProxyType({"api_key": "nested-secret", "mode": "auto"})
    attributes = {
        "nested": (nested, {"password": None, "access_token": ""}),
        "temperature": 0,
    }
    hass.states.set("sensor.source", "0", attributes)
    payload = asyncio.run(async_export_entities(hass))
    result = json.loads(payload["content"])
    assert result["entities_without_device"][0]["attributes"] == {
        "nested": [
            {"api_key": REDACTED, "mode": "auto"},
            {"password": None, "access_token": ""},
        ],
        "temperature": 0,
    }
    assert "nested-secret" not in payload["content"]
    assert hass.states.get("sensor.source").attributes["nested"][0] is nested
    assert nested["api_key"] == "nested-secret"
