"""Event-driven notification delivery, batching and reminder scheduling."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    EVENT_ALERT_ACKNOWLEDGED,
    EVENT_ALERT_RESOLVED,
    EVENT_ALERT_STARTED,
    EVENT_ALERT_UNACKNOWLEDGED,
    NOTIFICATION_BATCH_SECONDS,
    NOTIFICATION_STORAGE_KEY,
    NOTIFICATION_STORAGE_VERSION,
)
from .models import AlertRecord, AlertStatus
from .notifications import (
    NotificationManager,
    NotificationPolicy,
    profile_matches_labels,
    resolve_notification_policy,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class _NotificationItem:
    """Small immutable-enough lifecycle snapshot retained during batching."""

    alert_id: str
    entity_id: str
    name: str
    alert_type: str
    rule_id: str | None
    device_id: str | None
    device_name: str | None
    message: str | None
    condition: str | None

    @classmethod
    def from_event(cls, data: Mapping[str, Any]) -> _NotificationItem | None:
        """Build a bounded item from a public lifecycle event payload."""
        alert_id = data.get("id")
        entity_id = data.get("entity_id")
        if not isinstance(alert_id, str) or not alert_id:
            return None
        if not isinstance(entity_id, str) or not entity_id:
            return None
        return cls(
            alert_id=alert_id,
            entity_id=entity_id,
            name=_optional_text(data.get("name")) or entity_id,
            alert_type=_optional_text(data.get("type")) or "alert",
            rule_id=_optional_text(data.get("rule_id")),
            device_id=_optional_text(data.get("device_id")),
            device_name=_optional_text(data.get("device_name")),
            message=_optional_text(data.get("message")),
            condition=_optional_text(data.get("condition")),
        )


@dataclass(slots=True)
class _RuntimeEntry:
    """Minimal per-profile occurrence state used across restarts."""

    next_reminder: datetime | None = None

    def as_dict(self) -> dict[str, str | None]:
        """Serialize one runtime entry."""
        return {
            "next_reminder": (
                self.next_reminder.astimezone(UTC).isoformat()
                if self.next_reminder is not None
                else None
            )
        }


@dataclass(slots=True)
class _PendingBatch:
    """One fixed-window batch; new items never extend its deadline."""

    items: dict[str, _NotificationItem] = field(default_factory=dict)
    cancel: Callable[[], None] | None = None


class NotificationRuntime:
    """Consume alert lifecycle events without coupling delivery to detection."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: Any,
        config_getter: Callable[[], dict[str, Any]],
        records_getter: Callable[[], dict[str, AlertRecord]],
        delivery: NotificationManager,
    ) -> None:
        """Initialize the independent notification component."""
        self.hass = hass
        self.entry = entry
        self._config_getter = config_getter
        self._records_getter = records_getter
        self._delivery = delivery
        self._store = Store[dict[str, Any]](
            hass,
            NOTIFICATION_STORAGE_VERSION,
            NOTIFICATION_STORAGE_KEY,
            atomic_writes=True,
        )
        self._entity_registry = er.async_get(hass)
        self._device_registry = dr.async_get(hass)
        self._runtime_lock = asyncio.Lock()
        self._runtime: dict[str, dict[str, _RuntimeEntry]] = {}
        self._persisted_runtime: dict[str, Any] = {"profiles": {}}
        self._label_cache: dict[str, frozenset[str]] = {}
        self._batches: dict[tuple[str, str], _PendingBatch] = {}
        self._unsubscribe: list[Callable[[], None]] = []
        self._reminder_cancel: Callable[[], None] | None = None
        self._tasks: set[asyncio.Task[Any]] = set()
        self._unloading = False
        self._setup_complete = False
        self._accept_events = True

    @callback
    def pause_events(self) -> None:
        """Ignore lifecycle events manufactured by a configuration rebuild."""
        self._accept_events = False

    @callback
    def resume_events(self) -> None:
        """Resume normal lifecycle consumption after runtime reconciliation."""
        self._accept_events = True

    @callback
    def discard_batches(self) -> None:
        """Discard unsent batches after policies change or monitoring stops."""
        for batch in self._batches.values():
            if batch.cancel is not None:
                batch.cancel()
        self._batches.clear()

    async def async_setup(self) -> None:
        """Restore runtime state, then subscribe after initial alert evaluation."""
        await self._async_load_runtime()
        self._unsubscribe.extend(
            (
                self.hass.bus.async_listen(
                    EVENT_ALERT_STARTED, self._event_received(EVENT_ALERT_STARTED)
                ),
                self.hass.bus.async_listen(
                    EVENT_ALERT_RESOLVED, self._event_received(EVENT_ALERT_RESOLVED)
                ),
                self.hass.bus.async_listen(
                    EVENT_ALERT_ACKNOWLEDGED,
                    self._event_received(EVENT_ALERT_ACKNOWLEDGED),
                ),
                self.hass.bus.async_listen(
                    EVENT_ALERT_UNACKNOWLEDGED,
                    self._event_received(EVENT_ALERT_UNACKNOWLEDGED),
                ),
            )
        )
        self._setup_complete = True
        await self.async_config_updated()

    async def async_unload(self) -> None:
        """Cancel owned listeners, timers and delivery tasks."""
        self._unloading = True
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe.clear()
        self._cancel_reminder_timer()
        self.discard_batches()
        for task in tuple(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._setup_complete:
            await self._async_save_runtime()

    async def async_config_updated(self, *, reset_reminders: bool = False) -> None:
        """Reconcile profile/reminder state without replaying active alerts."""
        async with self._runtime_lock:
            await self._async_config_updated_locked(reset_reminders=reset_reminders)

    async def _async_config_updated_locked(self, *, reset_reminders: bool) -> None:
        """Reconcile notification state while holding the runtime lock."""
        now = dt_util.now().astimezone(UTC)
        config = self._config_getter()
        if not config.get("monitoring_enabled", True):
            self.discard_batches()
        profiles = {
            profile["id"]: profile
            for profile in config.get("notification_profiles", [])
            if profile.get("enabled")
        }
        records = self._records_getter()
        active_records = {
            alert_id: record
            for alert_id, record in records.items()
            if record.status is AlertStatus.ACTIVE
        }

        self._runtime = {
            profile_id: {
                alert_id: runtime
                for alert_id, runtime in self._runtime.get(profile_id, {}).items()
                if alert_id in active_records
            }
            for profile_id in profiles
        }
        for profile_id, profile in profiles.items():
            profile_runtime = self._runtime.setdefault(profile_id, {})
            for alert_id, record in active_records.items():
                labels = self._labels_for(
                    record.details.entity_id, record.details.device_id
                )
                if not profile_matches_labels(profile, labels):
                    profile_runtime.pop(alert_id, None)
                    continue
                policy = _policy_for_record(profile, record, labels)
                runtime = profile_runtime.setdefault(alert_id, _RuntimeEntry())
                if (
                    not config.get("monitoring_enabled", True)
                    or record.acknowledged
                    or policy.reminder_interval is None
                ):
                    runtime.next_reminder = None
                elif (
                    reset_reminders
                    or runtime.next_reminder is None
                    or runtime.next_reminder.astimezone(UTC) <= now
                ):
                    runtime.next_reminder = now + timedelta(
                        seconds=policy.reminder_interval
                    )
        await self._async_save_runtime()
        self._schedule_reminder_timer()

    def _event_received(self, event_type: str) -> Callable[[Event], None]:
        """Create a non-blocking bus callback for one lifecycle event."""

        @callback
        def received(event: Event) -> None:
            if self._unloading or not self._accept_events:
                return
            self._create_task(
                self._async_handle_event(event_type, event.data),
                f"alert_manager notification {event_type}",
            )

        return received

    async def _async_handle_event(
        self, event_type: str, data: Mapping[str, Any]
    ) -> None:
        """Route one lifecycle event into profile batches and reminder state."""
        async with self._runtime_lock:
            await self._async_handle_event_locked(event_type, data)

    async def _async_handle_event_locked(
        self, event_type: str, data: Mapping[str, Any]
    ) -> None:
        """Apply one lifecycle event while holding the runtime lock."""
        item = _NotificationItem.from_event(data)
        if item is None:
            return
        config = self._config_getter()
        now = dt_util.now().astimezone(UTC)
        labels = self._labels_for(item.entity_id, item.device_id)
        changed = False
        for profile in config.get("notification_profiles", []):
            if not profile.get("enabled") or not profile_matches_labels(
                profile, labels
            ):
                continue
            policy = resolve_notification_policy(
                profile,
                pack_id=item.alert_type if item.rule_id is None else None,
                rule_id=item.rule_id,
                label_ids=labels,
            )
            profile_id = profile["id"]
            if event_type == EVENT_ALERT_STARTED:
                runtime = self._runtime.setdefault(profile_id, {}).setdefault(
                    item.alert_id, _RuntimeEntry()
                )
                runtime.next_reminder = (
                    now + timedelta(seconds=policy.reminder_interval)
                    if policy.reminder_interval is not None
                    else None
                )
                if policy.notify_on_start:
                    self._queue_batch(profile_id, "started", item)
                changed = True
            elif event_type == EVENT_ALERT_RESOLVED:
                if self._cancel_transient_start(profile_id, item.alert_id):
                    self._runtime.get(profile_id, {}).pop(item.alert_id, None)
                    changed = True
                    continue
                if policy.notify_on_resolved:
                    self._queue_batch(profile_id, "resolved", item)
                self._runtime.get(profile_id, {}).pop(item.alert_id, None)
                changed = True
            elif event_type == EVENT_ALERT_ACKNOWLEDGED:
                runtime = self._runtime.get(profile_id, {}).get(item.alert_id)
                if runtime is not None:
                    runtime.next_reminder = None
                    changed = True
            elif event_type == EVENT_ALERT_UNACKNOWLEDGED:
                runtime = self._runtime.setdefault(profile_id, {}).setdefault(
                    item.alert_id, _RuntimeEntry()
                )
                runtime.next_reminder = (
                    now + timedelta(seconds=policy.reminder_interval)
                    if policy.reminder_interval is not None
                    else None
                )
                changed = True
        if changed:
            await self._async_save_runtime()
            self._schedule_reminder_timer()

    def _queue_batch(self, profile_id: str, kind: str, item: _NotificationItem) -> None:
        """Add an occurrence to a fixed collection window."""
        key = (profile_id, kind)
        batch = self._batches.setdefault(key, _PendingBatch())
        batch.items[item.alert_id] = item
        if batch.cancel is not None:
            return

        @callback
        def timer_due(_now: datetime) -> None:
            current = self._batches.get(key)
            if current is not None:
                current.cancel = None
            if self._unloading:
                return
            self._create_task(
                self._async_flush_batch(profile_id, kind),
                f"alert_manager notification batch {profile_id} {kind}",
            )

        batch.cancel = async_track_point_in_utc_time(
            self.hass,
            timer_due,
            dt_util.now().astimezone(UTC)
            + timedelta(seconds=NOTIFICATION_BATCH_SECONDS),
        )

    def _cancel_transient_start(self, profile_id: str, alert_id: str) -> bool:
        """Drop a start/resolution pair that never left its collection window."""
        key = (profile_id, "started")
        batch = self._batches.get(key)
        if batch is None or batch.items.pop(alert_id, None) is None:
            return False
        if not batch.items:
            if batch.cancel is not None:
                batch.cancel()
            self._batches.pop(key, None)
        return True

    async def _async_flush_batch(self, profile_id: str, kind: str) -> None:
        """Render and deliver one profile batch outside alert transitions."""
        batch = self._batches.pop((profile_id, kind), None)
        if batch is None or not batch.items:
            return
        try:
            profile = self._profile(profile_id)
        except ValueError:
            return
        items = list(batch.items.values())
        title, message = self._render_batch(kind, items)
        url = self._batch_url(kind, items)
        await self._delivery.async_send(
            primary_targets=profile["primary_targets"],
            fallback_targets=profile["fallback_targets"],
            title=title,
            message=message,
            click_url=url,
        )

    async def _async_send_reminders(self) -> None:
        """Send all due reminders in one grouped delivery per profile."""
        async with self._runtime_lock:
            deliveries = await self._async_collect_due_reminders_locked()
        for profile, title, message, url in deliveries:
            await self._delivery.async_send(
                primary_targets=profile["primary_targets"],
                fallback_targets=profile["fallback_targets"],
                title=title,
                message=message,
                click_url=url,
            )

    async def _async_collect_due_reminders_locked(
        self,
    ) -> list[tuple[dict[str, Any], str, str, str]]:
        """Advance due reminders atomically and return deliveries to perform."""
        self._reminder_cancel = None
        config = self._config_getter()
        if not config.get("monitoring_enabled", True):
            return []
        now = dt_util.now().astimezone(UTC)
        records = self._records_getter()
        changed = False
        deliveries: list[tuple[dict[str, Any], str, str, str]] = []
        for profile in config.get("notification_profiles", []):
            if not profile.get("enabled"):
                continue
            due_items: list[_NotificationItem] = []
  