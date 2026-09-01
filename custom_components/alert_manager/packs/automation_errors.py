"""Automatic pack detecting failed Home Assistant automation executions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from homeassistant.components.automation import DATA_COMPONENT
from homeassistant.components.trace.const import DATA_TRACE
from homeassistant.core import HomeAssistant, State
from homeassistant.util.hass_dict import HassKey

from .base import AutomaticPack, PackConfigField, PackMatch, PackNeutral

PACK_ID = "automation_errors"

_DATA_CYCLES: HassKey[dict[str, _AutomationCycle]] = HassKey(
    "alert_manager_automation_error_cycles"
)


@dataclass(slots=True)
class _AutomationCycle:
    """Minimal state retained until one current=0 cycle is complete."""

    active: bool = False
    expected_runs: int = 0
    completed_runs: int = 0
    traces: dict[str, _AutomationTrace] = field(default_factory=dict)
    failed: bool = False
    error: str | None = None
    result_ready: bool = False
    consecutive_failures: int = 0

    def start(self) -> None:
        """Discard the previous result and begin a new execution cycle."""
        self.active = True
        self.expected_runs = 0
        self.completed_runs = 0
        self.traces.clear()
        self.failed = False
        self.error = None
        self.result_ready = False


class _AutomationTrace(Protocol):
    """Small boundary around the internal Home Assistant trace object."""

    def as_short_dict(self) -> dict[str, Any]:
        """Return the short trace already held in memory."""


def _get_automation_run_traces(
    hass: HomeAssistant, entity_id: str
) -> tuple[_AutomationTrace, ...]:
    """Return in-memory short traces for one automation without restoring data."""
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

    runs: Iterable[_AutomationTrace] = getattr(trace_bucket, "runs", trace_bucket)
    values = getattr(runs, "values", None)
    return tuple(values()) if callable(values) else ()


def _applies(_hass: HomeAssistant, state: State) -> bool:
    """Select only real automation entities."""
    return state.entity_id.partition(".")[0] == "automation"


def _current(state: State) -> int | None:
    """Return a valid non-negative automation run count."""
    value = state.attributes.get("current")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _cycles(hass: HomeAssistant) -> dict[str, _AutomationCycle]:
    """Return runtime-only cycle state for this Home Assistant instance."""
    return hass.data.setdefault(_DATA_CYCLES, {})


def _trace_id(trace: _AutomationTrace, summary: dict[str, Any]) -> str:
    """Return the stable run id without serializing the complete trace."""
    run_id = summary.get("run_id")
    return str(run_id) if run_id is not None else str(id(trace))


def _capture_running_traces(
    hass: HomeAssistant, entity_id: str, cycle: _AutomationCycle
) -> None:
    """Keep references to new running traces before HA's short bucket evicts them."""
    for trace in _get_automation_run_traces(hass, entity_id):
        summary = trace.as_short_dict()
        if summary.get("state") != "running":
            continue
        cycle.traces.setdefault(_trace_id(trace, summary), trace)


def _process_completed_traces(cycle: _AutomationCycle) -> None:
    """Accumulate newly completed short traces into the current cycle result."""
    for run_id, trace in tuple(cycle.traces.items()):
        summary = trace.as_short_dict()
        timestamp = summary.get("timestamp")
        if (
            summary.get("state") != "stopped"
            or not isinstance(timestamp, dict)
            or timestamp.get("finish") is None
        ):
            continue
        cycle.traces.pop(run_id)
        cycle.completed_runs += 1
        if "error" not in summary:
            continue
        cycle.failed = True
        if cycle.error is None and summary.get("error"):
            cycle.error = str(summary["error"])


def _handle_state_change(
    hass: HomeAssistant,
    old_state: State | None,
    new_state: State,
    _config: dict[str, Any],
) -> bool:
    """Capture starts, accumulate each decrease and evaluate completed runs."""
    previous = _current(old_state) if old_state is not None else None
    current = _current(new_state)
    if previous is None or current is None:
        return False
    cycles = _cycles(hass)
    cycle = cycles.setdefault(new_state.entity_id, _AutomationCycle())
    if current > previous:
        if previous == 0 or not cycle.active:
            cycle.start()
        cycle.expected_runs += current - previous
        _capture_running_traces(hass, new_state.entity_id, cycle)
        return False
    if current < previous:
        _process_completed_traces(cycle)
        return True
    return False


def _failure_threshold(config: dict[str, Any], entity_id: str) -> int:
    """Return the configured consecutive failed-cycle threshold."""
    thresholds = config.get("failure_thresholds", {})
    value = thresholds.get(entity_id, 1) if isinstance(thresholds, dict) else 1
    return int(value)


def _evaluate(
    hass: HomeAssistant, state: State, config: dict[str, Any]
) -> PackMatch | PackNeutral | None:
    """Return the completed cycle result while preserving alerts mid-cycle."""
    if not _applies(hass, state):
        return None
    current = _current(state)
    if current is None:
        return PackNeutral()

    cycles = _cycles(hass)
    cycle = cycles.get(state.entity_id)
    if cycle is None:
        cycle = cycles[state.entity_id] = _AutomationCycle()
        if current > 0:
            cycle.start()
            cycle.expected_runs = current
            _capture_running_traces(hass, state.entity_id, cycle)
        return PackNeutral()

    if cycle.active:
        _capture_running_traces(hass, state.entity_id, cycle)
        _process_completed_traces(cycle)
    if current > 0:
        return PackNeutral()
    if cycle.active:
        if cycle.traces or cycle.completed_runs != cycle.expected_runs:
            return PackNeutral()
        cycle.active = False
        cycle.result_ready = True
        if cycle.failed:
            cycle.consecutive_failures += 1
        else:
            cycle.consecutive_failures = 0
    if not cycle.result_ready:
        return PackNeutral()
    if not cycle.failed:
        return None
    if cycle.consecutive_failures < _failure_threshold(config, state.entity_id):
        return PackNeutral()
    if cycle.error:
        return PackMatch(
            condition_key="automatic.automation_errors_detail",
            condition_params={"error": cycle.error},
            value=cycle.error,
        )
    return PackMatch(condition_key="automatic.automation_errors")


def _reset_runtime(hass: HomeAssistant) -> None:
    """Drop transient trace references when monitoring stops or unloads."""
    hass.data.pop(_DATA_CYCLES, None)


PACK = AutomaticPack(
    id=PACK_ID,
    translation_key="automation_errors",
    prerequisites=(),
    applies=_applies,
    evaluate=_evaluate,
    state_change_handler=_handle_state_change,
    reset_handler=_reset_runtime,
    config_fields=(
        PackConfigField(
            id="failure_thresholds",
            type="entity_number_map",
            translation_key="failure_thresholds",
            default={},
            minimum=1,
            maximum=100,
            step=1,
            entity_domain="automation",
        ),
    ),
)
