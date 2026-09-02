"""Automation and script execution error pack behavior tests."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from homeassistant.components.automation import DATA_COMPONENT
from homeassistant.components.trace.const import DATA_TRACE
from homeassistant.core import Event

from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.packs import execution_errors

_NO_ERROR = object()


class _Trace:
    """Mutable in-memory short trace with a forbidden full-trace API."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.state = "running"
        self.error: object = _NO_ERROR
        self.finish_at = None
        self.short_reads = 0

    def finish(self, error: object = _NO_ERROR) -> None:
        self.state = "stopped"
        self.error = error
        self.finish_at = datetime.now(UTC)

    def as_short_dict(self):
        self.short_reads += 1
        result = {
            "run_id": self.run_id,
            "state": self.state,
            "script_execution": "error" if self.error is not _NO_ERROR else "finished",
            "timestamp": {
                "start": datetime.now(UTC),
                "finish": self.finish_at,
            },
        }
        if self.error is not _NO_ERROR:
            result["error"] = self.error
        return result

    def as_extended_dict(self):  # pragma: no cover - a call must fail the test
        raise AssertionError("Alert Manager must never load a complete trace")


class _EntityComponent:
    def __init__(self, entity_id: str, unique_id: str) -> None:
        self.entity_id = entity_id
        self.entity = SimpleNamespace(unique_id=unique_id)

    def get_entity(self, entity_id: str):
        return self.entity if entity_id == self.entity_id else None


class _Scenario:
    entity_id = "automation.test"
    unique_id = "stable-automation-id"
    component_key = DATA_COMPONENT

    def __init__(self, hass, manager, *, trace_limit=5) -> None:
        self.hass = hass
        self.manager = manager
        self.trace_limit = trace_limit
        self.runs = OrderedDict()
        self.current = 0

    @classmethod
    async def create(cls, hass, entry, *, trace_limit=5):
        hass.states.set(cls.entity_id, "on", {"current": 0})
        hass.data[cls.component_key] = _EntityComponent(cls.entity_id, cls.unique_id)
        bucket = SimpleNamespace(runs=OrderedDict())
        domain = cls.entity_id.partition(".")[0]
        hass.data[DATA_TRACE] = {f"{domain}.{cls.unique_id}": bucket}
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        manager.config["automatic"]["execution_errors"]["delay"] = 0
        scenario = cls(hass, manager, trace_limit=trace_limit)
        scenario.runs = bucket.runs
        return scenario

    def _state_change(self, current: int) -> None:
        old_state = self.hass.states.get(self.entity_id)
        new_state = self.hass.states.set(
            self.entity_id,
            "on",
            {"current": current},
        )
        self.current = current
        self.manager._state_changed(
            Event(
                {
                    "entity_id": self.entity_id,
                    "old_state": old_state,
                    "new_state": new_state,
                }
            )
        )

    def start(self, run_id: str) -> _Trace:
        trace = _Trace(run_id)
        self.runs[run_id] = trace
        while len(self.runs) > self.trace_limit:
            self.runs.popitem(last=False)
        self._state_change(self.current + 1)
        return trace

    def finish(self, trace: _Trace, error: object = _NO_ERROR) -> None:
        self._state_change(self.current - 1)
        # Home Assistant finalizes the trace after writing the lower current state.
        trace.finish(error)

    async def flush(self) -> None:
        await asyncio.sleep(0)
        await asyncio.sleep(0)


class _ScriptScenario(_Scenario):
    entity_id = "script.test"
    unique_id = "stable-script-id"
    component_key = "script"


@pytest.fixture(params=[_Scenario, _ScriptScenario], ids=["automation", "script"])
def scenario_cls(request):
    """Exercise the same execution-cycle behavior for both HA domains."""
    return request.param


def test_pack_ignores_other_domains(hass):
    """Entities other than automations and scripts do not participate."""
    state = hass.states.set("sensor.other", "on", {"current": 0})

    assert not execution_errors.PACK.applies(hass, state)
    assert execution_errors.PACK.evaluate(hass, state, {}) is None


def test_pack_applies_to_scripts(hass):
    """Script entities participate in the same automatic pack."""
    state = hass.states.set("script.test", "off", {"current": 0})

    assert execution_errors.PACK.applies(hass, state)


def test_start_and_long_running_execution_are_neutral(hass, entry, scenario_cls):
    """A 0->1 transition and later updates while current stays positive do not alert."""

    async def scenario():
        runtime = await scenario_cls.create(hass, entry)
        trace = runtime.start("long")
        await runtime.flush()
        assert runtime.manager.records == {}

        old_state = hass.states.get(runtime.entity_id)
        new_state = hass.states.set(runtime.entity_id, "on", {"current": 1, "x": 1})
        runtime.manager._state_changed(
            Event(
                {
                    "entity_id": runtime.entity_id,
                    "old_state": old_state,
                    "new_state": new_state,
                }
            )
        )
        await runtime.flush()
        assert trace.state == "running"
        assert runtime.manager.records == {}

    asyncio.run(scenario())


def test_single_success_does_not_alert(hass, entry, scenario_cls):
    """A complete error-free 1->0 cycle resolves to no occurrence."""

    async def scenario():
        runtime = await scenario_cls.create(hass, entry)
        run = runtime.start("success")
        runtime.finish(run)
        await runtime.flush()
        assert runtime.manager.records == {}

    asyncio.run(scenario())


def test_single_error_creates_alert_with_trace_message(hass, entry, scenario_cls):
    """The short trace error becomes the alert condition and value."""

    async def scenario():
        runtime = await scenario_cls.create(hass, entry)
        run = runtime.start("failed")
        runtime.finish(run, "Light service unavailable")
        await runtime.flush()

        record = runtime.manager.records[f"execution_errors:{runtime.entity_id}"]
        assert record.status.value == "active"
        assert record.details.value == "Light service unavailable"
        assert record.details.condition.endswith("Light service unavailable")

    asyncio.run(scenario())


def test_error_then_success_resolves_only_after_complete_cycle(
    hass, entry, scenario_cls
):
    """An error survives while running and resolves after a successful cycle."""

    async def scenario():
        runtime = await scenario_cls.create(hass, entry)
        failed = runtime.start("failed")
        runtime.finish(failed, "First failure")
        await runtime.flush()
        alert_id = f"execution_errors:{runtime.entity_id}"
        assert alert_id in runtime.manager.records

        success = runtime.start("success")
        await runtime.flush()
        assert alert_id in runtime.manager.records
        runtime.finish(success)
        await runtime.flush()
        assert alert_id not in runtime.manager.records
        assert any(item.id == alert_id for item in runtime.manager.history)

    asyncio.run(scenario())


def test_error_then_error_keeps_and_updates_alert(hass, entry, scenario_cls):
    """A later failed cycle retains the stable occurrence with its new message."""

    async def scenario():
        runtime = await scenario_cls.create(hass, entry)
        first = runtime.start("first")
        runtime.finish(first, "First failure")
        await runtime.flush()
        alert_id = f"execution_errors:{runtime.entity_id}"
        record = runtime.manager.records[alert_id]

        second = runtime.start("second")
        runtime.finish(second, "Second failure")
        await runtime.flush()

        assert runtime.manager.records[alert_id] is record
        assert record.details.condition.endswith("Second failure")

    asyncio.run(scenario())


def test_per_entity_consecutive_failure_threshold(hass, entry, scenario_cls):
    """A configured automation or script alerts after enough failed cycles."""

    async def scenario():
        runtime = await scenario_cls.create(hass, entry)
        runtime.manager.config["automatic"]["execution_errors"][
            "failure_thresholds"
        ] = {runtime.entity_id: 3}
        alert_id = f"execution_errors:{runtime.entity_id}"

        for index in range(2):
            failed = runtime.start(f"failed-{index}")
            runtime.finish(failed, f"Failure {index}")
            await runtime.flush()
            assert alert_id not in runtime.manager.records

        failed = runtime.start("failed-2")
        runtime.finish(failed, "Third consecutive failure")
        await runtime.flush()
        assert runtime.manager.records[alert_id].details.condition.endswith(
            "Third consecutive failure"
        )

        success = runtime.start("success")
        runtime.finish(success)
        await runtime.flush()
        assert alert_id not in runtime.manager.records

        failed = runtime.start("failed-after-success")
        runtime.finish(failed, "Counter restarted")
        await runtime.flush()
        assert alert_id not in runtime.manager.records

    asyncio.run(scenario())


def test_parallel_cycle_accumulates_error_beyond_ha_trace_limit(
    hass, entry, scenario_cls
):
    """Each decrease is accumulated even after HA evicts an older run trace."""

    async def scenario():
        runtime = await scenario_cls.create(hass, entry, trace_limit=2)
        runs = [runtime.start(f"run-{index}") for index in range(6)]
        assert "run-0" not in runtime.runs

        runtime.finish(runs[0], "Evicted trace failed")
        for run in runs[1:]:
            runtime.finish(run)
        await runtime.flush()

        record = runtime.manager.records[f"execution_errors:{runtime.entity_id}"]
        assert record.details.condition.endswith("Evicted trace failed")
        assert all(run.short_reads > 0 for run in runs)

    asyncio.run(scenario())


def test_parallel_success_resolves_existing_error(hass, entry, scenario_cls):
    """Every run in a parallel cycle must succeed before resolution."""

    async def scenario():
        runtime = await scenario_cls.create(hass, entry)
        failed = runtime.start("failed")
        runtime.finish(failed, "Failure")
        await runtime.flush()
        alert_id = f"execution_errors:{runtime.entity_id}"

        runs = [runtime.start(f"ok-{index}") for index in range(3)]
        for run in (runs[1], runs[0], runs[2]):
            runtime.finish(run)
        await runtime.flush()
        assert alert_id not in runtime.manager.records

    asyncio.run(scenario())


def test_old_error_trace_is_not_part_of_new_cycle(hass, entry, scenario_cls):
    """A stopped trace present before cycle start cannot create a new alert."""

    async def scenario():
        old = _Trace("old-error")
        old.finish("Old failure")
        runtime = await scenario_cls.create(hass, entry)
        runtime.runs[old.run_id] = old

        success = runtime.start("new-success")
        runtime.finish(success)
        await runtime.flush()
        assert runtime.manager.records == {}

    asyncio.run(scenario())


def test_running_trace_is_never_interpreted_as_finished(hass, entry, scenario_cls):
    """A current=0 state cannot finalize a cycle while its trace still runs."""

    async def scenario():
        runtime = await scenario_cls.create(hass, entry)
        run = runtime.start("late-trace")
        runtime._state_change(0)
        await runtime.flush()
        assert runtime.manager.records == {}

        run.finish("Late failure")
        await runtime.manager.async_evaluate_entity(runtime.entity_id)
        assert f"execution_errors:{runtime.entity_id}" in runtime.manager.records

    asyncio.run(scenario())


def test_monitoring_disabled_ignores_cycles_and_freezes_existing_alert(
    hass, entry, scenario_cls
):
    """Monitoring off keeps existing records but does not observe new executions."""

    async def scenario():
        runtime = await scenario_cls.create(hass, entry)
        failed = runtime.start("initial-error")
        runtime.finish(failed, "Initial failure")
        await runtime.flush()
        alert_id = f"execution_errors:{runtime.entity_id}"

        await runtime.manager.async_set_monitoring(False)
        success = runtime.start("ignored-success")
        runtime.finish(success)
        await runtime.flush()
        assert alert_id in runtime.manager.records

        await runtime.manager.async_set_monitoring(True)
        assert alert_id in runtime.manager.records

    asyncio.run(scenario())


def test_excluded_execution_cycle_is_not_replayed_later(hass, entry, scenario_cls):
    """Generic entity exclusions prevent observation as well as alert creation."""

    async def scenario():
        runtime = await scenario_cls.create(hass, entry)
        await runtime.manager.async_update_config(
            {"excluded_entities": [runtime.entity_id]}
        )
        failed = runtime.start("excluded-error")
        runtime.finish(failed, "Excluded failure")
        await runtime.flush()
        assert runtime.manager.records == {}

        await runtime.manager.async_update_config({"excluded_entities": []})
        assert runtime.manager.records == {}

    asyncio.run(scenario())
