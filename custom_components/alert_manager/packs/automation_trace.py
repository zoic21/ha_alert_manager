"""Small boundary around Home Assistant's in-memory automation traces."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from homeassistant.components.automation import DATA_COMPONENT
from homeassistant.components.trace.const import DATA_TRACE
from homeassistant.core import HomeAssistant


class AutomationTraceRef(Protocol):
    """The only part of Home Assistant's internal trace object we consume."""

    def as_short_dict(self) -> dict[str, Any]:
        """Return the trace summary already held in memory."""


def get_automation_run_traces(
    hass: HomeAssistant, entity_id: str
) -> tuple[AutomationTraceRef, ...]:
    """Return in-memory run traces for one automation without restoring traces."""
    component = hass.data.get(DATA_COMPONENT)
    automation = component.get_entity(entity_id) if component is not None else None
    automation_id = getattr(automation, "unique_id", None)
    if not automation_id:
        return ()

    traces = hass.data.get(DATA_TRACE)
    if not isinstance(traces, dict):
        return ()
    trace_bucket = traces.get(f"automation.{automation_id}")
    if trace_bucket is None:
        return ()

    runs: Iterable[AutomationTraceRef] = getattr(trace_bucket, "runs", trace_bucket)
    values = getattr(runs, "values", None)
    return tuple(values()) if callable(values) else ()
