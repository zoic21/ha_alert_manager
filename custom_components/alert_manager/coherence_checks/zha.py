"""Static ZHA trigger references checked only during coherence scans.

snapshot runs on the event loop using HA registries. references runs in the
scanner executor and never accesses Home Assistant or live registry objects.
"""

from __future__ import annotations

import logging
import re

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

_LOGGER = logging.getLogger(__name__)
REFERENCE_TYPE = "zha_device_ieee"


def _literal(node: Node | None) -> str | None:
    """Accept only ordinary YAML strings, never custom tags or inputs."""
    if (
        isinstance(node, ScalarNode)
        and node.tag == "tag:yaml.org,2002:str"
        and "{{" not in node.value
        and "{%" not in node.value
    ):
        return node.value
    return None


def references(node: MappingNode) -> tuple[ScalarNode, ...]:
    """Return valid static IEEE nodes from one structurally identified trigger."""
    values = {
        key.value: value for key, value in node.value if isinstance(key, ScalarNode)
    }
    if _literal(values.get("trigger", values.get("platform"))) != "event":
        return ()
    event_type = values.get("event_type")
    if (
        isinstance(event_type, SequenceNode)
        and event_type.tag != "tag:yaml.org,2002:seq"
    ):
        return ()
    event_types = (
        event_type.value if isinstance(event_type, SequenceNode) else [event_type]
    )
    if not event_types or any(_literal(item) is None for item in event_types):
        return ()
    if "zha_event" not in [_literal(item) for item in event_types]:
        return ()
    data = values.get("event_data")
    if not isinstance(data, MappingNode) or data.tag != "tag:yaml.org,2002:map":
        return ()
    ieee_node = next(
        (value for key, value in data.value if _literal(key) == "device_ieee"), None
    )
    ieee = _literal(ieee_node)
    if ieee is None or not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){7}[0-9a-fA-F]{2}", ieee):
        return ()
    return (ieee_node,)


def snapshot(hass: HomeAssistant) -> tuple[frozenset[str] | None, str]:
    """Copy registry metadata on the event loop; isolate integration failures."""
    try:
        entries = hass.config_entries.async_entries("zha")
        if not entries:
            return None, "not_applicable"
        if any(entry.state is not ConfigEntryState.LOADED for entry in entries):
            return None, "not_loaded"
        entry_ids = {entry.entry_id for entry in entries}
        registry = dr.async_get(hass)
        ieees = frozenset(
            identifier.lower()
            for device in registry.devices.values()
            if entry_ids.intersection(device.config_entries)
            for domain, identifier in device.identifiers
            if domain == "zha"
        )
        return ieees, "executed"
    except Exception:
        _LOGGER.exception("Unable to collect ZHA metadata for coherence scan")
        return None, "metadata_error"
