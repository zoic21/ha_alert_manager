"""Automation execution error automatic pack."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant, State
from homeassistant.util.hass_dict import HassKey

from ..const import CATEGORY_AUTOMATION_ERRORS
from .automation_trace import AutomationTraceRef, get_automation_run_traces
from .base import AutomaticPack, PackMatch, PackNeutral

_DATA_CYCLES: HassKey[dict[str, _AutomationCycle]] = HassKey(
    "alert_manager_automation_error_cycles"
)


@dataclass(slots=True)
class _AutomationCycle:
    """Minimal state retained until one current=0 cycle is complete."""

    last_current: int
    active: bool = False
    expected_runs: int = 0
    completed_runs: int = 0
    traces: dict[str, AutomationTraceRef] = field(default_factory=dict)
    failed: bool = False
    error: str | None = None
    result_ready: bool = False

    def start(self) -> None:
        """Discard the previous result and begin a new execution cycle."""
        self.active = True
        self.expected_runs = 0
        self.completed_runs = 0
        self.traces.clear()
        self.failed = False
        self.error = None
        self.result_ready = False


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


def _trace_id(trace: AutomationTraceRef, summary: dict[str, Any]) -> str:
    """Return the stable run id without serializing the complete trace."""
    run_id = summary.get("run_id")
    return str(run_id) if run_id is not None else str(id(trace))


def _capture_running_traces(
    hass: HomeAssistant, entity_id: str, cycle: _AutomationCycle
) -> None:
    """Keep references to new running traces before HA's short bucket evicts them."""
    for trace in get_automation_run_traces(hass, entity_id):
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


def _observe_transition(
    hass: HomeAssistant, state: State, _config: dict[str, Any]
) -> bool:
    """Capture every run-count transition and evaluate only on decreases."""
    current = _current(state)
    if current is None:
        return False
    cycles = _cycles(hass)
    cycle = cycles.get(state.entity_id)
    if cycle is None:
        cycles[state.entity_id] = _AutomationCycle(last_current=current)
        return False

    previous = cycle.last_current
    cycle.last_current = current
    if current > previous:
        if previous == 0 or not cycle.active:
            cycle.start()
        cycle.expected_runs += current - previous
        _capture_running_traces(hass, state.entity_id, cycle)
        return False
    return current < previous


def _evaluate(
    hass: HomeAssistant, state: State, _config: dict[str, Any]
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
        cycle = cycles[state.entity_id] = _AutomationCycle(last_current=current)
        if current > 0:
            cycle.start()
            cycle.expected_runs = current
            _capture_running_traces(hass, state.entity_id, cycle)
        return PackNeutral()

    cycle.last_current = current
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
    if not cycle.result_ready:
        return PackNeutral()
    if not cycle.failed:
        return None
    if cycle.error:
        return PackMatch(
            condition_key="automatic.automation_errors_detail",
            condition_params={"error": cycle.error},
            value=cycle.error,
        )
    return PackMatch(condition_key="automatic.automation_errors")


def reset_runtime(hass: HomeAssistant) -> None:
    """Drop transient trace references when monitoring stops or unloads."""
    hass.data.pop(_DATA_CYCLES, None)


PACK = AutomaticPack(
    id=CATEGORY_AUTOMATION_ERRORS,
    translation_key="automation_errors",
    prerequisites=(),
    applies=_applies,
    evaluate=_evaluate,
    transition_filter=_observe_transition,
)
