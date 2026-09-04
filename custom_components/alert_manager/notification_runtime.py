"""Event-driven notification delivery, batching and reminder scheduling."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
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
    SIGNAL_NOTIFICATION_LIFECYCLE,
)
from .models import AlertRecord, AlertStatus
from .notifications import (
    NotificationManager,
    NotificationPolicy,
    profile_matches_labels,
    resolve_notification_policy,
)

_LOGGER = logging.getLogger(__name__)

_RUNTIME_SAVE_DELAY_SECONDS = 1
_USAGE_WINDOW_HOURS = 24


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
        """Build a bounded item from a lifecycle payload."""
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
        self._usage: dict[str, dict[int, int]] = {}
        self._persisted_runtime: dict[str, Any] = {"profiles": {}, "usage": {}}
        self._label_cache: dict[str, frozenset[str]] = {}
        self._batches: dict[tuple[str, str], _PendingBatch] = {}
        self._unsubscribe: list[Callable[[], None]] = []
        self._reminder_cancel: Callable[[], None] | None = None
        self._runtime_save_cancel: Callable[[], None] | None = None
        self._tasks: set[asyncio.Task[Any]] = set()
        self._unloading = False
        self._setup_complete = False
        self._accept_events = True
        self._events_pause_depth = 0
        self._event_generation = 0

    @callback
    def pause_events(self) -> None:
        """Ignore lifecycle events manufactured by a configuration rebuild."""
        self._events_pause_depth += 1
        self._event_generation += 1
        self._accept_events = False

    @callback
    def resume_events(self) -> None:
        """Resume normal lifecycle consumption after runtime reconciliation."""
        self._events_pause_depth = max(0, self._events_pause_depth - 1)
        self._accept_events = self._events_pause_depth == 0

    @contextmanager
    def events_paused(self) -> Iterator[None]:
        """Guarantee lifecycle consumption resumes after a config transaction."""
        self.pause_events()
        try:
            yield
        finally:
            self.resume_events()

    @callback
    def discard_batches(self) -> None:
        """Discard unsent batches after policies change or monitoring stops."""
        for batch in self._batches.values():
            if batch.cancel is not None:
                batch.cancel()
        self._batches.clear()

    async def async_discard_alerts(self, alert_ids: set[str]) -> None:
        """Forget alerts silently removed by their owning configuration."""
        if not alert_ids:
            return
        async with self._runtime_lock:
            runtime_changed = False
            for profile_runtime in self._runtime.values():
                for alert_id in alert_ids:
                    if profile_runtime.pop(alert_id, None) is not None:
                        runtime_changed = True
            for key, batch in tuple(self._batches.items()):
                for alert_id in alert_ids:
                    batch.items.pop(alert_id, None)
                if batch.items:
                    continue
                if batch.cancel is not None:
                    batch.cancel()
                self._batches.pop(key, None)
            if runtime_changed:
                self._schedule_runtime_save()
                self._schedule_reminder_timer()

    async def async_setup(self) -> None:
        """Restore runtime state, then subscribe after initial alert evaluation."""
        await self._async_load_runtime()
        self._unsubscribe.append(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_NOTIFICATION_LIFECYCLE,
                self._lifecycle_event_received,
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
        self._cancel_runtime_save()
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
        self._prune_usage(now)
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
        self._cancel_runtime_save()
        await self._async_save_runtime()
        self._schedule_reminder_timer()

    @callback
    def _lifecycle_event_received(
        self, event_type: str, data: Mapping[str, Any]
    ) -> None:
        """Snapshot one trusted internal lifecycle signal without blocking."""
        if self._unloading or not self._accept_events:
            return
        config = self._config_getter()
        if not config.get("monitoring_enabled", True) or not any(
            profile.get("enabled")
            for profile in config.get("notification_profiles", [])
        ):
            return
        generation = self._event_generation
        self._create_task(
            self._async_handle_event(event_type, dict(data), generation=generation),
            f"alert_manager notification {event_type}",
        )

    async def _async_handle_event(
        self,
        event_type: str,
        data: Mapping[str, Any],
        *,
        generation: int | None = None,
    ) -> None:
        """Route one lifecycle event into profile batches and reminder state."""
        async with self._runtime_lock:
            if generation is not None and generation != self._event_generation:
                return
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
            if not profile.get("enabled"):
                continue
            profile_id = profile["id"]
            matches_labels = profile_matches_labels(profile, labels)
            tracks_alert = item.alert_id in self._runtime.get(profile_id, {})
            if event_type == EVENT_ALERT_RESOLVED:
                tracks_alert = tracks_alert or self._batch_contains(
                    profile_id, "started", item.alert_id
                )
            if not matches_labels and not (
                event_type == EVENT_ALERT_RESOLVED and tracks_alert
            ):
                continue
            policy = resolve_notification_policy(
                profile,
                pack_id=item.alert_type if item.rule_id is None else None,
                rule_id=item.rule_id,
                label_ids=labels,
            )
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
            self._schedule_runtime_save()
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

    def _batch_contains(self, profile_id: str, kind: str, alert_id: str) -> bool:
        """Return whether an alert is retained in one unsent batch."""
        batch = self._batches.get((profile_id, kind))
        return batch is not None and alert_id in batch.items

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
        result = await self._delivery.async_send(
            targets=profile["targets"],
            title=title,
            message=message,
            click_url=url,
        )
        await self._async_record_usage(profile_id, result)

    async def _async_send_reminders(self) -> None:
        """Send all due reminders in one grouped delivery per profile."""
        async with self._runtime_lock:
            deliveries = await self._async_collect_due_reminders_locked()
        for profile, title, message, url in deliveries:
            result = await self._delivery.async_send(
                targets=profile["targets"],
                title=title,
                message=message,
                click_url=url,
            )
            await self._async_record_usage(profile["id"], result)

    async def _async_record_usage(
        self, profile_id: str, result: Mapping[str, Any]
    ) -> None:
        """Count one successful profile delivery in its current hourly bucket."""
        delivered = result.get("delivered_targets")
        if not isinstance(delivered, list) or not delivered:
            return
        async with self._runtime_lock:
            configured_ids = {
                profile["id"]
                for profile in self._config_getter().get("notification_profiles", [])
            }
            if profile_id not in configured_ids:
                return
            now = dt_util.now().astimezone(UTC)
            self._prune_usage(now)
            bucket = _usage_bucket(now)
            buckets = self._usage.setdefault(profile_id, {})
            buckets[bucket] = buckets.get(bucket, 0) + 1
            self._schedule_runtime_save()

    @callback
    def usage_snapshot(self) -> dict[str, dict[str, int]]:
        """Return current per-profile usage without exposing stored buckets."""
        if self._prune_usage(dt_util.now().astimezone(UTC)):
            self._schedule_runtime_save()
        profile_ids = sorted(
            profile["id"]
            for profile in self._config_getter().get("notification_profiles", [])
        )
        return {
            "last_24h": {
                profile_id: sum(self._usage.get(profile_id, {}).values())
                for profile_id in profile_ids
            }
        }

    @callback
    def _prune_usage(self, now: datetime) -> bool:
        """Keep only configured profiles and the current 24 hourly buckets."""
        newest = _usage_bucket(now)
        oldest = newest - _USAGE_WINDOW_HOURS + 1
        configured_ids = {
            profile["id"]
            for profile in self._config_getter().get("notification_profiles", [])
        }
        retained = {
            profile_id: {
                bucket: count
                for bucket, count in buckets.items()
                if oldest <= bucket <= newest
            }
            for profile_id, buckets in self._usage.items()
            if profile_id in configured_ids
        }
        retained = {
            profile_id: buckets for profile_id, buckets in retained.items() if buckets
        }
        if retained == self._usage:
            return False
        self._usage = retained
        return True

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
            profile_runtime = self._runtime.get(profile["id"], {})
            for alert_id, runtime in list(profile_runtime.items()):
                if runtime.next_reminder is None or runtime.next_reminder > now:
                    continue
                record = records.get(alert_id)
                if (
                    record is None
                    or record.status is not AlertStatus.ACTIVE
                    or record.acknowledged
                ):
                    profile_runtime.pop(alert_id, None)
                    changed = True
                    continue
                labels = self._labels_for(
                    record.details.entity_id, record.details.device_id
                )
                if not profile_matches_labels(profile, labels):
                    profile_runtime.pop(alert_id, None)
                    changed = True
                    continue
                policy = _policy_for_record(profile, record, labels)
                if policy.reminder_interval is None:
                    runtime.next_reminder = None
                    changed = True
                    continue
                item = _NotificationItem.from_event(record.as_public_dict())
                if item is not None:
                    due_items.append(item)
                runtime.next_reminder = now + timedelta(
                    seconds=policy.reminder_interval
                )
                changed = True
            if due_items:
                title, message = self._render_batch("reminder", due_items)
                deliveries.append(
                    (
                        profile,
                        title,
                        message,
                        self._batch_url("started", due_items),
                    )
                )
        if changed:
            self._schedule_runtime_save()
        self._schedule_reminder_timer()
        return deliveries

    def _schedule_reminder_timer(self) -> None:
        """Keep exactly one timer for the earliest reminder deadline."""
        self._cancel_reminder_timer()
        if self._unloading or not self._config_getter().get("monitoring_enabled", True):
            return
        deadlines = [
            runtime.next_reminder
            for profile_runtime in self._runtime.values()
            for runtime in profile_runtime.values()
            if runtime.next_reminder is not None
        ]
        if not deadlines:
            return

        @callback
        def timer_due(_now: datetime) -> None:
            self._reminder_cancel = None
            if not self._unloading:
                self._create_task(
                    self._async_send_reminders(),
                    "alert_manager notification reminders",
                )

        self._reminder_cancel = async_track_point_in_utc_time(
            self.hass, timer_due, min(deadlines).astimezone(UTC)
        )

    def _cancel_reminder_timer(self) -> None:
        """Cancel the shared reminder deadline if present."""
        if self._reminder_cancel is not None:
            self._reminder_cancel()
            self._reminder_cancel = None

    @callback
    def _schedule_runtime_save(self) -> None:
        """Coalesce a burst of runtime mutations into one storage write."""
        if self._unloading or self._runtime_save_cancel is not None:
            return

        @callback
        def timer_due(_now: datetime) -> None:
            self._runtime_save_cancel = None
            if not self._unloading:
                self._create_task(
                    self._async_flush_runtime_save(),
                    "alert_manager notification runtime save",
                )

        self._runtime_save_cancel = async_track_point_in_utc_time(
            self.hass,
            timer_due,
            dt_util.now().astimezone(UTC)
            + timedelta(seconds=_RUNTIME_SAVE_DELAY_SECONDS),
        )

    async def _async_flush_runtime_save(self) -> None:
        """Persist the latest coalesced snapshot under the runtime lock."""
        async with self._runtime_lock:
            await self._async_save_runtime()

    @callback
    def _cancel_runtime_save(self) -> None:
        """Cancel a pending coalesced write before a forced save."""
        if self._runtime_save_cancel is not None:
            self._runtime_save_cancel()
            self._runtime_save_cancel = None

    def _render_batch(
        self, kind: str, items: list[_NotificationItem]
    ) -> tuple[str, str]:
        """Render compact device-grouped notification text."""
        count = len(items)
        title_key = {
            "started": "started_title",
            "resolved": "resolved_title",
            "reminder": "reminder_title",
        }[kind]
        fallback = {
            "started": f"Alert Manager — {count} new alert(s)",
            "resolved": f"Alert Manager — {count} back to normal",
            "reminder": f"Alert Manager — {count} active alert(s)",
        }[kind]
        title = self._delivery.text(title_key, fallback).replace("{count}", str(count))
        grouped: dict[str, list[_NotificationItem]] = {}
        for item in items:
            key = (
                f"device:{item.device_id}"
                if item.device_id
                else f"entity:{item.entity_id}"
            )
            grouped.setdefault(key, []).append(item)
        lines: list[str] = []
        for grouped_items in grouped.values():
            first = grouped_items[0]
            name = first.device_name or first.name
            if len(grouped_items) > 1:
                summary = self._delivery.text(
                    "grouped_alerts", "{count} alerts"
                ).replace("{count}", str(len(grouped_items)))
            else:
                summary = first.message or first.condition or first.alert_type
            lines.append(f"• {name} — {summary}")
        return title, "\n".join(lines)

    @staticmethod
    def _batch_url(kind: str, items: list[_NotificationItem]) -> str:
        """Return a stable panel URL, specializing only unambiguous live alerts."""
        if kind != "resolved" and len(items) == 1:
            return f"/alert-manager?alert={quote(items[0].alert_id, safe='')}"
        if kind == "resolved" and len(items) == 1:
            return "/alert-manager/history"
        return "/alert-manager"

    def _profile(self, profile_id: str) -> dict[str, Any]:
        """Resolve one enabled profile or raise a stable API error."""
        for profile in self._config_getter().get("notification_profiles", []):
            if profile["id"] == profile_id:
                if not profile["enabled"]:
                    raise ValueError(f"Notification profile is disabled: {profile_id}")
                return profile
        raise ValueError(f"Unknown notification profile id: {profile_id}")

    def _labels_for(self, entity_id: str, device_id: str | None) -> frozenset[str]:
        """Cache the union of native entity and device labels without scans."""
        cache_key = f"{entity_id}|{device_id or ''}"
        if cache_key in self._label_cache:
            return self._label_cache[cache_key]
        labels: set[str] = set()
        entity_entry = self._entity_registry.async_get(entity_id)
        labels.update(getattr(entity_entry, "labels", ()) or ())
        resolved_device_id = device_id or getattr(entity_entry, "device_id", None)
        if resolved_device_id:
            device = self._device_registry.async_get(resolved_device_id)
            labels.update(getattr(device, "labels", ()) or ())
        result = frozenset(labels)
        self._label_cache[cache_key] = result
        return result

    @callback
    def registry_changed(self) -> None:
        """Invalidate derived labels from the manager's registry listener."""
        self._label_cache.clear()

    async def _async_load_runtime(self) -> None:
        """Load only valid bounded reminder state from the independent store."""
        try:
            raw = await self._store.async_load()
        except Exception:
            _LOGGER.exception("Unable to load Alert Manager notification runtime")
            return
        if not isinstance(raw, dict) or not isinstance(raw.get("profiles", {}), dict):
            return
        self._persisted_runtime = raw
        raw_profiles = raw.get("profiles", {})
        raw_usage = raw.get("usage", {})
        configured_profile_ids = {
            profile["id"]
            for profile in self._config_getter().get("notification_profiles", [])
        }
        profile_ids = {
            profile["id"]
            for profile in self._config_getter().get("notification_profiles", [])
            if profile.get("enabled")
        }
        active_alert_ids = {
            alert_id
            for alert_id, record in self._records_getter().items()
            if record.status is AlertStatus.ACTIVE
        }
        for profile_id in profile_ids:
            raw_entries = raw_profiles.get(profile_id)
            if not isinstance(raw_entries, dict):
                continue
            entries: dict[str, _RuntimeEntry] = {}
            for alert_id in active_alert_ids:
                raw_entry = raw_entries.get(alert_id)
                if not isinstance(raw_entry, dict):
                    continue
                next_reminder = _parse_datetime(raw_entry.get("next_reminder"))
                entries[alert_id] = _RuntimeEntry(next_reminder=next_reminder)
            if entries:
                self._runtime[profile_id] = entries
        if isinstance(raw_usage, dict):
            newest = _usage_bucket(dt_util.now().astimezone(UTC))
            oldest = newest - _USAGE_WINDOW_HOURS + 1
            for profile_id in configured_profile_ids:
                raw_buckets = raw_usage.get(profile_id)
                if not isinstance(raw_buckets, dict):
                    continue
                buckets: dict[int, int] = {}
                for raw_bucket, count in raw_buckets.items():
                    try:
                        bucket = int(raw_bucket)
                    except (TypeError, ValueError):
                        continue
                    if (
                        isinstance(count, bool)
                        or not isinstance(count, int)
                        or count <= 0
                        or not oldest <= bucket <= newest
                    ):
                        continue
                    buckets[bucket] = count
                if buckets:
                    self._usage[profile_id] = buckets

    async def _async_save_runtime(self) -> None:
        """Persist minimal recipient state without touching AlertRecord."""
        payload = self._runtime_payload()
        if payload == self._persisted_runtime:
            return
        try:
            await self._store.async_save(payload)
        except Exception:
            _LOGGER.exception("Unable to persist Alert Manager notification runtime")
            return
        self._persisted_runtime = payload

    def _runtime_payload(self) -> dict[str, Any]:
        """Build the deterministic independent store payload."""
        return {
            "profiles": {
                profile_id: {
                    alert_id: runtime.as_dict()
                    for alert_id, runtime in sorted(entries.items())
                }
                for profile_id, entries in sorted(self._runtime.items())
                if entries
            },
            "usage": {
                profile_id: {
                    str(bucket): count for bucket, count in sorted(buckets.items())
                }
                for profile_id, buckets in sorted(self._usage.items())
                if buckets
            },
        }

    def _create_task(self, coroutine: Any, name: str) -> None:
        """Track an integration-owned task so unload remains deterministic."""
        task = self.entry.async_create_task(self.hass, coroutine, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


def _policy_for_record(
    profile: dict[str, Any], record: AlertRecord, labels: frozenset[str]
) -> NotificationPolicy:
    """Resolve a profile policy from authoritative alert metadata."""
    return resolve_notification_policy(
        profile,
        pack_id=record.details.type if record.details.rule_id is None else None,
        rule_id=record.details.rule_id,
        label_ids=labels,
    )


def _parse_datetime(value: Any) -> datetime | None:
    """Parse an aware stored datetime, ignoring malformed runtime data."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _usage_bucket(value: datetime) -> int:
    """Return a stable UTC hour number for compact persisted aggregation."""
    return int(value.astimezone(UTC).timestamp()) // 3600


def _optional_text(value: Any) -> str | None:
    """Return bounded event text or null."""
    if not isinstance(value, str) or not value:
        return None
    return value[:1024]
