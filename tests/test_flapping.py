"""Flapping occurrence memory, activation and resolution tests."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from homeassistant.core import Event

from custom_components.alert_manager import manager_runtime
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertDetails, AlertStatus
from custom_components.alert_manager.packs import flapping
from custom_components.alert_manager.packs.base import PackOccurrence

PACK = flapping.PACK


def run(coroutine):
    return asyncio.run(coroutine)


def make_manager(hass, entry):
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    return manager


def configure(
    manager,
    *,
    occurrences=3,
    window=3600,
    recovery=1800,
    overrides=None,
    source_packs=None,
):
    flapping_config = {
        "enabled": True,
        "occurrences": occurrences,
        "window": window,
        "recovery": recovery,
        "device_overrides": overrides or {},
    }
    if source_packs is not None:
        flapping_config["source_packs"] = source_packs
    run(manager.async_update_config({"automatic": {"flapping": flapping_config}}))


def live_state(manager, hass, entity_id, value, attributes=None):
    """Send one state transition through the normal live evaluation batch."""

    async def transition():
        old_state = hass.states.get(entity_id)
        new_state = hass.states.set(entity_id, value, attributes)
        manager._state_changed(
            Event(
                {
                    "entity_id": entity_id,
                    "old_state": old_state,
                    "new_state": new_state,
                }
            )
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    run(transition())


def occurrence(
    manager, hass, set_now, when, entity_id="sensor.test", *, attributes=None
):
    set_now(when)
    live_state(manager, hass, entity_id, "unavailable", attributes)
    live_state(manager, hass, entity_id, "ok", attributes)


def test_threshold_activates_immediately_without_flapping_pending(hass, entry, set_now):
    """The Nth short pending source occurrence emits an immediate active alert."""
    start = datetime(2026, 9, 3, 8, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "ok")
    manager = make_manager(hass, entry)
    configure(manager, occurrences=3)

    occurrence(manager, hass, set_now, start)
    occurrence(manager, hass, set_now, start + timedelta(minutes=5))
    assert not [
        record
        for record in manager.records.values()
        if record.details.type == "flapping"
    ]

    occurrence(manager, hass, set_now, start + timedelta(minutes=10))
    alert_id = "flapping:unavailable:sensor.test"
    record = manager.records[alert_id]
    assert record.status is AlertStatus.ACTIVE
    assert record.active_since == start + timedelta(minutes=10)
    assert record.delay == 0
    assert record.expires_at == start + timedelta(minutes=40)
    assert not [
        item
        for item in manager.public_snapshot()["pending"]
        if item["type"] == "flapping"
    ]
    assert manager.history == []
    assert len(manager._pack_runtime["flapping"]["unavailable:sensor.test"]) == 3


def test_live_state_batch_observes_once_and_uses_one_store_write(hass, entry, set_now):
    """The existing state batch persists its source and flapping changes together."""
    start = datetime(2026, 9, 3, 8, tzinfo=UTC)
    set_now(start)
    old_state = hass.states.set("sensor.test", "ok")
    manager = make_manager(hass, entry)
    configure(manager, occurrences=2)

    async def transition(value, old, when):
        set_now(when)
        new = hass.states.set("sensor.test", value)
        before = hass.store_save_count
        manager._state_changed(
            Event(
                {
                    "entity_id": "sensor.test",
                    "old_state": old,
                    "new_state": new,
                }
            )
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        return new, hass.store_save_count - before

    first, writes = run(transition("unavailable", old_state, start))
    assert writes == 1
    stored_sources = hass.stores["alert_manager"]["pack_runtime"]["flapping"]
    assert stored_sources["unavailable:sensor.test"] == [start.timestamp()]
    normal, _writes = run(transition("ok", first, start + timedelta(seconds=1)))
    _second, writes = run(
        transition("unavailable", normal, start + timedelta(seconds=2))
    )
    assert writes == 1
    assert "flapping:unavailable:sensor.test" in manager.records


def test_occurrence_pack_runs_once_after_every_entity_in_batch(
    hass, entry, set_now, monkeypatch
):
    """Occurrence packs receive one complete callback after source evaluation."""
    start = datetime(2026, 9, 3, 8, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.one", "ok")
    hass.states.set("sensor.two", "ok")
    manager = make_manager(hass, entry)
    configure(manager, occurrences=3)
    calls = []
    original_handler = PACK.occurrence_batch_handler
    assert original_handler is not None

    def handler(hass_arg, occurrences, config, data):
        calls.append(occurrences)
        return original_handler(hass_arg, occurrences, config, data)

    wrapped_pack = replace(PACK, occurrence_batch_handler=handler)
    monkeypatch.setattr(
        manager_runtime,
        "OCCURRENCE_PACKS",
        tuple(
            wrapped_pack if pack.id == wrapped_pack.id else pack
            for pack in manager_runtime.OCCURRENCE_PACKS
        ),
    )

    async def transition_burst():
        for entity_id in ("sensor.one", "sensor.two"):
            old_state = hass.states.get(entity_id)
            new_state = hass.states.set(entity_id, "unavailable")
            manager._state_changed(
                Event(
                    {
                        "entity_id": entity_id,
                        "old_state": old_state,
                        "new_state": new_state,
                    }
                )
            )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    run(transition_burst())
    assert len(calls) == 1
    assert {item.source.id for item in calls[0]} == {
        "unavailable:sensor.one",
        "unavailable:sensor.two",
    }


def test_disabled_occurrence_pack_adds_no_work_to_source_creation(
    hass, entry, set_now, monkeypatch
):
    """No occurrence objects are built while every consumer is disabled."""
    start = datetime(2026, 9, 3, 8, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "ok")
    manager = make_manager(hass, entry)

    def unexpected_occurrence(**_kwargs):
        raise AssertionError("disabled occurrence pack entered the hot path")

    monkeypatch.setattr(manager_runtime, "PackOccurrence", unexpected_occurrence)
    live_state(manager, hass, "sensor.test", "unavailable")

    assert "unavailable:sensor.test" in manager.records
    assert manager._pack_runtime == {}


def test_old_occurrences_leave_the_window(hass, entry, set_now):
    """Only occurrences inside the configured rolling window count."""
    start = datetime(2026, 9, 3, 8, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "ok")
    manager = make_manager(hass, entry)
    configure(manager, occurrences=3, window=60)

    occurrence(manager, hass, set_now, start)
    occurrence(manager, hass, set_now, start + timedelta(seconds=10))
    occurrence(manager, hass, set_now, start + timedelta(seconds=71))
    assert "flapping:unavailable:sensor.test" not in manager.records
    stored = manager._pack_runtime["flapping"]["unavailable:sensor.test"]
    assert len(stored) == 1


def test_rule_and_pack_source_ids_are_independent(hass, entry, set_now):
    """Rules and automatic packs never share a counter for the same entity."""
    start = datetime(2026, 9, 3, 8, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "ok")
    manager = make_manager(hass, entry)
    configure(manager, occurrences=2)
    first = run(
        manager.async_create_rule(
            {
                "name": "Rule one",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "bad",
                "duration": 900,
                "flapping_enabled": True,
            }
        )
    )
    second = run(
        manager.async_create_rule(
            {
                "name": "Rule two",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "bad",
                "duration": 900,
                "flapping_enabled": True,
            }
        )
    )

    for offset in (0, 30):
        set_now(start + timedelta(seconds=offset))
        live_state(manager, hass, "sensor.test", "bad")
        live_state(manager, hass, "sensor.test", "ok")

    assert f"flapping:rule:{first['id']}:sensor.test" in manager.records
    assert f"flapping:rule:{second['id']}:sensor.test" in manager.records

    for offset, value in (
        (60, "unavailable"),
        (61, "ok"),
        (90, "unavailable"),
        (91, "ok"),
    ):
        set_now(start + timedelta(seconds=offset))
        live_state(manager, hass, "sensor.test", value)
    assert "flapping:unavailable:sensor.test" in manager.records


def test_two_automatic_packs_on_one_entity_are_independent(hass, entry, set_now):
    """Different automatic source IDs retain distinct counters."""
    start = datetime(2026, 9, 3, 8, tzinfo=UTC)
    attributes = {"device_class": "battery"}
    set_now(start)
    hass.states.set("sensor.test", "50", attributes)
    manager = make_manager(hass, entry)
    configure(
        manager,
        occurrences=2,
        source_packs={
            "unavailable": {"occurrences": None, "window": None, "recovery": None},
            "battery": {"occurrences": None, "window": None, "recovery": None},
        },
    )

    for offset, value in ((0, "unavailable"), (1, "50"), (2, "10"), (3, "50")):
        set_now(start + timedelta(seconds=offset))
        live_state(manager, hass, "sensor.test", value, attributes)
    for offset, value in ((10, "unavailable"), (11, "50"), (12, "10"), (13, "50")):
        set_now(start + timedelta(seconds=offset))
        live_state(manager, hass, "sensor.test", value, attributes)

    assert "flapping:unavailable:sensor.test" in manager.records
    assert "flapping:battery:sensor.test" in manager.records


def test_custom_rule_flapping_is_opt_in_and_supports_all_overrides(
    hass, entry, set_now
):
    """Rules are disabled by default and may override count, window and recovery."""
    start = datetime(2026, 9, 3, 8, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "ok")
    manager = make_manager(hass, entry)
    configure(manager, occurrences=5, window=3600, recovery=1800)
    disabled = run(
        manager.async_create_rule(
            {
                "name": "Disabled flapping",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "bad",
                "duration": 900,
            }
        )
    )
    enabled = run(
        manager.async_create_rule(
            {
                "name": "Enabled flapping",
                "entity_ids": ["sensor.test"],
                "operator": "equals",
                "value": "bad",
                "duration": 900,
                "flapping_enabled": True,
                "flapping_occurrences": 2,
                "flapping_window": 20,
                "flapping_recovery": 30,
            }
        )
    )

    for offset in (0, 10):
        set_now(start + timedelta(seconds=offset))
        live_state(manager, hass, "sensor.test", "bad")
        live_state(manager, hass, "sensor.test", "ok")

    assert f"flapping:rule:{disabled['id']}:sensor.test" not in manager.records
    alert = manager.records[f"flapping:rule:{enabled['id']}:sensor.test"]
    assert alert.expires_at == start + timedelta(seconds=40)
    assert alert.details.condition_params["duration_seconds"] == 20


def test_automatic_pack_flapping_defaults_and_overrides(hass, entry, set_now):
    """Only unavailable/connectivity default on; a pack may override all settings."""
    start = datetime(2026, 9, 3, 8, tzinfo=UTC)
    attributes = {"device_class": "battery"}
    set_now(start)
    hass.states.set("sensor.test", "50", attributes)
    manager = make_manager(hass, entry)
    configure(manager, occurrences=5, window=3600, recovery=1800)

    for offset, value in ((0, "10"), (1, "50"), (10, "10"), (11, "50")):
        set_now(start + timedelta(seconds=offset))
        live_state(manager, hass, "sensor.test", value, attributes)
    assert "flapping:battery:sensor.test" not in manager.records

    configure(
        manager,
        occurrences=5,
        window=3600,
        recovery=1800,
        source_packs={"battery": {"occurrences": 2, "window": 20, "recovery": 30}},
    )
    for offset, value in ((30, "10"), (31, "50"), (40, "10"), (41, "50")):
        set_now(start + timedelta(seconds=offset))
        live_state(manager, hass, "sensor.test", value, attributes)
    alert = manager.records["flapping:battery:sensor.test"]
    assert alert.expires_at == start + timedelta(seconds=70)
    assert alert.details.condition_params["duration_seconds"] == 20


def test_technical_reevaluations_do_not_create_occurrences(hass, entry, set_now):
    """Startup and configuration reevaluations never manufacture flapping."""
    start = datetime(2026, 9, 3, 8, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)
    configure(manager, occurrences=2)
    run(manager.async_evaluate_all(restoring=True))
    run(manager.async_evaluate_all())
    assert manager._pack_runtime.get("flapping", {}) == {}
    assert not [
        record
        for record in manager.records.values()
        if record.details.type == "flapping"
    ]


def test_flapping_pack_does_not_observe_itself(hass, set_now):
    """A generated flapping alert can never feed the pack's own memory."""
    now = datetime(2026, 9, 3, 8, tzinfo=UTC)
    set_now(now)
    source = AlertDetails(
        id="flapping:unavailable:sensor.test",
        type="flapping",
        entity_id="sensor.test",
        name="Test",
        value=3,
        condition="Instability",
    )
    data = {}
    result = PACK.occurrence_batch_handler(
        hass,
        (PackOccurrence(source=source, occurred_at=now),),
        {},
        data,
    )
    assert result == ()
    assert data == {}


def test_occurrence_memory_keeps_only_the_newest_sources(hass, set_now, monkeypatch):
    """The pack enforces its source bound even between periodic cleanups."""
    now = datetime(2026, 9, 3, 8, tzinfo=UTC)
    set_now(now)
    monkeypatch.setattr(flapping, "MAX_SOURCES", 2)
    occurrences = tuple(
        PackOccurrence(
            source=AlertDetails(
                id=f"unavailable:sensor.test_{index}",
                type="unavailable",
                entity_id=f"sensor.test_{index}",
                name=f"Test {index}",
                value="unavailable",
                condition="Unavailable",
            ),
            occurred_at=now + timedelta(seconds=index),
        )
        for index in range(3)
    )
    data = {}

    PACK.occurrence_batch_handler(
        hass,
        occurrences,
        {
            "automatic": {
                "flapping": {
                    "occurrences": 5,
                    "window": 60,
                    "recovery": 60,
                    "device_overrides": {},
                    "source_packs": {
                        "unavailable": {
                            "occurrences": None,
                            "window": None,
                            "recovery": None,
                        }
                    },
                }
            },
            "rules": [],
        },
        data,
    )

    assert set(data) == {
        "unavailable:sensor.test_1",
        "unavailable:sensor.test_2",
    }


def test_new_occurrence_extends_resolution_and_timer_resolves(hass, entry, set_now):
    """An active source occurrence moves the deadline; quiet time resolves it."""
    start = datetime(2026, 9, 3, 8, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "ok")
    manager = make_manager(hass, entry)
    configure(manager, occurrences=2, recovery=60)
    occurrence(manager, hass, set_now, start)
    occurrence(manager, hass, set_now, start + timedelta(seconds=10))
    alert_id = "flapping:unavailable:sensor.test"
    first_deadline = manager.records[alert_id].expires_at

    occurrence(manager, hass, set_now, start + timedelta(seconds=50))
    record = manager.records[alert_id]
    assert record.expires_at == start + timedelta(seconds=110)
    assert record.expires_at > first_deadline

    timer = next(
        item
        for item in reversed(hass.timers)
        if item["point"] == record.expires_at and not item["cancelled"]
    )

    async def fire_timer():
        set_now(record.expires_at)
        timer["action"](record.expires_at)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    run(fire_timer())
    assert alert_id not in manager.records
    assert manager.history[0].id == alert_id


def test_active_alert_and_occurrences_survive_restart(hass, entry, set_now):
    """The small occurrence store and active resolution deadline are durable."""
    start = datetime(2026, 9, 3, 8, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "ok")
    manager = make_manager(hass, entry)
    configure(manager, occurrences=2, recovery=120)
    occurrence(manager, hass, set_now, start)
    occurrence(manager, hass, set_now, start + timedelta(seconds=10))
    alert_id = "flapping:unavailable:sensor.test"
    expected_deadline = manager.records[alert_id].expires_at
    assert "pack_runtime" in hass.stores["alert_manager"]

    set_now(start + timedelta(seconds=20))
    reloaded = AlertManager(hass, entry)
    run(reloaded.async_setup())
    assert reloaded.records[alert_id].status is AlertStatus.ACTIVE
    assert reloaded.records[alert_id].expires_at == expected_deadline
    assert reloaded._pack_runtime["flapping"]
    assert any(
        timer["point"] == expected_deadline and not timer["cancelled"]
        for timer in hass.timers
    )


def test_device_override_and_device_less_global_settings(
    hass, entry, set_now, registry_entry, device_entry
):
    """Device overrides win while unregistered entities use global values."""
    start = datetime(2026, 9, 3, 8, tzinfo=UTC)
    device = device_entry(hass, device_id="a" * 32)
    registry_entry(hass, "sensor.device", device_id=device.id)
    set_now(start)
    hass.states.set("sensor.device", "ok")
    hass.states.set("sensor.no_device", "ok")
    manager = make_manager(hass, entry)
    configure(
        manager,
        occurrences=3,
        window=3600,
        recovery=1800,
        overrides={device.id: {"occurrences": 2, "window": 120, "recovery": 30}},
    )

    for entity_id in ("sensor.device", "sensor.no_device"):
        occurrence(manager, hass, set_now, start, entity_id)
        occurrence(manager, hass, set_now, start + timedelta(seconds=10), entity_id)
    device_alert = manager.records["flapping:unavailable:sensor.device"]
    assert device_alert.expires_at == start + timedelta(seconds=40)
    assert "flapping:unavailable:sensor.no_device" not in manager.records

    occurrence(
        manager,
        hass,
        set_now,
        start + timedelta(seconds=20),
        "sensor.no_device",
    )
    global_alert = manager.records["flapping:unavailable:sensor.no_device"]
    assert global_alert.expires_at == start + timedelta(seconds=1820)

    run(
        manager.async_update_config(
            {"automatic": {"flapping": {"device_overrides": {}}}}
        )
    )
    assert manager.config["automatic"]["flapping"]["device_overrides"] == {}


def test_disabling_pack_cancels_alert_timer_and_keeps_history(hass, entry, set_now):
    """Disabling the pack cleans runtime work and resolves its active alerts."""
    start = datetime(2026, 9, 3, 8, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "ok")
    manager = make_manager(hass, entry)
    configure(manager, occurrences=2, recovery=120)
    occurrence(manager, hass, set_now, start)
    occurrence(manager, hass, set_now, start + timedelta(seconds=10))
    alert_id = "flapping:unavailable:sensor.test"

    run(manager.async_update_config({"automatic": {"flapping": {"enabled": False}}}))
    assert alert_id not in manager.records
    assert "flapping" not in manager._pack_runtime
    assert flapping._LAST_CLEANUP not in hass.data
    assert manager.history[0].id == alert_id
    assert not [
        timer
        for timer in hass.timers
        if timer["point"] == start + timedelta(seconds=130) and not timer["cancelled"]
    ]


def test_excluding_source_resolves_flapping_through_normal_evaluation(
    hass, entry, set_now
):
    """Generic eligibility removes a deadline alert and its timer."""
    start = datetime(2026, 9, 3, 8, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "ok")
    manager = make_manager(hass, entry)
    configure(manager, occurrences=2, recovery=120)
    occurrence(manager, hass, set_now, start)
    occurrence(manager, hass, set_now, start + timedelta(seconds=10))
    alert_id = "flapping:unavailable:sensor.test"
    deadline = manager.records[alert_id].expires_at

    run(manager.async_update_config({"excluded_entities": ["sensor.test"]}))

    assert alert_id not in manager.records
    assert manager._pack_runtime == {}
    assert manager.history[0].id == alert_id
    assert not [
        timer
        for timer in hass.timers
        if timer["point"] == deadline and not timer["cancelled"]
    ]
