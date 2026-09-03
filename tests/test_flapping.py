"""Flapping occurrence memory, activation and resolution tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from homeassistant.core import Event, State

from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertDetails, AlertStatus
from custom_components.alert_manager.packs.base import PackOccurrence
from custom_components.alert_manager.packs.flapping import PACK


def run(coroutine):
    return asyncio.run(coroutine)


def make_manager(hass, entry):
    manager = AlertManager(hass, entry)
    run(manager.async_setup())
    return manager


def configure(manager, *, occurrences=3, window=3600, recovery=1800, overrides=None):
    run(
        manager.async_update_config(
            {
                "automatic": {
                    "flapping": {
                        "enabled": True,
                        "occurrences": occurrences,
                        "window": window,
                        "recovery": recovery,
                        "device_overrides": overrides or {},
                    }
                }
            }
        )
    )


def occurrence(
    manager, hass, set_now, when, entity_id="sensor.test", *, attributes=None
):
    set_now(when)
    hass.states.set(entity_id, "unavailable", attributes)
    run(manager.async_evaluate_entity(entity_id, observe_occurrences=True))
    hass.states.set(entity_id, "ok", attributes)
    run(manager.async_evaluate_entity(entity_id, observe_occurrences=True))


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
    assert (
        len(manager._pack_runtime["flapping"]["sources"]["unavailable:sensor.test"])
        == 3
    )


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
    normal, _writes = run(transition("ok", first, start + timedelta(seconds=1)))
    _second, writes = run(
        transition("unavailable", normal, start + timedelta(seconds=2))
    )
    assert writes == 1
    assert "flapping:unavailable:sensor.test" in manager.records


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
    stored = manager._pack_runtime["flapping"]["sources"]["unavailable:sensor.test"]
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
            }
        )
    )

    for offset in (0, 30):
        set_now(start + timedelta(seconds=offset))
        hass.states.set("sensor.test", "bad")
        run(manager.async_evaluate_entity("sensor.test", observe_occurrences=True))
        hass.states.set("sensor.test", "ok")
        run(manager.async_evaluate_entity("sensor.test", observe_occurrences=True))

    assert f"flapping:rule:{first['id']}:sensor.test" in manager.records
    assert f"flapping:rule:{second['id']}:sensor.test" in manager.records

    for offset, value in (
        (60, "unavailable"),
        (61, "ok"),
        (90, "unavailable"),
        (91, "ok"),
    ):
        set_now(start + timedelta(seconds=offset))
        hass.states.set("sensor.test", value)
        run(manager.async_evaluate_entity("sensor.test", observe_occurrences=True))
    assert "flapping:unavailable:sensor.test" in manager.records


def test_two_automatic_packs_on_one_entity_are_independent(hass, entry, set_now):
    """Different automatic source IDs retain distinct counters."""
    start = datetime(2026, 9, 3, 8, tzinfo=UTC)
    attributes = {"device_class": "battery"}
    set_now(start)
    hass.states.set("sensor.test", "50", attributes)
    manager = make_manager(hass, entry)
    configure(manager, occurrences=2)

    for offset, value in ((0, "unavailable"), (1, "50"), (2, "10"), (3, "50")):
        set_now(start + timedelta(seconds=offset))
        hass.states.set("sensor.test", value, attributes)
        run(manager.async_evaluate_entity("sensor.test", observe_occurrences=True))
    for offset, value in ((10, "unavailable"), (11, "50"), (12, "10"), (13, "50")):
        set_now(start + timedelta(seconds=offset))
        hass.states.set("sensor.test", value, attributes)
        run(manager.async_evaluate_entity("sensor.test", observe_occurrences=True))

    assert "flapping:unavailable:sensor.test" in manager.records
    assert "flapping:battery:sensor.test" in manager.records


def test_technical_reevaluations_do_not_create_occurrences(hass, entry, set_now):
    """Startup and configuration reevaluations never manufacture flapping."""
    start = datetime(2026, 9, 3, 8, tzinfo=UTC)
    set_now(start)
    hass.states.set("sensor.test", "unavailable")
    manager = make_manager(hass, entry)
    configure(manager, occurrences=2)
    run(manager.async_evaluate_all(restoring=True))
    run(manager.async_evaluate_all())
    assert manager._pack_runtime.get("flapping", {}).get("sources", {}) == {}
    assert not [
        record
        for record in manager.records.values()
        if record.details.type == "flapping"
    ]


def test_flapping_pack_does_not_observe_itself(hass, set_now):
    """A generated flapping alert can never feed the pack's own memory."""
    now = datetime(2026, 9, 3, 8, tzinfo=UTC)
    set_now(now)
    state = State("sensor.test", "unavailable")
    source = AlertDetails(
        id="flapping:unavailable:sensor.test",
        type="flapping",
        entity_id="sensor.test",
        name="Test",
        value=3,
        condition="Instability",
    )
    data = {}
    result = PACK.occurrence_handler(
        hass,
        PackOccurrence(source=source, state=state, occurred_at=now),
        {"occurrences": 2, "window": 60, "recovery": 60},
        data,
    )
    assert result is None
    assert data == {}


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
    assert reloaded._pack_runtime["flapping"]["sources"]
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
    assert manager.history[0].id == alert_id
    assert not [
        timer
        for timer in hass.timers
        if timer["point"] == start + timedelta(seconds=130) and not timer["cancelled"]
    ]
