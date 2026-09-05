"""Automatic pack detecting failed automation and script executions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from homeassistant.components.automation import DATA_COMPONENT
from homeassistant.components.trace.const import DATA_TRACE
from homeassistant.core import HomeAssistant, State
from homeassistant.util.hass_dict import HassKey

from .base import (
    AutomaticPack,
    PackConfigField,
    PackMatch,
    PackNeutral,
    PackRecheck,
)

PACK_ID = "execution_errors"
_SUPPORTED_DOMAINS = ("automation", "script")
_TRACE_RECHECK_DELAY = 0.1
_TRACE_RECHECK_LIMIT = 5
_MAX_COMPLETED_CYCLES = 32
_MAX_TRACE_REFERENCES = 64

_DATA_CYCLES: HassKey[dict[str, _ExecutionTracker]] = HassKey(
    "alert_manager_execution_error_cycles"
)


@dataclass(slots=True)
class _ExecutionCycle:
    """Trace references retained until one execution cycle is complete."""

    expected_runs: int = 0
    completed_runs: int = 0
    traces: dict[str, _ExecutionTrace] = field(default_factory=dict)
    failed: bool = False
    error: str | None = None
    rechecks: int = 0


@dataclass(slots=True)
class _ExecutionTracker:
    """Current cycle, completed cycles awaiting evaluation and failure count."""

    active: _ExecutionCycle | None = None
    completed: list[_ExecutionCycle] = field(default_factory=list)
    consecutive_failures: int = 0


class _ExecutionTrace(Protocol):
    """Small boundary around the internal Home Assistant trace object."""

    def as_short_dict(self) -> dict[str, Any]:
        """Return the short trace already held in memory."""


def _get_entity_run_traces(
    hass: HomeAssistant, entity_id: str
) -> tuple[_ExecutionTrace, ...]:
    """Return in-memory short traces for one entity without restoring data."""
    domain = entity_id.partition(".")[0]
    component_key = DATA_COMPONENT if domain == "automation" else domain
    component = hass.data.get(component_key)
    entity = component.get_entity(entity_id) if component is not None else None
    unique_id = getattr(entity, "unique_id", None)
    if not unique_id:
        return ()

    traces = hass.data.get(DATA_TRACE)
    if not isinstance(traces, dict):
        return ()
    trace_bucket = traces.get(f"{domain}.{unique_id}")
    if trace_bucket is None:
        return ()

    runs: Iterable[_ExecutionTrace] = getattr(trace_bucket, "runs", trace_bucket)
    values = getattr(runs, "values", None)
    return tuple(values()) if callable(values) else ()


def _applies(_hass: HomeAssistant, state: State) -> bool:
    """Select real automation and script entities."""
    return state.entity_id.partition(".")[0] in _SUPPORTED_DOMAINS


def _current(state: State) -> int | None:
    """Return a valid non-negative execution count."""
    value = state.attributes.get("current")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _cycles(hass: HomeAssistant) -> dict[str, _ExecutionTracker]:
    """Return runtime-only cycle state for this Home Assistant instance."""
    return hass.data.setdefault(_DATA_CYCLES, {})


def _trace_id(trace: _ExecutionTrace, summary: dict[str, Any]) -> str:
    """Return the stable run id without serializing the complete trace."""
    run_id = summary.get("run_id")
    return str(run_id) if run_id is not None else str(id(trace))


def _short_summary(trace: _ExecutionTrace) -> dict[str, Any] | None:
    """Return a usable short summary while rejecting malformed trace data."""
    summary = trace.as_short_dict()
    return summary if isinstance(summary, dict) else None


def _capture_running_traces(
    hass: HomeAssistant, entity_id: str, cycle: _ExecutionCycle
) -> None:
    """Keep references to new running traces before HA's short bucket evicts them."""
    for trace in _get_entity_run_traces(hass, entity_id):
        summary = _short_summary(trace)
        if summary is None or summary.get("state") != "running":
            continue
        run_id = _trace_id(trace, summary)
        if run_id in cycle.traces:
            continue
        if len(cycle.traces) >= _MAX_TRACE_REFERENCES:
            continue
        cycle.traces[run_id] = trace


def _process_completed_traces(cycle: _ExecutionCycle) -> None:
    """Accumulate newly completed short traces into the current cycle result."""
    for run_id, trace in tuple(cycle.traces.items()):
        summary = _short_summary(trace)
        if summary is None:
            continue
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


def _cycle_is_complete(cycle: _ExecutionCycle) -> bool:
    """Return whether every captured run has a finalized short trace."""
    return not cycle.traces and cycle.completed_runs == cycle.expected_runs


def _apply_cycle_outcome(tracker: _ExecutionTracker, cycle: _ExecutionCycle) -> None:
    """Advance the consecutive-failure counter for one complete cycle."""
    if cycle.failed:
        tracker.consecutive_failures += 1
    else:
        tracker.consecutive_failures = 0


def _discard_incomplete_cycle(
    tracker: _ExecutionTracker, cycle: _ExecutionCycle
) -> None:
    """Release trace references and break an unverifiable failure sequence."""
    cycle.traces.clear()
    tracker.consecutive_failures = 0


def _queue_completed_cycle(tracker: _ExecutionTracker, cycle: _ExecutionCycle) -> None:
    """Retain a bounded queue without losing completed-cycle semantics."""
    if len(tracker.completed) >= _MAX_COMPLETED_CYCLES:
        _apply_cycle_outcome(tracker, tracker.completed.pop(0))
    tracker.completed.append(cycle)


def _should_evaluate(
    hass: HomeAssistant,
    old_state: State | None,
    new_state: State,
    _config: dict[str, Any],
) -> bool:
    """Capture starts and request grouped evaluation on each decrease."""
    previous = _current(old_state) if old_state is not None else None
    current = _current(new_state)
    if previous is None or current is None:
        return False
    cycles = _cycles(hass)
    tracker = cycles.setdefault(new_state.entity_id, _ExecutionTracker())
    if current > previous:
        if previous == 0 or tracker.active is None:
            if tracker.active is not None:
                _process_completed_traces(tracker.active)
                if _cycle_is_complete(tracker.active):
                    _queue_completed_cycle(tracker, tracker.active)
                else:
                    _discard_incomplete_cycle(tracker, tracker.active)
            tracker.active = _ExecutionCycle()
        tracker.active.expected_runs += current - previous
        _capture_running_traces(hass, new_state.entity_id, tracker.active)
        return False
    return current < previous


def _failure_threshold(config: dict[str, Any], entity_id: str) -> int:
    """Return the configured consecutive failed-cycle threshold."""
    thresholds = config.get("failure_thresholds", {})
    value = thresholds.get(entity_id, 1) if isinstance(thresholds, dict) else 1
    return int(value)


def _evaluate(
    hass: HomeAssistant, state: State, config: dict[str, Any]
) -> PackMatch | PackNeutral | PackRecheck | None:
    """Return the completed cycle result while preserving alerts mid-cycle."""
    if not _applies(hass, state):
        return None
    current = _current(state)
    if current is None:
        return PackNeutral()

    cycles = _cycles(hass)
    tracker = cycles.get(state.entity_id)
    if tracker is None:
        tracker = cycles[state.entity_id] = _ExecutionTracker()
        if current > 0:
            tracker.active = _ExecutionCycle(expected_runs=current)
            _capture_running_traces(hass, state.entity_id, tracker.active)
        return PackNeutral()

    if tracker.active is not None:
        _capture_running_traces(hass, state.entity_id, tracker.active)
        _process_completed_traces(tracker.active)
        if current == 0:
            if _cycle_is_complete(tracker.active):
                _queue_completed_cycle(tracker, tracker.active)
                tracker.active = None
            elif tracker.active.rechecks < _TRACE_RECHECK_LIMIT:
                tracker.active.rechecks += 1
                return PackRecheck(_TRACE_RECHECK_DELAY)
            else:
                _discard_incomplete_cycle(tracker, tracker.active)
                tracker.active = None

    result: _ExecutionCycle | None = None
    while tracker.completed:
        completed = tracker.completed.pop(0)
        _process_completed_traces(completed)
        if not _cycle_is_complete(completed):
            _discard_incomplete_cycle(tracker, completed)
            continue
        result = completed
        _apply_cycle_outcome(tracker, result)

    if result is None:
        return PackNeutral()
    if not result.failed:
        return None
    if tracker.consecutive_failures < _failure_threshold(config, state.entity_id):
        return PackNeutral()
    if result.error:
        return PackMatch(
            condition_key="automatic.execution_errors_detail",
            condition_params={"error": result.error},
            value=result.error,
        )
    return PackMatch(condition_key="automatic.execution_errors")


def _reset_runtime(hass: HomeAssistant) -> None:
    """Drop transient trace references when monitoring stops or unloads."""
    hass.data.pop(_DATA_CYCLES, None)


PACK = AutomaticPack(
    id=PACK_ID,
    translation_key="execution_errors",
    prerequisites=(),
    applies=_applies,
    evaluate=_evaluate,
    should_evaluate=_should_evaluate,
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
            entity_domains=_SUPPORTED_DOMAINS,
        ),
    ),
)
