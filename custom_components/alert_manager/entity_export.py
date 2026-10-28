"""On-demand entity inventory, independent of coherence scans and alert state."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from homeassistant.helpers.entity import entity_sources
from homeassistant.helpers.json import JSONEncoder
from homeassistant.util import dt as dt_util

from .const import INTEGRATION_VERSION

_REDACTED = "**REDACTED**"
_SENSITIVE_ATTRIBUTES = frozenset(
    {
        "access_token",
        "refresh_token",
        "token",
        "api_key",
        "api_token",
        "password",
        "secret",
        "authorization",
        "entity_picture",
        "entity_picture_local",
        "latitude",
        "longitude",
        "gps",
        "mac",
        "mac_address",
        "ip",
        "ip_address",
        "ip_addresses",
        "local_ip",
        "public_ip",
        "external_ip",
        "internal_ip",
        "ipv4",
        "ipv6",
    }
)


def _redact_attributes(data: Any) -> Any:
    """Copy known sensitive fields without requiring an optional HA component."""
    if isinstance(data, Mapping):
        return {
            key: (
                _REDACTED
                if key in _SENSITIVE_ATTRIBUTES
                and value is not None
                and not (isinstance(value, str) and not value)
                else _redact_attributes(value)
            )
            for key, value in data.items()
        }
    if isinstance(data, list | tuple):
        return [_redact_attributes(value) for value in data]
    return data


async def async_export_entities(hass: HomeAssistant) -> dict[str, str]:
    """Capture HA state and registry metadata before yielding to the executor."""
    exported_at = dt_util.utcnow()
    # Registry updates replace frozen entries. State.last_reported can mutate in
    # place, so capture its value along with the other state fields now.
    # Never traverse a live registry or access hass from the worker thread.
    states = {
        state.entity_id: {
            "state": state.state,
            "attributes": state.attributes,
            "last_changed": state.last_changed,
            "last_updated": state.last_updated,
            "last_reported": state.last_reported,
        }
        for state in hass.states.async_all()
    }
    entities = dict(er.async_get(hass).entities)
    devices = dict(dr.async_get(hass).devices)
    areas = {entry.id: entry.name for entry in ar.async_get(hass).areas.values()}
    labels = {
        entry.label_id: entry.name for entry in lr.async_get(hass).labels.values()
    }
    integrations = {
        entry.entry_id: entry.domain for entry in hass.config_entries.async_entries()
    }
    sources = {
        entity_id: dict(source) for entity_id, source in entity_sources(hass).items()
    }
    content = await hass.async_add_executor_job(
        _serialize_inventory,
        exported_at.isoformat(),
        states,
        entities,
        devices,
        areas,
        labels,
        integrations,
        sources,
    )
    return {
        "filename": f"home-assistant-entities-{exported_at:%Y-%m-%d_%H-%M-%SZ}.json",
        "content_type": "application/json;charset=utf-8",
        "content": content,
    }


def _serialize_inventory(
    exported_at: str,
    states: dict[str, dict[str, Any]],
    entities: dict[str, Any],
    devices: dict[str, Any],
    areas: dict[str, str],
    labels: dict[str, str],
    integrations: dict[str, str],
    sources: dict[str, dict[str, str]],
) -> str:
    """Group, sort and encode the captured inventory away from the event loop."""

    def area(area_id: str | None) -> dict[str, Any] | None:
        return {"id": area_id, "name": areas.get(area_id)} if area_id else None

    def entry_labels(entry: Any) -> list[dict[str, Any]]:
        return [
            {"id": label_id, "name": labels.get(label_id)}
            for label_id in sorted(getattr(entry, "labels", ()))
        ]

    grouped: dict[str, dict[str, Any]] = {}
    for device_id, device in sorted(devices.items()):
        # Current HA has one entry per device; older supported versions use a set.
        config_entry_id = getattr(device, "config_entry_id", None)
        config_entry_ids = (
            [config_entry_id]
            if config_entry_id is not None
            else sorted(getattr(device, "config_entries", ()))
        )
        grouped[device_id] = {
            "device_id": device_id,
            "name": device.name_by_user or device.name,
            "manufacturer": getattr(device, "manufacturer", None),
            "model": getattr(device, "model", None),
            "sw_version": getattr(device, "sw_version", None),
            "hw_version": getattr(device, "hw_version", None),
            "via_device_id": getattr(device, "via_device_id", None),
            "area": area(device.area_id),
            "labels": entry_labels(device),
            "config_entry_ids": config_entry_ids,
            "integrations": sorted(
                {integrations[key] for key in config_entry_ids if key in integrations}
            ),
            "disabled": device.disabled_by is not None,
            "disabled_by": device.disabled_by,
            # HA has no device-level hidden flag. Do not infer it from its entities.
            "hidden": None,
            "hidden_by": None,
            "entities": [],
        }

    without_device: list[dict[str, Any]] = []
    for entity_id in sorted(states.keys() | entities.keys()):
        entry = entities.get(entity_id)
        state = states.get(entity_id)
        device_id = getattr(entry, "device_id", None)
        device = devices.get(device_id)
        area_id = getattr(entry, "area_id", None)
        effective_area_id = area_id or getattr(device, "area_id", None)
        hidden_by = getattr(entry, "hidden_by", None)
        disabled_by = getattr(entry, "disabled_by", None)
        attributes = state["attributes"] if state is not None else None
        source = sources.get(entity_id, {})
        entity = {
            "entity_id": entity_id,
            "name": (
                (attributes or {}).get("friendly_name")
                or getattr(entry, "name", None)
                or getattr(entry, "original_name", None)
                or entity_id
            ),
            "device_id": device_id,
            "integration": getattr(entry, "platform", None) or source.get("domain"),
            "config_entry_id": getattr(entry, "config_entry_id", None)
            or source.get("config_entry"),
            "unique_id": getattr(entry, "unique_id", None),
            "registered": entry is not None,
            "entity_category": getattr(entry, "entity_category", None),
            "area": area(area_id),
            "effective_area": area(effective_area_id),
            "labels": entry_labels(entry),
            "disabled": disabled_by is not None if entry is not None else None,
            "disabled_by": disabled_by,
            "hidden": hidden_by is not None if entry is not None else None,
            "hidden_by": hidden_by,
            "state": state["state"] if state is not None else None,
            "attributes": _redact_attributes(attributes),
            "last_changed": state["last_changed"] if state is not None else None,
            "last_updated": state["last_updated"] if state is not None else None,
            "last_reported": state["last_reported"] if state is not None else None,
        }
        if device_id in grouped:
            grouped[device_id]["entities"].append(entity)
        else:
            without_device.append(entity)

    return json.dumps(
        {
            "schema_version": 1,
            "exported_at": exported_at,
            "home_assistant_version": HA_VERSION,
            "alert_manager_version": INTEGRATION_VERSION,
            "counts": {
                "devices": len(grouped),
                "entities": len(states.keys() | entities.keys()),
                "entities_without_device": len(without_device),
            },
            "devices": list(grouped.values()),
            "entities_without_device": without_device,
        },
        cls=JSONEncoder,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )
