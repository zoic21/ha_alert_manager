"""Native registry metadata, including child devices on recent Home Assistant."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from homeassistant.const import ATTR_FRIENDLY_NAME
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er


def device_entries(registry: dr.DeviceRegistry) -> Iterable[Any]:
    """Iterate main devices without the deprecated mapping API on recent HA."""
    devices = registry.devices
    return devices.values() if isinstance(devices, Mapping) else devices


def device_area_id(hass: HomeAssistant, device: Any) -> str | None:
    """Use native parent-area inheritance; HA 2026.8 has no child devices."""
    if resolver := getattr(dr, "async_get_effective_area_id", None):
        return resolver(hass, device)
    return device.area_id


def entity_display_name(
    hass: HomeAssistant, entity_id: str, *, state: State | None = None
) -> str:
    """Resolve current native names without rewriting historical snapshots."""
    entry = er.async_get(hass).async_get(entity_id)
    if entry is not None and (name := er.async_get_full_entity_name(hass, entry)):
        return name
    if state is None:
        state = hass.states.get(entity_id)
    if state is not None and (name := state.attributes.get(ATTR_FRIENDLY_NAME)):
        return name
    return entity_id
