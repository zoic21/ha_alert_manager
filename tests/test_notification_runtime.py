"""Event-driven notification batching and reminder regression tests."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from custom_components.alert_manager.const import (
    DEFAULT_CONFIG,
    EVENT_ALERT_RESOLVED,
    EVENT_ALERT_STARTED,
    SIGNAL_NOTIFICATION_LIFECYCLE,
)
from custom_components.alert_manager.models import (
    AlertDetails,
    AlertRecord,
    AlertStatus,
)
from custom_components.alert_manager.notification_runtime import NotificationRuntime
from custom_components.alert_manager.validation import validate_config


class _DeliverySpy:
    """Capture rendered deliveries without registering a notify integration."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def text(self, _key: str, fallback: str) -> str:
        return fallback

    async def async_send(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {"success": True}


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


def test_fixed_window_groups_two_device_alerts_in_one_delivery(hass, entry) -> None:
    """Adding an alert does not extend the first batch deadline."""

    async def scenario() -> None:
        config = validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [_profile()]}
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
