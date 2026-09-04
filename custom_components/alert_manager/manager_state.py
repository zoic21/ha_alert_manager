"""Alert state, persistence, timers and lifecycle events."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.core import CoreState, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .const import (
    CATEGORY_UNAVAILABLE,
    DEVICE_EVENT_DEBOUNCE_SECONDS,
    EVENT_ALERT_ACKNOWLEDGED,
    EVENT_ALERT_RESOLVED,
    EVENT_ALERT_STARTED,
    EVENT_ALERT_UNACKNOWLEDGED,
    EVENT_DEVICE_ALERT_STARTED,
    LIVE_MESSAGE_FLUSH_INTERVAL_SECONDS,
    SIGNAL_ALERTS_UPDATED,
    SIGNAL_HISTORY_UPDATED,
)
from .models import AlertRecord, AlertStatus, calculate_due_at
from .runtime_phase import RuntimePhase
from .storage import sort_history

_LOGGER = logging.getLogger(__name__)


class _StateMixin:
    """Maintain live alert state, durability, timers and emitted events."""

    def _rebuild_record_index(self) -> None:
        """Rebuild the entity lookup cache from authoritative runtime records."""
        index: dict[str, set[str]] = {}
        for alert_id, record in self.records.items():
            index.setdefault(record.details.entity_id, set()).add(alert_id)
        self._record_ids_by_entity = index

    def _set_record(self, record: AlertRecord) -> None:
        """Store one authoritative record and update its entity lookup entry."""
        alert_id = record.details.id
        previous = self.records.get(alert_id)
        if (
            previous is not None
            and previous.details.entity_id != record.details.entity_id
        ):
            self._remove_record_from_index(alert_id, previous.details.entity_id)
        self.records[alert_id] = record
        self._record_ids_by_entity.setdefault(record.details.entity_id, set()).add(
            alert_id
        )

    def _pop_record(self, alert_id: str) -> AlertRecord | None:
        """Remove one authoritative record and its entity lookup entry."""
        record = self.records.pop(alert_id, None)
        if record is not None:
            if self._startup_reconciliation_transaction is not None:
                self._startup_reconciliation_transaction.record_removed(alert_id)
            self._unverified_restored_alert_ids.discard(alert_id)
            self._remove_record_from_index(alert_id, record.details.entity_id)
        return record

    def _replace_records(self, records: dict[str, AlertRecord]) -> None:
        """Replace authoritative records and rebuild the derived lookup cache."""
        self.records = records
        self._unverified_restored_alert_ids.intersection_update(records)
        self._rebuild_record_index()

    def _remove_record_from_index(self, alert_id: str, entity_id: str) -> None:
        """Discard one cached record id and remove empty entity buckets."""
        record_ids = self._record_ids_by_entity.get(entity_id)
        if record_ids is None:
            return
        record_ids.discard(alert_id)
        if not record_ids:
            self._record_ids_by_entity.pop(entity_id, None)

    def _build_public_snapshot(
        self,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        """Build one public snapshot and its already-grouped active devices."""
        now = dt_util.now()
        active_records = sorted(
            (
                record
                for record in self.records.values()
                if record.status is AlertStatus.ACTIVE
            ),
            key=lambda record: (record.active_since or record.due_at).astimezone(UTC),
        )
        pending_records = sorted(
            (
                record
                for record in self.records.values()
                if record.status is AlertStatus.PENDING
                and self._pending_is_visible(record, now)
                and not (
                    self._runtime_phase.is_startup
                    and record.details.type == CATEGORY_UNAVAILABLE
                )
            ),
            key=lambda record: record.due_at.astimezone(UTC),
        )
        unacknowledged: list[dict[str, Any]] = []
        acknowledged: list[dict[str, Any]] = []
        for record in active_records:
            target = acknowledged if record.acknowledged else unacknowledged
            target.append(record.as_public_dict())
        pending = [record.as_public_dict() for record in pending_records]
        device_groups = self._active_device_groups(active_records)
        active_devices = sorted(
            device_groups.values(),
            key=lambda device: (
                str(device["device_name"]).casefold(),
                device["device_id"],
            ),
        )
        return (
            {
                "active_count": len(unacknowledged),
                "acknowledge_count": len(acknowledged),
                "pending_count": len(pending),
                "tracked_count": self._tracked_count(),
                "alerts": unacknowledged,
                "acknowledge": acknowledged,
                "pending": pending,
                "device_active_count": len(active_devices),
                "active_devices": active_devices,
                "startup": {
                    "in_progress": self._runtime_phase.is_startup,
                    "stabilization_until": (
                        self._startup_reconciliation_deadline.isoformat()
                        if self._startup_reconciliation_deadline is not None
                        else None
                    ),
                },
            },
            device_groups,
        )

    def _pending_is_visible(
        self, record: AlertRecord, now: datetime | None = None
    ) -> bool:
        """Return whether a pending occurrence reached its presentation time."""
        if record.status is not AlertStatus.PENDING:
            return False
        if record.visible_at is None:
            return True
        current = now or dt_util.now()
        return current.astimezone(UTC) >= record.visible_at.astimezone(UTC)

    def _recalculate_hidden_pending_visibility(
        self, record: AlertRecord, now: datetime
    ) -> None:
        """Apply current settings only while a pending alert is still hidden."""
        if record.status is not AlertStatus.PENDING or self._pending_is_visible(
            record, now
        ):
            return
        record.visible_at = calculate_due_at(
            record.detected_at,
            min(self.config["pending_display_delay"], record.delay),
        ) + timedelta(seconds=record.paused_seconds)

    def _active_device_groups(
        self, active_records: list[AlertRecord] | None = None
    ) -> dict[str, dict[str, Any]]:
        """Group registry devices by name and device-less sources by entity."""
        records = active_records
        if records is None:
            records = sorted(
                (
                    record
                    for record in self.records.values()
                    if record.status is AlertStatus.ACTIVE
                ),
                key=lambda record: (record.active_since or record.due_at).astimezone(
                    UTC
                ),
            )
        grouped: dict[str, list[AlertRecord]] = {}
        for record in records:
            if record.details.device_id:
                device_name = (
                    record.details.device_name or record.details.device_id
                ).strip()
                group_id = f"device-name:{device_name.casefold()}"
            else:
                group_id = f"entity:{record.details.entity_id}"
            grouped.setdefault(group_id, []).append(record)

        devices: dict[str, dict[str, Any]] = {}
        for group_id, device_records in grouped.items():
            ordered = device_records
            first = ordered[0]
            device_ids = sorted(
                {
                    record.details.device_id or record.details.entity_id
                    for record in ordered
                }
            )
            device_id = device_ids[0]
            device_name = (
                first.details.device_name
                or first.details.name
                or first.details.entity_id
            ).strip()
            alert_ids = [record.details.id for record in ordered]
            messages = list(
                dict.fromkeys(
                    record.details.message
                    for record in ordered
                    if record.details.message
                )
            )
            rules = list(
                dict.fromkeys(
                    record.details.rule_name or record.details.type
                    for record in ordered
                )
            )
            acknowledged = sum(record.acknowledged for record in ordered)
            devices[group_id] = {
                "device_id": device_id,
                "device_ids": device_ids,
                "device_name": device_name,
                "area": first.details.area,
                "started_at": (first.active_since or first.due_at).isoformat(),
                "alert_count": len(ordered),
                "unacknowledged_alert_count": len(ordered) - acknowledged,
                "acknowledged_alert_count": acknowledged,
                "alert_ids": alert_ids,
                "messages": messages,
                "rules": rules,
            }
        return devices

    def _cancel_all_timers(self) -> None:
        """Cancel each scheduled due transition before a full rebuild."""
        for cancel in self._timers.values():
            cancel()
        self._timers.clear()

    async def _async_save_state(self) -> None:
        """Persist runtime first, then archive without coupling business success."""
        live_message_flush_pending = self._live_message_flush_pending
        self._cancel_live_message_flush()
        if self.recovery_active:
            self._immediate_state_save_required = False
            self._variation_baselines_dirty = False
            return
        immediate_save_required = self._immediate_state_save_required
        variation_baselines_dirty = self._variation_baselines_dirty
        self._immediate_state_save_required = False
        self._variation_baselines_dirty = False
        saved = False
        try:
            await self.storage.async_save(self.config, self.records)
            saved = True
        finally:
            if not saved:
                self._immediate_state_save_required |= immediate_save_required
                self._variation_baselines_dirty |= variation_baselines_dirty
                if (
                    live_message_flush_pending
                    and not self._unloading
                    and self._runtime_phase is not RuntimePhase.STOPPING
                ):
                    self._schedule_live_message_flush()
        await self._async_flush_history()

    def _schedule_live_message_flush(self) -> None:
        """Persist and publish the latest live messages at a bounded frequency."""
        if (
            self._unloading
            or self._runtime_phase is not RuntimePhase.RUNNING
            or self.hass.state is not CoreState.running
        ):
            return
        self._live_message_flush_pending = True
        if self._live_message_flush_timer is not None:
            return

        @callback
        def timer_due(_now: datetime) -> None:
            self._live_message_flush_timer = None
            if (
                self._unloading
                or not self._live_message_flush_pending
                or self._runtime_phase is not RuntimePhase.RUNNING
                or self.hass.state is not CoreState.running
            ):
                return
            self.entry.async_create_task(
                self.hass,
                self._async_flush_live_messages(),
                name="alert_manager live-message flush",
            )

        self._live_message_flush_timer = async_track_point_in_utc_time(
            self.hass,
            timer_due,
            (
                dt_util.now() + timedelta(seconds=LIVE_MESSAGE_FLUSH_INTERVAL_SECONDS)
            ).astimezone(UTC),
        )

    async def _async_flush_live_messages(self) -> None:
        """Write and publish the most recent values for every live message."""
        async with self._config_mutation_lock:
            if (
                self._unloading
                or self._runtime_phase is not RuntimePhase.RUNNING
                or self.hass.state is not CoreState.running
                or not self._live_message_flush_pending
            ):
                return
            await self._async_save_state()
            self._publish_if_changed()

    def _cancel_live_message_flush(self) -> None:
        """Cancel a redundant delayed flush after an immediate durable write."""
        if self._live_message_flush_timer is not None:
            self._live_message_flush_timer()
            self._live_message_flush_timer = None
        self._live_message_flush_pending = False

    async def _async_flush_history(self) -> None:
        """Best-effort archive queued resolutions after runtime is durable."""
        if not self._pending_history:
            return
        if self.config["history_limit"] == 0:
            self._pending_history.clear()
            return
        candidate = sort_history([*self.history, *self._pending_history])[
            : self.config["history_limit"]
        ]
        try:
            await self.history_storage.async_save(candidate)
        except Exception:
            _LOGGER.exception(
                "Unable to persist completed alert history; runtime transition "
                "remains valid"
            )
            return
        self.history = candidate
        self._pending_history.clear()
        async_dispatcher_send(self.hass, SIGNAL_HISTORY_UPDATED)

    def _trim_history(self) -> bool:
        """Apply the configured retention limit deterministically in memory."""
        trimmed = sort_history(self.history)[: self.config["history_limit"]]
        if trimmed == self.history:
            return False
        self.history = trimmed
        return True

    def _freeze_pending_alerts(self, now: datetime) -> bool:
        """Remember when each pending delay stopped consuming monitored time."""
        changed = False
        for record in self.records.values():
            if record.status is AlertStatus.PENDING and record.paused_at is None:
                record.paused_at = now
                changed = True
        return changed

    def _resume_pending_alerts(self, now: datetime) -> bool:
        """Move due dates by the suspension duration, preserving remaining time."""
        changed = False
        now_utc = now.astimezone(UTC)
        for record in self.records.values():
            if record.status is not AlertStatus.PENDING or record.paused_at is None:
                continue
            paused_for = now_utc - record.paused_at.astimezone(UTC)
            if paused_for.total_seconds() > 0:
                record.due_at += paused_for
                if record.visible_at is not None:
                    record.visible_at += paused_for
                record.paused_seconds += paused_for.total_seconds()
            record.paused_at = None
            changed = True
        return changed

    def _reschedule_record_timers(self) -> None:
        """Restore pending transition and presentation timers."""
        if (
            not self.monitoring_enabled
            or self._runtime_phase is not RuntimePhase.RUNNING
            or self.hass.state is not CoreState.running
        ):
            return
        for record in self.records.values():
            if record.status is AlertStatus.PENDING:
                self._schedule_timer(record)

    def _reschedule_hidden_pending_visibility(self, now: datetime) -> None:
        """Recalculate only not-yet-exposed pending alerts and their timers."""
        for record in self.records.values():
            if record.status is not AlertStatus.PENDING:
                continue
            self._recalculate_hidden_pending_visibility(record, now)
            self._cancel_timer(record.details.id)
            self._schedule_timer(record)

    def _schedule_timer(self, record: AlertRecord) -> None:
        """Schedule exactly one lifecycle or presentation timer for an alert."""
        if (
            not self.monitoring_enabled
            or self._runtime_phase is not RuntimePhase.RUNNING
            or self.hass.state is not CoreState.running
        ):
            return
        alert_id = record.details.id
        self._cancel_timer(alert_id)
        if record.status is not AlertStatus.PENDING:
            return
        when = record.due_at.astimezone(UTC)
        if record.visible_at is not None and not self._pending_is_visible(record):
            when = min(when, record.visible_at.astimezone(UTC))

        @callback
        def timer_due(_now: datetime) -> None:
            self._timer_due(alert_id)

        self._timers[alert_id] = async_track_point_in_utc_time(
            self.hass,
            timer_due,
            when,
        )

    @callback
    def _timer_due(self, alert_id: str) -> None:
        """Fold due timers into the same batched evaluation path."""
        self._timers.pop(alert_id, None)
        if (
            not self.monitoring_enabled
            or self._runtime_phase is not RuntimePhase.RUNNING
            or self.hass.state is not CoreState.running
        ):
            return
        record = self.records.get(alert_id)
        if record is None:
            return
        self._queued_public_refresh = True
        self._queue_entity_evaluations((record.details.entity_id,))

    def _cancel_timer(self, alert_id: str) -> None:
        """Cancel a pending timer if present."""
        if cancel := self._timers.pop(alert_id, None):
            cancel()

    def _fire_started(self, record: AlertRecord) -> None:
        """Emit the documented start event exactly on activation."""
        self.hass.bus.async_fire(EVENT_ALERT_STARTED, record.as_public_dict())

    def _fire_resolved(self, record: AlertRecord, now: datetime) -> None:
        """Emit resolution information without retaining history."""
        data = record.as_public_dict()
        data["resolved_at"] = now.isoformat()
        self.hass.bus.async_fire(EVENT_ALERT_RESOLVED, data)

    def _fire_acknowledged(self, record: AlertRecord) -> None:
        """Emit an acknowledgement event only after durable state changed."""
        self.hass.bus.async_fire(EVENT_ALERT_ACKNOWLEDGED, record.as_public_dict())

    def _fire_unacknowledged(
        self,
        record: AlertRecord,
        now: datetime,
        actor: str | None,
        previous_at: datetime | None,
        previous_by: str | None,
    ) -> None:
        """Emit removal metadata without retaining it on the active alert."""
        data = record.as_public_dict()
        data["unacknowledged_at"] = now.isoformat()
        if actor is not None:
            data["unacknowledged_by"] = actor
        if previous_at is not None:
            data["previous_acknowledged_at"] = previous_at.isoformat()
        if previous_by is not None:
            data["previous_acknowledged_by"] = previous_by
        self.hass.bus.async_fire(EVENT_ALERT_UNACKNOWLEDGED, data)

    def _schedule_new_device_alerts(self, devices: dict[str, dict[str, Any]]) -> None:
        """Debounce the first device event until its alert set is quiet."""
        current_group_ids = set(devices)
        for group_id in self._active_device_group_ids - current_group_ids:
            self._cancel_device_event_timer(group_id)
        for group_id, device in devices.items():
            current_alert_ids = frozenset(device["alert_ids"])
            is_new_group = group_id not in self._active_device_group_ids
            pending_alert_ids = self._device_event_alert_ids.get(group_id)
            has_new_pending_alert = bool(
                pending_alert_ids is not None and current_alert_ids - pending_alert_ids
            )
            if is_new_group or has_new_pending_alert:
                self._schedule_device_event_timer(group_id, current_alert_ids)
        self._active_device_group_ids = set(devices)

    def _schedule_device_event_timer(
        self, group_id: str, alert_ids: frozenset[str]
    ) -> None:
        """Restart one per-device quiet-period timer."""
        if self._unloading or self._runtime_phase is RuntimePhase.STOPPING:
            return
        self._cancel_device_event_timer(group_id)
        self._device_event_alert_ids[group_id] = alert_ids

        @callback
        def timer_due(_now: datetime) -> None:
            self._device_event_timers.pop(group_id, None)
            self._device_event_alert_ids.pop(group_id, None)
            if (
                self._unloading
                or not self.monitoring_enabled
                or self._runtime_phase is RuntimePhase.STOPPING
            ):
                return
            device = self._active_device_groups().get(group_id)
            if device is not None:
                event_data = {
                    key: value for key, value in device.items() if key != "device_id"
                }
                event_data["messages"] = list(
                    dict.fromkeys(
                        record.details.message
                        or record.details.rule_name
                        or record.details.type
                        for alert_id in device["alert_ids"]
                        if (record := self.records.get(alert_id)) is not None
                    )
                )
                self.hass.bus.async_fire(EVENT_DEVICE_ALERT_STARTED, event_data)

        self._device_event_timers[group_id] = async_track_point_in_utc_time(
            self.hass,
            timer_due,
            (
                dt_util.now() + timedelta(seconds=DEVICE_EVENT_DEBOUNCE_SECONDS)
            ).astimezone(UTC),
        )

    def _cancel_device_event_timer(self, group_id: str) -> None:
        """Cancel one pending device event and forget its debounce snapshot."""
        if cancel := self._device_event_timers.pop(group_id, None):
            cancel()
        self._device_event_alert_ids.pop(group_id, None)

    def _cancel_all_device_event_timers(self) -> None:
        """Cancel every pending device event during unload or suspension."""
        for cancel in self._device_event_timers.values():
            cancel()
        self._device_event_timers.clear()
        self._device_event_alert_ids.clear()

    def _publish_if_changed(self, *, force: bool = False) -> None:
        """Avoid redundant sensor writes and Recorder churn."""
        if self._unloading or self._runtime_phase is RuntimePhase.STOPPING:
            return
        live_message_pairs = {
            (rule.id, entity_id)
            for rule in self._rules
            if rule.enabled
            and rule.message is not None
            and rule.update_message_when_active
            for entity_id in rule.entity_ids
        }
        for record in self.records.values():
            if record.status is not AlertStatus.ACTIVE or not record.details.rule_id:
                continue
            pair = (record.details.rule_id, record.details.entity_id)
            if pair in live_message_pairs:
                continue
            self._rule_message_render_info.pop(pair, None)
            self._remove_dependency_key(("message", pair[0], pair[1]))
        snapshot, device_groups = self._build_public_snapshot()
        if not force and snapshot == self._last_public_snapshot:
            return
        self._schedule_new_device_alerts(device_groups)
        self._last_public_snapshot = snapshot
        async_dispatcher_send(self.hass, SIGNAL_ALERTS_UPDATED)
