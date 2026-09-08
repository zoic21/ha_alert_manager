"""Event-driven notification batching and reminder regression tests."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from homeassistant.core import CoreState, Event

from custom_components.alert_manager.const import (
    DEFAULT_CONFIG,
    EVENT_ALERT_RESOLVED,
    EVENT_ALERT_STARTED,
    EVENT_ALERT_UNACKNOWLEDGED,
    SIGNAL_NOTIFICATION_LIFECYCLE,
)
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import (
    AlertDetails,
    AlertRecord,
    AlertStatus,
)
from custom_components.alert_manager.notification_runtime import (
    NotificationRuntime,
    _NotificationItem,
)
from custom_components.alert_manager.notifications import NotificationManager
from custom_components.alert_manager.runtime_phase import RuntimePhase
from custom_components.alert_manager.validation import validate_config


class _DeliverySpy:
    """Capture rendered deliveries without registering a notify integration."""

    def __init__(self, *, success: bool = True) -> None:
        self.calls: list[dict] = []
        self.success = success

    def text(self, _key: str, fallback: str) -> str:
        return fallback

    async def async_send(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        delivered = list(kwargs["targets"]) if self.success else []
        return {
            "success": self.success,
            "delivered_targets": delivered,
            "failed_targets": [],
        }


def _profile(*, reminder_interval: int | None = None) -> dict:
    return {
        "id": "profile",
        "name": "Profile",
        "enabled": True,
        "targets": ["notify.phone"],
        "label_ids": [],
        "default_policy": {
            "notify_on_start": True,
            "notify_on_resolved": True,
            "reminder_interval": reminder_interval,
        },
        "exceptions": [],
    }


def _event_data(alert_id: str, *, entity_id: str, device_id: str | None) -> dict:
    return {
        "id": alert_id,
        "entity_id": entity_id,
        "name": entity_id,
        "type": "unavailable",
        "device_id": device_id,
        "device_name": "Thermostat" if device_id else None,
        "condition": "Unavailable",
    }


def _active_record(now: datetime) -> AlertRecord:
    return AlertRecord(
        details=AlertDetails(
            id="unavailable:sensor.test",
            type="unavailable",
            entity_id="sensor.test",
            name="Test",
            value="unavailable",
            condition="Unavailable",
        ),
        status=AlertStatus.ACTIVE,
        detected_at=now,
        due_at=now,
        delay=0,
        active_since=now,
    )


@pytest.mark.parametrize(
    ("kind", "icon"), [("started", "🚨"), ("reminder", "🔔"), ("resolved", "✅")]
)
@pytest.mark.parametrize("language", [None, "en", "fr"])
@pytest.mark.parametrize("count", [1, 2])
@pytest.mark.parametrize("grouped", [False, True])
def test_notification_compact_titles(
    hass, entry, kind, icon, language, count, grouped
) -> None:
    """Render concise singular/plural titles for individual and grouped alerts."""
    delivery = NotificationManager(hass, lambda: [])
    if language:
        path = (
            Path(__file__).parents[1]
            / "custom_components/alert_manager/translations"
            / f"{language}.json"
        )
        catalog = json.loads(path.read_text())["config_panel"]["notifications"]
        delivery.set_translations(
            {
                f"component.alert_manager.config_panel.notifications.{key}": value
                for key, value in catalog.items()
            }
        )
    runtime = NotificationRuntime(hass, entry, lambda: {}, lambda: {}, delivery)
    items = [
        _NotificationItem.from_event(
            _event_data(
                f"unavailable:sensor.test_{index}",
                entity_id=f"sensor.test_{index}",
                device_id="thermostat" if grouped else None,
            )
            | {"message": "Previous error"}
        )
        for index in range(count)
    ]

    title, message = runtime._render_batch(kind, items)

    expected_titles = {
        "fr": {
            "started": ("Nouvelle alerte", "2 nouvelles alertes"),
            "resolved": ("Retour à la normale", "2 alertes résolues"),
            "reminder": ("Rappel d\u2019alerte", "Rappel : 2 alertes"),
        },
        "en": {
            "started": ("New alert", "2 new alerts"),
            "resolved": ("Back to normal", "2 alerts resolved"),
            "reminder": ("Alert reminder", "Reminder: 2 alerts"),
        },
    }
    assert title == f"{icon} {expected_titles[language or 'en'][kind][count - 1]}"
    assert title.count(icon) == 1
    assert "{count}" not in title
    assert len(message.splitlines()) == (1 if grouped else count)
    if kind == "resolved":
        assert "Previous error" not in message
        assert "Unavailable" not in message
        assert "unavailable" not in message
        if grouped and count > 1:
            expected = (
                catalog["grouped_resolved"] if language else "{count} alerts resolved"
            )
            expected = expected.replace("{count}", str(count))
        else:
            expected = catalog["on_resolved"] if language else "Return to normal"
        assert expected in message
    elif not grouped or count == 1:
        assert "Previous error" in message


@pytest.mark.parametrize(
    ("kind", "count", "expected_url"),
    [
        ("resolved", 1, "/alert-manager/history"),
        ("resolved", 2, "/alert-manager/history"),
        ("started", 1, "/alert-manager?alert=unavailable%3Asensor.test_0"),
        ("started", 2, "/alert-manager"),
        ("reminder", 1, "/alert-manager?alert=unavailable%3Asensor.test_0"),
        ("reminder", 2, "/alert-manager"),
    ],
)
def test_notification_batch_url(kind, count, expected_url) -> None:
    """Route every resolution to history and preserve live alert deep links."""
    items = [
        _NotificationItem.from_event(
            _event_data(
                f"unavailable:sensor.test_{index}",
                entity_id=f"sensor.test_{index}",
                device_id=None,
            )
        )
        for index in range(count)
    ]

    assert NotificationRuntime._batch_url(kind, items) == expected_url


def test_start_resolved_inside_batch_window_is_cancelled(hass, entry) -> None:
    """A transient condition creates neither a start nor a resolved delivery."""

    async def scenario() -> None:
        config = validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [_profile()]}
        )
        delivery = _DeliverySpy()
        runtime = NotificationRuntime(hass, entry, lambda: config, lambda: {}, delivery)
        await runtime.async_setup()
        event = _event_data(
            "unavailable:sensor.test",
            entity_id="sensor.test",
            device_id=None,
        )

        await runtime._async_handle_event(EVENT_ALERT_STARTED, event)
        await runtime._async_handle_event(EVENT_ALERT_RESOLVED, event)

        assert runtime._batches == {}
        assert delivery.calls == []
        await runtime.async_unload()

    asyncio.run(scenario())


def test_timed_expiry_notifies_without_reminders_but_respects_start_policy(hass, entry):
    """Only automatic expiry re-notifies; manual unacknowledgement stays unchanged."""

    async def scenario():
        for notify in (True, False):
            profile = _profile()
            profile["default_policy"]["notify_on_start"] = notify
            config = validate_config(
                {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [profile]}
            )
            runtime = NotificationRuntime(
                hass, entry, lambda config=config: config, lambda: {}, _DeliverySpy()
            )
            await runtime.async_setup()
            event = _event_data(
                "unavailable:sensor.test", entity_id="sensor.test", device_id=None
            )
            await runtime._async_handle_event(EVENT_ALERT_UNACKNOWLEDGED, event)
            assert not runtime._batches
            event["acknowledgement_expired"] = True
            await runtime._async_handle_event(EVENT_ALERT_UNACKNOWLEDGED, event)
            assert bool(runtime._batches) is notify
            assert runtime._runtime["profile"][event["id"]].next_reminder is None
            await runtime.async_unload()

    asyncio.run(scenario())


def test_runtime_consumes_only_trusted_internal_lifecycle_signal(hass, entry) -> None:
    """Public bus events remain observable but cannot manufacture deliveries."""

    async def scenario() -> None:
        config = validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [_profile()]}
        )
        runtime = NotificationRuntime(
            hass, entry, lambda: config, lambda: {}, _DeliverySpy()
        )
        await runtime.async_setup()
        event = _event_data(
            "unavailable:sensor.test",
            entity_id="sensor.test",
            device_id=None,
        )

        assert hass.bus.listeners[EVENT_ALERT_STARTED] == []
        hass.bus.async_fire(EVENT_ALERT_STARTED, event)
        await asyncio.sleep(0)
        assert runtime._batches == {}

        hass.dispatchers[SIGNAL_NOTIFICATION_LIFECYCLE][0](EVENT_ALERT_STARTED, event)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert (
            "unavailable:sensor.test" in runtime._batches[("profile", "started")].items
        )
        await runtime.async_unload()

    asyncio.run(scenario())


def test_event_queued_before_config_pause_is_discarded(hass, entry) -> None:
    """A queued lifecycle task cannot cross a configuration transaction."""

    async def scenario() -> None:
        config = validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [_profile()]}
        )
        runtime = NotificationRuntime(
            hass, entry, lambda: config, lambda: {}, _DeliverySpy()
        )
        await runtime.async_setup()
        await runtime._runtime_lock.acquire()
        hass.dispatchers[SIGNAL_NOTIFICATION_LIFECYCLE][0](
            EVENT_ALERT_STARTED,
            _event_data(
                "unavailable:sensor.test",
                entity_id="sensor.test",
                device_id=None,
            ),
        )
        runtime.pause_events()
        runtime.resume_events()
        runtime._runtime_lock.release()

        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert runtime._batches == {}
        assert all(not entries for entries in runtime._runtime.values())
        await runtime.async_unload()

    asyncio.run(scenario())


def test_event_queued_before_shutdown_is_discarded(hass, entry) -> None:
    """A lifecycle task waiting on the runtime lock cannot cross shutdown."""

    async def scenario() -> None:
        config = validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [_profile()]}
        )
        runtime = NotificationRuntime(
            hass, entry, lambda: config, lambda: {}, _DeliverySpy()
        )
        await runtime.async_setup()
        await runtime._runtime_lock.acquire()
        hass.dispatchers[SIGNAL_NOTIFICATION_LIFECYCLE][0](
            EVENT_ALERT_STARTED,
            _event_data(
                "unavailable:sensor.test",
                entity_id="sensor.test",
                device_id=None,
            ),
        )
        runtime.begin_shutdown()
        runtime.resume_events()
        runtime._runtime_lock.release()

        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert runtime._batches == {}
        assert all(not entries for entries in runtime._runtime.values())
        assert runtime._accept_events is False
        await runtime.async_unload()
        assert not hass.dispatchers[SIGNAL_NOTIFICATION_LIFECYCLE]
        assert not [timer for timer in hass.timers if not timer["cancelled"]]

    asyncio.run(scenario())


def test_runtime_save_queued_before_shutdown_is_discarded(hass, entry) -> None:
    """A coalesced save waiting on the runtime lock cannot cross shutdown."""

    async def scenario() -> None:
        config = validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [_profile()]}
        )
        runtime = NotificationRuntime(
            hass, entry, lambda: config, lambda: {}, _DeliverySpy()
        )
        await runtime.async_setup()
        await runtime._async_handle_event(
            EVENT_ALERT_STARTED,
            _event_data(
                "unavailable:sensor.test",
                entity_id="sensor.test",
                device_id=None,
            ),
        )
        save_timer = next(
            timer
            for timer in hass.timers
            if not timer["cancelled"]
            and "_schedule_runtime_save.<locals>.timer_due"
            in timer["action"].__qualname__
        )

        await runtime._runtime_lock.acquire()
        save_timer["action"](save_timer["point"])
        await asyncio.sleep(0)
        runtime.begin_shutdown()
        saves_at_shutdown = hass.store_save_count
        runtime._runtime_lock.release()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert hass.store_save_count == saves_at_shutdown
        await runtime.async_unload()

    asyncio.run(scenario())


def test_reminder_queued_before_shutdown_is_discarded(hass, entry, set_now) -> None:
    """A reminder waiting on the runtime lock cannot deliver after shutdown."""

    async def scenario() -> None:
        now = datetime(2026, 9, 4, 12, 30, tzinfo=UTC)
        set_now(now)
        config = validate_config(
            {
                **deepcopy(DEFAULT_CONFIG),
                "notification_profiles": [_profile(reminder_interval=300)],
            }
        )
        record = _active_record(now - timedelta(minutes=10))
        delivery = _DeliverySpy()
        runtime = NotificationRuntime(
            hass,
            entry,
            lambda: config,
            lambda: {record.details.id: record},
            delivery,
        )
        await runtime.async_setup()
        runtime._runtime["profile"][record.details.id].next_reminder = now

        await runtime._runtime_lock.acquire()
        runtime._create_task(
            runtime._async_send_reminders(),
            "alert_manager notification reminders",
        )
        await asyncio.sleep(0)
        runtime.begin_shutdown()
        runtime._runtime_lock.release()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert delivery.calls == []
        await runtime.async_unload()

    asyncio.run(scenario())


def test_notification_setup_failure_removes_lifecycle_subscription(hass, entry) -> None:
    """A failed setup leaves no listener or partially initialized runtime."""

    async def scenario() -> None:
        config = validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [_profile()]}
        )
        runtime = NotificationRuntime(
            hass, entry, lambda: config, lambda: {}, _DeliverySpy()
        )

        async def fail_config_update(*, reset_reminders: bool) -> None:
            raise RuntimeError("config update failed")

        runtime._async_config_updated_locked = fail_config_update

        try:
            await runtime.async_setup()
        except RuntimeError as err:
            assert str(err) == "config update failed"
        else:  # pragma: no cover - explicit failure contract
            raise AssertionError("setup unexpectedly succeeded")

        assert not hass.dispatchers[SIGNAL_NOTIFICATION_LIFECYCLE]
        assert runtime._unsubscribe == []
        assert runtime._setup_complete is False

    asyncio.run(scenario())


@pytest.mark.parametrize("delay", [10, 30, 300])
def test_fixed_window_groups_two_device_alerts_in_one_delivery(
    hass, entry, delay
) -> None:
    """Adding an alert does not extend the first batch deadline."""

    async def scenario() -> None:
        config = validate_config(
            {
                **deepcopy(DEFAULT_CONFIG),
                "notification_profiles": [_profile()],
                "notification_batch_delay": delay,
            }
        )
        delivery = _DeliverySpy()
        runtime = NotificationRuntime(hass, entry, lambda: config, lambda: {}, delivery)
        await runtime.async_setup()
        device_id = "a" * 32

        await runtime._async_handle_event(
            EVENT_ALERT_STARTED,
            _event_data(
                "unavailable:sensor.one",
                entity_id="sensor.one",
                device_id=device_id,
            ),
        )
        first_deadline = max(
            timer["point"] for timer in hass.timers if not timer["cancelled"]
        )
        assert first_deadline == datetime(2026, 8, 24, 12, tzinfo=UTC) + timedelta(
            seconds=delay
        )
        config["notification_batch_delay"] = 120
        await runtime._async_handle_event(
            EVENT_ALERT_STARTED,
            _event_data(
                "unavailable:sensor.two",
                entity_id="sensor.two",
                device_id=device_id,
            ),
        )

        batch_timers = [
            timer
            for timer in hass.timers
            if not timer["cancelled"] and timer["point"] == first_deadline
        ]
        assert len(batch_timers) == 1
        batch_timers[0]["action"](first_deadline)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert len(delivery.calls) == 1
        assert delivery.calls[0]["click_url"] == "/alert-manager"
        assert delivery.calls[0]["message"] == "• Thermostat — 2 alerts"
        assert runtime.usage_snapshot() == {"last_24h": {"profile": 1}}
        await runtime._async_handle_event(
            EVENT_ALERT_STARTED,
            _event_data(
                "unavailable:sensor.three", entity_id="sensor.three", device_id=None
            ),
        )
        assert hass.timers[-1]["point"] == datetime(2026, 8, 24, 12, 2, tzinfo=UTC)
        await runtime.async_unload()

    asyncio.run(scenario())


def test_usage_counts_started_resolved_and_reminder_batches(
    hass, entry, set_now
) -> None:
    """Every successful production batch counts once, regardless of its targets."""

    async def scenario() -> None:
        now = datetime(2026, 9, 4, 12, 30, tzinfo=UTC)
        set_now(now)
        config = validate_config(
            {
                **deepcopy(DEFAULT_CONFIG),
                "notification_profiles": [_profile(reminder_interval=300)],
            }
        )
        config["notification_profiles"][0]["targets"] = [
            "notify.phone",
            "notify.tablet",
        ]
        record = _active_record(now)
        runtime = NotificationRuntime(
            hass,
            entry,
            lambda: config,
            lambda: {record.details.id: record},
            _DeliverySpy(),
        )
        await runtime.async_setup()
        event = _event_data(
            record.details.id,
            entity_id=record.details.entity_id,
            device_id=None,
        )

        await runtime._async_handle_event(EVENT_ALERT_STARTED, event)
        await runtime._async_flush_batch("profile", "started")
        runtime._runtime["profile"][record.details.id].next_reminder = now
        await runtime._async_send_reminders()
        await runtime._async_handle_event(EVENT_ALERT_RESOLVED, event)
        await runtime._async_flush_batch("profile", "resolved")

        assert runtime.usage_snapshot() == {"last_24h": {"profile": 3}}
        await runtime.async_unload()

    asyncio.run(scenario())


def test_usage_ignores_failed_deliveries(hass, entry) -> None:
    """A batch with no successful target does not count as profile usage."""

    async def scenario() -> None:
        config = validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [_profile()]}
        )
        runtime = NotificationRuntime(
            hass, entry, lambda: config, lambda: {}, _DeliverySpy(success=False)
        )
        await runtime.async_setup()
        await runtime._async_handle_event(
            EVENT_ALERT_STARTED,
            _event_data(
                "unavailable:sensor.test",
                entity_id="sensor.test",
                device_id=None,
            ),
        )
        await runtime._async_flush_batch("profile", "started")

        assert runtime.usage_snapshot() == {"last_24h": {"profile": 0}}
        await runtime.async_unload()

    asyncio.run(scenario())


def test_runtime_writes_are_coalesced_during_an_event_burst(hass, entry) -> None:
    """Many lifecycle events schedule one runtime storage write."""

    async def scenario() -> None:
        config = validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [_profile()]}
        )
        runtime = NotificationRuntime(
            hass, entry, lambda: config, lambda: {}, _DeliverySpy()
        )
        await runtime.async_setup()

        for index in range(25):
            await runtime._async_handle_event(
                EVENT_ALERT_STARTED,
                _event_data(
                    f"unavailable:sensor.test_{index}",
                    entity_id=f"sensor.test_{index}",
                    device_id=None,
                ),
            )

        save_timers = [
            timer
            for timer in hass.timers
            if not timer["cancelled"]
            and timer["point"] == datetime(2026, 8, 24, 12, 0, 1, tzinfo=UTC)
        ]
        assert len(save_timers) == 1
        assert hass.store_save_count == 0

        save_timers[0]["action"](save_timers[0]["point"])
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert hass.store_save_count == 1
        assert (
            len(hass.stores["alert_manager.notifications"]["profiles"]["profile"]) == 25
        )
        await runtime.async_unload()

    asyncio.run(scenario())


def test_resolution_cleans_runtime_after_matching_label_is_removed(hass, entry) -> None:
    """A label change cannot leave a resolved alert persisted indefinitely."""

    async def scenario() -> None:
        profile = _profile()
        profile["label_ids"] = ["important"]
        config = validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [profile]}
        )
        hass.entity_registry.entries["sensor.test"] = SimpleNamespace(
            labels={"important"}, device_id=None
        )
        runtime = NotificationRuntime(
            hass, entry, lambda: config, lambda: {}, _DeliverySpy()
        )
        await runtime.async_setup()
        event = _event_data(
            "unavailable:sensor.test",
            entity_id="sensor.test",
            device_id=None,
        )

        await runtime._async_handle_event(EVENT_ALERT_STARTED, event)
        hass.entity_registry.entries["sensor.test"].labels = set()
        runtime.registry_changed()
        await runtime._async_handle_event(EVENT_ALERT_RESOLVED, event)

        assert runtime._runtime.get("profile", {}) == {}
        await runtime.async_unload()

    asyncio.run(scenario())


def test_queued_resolution_survives_registry_runtime_refresh(hass, entry) -> None:
    """A registry refresh cannot erase that a queued resolution was tracked."""

    async def scenario() -> None:
        profile = _profile()
        profile["label_ids"] = ["important"]
        config = validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [profile]}
        )
        registry = SimpleNamespace(labels={"important"}, device_id=None)
        hass.entity_registry.entries["sensor.test"] = registry
        runtime = NotificationRuntime(
            hass, entry, lambda: config, lambda: {}, _DeliverySpy()
        )
        await runtime.async_setup()
        alert_id = "unavailable:sensor.test"
        event = _event_data(alert_id, entity_id="sensor.test", device_id=None)
        await runtime._async_handle_event(EVENT_ALERT_STARTED, event)
        await runtime._async_flush_batch("profile", "started")

        registry.labels.clear()
        runtime.registry_changed()
        await runtime._runtime_lock.acquire()
        try:
            hass.dispatchers[SIGNAL_NOTIFICATION_LIFECYCLE][0](
                EVENT_ALERT_RESOLVED, event
            )
            await runtime._async_config_updated_locked(reset_reminders=False)
            assert alert_id not in runtime._runtime["profile"]
        finally:
            runtime._runtime_lock.release()

        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert alert_id in runtime._batches[("profile", "resolved")].items
        await runtime.async_unload()

    asyncio.run(scenario())


def test_startup_registry_refresh_keeps_tracked_resolution(
    hass, entry, registry_entry
) -> None:
    """Startup reconciliation preserves resolved delivery across label refresh."""

    async def scenario() -> None:
        profile = _profile(reminder_interval=300)
        profile["label_ids"] = ["important"]
        registry = registry_entry(hass, "sensor.test", labels={"important"})
        hass.states.set("sensor.test", "unavailable")

        first = AlertManager(hass, entry)
        assert await first.async_setup() is True
        await first.async_update_config(
            {
                "automatic": {"unavailable": {"delay": 0}},
                "notification_profiles": [profile],
            }
        )
        alert_id = "unavailable:sensor.test"
        assert first.records[alert_id].status is AlertStatus.ACTIVE
        assert alert_id in first.notification_runtime._runtime["profile"]
        await first.async_unload()

        hass.state = CoreState.starting
        hass.states.set("sensor.test", "ok")
        restarted = AlertManager(hass, entry)
        assert await restarted.async_setup() is True
        assert alert_id in restarted.notification_runtime._runtime["profile"]

        lifecycle_release = asyncio.Event()
        original_handle_event = restarted.notification_runtime._async_handle_event

        async def delayed_handle_event(*args, **kwargs):
            await lifecycle_release.wait()
            await original_handle_event(*args, **kwargs)

        restarted.notification_runtime._async_handle_event = delayed_handle_event
        hass.state = CoreState.running
        restarted._home_assistant_started(Event())
        registry.labels.clear()
        restarted._registry_changed(
            Event({"action": "update", "entity_id": "sensor.test"})
        )

        reconciliation_timer = next(
            timer
            for timer in hass.timers
            if not timer["cancelled"]
            and "_schedule_startup_reconciliation" in timer["action"].__qualname__
        )
        reconciliation_timer["cancelled"] = True
        reconciliation_timer["action"](reconciliation_timer["point"])
        for _index in range(5):
            await asyncio.sleep(0)

        assert restarted._runtime_phase is RuntimePhase.RUNNING
        assert alert_id not in restarted.records
        assert alert_id not in restarted.notification_runtime._runtime["profile"]

        lifecycle_release.set()
        for _index in range(3):
            await asyncio.sleep(0)
        assert (
            alert_id
            in restarted.notification_runtime._batches[("profile", "resolved")].items
        )
        await restarted.async_unload()

    asyncio.run(scenario())


def test_restart_resumes_one_reminder_without_backlog(hass, entry, set_now) -> None:
    """An overdue stored reminder restarts from now and is not replayed."""

    async def scenario() -> None:
        now = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
        set_now(now)
        config = validate_config(
            {
                **deepcopy(DEFAULT_CONFIG),
                "notification_profiles": [_profile(reminder_interval=300)],
            }
        )
        record = _active_record(now - timedelta(hours=1))
        hass.stores["alert_manager.notifications"] = {
            "profiles": {
                "profile": {
                    record.details.id: {
                        "next_reminder": (now - timedelta(minutes=30)).isoformat()
                    }
                }
            }
        }
        delivery = _DeliverySpy()
        runtime = NotificationRuntime(
            hass,
            entry,
            lambda: config,
            lambda: {record.details.id: record},
            delivery,
        )

        await runtime.async_setup()

        assert delivery.calls == []
        active_timers = [timer for timer in hass.timers if not timer["cancelled"]]
        assert len(active_timers) == 1
        assert active_timers[0]["point"] == now + timedelta(minutes=5)
        await runtime.async_unload()

    asyncio.run(scenario())


@pytest.mark.parametrize("source_state", ["ok", "unavailable"])
@pytest.mark.parametrize("reminder_after", [20, 120])
def test_restored_reminders_wait_for_committed_startup(
    hass, entry, set_now, source_state, reminder_after
):
    """Only confirmed alerts resume reminders after startup, without a backlog."""

    async def scenario():
        now = datetime(2026, 9, 5, 10, tzinfo=UTC)
        set_now(now)
        config = validate_config(
            {
                **deepcopy(DEFAULT_CONFIG),
                "notification_profiles": [_profile(reminder_interval=300)],
            }
        )
        config["automatic"]["unavailable"]["delay"] = 0
        record = _active_record(now - timedelta(hours=1))
        seed = AlertManager(hass, entry)
        await seed.storage.async_save(config, {record.details.id: record})
        hass.stores["alert_manager.notifications"] = {
            "profiles": {
                "profile": {
                    record.details.id: {
                        "next_reminder": (
                            now + timedelta(seconds=reminder_after)
                        ).isoformat()
                    }
                }
            }
        }
        hass.states.set(record.details.entity_id, source_state)
        manager = AlertManager(hass, entry)
        delivery = _DeliverySpy()
        manager.notification_runtime._delivery = delivery
        await manager.async_setup()
        runtime = manager.notification_runtime
        assert manager._runtime_phase is RuntimePhase.STARTUP_GRACE
        assert runtime._reminder_cancel is None
        set_now(now + timedelta(seconds=30))
        # Also protect a callback admitted before the readiness check changed.
        await runtime._async_send_reminders()
        assert not delivery.calls
        assert runtime._runtime["profile"][record.details.id].next_reminder == (
            now + timedelta(seconds=reminder_after)
        )
        set_now(now + timedelta(seconds=60))
        await manager._async_finish_startup_reconciliation()
        assert manager._runtime_phase is RuntimePhase.RUNNING
        assert not delivery.calls
        if source_state == "ok":
            assert record.details.id not in manager.records
            assert not runtime._runtime["profile"]
            assert runtime._reminder_cancel is None
        else:
            deadline = now + timedelta(seconds=360 if reminder_after == 20 else 120)
            assert (
                runtime._runtime["profile"][record.details.id].next_reminder == deadline
            )
            assert runtime._reminder_cancel is not None
            set_now(deadline)
            await runtime._async_send_reminders()
            assert len(delivery.calls) == 1
        await manager.async_unload()

    asyncio.run(scenario())


@pytest.mark.parametrize("write_fails", [False, True])
def test_reminders_stay_paused_during_startup_write_and_rollback(
    hass, entry, set_now, monkeypatch, write_fails
):
    """Speculative restored records never produce a reminder during startup I/O."""

    async def scenario():
        now = datetime(2026, 9, 5, 10, tzinfo=UTC)
        set_now(now)
        config = validate_config(
            {
                **deepcopy(DEFAULT_CONFIG),
                "notification_profiles": [_profile(reminder_interval=300)],
            }
        )
        record = _active_record(now - timedelta(hours=1))
        seed = AlertManager(hass, entry)
        await seed.storage.async_save(config, {record.details.id: record})
        hass.stores["alert_manager.notifications"] = {
            "profiles": {
                "profile": {
                    record.details.id: {
                        "next_reminder": (now + timedelta(seconds=20)).isoformat()
                    }
                }
            }
        }
        hass.states.set(record.details.entity_id, "ok")
        manager = AlertManager(hass, entry)
        delivery = _DeliverySpy()
        manager.notification_runtime._delivery = delivery
        await manager.async_setup()
        entered, release = asyncio.Event(), asyncio.Event()
        original_save = manager._async_save_main_store

        async def delayed_save():
            if not entered.is_set():
                entered.set()
                await release.wait()
                if write_fails:
                    raise OSError("temporary storage error")
            await original_save()

        monkeypatch.setattr(manager, "_async_save_main_store", delayed_save)
        set_now(now + timedelta(seconds=60))
        task = asyncio.create_task(manager._async_finish_startup_reconciliation())
        await entered.wait()
        assert manager._runtime_phase is RuntimePhase.RECONCILING
        assert record.details.id in manager.notification_runtime._records_getter()
        await manager.notification_runtime._async_send_reminders()
        assert not delivery.calls
        release.set()
        await task
        if write_fails:
            assert manager._runtime_phase is RuntimePhase.STARTUP_GRACE
            assert manager.notification_runtime._reminder_cancel is None
            await manager.notification_runtime._async_send_reminders()
            assert not delivery.calls
            await manager._async_finish_startup_reconciliation()
        assert manager._runtime_phase is RuntimePhase.RUNNING
        assert record.details.id not in manager.records
        assert manager.notification_runtime._reminder_cancel is None
        await manager.async_unload()

    asyncio.run(scenario())


def test_lifecycle_burst_coalesces_reminder_deadline_scans(hass, entry, monkeypatch):
    """Hundreds of lifecycle mutations schedule one scan with the final deadlines."""

    async def scenario():
        config = validate_config(
            {
                **deepcopy(DEFAULT_CONFIG),
                "notification_profiles": [_profile(reminder_interval=300)],
            }
        )
        runtime = NotificationRuntime(
            hass, entry, lambda: config, lambda: {}, _DeliverySpy()
        )
        await runtime.async_setup()
        schedule = Mock(wraps=runtime._schedule_reminder_timer)
        monkeypatch.setattr(runtime, "_schedule_reminder_timer", schedule)
        for index in range(200):
            await runtime._async_handle_event(
                EVENT_ALERT_STARTED,
                _event_data(
                    f"unavailable:sensor.test_{index}",
                    entity_id=f"sensor.test_{index}",
                    device_id=None,
                ),
            )
        assert schedule.call_count == 0
        await asyncio.sleep(0)
        assert schedule.call_count == 1
        assert runtime._reminder_cancel is not None
        await runtime.async_discard_alerts(set(runtime._runtime["profile"]))
        await asyncio.sleep(0)
        assert schedule.call_count == 2
        assert runtime._reminder_cancel is None
        await runtime.async_unload()

    asyncio.run(scenario())


def test_shutdown_cancels_deferred_reminder_refresh(hass, entry, monkeypatch):
    """A deferred deadline refresh cannot recreate a timer after unload begins."""

    async def scenario():
        config = validate_config(
            {
                **deepcopy(DEFAULT_CONFIG),
                "notification_profiles": [_profile(reminder_interval=300)],
            }
        )
        runtime = NotificationRuntime(
            hass, entry, lambda: config, lambda: {}, _DeliverySpy()
        )
        await runtime.async_setup()
        schedule = Mock(wraps=runtime._schedule_reminder_timer)
        monkeypatch.setattr(runtime, "_schedule_reminder_timer", schedule)
        await runtime._async_handle_event(
            EVENT_ALERT_STARTED,
            _event_data(
                "unavailable:sensor.test", entity_id="sensor.test", device_id=None
            ),
        )
        runtime.begin_shutdown()
        await asyncio.sleep(0)
        assert schedule.call_count == 0
        assert runtime._reminder_refresh_handle is None
        assert runtime._reminder_cancel is None
        await runtime.async_unload()

    asyncio.run(scenario())


def test_runtime_load_prunes_unknown_profiles_and_alerts(hass, entry) -> None:
    """Untrusted persisted runtime is bounded to authoritative live state."""

    async def scenario() -> None:
        now = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
        config = validate_config(
            {
                **deepcopy(DEFAULT_CONFIG),
                "notification_profiles": [_profile(reminder_interval=300)],
            }
        )
        record = _active_record(now)
        next_reminder = (now + timedelta(minutes=5)).isoformat()
        hass.stores["alert_manager.notifications"] = {
            "profiles": {
                "profile": {
                    record.details.id: {"next_reminder": next_reminder},
                    "unavailable:sensor.orphan": {"next_reminder": next_reminder},
                },
                "deleted-profile": {
                    record.details.id: {"next_reminder": next_reminder}
                },
            }
        }
        runtime = NotificationRuntime(
            hass,
            entry,
            lambda: config,
            lambda: {record.details.id: record},
            _DeliverySpy(),
        )

        await runtime.async_setup()

        assert set(runtime._runtime) == {"profile"}
        assert set(runtime._runtime["profile"]) == {record.details.id}
        assert set(hass.stores["alert_manager.notifications"]["profiles"]) == {
            "profile"
        }
        assert set(
            hass.stores["alert_manager.notifications"]["profiles"]["profile"]
        ) == {record.details.id}
        await runtime.async_unload()

    asyncio.run(scenario())


def test_usage_is_not_restored_or_persisted(hass, entry, set_now) -> None:
    """Legacy usage is ignored and removed; new statistics never reach storage."""

    async def scenario() -> None:
        now = datetime(2026, 9, 4, 12, 30, tzinfo=UTC)
        set_now(now)
        current_bucket = int(now.timestamp()) // 3600
        config = validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [_profile()]}
        )
        hass.stores["alert_manager.notifications"] = {
            "profiles": {},
            "usage": {
                "profile": {
                    str(current_bucket): 2,
                    str(current_bucket - 23): 3,
                    str(current_bucket - 24): 100,
                    str(current_bucket + 1): 100,
                    "invalid": 100,
                },
                "deleted-profile": {str(current_bucket): 100},
            },
        }
        runtime = NotificationRuntime(
            hass, entry, lambda: config, lambda: {}, _DeliverySpy()
        )

        await runtime.async_setup()

        assert runtime.usage_snapshot() == {"last_24h": {"profile": 0}}
        assert "usage" not in hass.stores["alert_manager.notifications"]
        saves = hass.store_save_count
        await runtime._async_record_usage(
            "profile", {"delivered_targets": ["notify.phone"]}
        )
        assert runtime.statistics.snapshot()["notifications"] == 1
        assert runtime.usage_snapshot() == {"last_24h": {"profile": 1}}
        assert runtime._runtime_save_cancel is None
        assert hass.store_save_count == saves
        await runtime.async_unload()

    asyncio.run(scenario())


def test_occurrence_delivery_statistics_and_history(hass, entry) -> None:
    """Count profiles, not targets; keep late deliveries on the old occurrence."""
    from custom_components.alert_manager.models import AlertHistoryEntry
    from custom_components.alert_manager.notification_runtime import _NotificationItem

    async def scenario() -> None:
        manager = AlertManager(hass, entry)
        now = datetime(2026, 9, 5, 10, tzinfo=UTC)
        record = _active_record(now)
        manager.records = {record.details.id: record}
        item = _NotificationItem.from_event(record.as_public_dict())
        profile = _profile()
        delivery = _DeliverySpy()
        runtime = NotificationRuntime(
            hass,
            entry,
            lambda: manager.config,
            lambda: manager.records,
            delivery,
            manager._async_record_notification,
        )
        manager.config["notification_profiles"] = [profile]
        await manager._async_record_notification([item], profile, "matched", now)
        assert record.notifications["alert"]["count"] == 0
        assert record.notifications["alert"]["profiles"] == {"profile": "Profile"}
        await runtime._async_record_delivery(
            profile,
            "started",
            [item],
            {
                "delivered_targets": ["notify.one", "notify.two"],
            },
        )
        await runtime._async_record_delivery(
            profile,
            "reminder",
            [item],
            {
                "delivered_targets": ["notify.one"],
                "failed_targets": ["notify.two"],
            },
        )
        await runtime._async_record_delivery(
            profile,
            "reminder",
            [item],
            {
                "delivered_targets": [],
            },
        )
        assert record.notifications["alert"]["count"] == 2
        assert (
            AlertRecord.from_dict(record.as_storage_dict()).notifications
            == record.notifications
        )
        archived = AlertHistoryEntry.resolved(record, now + timedelta(minutes=5))
        manager.history = [archived]
        replacement = _active_record(now + timedelta(minutes=6))
        manager.records = {replacement.details.id: replacement}
        await manager._async_record_notification(
            [item], profile, "resolved", now + timedelta(minutes=7)
        )
        second = {**profile, "id": "second", "name": "Second"}
        await manager._async_record_notification(
            [item], second, "resolved", now + timedelta(minutes=8)
        )
        stats = manager.history[0].notifications
        assert replacement.notifications is None
        assert stats["alert"]["count"] == 2
        assert stats["resolved"] == {
            "count": 2,
            "profiles": {"profile": "Profile", "second": "Second"},
            "last_sent": (now + timedelta(minutes=8)).isoformat(),
        }
        restored, _ = await manager.history_storage.async_load()
        assert restored[0].notifications == stats
        await runtime.async_unload()

    asyncio.run(scenario())


def test_batch_and_reminders_pass_occurrences_to_accounting(
    hass, entry, set_now
) -> None:
    """The actual send paths retain identities, including profiles without reminders."""

    async def scenario() -> None:
        now = datetime(2026, 9, 5, 10, tzinfo=UTC)
        set_now(now)
        record = _active_record(now)
        records = {record.details.id: record}
        profile = _profile(reminder_interval=60)
        config = validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [profile]}
        )
        seen = []

        async def account(items, profile, kind, sent_at):
            seen.append((kind, [item.detected_at for item in items]))

        runtime = NotificationRuntime(
            hass, entry, lambda: config, lambda: records, _DeliverySpy(), account
        )
        await runtime.async_setup()
        await runtime._async_handle_event(EVENT_ALERT_STARTED, record.as_public_dict())
        await runtime._async_flush_batch("profile", "started")
        runtime._runtime["profile"][record.details.id].next_reminder = now - timedelta(
            seconds=1
        )
        await runtime._async_send_reminders()
        assert seen == [
            (kind, [now.isoformat()]) for kind in ("matched", "started", "reminder")
        ]
        await runtime.async_unload()

    asyncio.run(scenario())


def test_legacy_and_invalid_notification_statistics_do_not_drop_alert() -> None:
    record = _active_record(datetime.now(UTC))
    data = record.as_storage_dict()
    assert AlertRecord.from_dict(data).notifications is None
    data["notifications"] = {"alert": {"count": -1, "profiles": []}}
    assert AlertRecord.from_dict(data).notifications is None


def test_delivery_waiting_for_archive_is_counted_once(hass, entry) -> None:
    """Resolution while accounting waits for storage cannot duplicate a delivery."""
    from custom_components.alert_manager.models import AlertHistoryEntry
    from custom_components.alert_manager.notification_runtime import _NotificationItem

    async def scenario() -> None:
        manager = AlertManager(hass, entry)
        manager.config = deepcopy(DEFAULT_CONFIG)
        now = datetime(2026, 9, 5, 10, tzinfo=UTC)
        record = _active_record(now)
        manager.records = {record.details.id: record}
        item = _NotificationItem.from_event(record.as_public_dict())
        async with manager._history_archive_lock:
            task = asyncio.create_task(
                manager._async_record_notification(
                    [item],
                    _profile(),
                    "started",
                    now,
                )
            )
            await asyncio.sleep(0)
            manager._pending_history = [AlertHistoryEntry.resolved(record, now)]
            manager.records.clear()
        await task
        assert manager._pending_history[0].notifications["alert"]["count"] == 1
        await manager._async_flush_history()
        restored, _ = await manager.history_storage.async_load()
        assert restored[0].notifications["alert"]["count"] == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("source", ["rule", "battery"])
def test_source_labels_route_start_reminders_and_resolution(
    hass, entry, set_now, source
):
    """Rule and pack labels route every notification lifecycle step."""

    async def scenario():
        now = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
        set_now(now)
        profile = _profile()
        profile["label_ids"] = ["cold"]
        profile["default_policy"]["notify_on_resolved"] = False
        profile["exceptions"] = [
            {
                "selector_type": "label",
                "selector_id": "cold",
                "notify_on_resolved": True,
                "reminder_interval": 300,
            }
        ]
        config = validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [profile]}
        )
        record = _active_record(now)
        record.details.type = source
        record.details.rule_id = "freezer" if source == "rule" else None
        record.details.labels = ["cold"]
        delivery = _DeliverySpy()
        runtime = NotificationRuntime(
            hass, entry, lambda: config, lambda: {record.details.id: record}, delivery
        )
        await runtime.async_setup()
        assert runtime._runtime["profile"][
            record.details.id
        ].next_reminder == now + timedelta(seconds=300)
        # Two rules on the same source must never contaminate the shared entity cache.
        assert runtime._labels_for("sensor.test", None, ["other"]) == {"other"}
        assert runtime._labels_for("sensor.test", None) == set()
        event = record.details.as_dict()
        await runtime._async_handle_event(EVENT_ALERT_STARTED, event)
        await runtime._async_flush_batch("profile", "started")
        runtime._runtime["profile"][record.details.id].next_reminder = now
        await runtime._async_send_reminders()
        await runtime._async_handle_event(EVENT_ALERT_RESOLVED, event)
        await runtime._async_flush_batch("profile", "resolved")
        assert runtime.usage_snapshot() == {"last_24h": {"profile": 3}}
        assert len(delivery.calls) == 3
        await runtime.async_unload()

    asyncio.run(scenario())


def test_rule_label_update_refreshes_frozen_alert_and_reminders(hass, entry):
    """Label edits during a pause survive storage and resume notification routing."""

    async def scenario():
        from custom_components.alert_manager.models import AlertHistoryEntry

        hass.states.set("sensor.test", "10")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(
            {
                "name": "Hot sensor",
                "entity_ids": ["sensor.test"],
                "operator": "above",
                "value": 8,
                "duration": 0,
                "label_ids": ["old"],
            }
        )
        alert_id = f"rule:{rule['id']}:sensor.test"
        profile = _profile(reminder_interval=300)
        profile["label_ids"] = ["new"]
        await manager.async_update_config({"notification_profiles": [profile]})
        assert alert_id not in manager.notification_runtime._runtime["profile"]
        await manager.async_set_monitoring(False)
        await manager.async_update_rule(rule["id"], {"label_ids": ["new"]})
        record = manager.records[alert_id]
        assert record.details.labels == ["new"]
        assert AlertRecord.from_dict(record.as_storage_dict()).details.labels == ["new"]
        await manager.async_set_monitoring(True)
        assert (
            manager.notification_runtime._runtime["profile"][alert_id].next_reminder
            is not None
        )
        history = AlertHistoryEntry.resolved(record, record.active_since)
        record.details.labels.clear()
        assert AlertHistoryEntry.from_dict(history.as_dict()).labels == ["new"]
        await manager.async_unload()

    asyncio.run(scenario())


@pytest.mark.parametrize("paused", [False, True])
def test_pack_label_update_preserves_alert_and_refreshes_routing(hass, entry, paused):
    """Label edits update frozen/live alerts without evaluating sources or events."""
    from unittest.mock import AsyncMock

    from custom_components.alert_manager.models import AlertHistoryEntry

    async def scenario():
        hass.states.set("sensor.battery", "10", {"device_class": "battery"})
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        await manager.async_update_config(
            {"automatic": {"battery": {"delay": 0, "label_ids": ["old"]}}}
        )
        alert_id = "battery:sensor.battery"
        record = manager.records[alert_id]
        assert record.details.labels == ["old"]
        active_since = record.active_since
        history = AlertHistoryEntry.resolved(record, active_since)
        profile = _profile(reminder_interval=300)
        profile["label_ids"] = ["new"]
        await manager.async_update_config({"notification_profiles": [profile]})
        assert alert_id not in manager.notification_runtime._runtime["profile"]
        if paused:
            await manager.async_set_monitoring(False)
        evaluator = manager.async_evaluate_all
        manager.async_evaluate_all = AsyncMock()
        events_before = list(hass.bus.fired)
        await manager.async_update_config(
            {"automatic": {"battery": {"label_ids": ["new", "new"]}}}
        )
        manager.async_evaluate_all.assert_not_awaited()
        manager.async_evaluate_all = evaluator
        assert manager.records[alert_id] is record
        assert record.active_since == active_since
        assert record.details.labels == ["new"]
        assert AlertRecord.from_dict(record.as_storage_dict()).details.labels == ["new"]
        assert history.labels == ["old"]
        assert hass.bus.fired == events_before
        if paused:
            await manager.async_set_monitoring(True)
        assert manager.notification_runtime._runtime["profile"][alert_id].next_reminder
        await manager.async_update_config({"automatic": {"battery": {"label_ids": []}}})
        assert manager.records[alert_id].details.labels == []
        assert alert_id not in manager.notification_runtime._runtime["profile"]
        await manager.async_unload()

    asyncio.run(scenario())


def test_pack_label_save_failure_restores_config_and_alert(hass, entry):
    """Failed persistence preserves labels and notification policy."""
    from unittest.mock import AsyncMock

    async def scenario():
        hass.states.set("sensor.battery", "10", {"device_class": "battery"})
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        await manager.async_update_config(
            {"automatic": {"battery": {"delay": 0, "label_ids": ["old"]}}}
        )
        save = manager._async_save_state
        manager._async_save_state = AsyncMock(side_effect=OSError("disk full"))
        with pytest.raises(OSError, match="disk full"):
            await manager.async_update_config(
                {"automatic": {"battery": {"label_ids": ["new"]}}}
            )
        manager._async_save_state = save
        assert manager.config["automatic"]["battery"]["label_ids"] == ["old"]
        assert manager.records["battery:sensor.battery"].details.labels == ["old"]
        await manager.async_unload()

    asyncio.run(scenario())


def test_rule_label_edit_discards_only_its_pending_notifications(hass, entry):
    """Changing routing labels cancels stale batches without losing other rules."""

    async def scenario():
        hass.states.set("sensor.test", "10")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        profile = _profile(reminder_interval=300)
        profile["label_ids"] = ["old"]
        await manager.async_update_config({"notification_profiles": [profile]})
        delivery = _DeliverySpy()
        runtime = manager.notification_runtime
        runtime._delivery = delivery
        rules = [
            await manager.async_create_rule(
                {
                    "name": name,
                    "entity_ids": ["sensor.test"],
                    "operator": "above",
                    "value": 8,
                    "duration": 0,
                    "label_ids": ["old"],
                }
            )
            for name in ("Changed", "Unchanged")
        ]
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        alert_ids = [f"rule:{rule['id']}:sensor.test" for rule in rules]
        assert set(runtime._batches[("profile", "started")].items) == set(alert_ids)
        await manager.async_update_rule(rules[0]["id"], {"label_ids": ["new"]})
        assert set(runtime._batches[("profile", "started")].items) == {alert_ids[1]}
        assert alert_ids[0] not in runtime._runtime["profile"]
        await runtime._async_flush_batch("profile", "started")
        assert len(delivery.calls) == 1
        assert (
            runtime._batch_url(
                "started",
                [
                    _NotificationItem.from_event(
                        manager.records[alert_ids[1]].as_public_dict()
                    )
                ],
            )
            == delivery.calls[0]["click_url"]
        )
        await manager.async_unload()

    asyncio.run(scenario())


@pytest.mark.parametrize("fail_save", [False, True])
@pytest.mark.parametrize("cancel_caller", [False, True])
@pytest.mark.parametrize("mutation", ["create", "update"])
def test_rule_notifications_wait_for_transaction_commit(
    hass, entry, fail_save, cancel_caller, mutation
):
    """A pending write sends nothing; commit sends once, rollback sends nothing."""

    async def scenario():
        hass.states.set("sensor.test", "10")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule_data = {
            "name": "Hot",
            "entity_ids": ["sensor.test"],
            "operator": "above",
            "value": 8,
            "duration": 0,
        }
        if mutation == "update":
            existing = await manager.async_create_rule({**rule_data, "value": 20})
        await manager.async_update_config({"notification_profiles": [_profile()]})
        initial_rules = deepcopy(manager.config["rules"])
        delivery = _DeliverySpy()
        runtime = manager.notification_runtime
        runtime._delivery = delivery
        original_save = manager.storage.async_save
        save_started = asyncio.Event()
        release_save = asyncio.Event()

        async def blocked_save(*args, **kwargs):
            save_started.set()
            await release_save.wait()
            if fail_save:
                raise OSError("disk full")
            await original_save(*args, **kwargs)

        manager.storage.async_save = blocked_save
        task = asyncio.create_task(
            manager.async_create_rule(rule_data)
            if mutation == "create"
            else manager.async_update_rule(existing["id"], {"value": 8})
        )
        await save_started.wait()
        await asyncio.sleep(0)
        assert not runtime._batches
        assert not delivery.calls
        if cancel_caller:
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
        release_save.set()
        if cancel_caller or fail_save:
            with pytest.raises(asyncio.CancelledError if cancel_caller else OSError):
                await task
        else:
            await task
        manager.storage.async_save = original_save
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await runtime._async_flush_batch("profile", "started")
        assert len(delivery.calls) == (0 if fail_save else 1)
        assert bool(manager.records) is not fail_save
        if fail_save:
            assert manager.config["rules"] == initial_rules
        else:
            assert manager.config["rules"][0]["value"] == 8
        assert runtime._deferred_events is None
        await manager.async_unload()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "alert_type",
    ["execution_errors", "unavailable", "connectivity", "flapping", "rule"],
)
@pytest.mark.parametrize("old_message", [None, "Previous execution failed"])
def test_resolved_notification_omits_old_diagnostic(
    hass, entry, alert_type, old_message
):
    runtime = NotificationRuntime(hass, entry, lambda: {}, lambda: {}, _DeliverySpy())
    data = _event_data("test:sensor.test", entity_id="sensor.test", device_id=None)
    data.update(type=alert_type, message=old_message, condition="Previous failure")
    item = _NotificationItem.from_event(data)

    _, message = runtime._render_batch("resolved", [item])

    assert message == "• sensor.test — Return to normal"
    assert item.message == old_message
    assert item.condition == "Previous failure"


@pytest.mark.parametrize("source", ["transition", "attribute_transition"])
def test_transition_expiration_cleans_reminders_without_recovery(hass, entry, source):
    """Expiration stops reminders but must never claim a return to normal."""

    async def scenario():
        profile = _profile(reminder_interval=300)
        config = validate_config({"notification_profiles": [profile]})
        runtime = NotificationRuntime(
            hass, entry, lambda: config, lambda: {}, _DeliverySpy()
        )
        await runtime.async_setup()
        event = {
            **_event_data(
                "rule:edge:sensor.test", entity_id="sensor.test", device_id=None
            ),
            "source": source,
        }
        await runtime._async_handle_event(EVENT_ALERT_STARTED, event)
        # Model a start already sent, exercising the actual resolution branch.
        runtime.discard_batches()
        assert runtime._runtime["profile"]
        await runtime._async_handle_event(EVENT_ALERT_RESOLVED, event)
        assert not runtime._runtime.get("profile")
        assert not runtime._batch_contains("profile", "resolved", event["id"])
        await runtime.async_unload()

    asyncio.run(scenario())
