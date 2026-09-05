"""Runtime evaluation pipeline for Alert Manager."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryChange
from homeassistant.const import (
    ATTR_FRIENDLY_NAME,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CoreState, Event, State, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from .const import (
    CATEGORY_UNAVAILABLE,
    DOMAIN,
    STARTUP_RECONCILIATION_DELAY_SECONDS,
    VARIATION_SOURCES,
)
from .models import (
    AlertDetails,
    AlertHistoryEntry,
    AlertRecord,
    AlertStatus,
    Rule,
    advance_record,
    calculate_due_at,
    safe_float,
)
from .packs import (
    OCCURRENCE_PACKS,
    PACKS,
    PACKS_BY_ID,
    PackNeutral,
    PackOccurrence,
    PackRecheck,
)
from .rule_evaluation import RuleEvaluation, evaluate_rule, rule_current_value
from .runtime_phase import RuntimePhase
from .transactions import (
    StartupReconciliationTransaction,
    async_finish_non_interruptible,
    select_alert_collision,
)

if TYPE_CHECKING:
    from .manager_api import _ConfigurationSnapshot

_LOGGER = logging.getLogger(__name__)

_EVALUATION_BATCH_SIZE = 50

_PACK_CONDITION_FALLBACKS = {
    "automatic.execution_errors": "Execution ended with an error",
    "automatic.execution_errors_detail": ("Execution ended with an error: {error}"),
    "automatic.flapping": (
        "Instability detected: {count} occurrences within {duration}. "
        "Source: {source}. Last occurrence: {last_occurrence}"
    ),
    "automatic.battery": "Battery less than or equal to {threshold}%",
    "automatic.connectivity": "Connectivity is off",
    "automatic.unavailable": "State is unavailable",
    "automatic.unifi": "UniFi device is away",
}


@dataclass(slots=True)
class _StartupReconciliationAttempt:
    """Own all mutable bookkeeping for one startup reconciliation attempt."""

    snapshot: _ConfigurationSnapshot
    transaction: StartupReconciliationTransaction
    initial_immediate_save_required: bool
    initial_pack_availability: dict[str, bool]
    consumed_registry_dirty: bool = False
    consumed_pack_dirty: bool = False
    consumed_entity_renames: dict[str, str] = field(default_factory=dict)
    store_write_attempted: bool = False
    committed: bool = False


class _RuntimeMixin:
    """Handle Home Assistant events and turn current states into alerts."""

    @callback
    def _home_assistant_started(self, _event: Event) -> None:
        """Start one bounded grace period after Home Assistant startup."""
        self._begin_startup_grace()

    @callback
    def _begin_startup_grace(self) -> None:
        """Freeze restored state until integrations have published stable values."""
        if self._runtime_phase is RuntimePhase.STOPPING:
            return
        if self._runtime_phase is RuntimePhase.RECONCILING:
            return
        if self._runtime_phase is not RuntimePhase.STARTUP_GRACE:
            self._runtime_phase = RuntimePhase.STARTUP_GRACE
        if (
            self._startup_reconciliation_timer is None
            and not self._startup_reconciliation_scheduled
        ):
            self._schedule_startup_reconciliation()

    @callback
    def _schedule_startup_reconciliation(self) -> None:
        """Schedule one authoritative scan at the end of startup grace."""
        self._cancel_startup_reconciliation()

        @callback
        def timer_due(_now: datetime) -> None:
            self._startup_reconciliation_timer = None
            self._startup_reconciliation_deadline = None
            if (
                self._runtime_phase is not RuntimePhase.STARTUP_GRACE
                or self._startup_reconciliation_scheduled
            ):
                return
            self._startup_reconciliation_scheduled = True
            self.entry.async_create_task(
                self.hass,
                self._async_finish_startup_reconciliation(),
                name=f"{DOMAIN} startup reconciliation",
                eager_start=False,
            )
            if self._last_public_snapshot is not None:
                self._publish_if_changed()

        self._startup_reconciliation_deadline = dt_util.now() + timedelta(
            seconds=STARTUP_RECONCILIATION_DELAY_SECONDS
        )
        self._startup_reconciliation_timer = async_track_point_in_utc_time(
            self.hass,
            timer_due,
            self._startup_reconciliation_deadline,
        )
        if self._last_public_snapshot is not None:
            self._publish_if_changed()

    def _cancel_startup_reconciliation(self) -> None:
        """Cancel the one-shot post-start reconciliation timer."""
        if self._startup_reconciliation_timer is not None:
            self._startup_reconciliation_timer()
            self._startup_reconciliation_timer = None
        self._startup_reconciliation_deadline = None

    async def _async_finish_startup_reconciliation(self) -> None:
        """Admit one startup reconciliation transaction under the mutation lock."""
        try:
            async with self._config_mutation_lock:
                if (
                    self._runtime_phase is not RuntimePhase.STARTUP_GRACE
                    or self.hass.state is not CoreState.running
                ):
                    return
                await async_finish_non_interruptible(
                    self._async_run_startup_reconciliation()
                )
        finally:
            self._startup_reconciliation_scheduled = False
            if (
                not self._unloading
                and self._runtime_phase is RuntimePhase.STARTUP_GRACE
                and self.hass.state is CoreState.running
            ):
                self._schedule_startup_reconciliation()

    async def _async_run_startup_reconciliation(self) -> None:
        """Run one admitted startup transaction through its explicit phases."""
        attempt: _StartupReconciliationAttempt | None = None
        try:
            attempt = self._begin_startup_reconciliation_attempt()
            if not await self._async_reconcile_startup_until_stable(attempt):
                return
            previous_records = self._commit_startup_reconciliation(attempt)
            if previous_records is None:
                return
            await self._async_postcommit_startup_reconciliation(
                attempt, previous_records
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - defensive lifecycle boundary
            _LOGGER.exception("Unable to reconcile Alert Manager startup state")
        finally:
            if attempt is not None and not attempt.committed:
                try:
                    await self._async_rollback_startup_reconciliation(attempt)
                except asyncio.CancelledError:
                    raise
                except Exception:  # pragma: no cover - cleanup guard
                    _LOGGER.exception("Unable to roll back startup reconciliation")

    def _begin_startup_reconciliation_attempt(
        self,
    ) -> _StartupReconciliationAttempt:
        """Capture rollback state and expose one immutable restored ledger."""
        snapshot = self._configuration_snapshot()
        transaction = StartupReconciliationTransaction.capture(
            self.records, self._unverified_restored_alert_ids
        )
        attempt = _StartupReconciliationAttempt(
            snapshot,
            transaction,
            self._immediate_state_save_required,
            dict(self._pack_availability),
        )
        self._startup_reconciliation_snapshot = snapshot
        self._startup_reconciliation_transaction = transaction
        self._runtime_phase = RuntimePhase.RECONCILING
        return attempt

    async def _async_reconcile_startup_until_stable(
        self, attempt: _StartupReconciliationAttempt
    ) -> bool:
        """Repeat scans and durable writes until no observation can be stale."""
        changed = False
        full_scan_required = True
        while self._startup_reconciliation_can_continue():
            observed_at = dt_util.now()
            changed |= await self._async_reconcile_startup_pass(
                attempt, full_scan_required
            )
            full_scan_required = False
            if not self._startup_reconciliation_can_continue():
                return False
            if self._startup_reconciliation_has_pending_work():
                continue
            boundary = self._next_reconciliation_time_boundary(observed_at)
            if self._reconciliation_time_boundary_reached(boundary):
                full_scan_required = True
                continue
            if not changed and not self._immediate_state_save_required:
                return True
            attempt.store_write_attempted = True
            await self._async_save_state()
            changed = False
            if not self._startup_reconciliation_can_continue():
                return False
            if self._startup_reconciliation_has_pending_work():
                continue
            if self._reconciliation_time_boundary_reached(boundary):
                full_scan_required = True
                continue
            return True
        return False

    async def _async_reconcile_startup_pass(
        self,
        attempt: _StartupReconciliationAttempt,
        full_scan_required: bool,
    ) -> bool:
        """Consume one coherent batch of registry, pack and state work."""
        registry_dirty = self._registry_evaluation_dirty
        attempt.consumed_registry_dirty |= registry_dirty
        self._registry_evaluation_dirty = False
        attempt.consumed_entity_renames.update(self._pending_entity_renames)
        renamed = self._apply_pending_entity_renames()
        pack_dirty = self._pack_refresh_dirty
        attempt.consumed_pack_dirty |= pack_dirty
        self._pack_refresh_dirty = False
        if pack_dirty:
            self._replace_pack_availability_snapshot()
        changed = renamed
        if full_scan_required or registry_dirty or pack_dirty or renamed:
            changed |= await self.async_evaluate_all(
                save=False,
                publish=False,
                emit_events=False,
                archive_resolutions=False,
            )
        changed |= await self._async_drain_startup_state_events()
        changed |= self._resolve_reconciliation_expirations()
        return changed

    def _resolve_reconciliation_expirations(self) -> bool:
        """Fold elapsed active deadlines into the private candidate state."""
        return self._resolve_expired_alerts(
            dt_util.now(),
            alert_ids=(
                alert_id
                for alert_id, record in self.records.items()
                if record.status is AlertStatus.ACTIVE and record.expires_at is not None
            ),
            emit_events=False,
            archive_resolutions=False,
        )

    def _startup_reconciliation_can_continue(self) -> bool:
        """Return whether the admitted attempt still owns a live startup."""
        return (
            self._runtime_phase is RuntimePhase.RECONCILING
            and self.hass.state is CoreState.running
        )

    def _startup_reconciliation_has_pending_work(self) -> bool:
        """Return whether events invalidated the most recent private scan."""
        return bool(
            self._queued_evaluation_entities
            or self._registry_evaluation_dirty
            or self._pack_refresh_dirty
        )

    def _commit_startup_reconciliation(
        self, attempt: _StartupReconciliationAttempt
    ) -> dict[str, AlertRecord] | None:
        """Cross the irreversible boundary and start authoritative timers."""
        self._queued_public_refresh = False
        self._unverified_restored_alert_ids = (
            attempt.transaction.committed_unverified_alert_ids(self.records)
        )
        self._startup_reconciliation_transaction = None
        self._runtime_phase = RuntimePhase.RUNNING
        self._reschedule_record_timers()
        if (
            self._runtime_phase is not RuntimePhase.RUNNING
            or self.hass.state is not CoreState.running
        ):
            return None
        self._refresh_pending_persistence_timer()
        attempt.committed = True
        self._startup_reconciliation_snapshot = None
        return attempt.transaction.reconciled_original_records()

    async def _async_postcommit_startup_reconciliation(
        self,
        attempt: _StartupReconciliationAttempt,
        previous_records: dict[str, AlertRecord],
    ) -> None:
        """Publish lifecycle and refresh external consumers after commit."""
        self._commit_reconciliation_lifecycle(previous_records)
        self._publish_if_changed(force=True)
        self._schedule_deferred_runtime_work()
        if attempt.consumed_registry_dirty:
            await self._async_refresh_notification_runtime()
        await self._async_flush_history()

    async def _async_rollback_startup_reconciliation(
        self, attempt: _StartupReconciliationAttempt
    ) -> None:
        """Restore memory and compensate Store before the owner may retry."""
        pending_renames = dict(attempt.consumed_entity_renames)
        pending_renames.update(self._pending_entity_renames)
        registry_dirty = (
            attempt.consumed_registry_dirty
            or self._registry_evaluation_dirty
            or bool(pending_renames)
        )
        pack_dirty = attempt.consumed_pack_dirty or self._pack_refresh_dirty
        stopping = (
            self._runtime_phase is RuntimePhase.STOPPING
            or self.hass.state is not CoreState.running
        )
        if not stopping:
            self._runtime_phase = RuntimePhase.STARTUP_GRACE
        try:
            restored = False
            try:
                restored = self._restore_startup_reconciliation_snapshot(attempt)
            finally:
                self._restore_startup_side_work(
                    stopping, pending_renames, registry_dirty, pack_dirty
                )
            if self._startup_store_needs_compensation(attempt, restored):
                await self._async_compensate_startup_store()
        finally:
            self._startup_reconciliation_snapshot = None
            self._startup_reconciliation_transaction = None

    def _restore_startup_reconciliation_snapshot(
        self, attempt: _StartupReconciliationAttempt
    ) -> bool:
        """Restore the pre-attempt memory snapshot, logging defensive failures."""
        self._immediate_state_save_required = attempt.initial_immediate_save_required
        self._pack_availability = attempt.initial_pack_availability
        try:
            self._restore_configuration_snapshot(attempt.snapshot)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - defensive rollback
            _LOGGER.exception("Unable to restore failed startup reconciliation")
            return False
        return True

    def _restore_startup_side_work(
        self,
        stopping: bool,
        pending_renames: dict[str, str],
        registry_dirty: bool,
        pack_dirty: bool,
    ) -> None:
        """Restore deferred work without leaving speculative timers alive."""
        if stopping:
            self._begin_shutdown()
            return
        self._cancel_all_pack_rechecks()
        self._cancel_template_dependency_timers()
        self._cancel_pending_persistence_timer()
        self._cancel_live_message_flush()
        self._pending_entity_renames = pending_renames
        self._registry_evaluation_dirty = registry_dirty
        self._pack_refresh_dirty = pack_dirty
        self._clear_queued_evaluations()

    def _startup_store_needs_compensation(
        self, attempt: _StartupReconciliationAttempt, restored: bool
    ) -> bool:
        """Return whether Store may contain state from a failed attempt."""
        return (
            attempt.store_write_attempted
            and restored
            and self._persistence_ready
            and not self.recovery_active
        )

    async def _async_compensate_startup_store(self) -> None:
        """Rewrite the restored snapshot after a failed speculative write."""
        try:
            await self._async_save_state()
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - storage retry boundary
            _LOGGER.exception("Unable to compensate failed startup reconciliation")

    def _next_reconciliation_time_boundary(
        self, observed_at: datetime
    ) -> datetime | None:
        """Return the first clock edge that can invalidate this observation."""
        if not self.monitoring_enabled:
            return None
        boundaries = [
            record.due_at.astimezone(UTC)
            for record in self.records.values()
            if record.status is AlertStatus.PENDING and record.paused_at is None
        ]
        boundaries.extend(
            record.expires_at.astimezone(UTC)
            for record in self.records.values()
            if record.status is AlertStatus.ACTIVE and record.expires_at is not None
        )
        if self._template_time_dependencies:
            observed_utc = observed_at.astimezone(UTC)
            boundaries.append(
                observed_utc.replace(second=0, microsecond=0) + timedelta(minutes=1)
            )
        return min(boundaries) if boundaries else None

    @staticmethod
    def _reconciliation_time_boundary_reached(boundary: datetime | None) -> bool:
        """Return whether a scan became stale while reconciliation yielded."""
        return boundary is not None and dt_util.now().astimezone(UTC) >= boundary

    @callback
    def _schedule_deferred_runtime_work(self) -> None:
        """Resume side work that arrived during the committed Store write."""
        if (
            self._runtime_phase is not RuntimePhase.RUNNING
            or self.hass.state is not CoreState.running
        ):
            return
        if (
            self._queued_evaluation_entities
            or self._queued_public_refresh
            or self._queued_expired_alert_ids
        ):
            self._schedule_evaluation_flush()
        self._schedule_registry_evaluation()
        if self._pack_refresh_dirty:
            self._schedule_pack_availability_refresh()
        if self.monitoring_enabled:
            self._schedule_template_time_tick()

    def _commit_reconciliation_lifecycle(
        self,
        previous_records: dict[str, AlertRecord],
    ) -> None:
        """Emit and archive only lifecycle changes in the committed snapshot."""
        now = dt_util.now()
        for alert_id, previous in previous_records.items():
            current = self.records.get(alert_id)
            if current is None:
                if previous.status is not AlertStatus.ACTIVE:
                    continue
                self._pending_history.append(AlertHistoryEntry.resolved(previous, now))
                self._fire_resolved(previous, now)
            elif (
                previous.status is AlertStatus.PENDING
                and current.status is AlertStatus.ACTIVE
            ):
                self._fire_started(current)
        for alert_id, current in self.records.items():
            if (
                alert_id not in previous_records
                and current.status is AlertStatus.ACTIVE
            ):
                self._fire_started(current)

    async def _async_drain_startup_state_events(self) -> bool:
        """Re-evaluate state changes that landed while the startup scan awaited."""
        changed = False
        while self._queued_evaluation_entities:
            entity_ids = sorted(self._queued_evaluation_entities)
            self._queued_evaluation_entities.clear()
            self._queued_evaluation_collect_occurrences = False
            self._queued_public_refresh = False
            for entity_id in entity_ids:
                changed |= await self.async_evaluate_entity(
                    entity_id,
                    save=False,
                    publish=False,
                    emit_events=False,
                    archive_resolutions=False,
                )
                if self._runtime_phase is not RuntimePhase.RECONCILING:
                    return changed
        self._queued_expired_alert_ids.clear()
        self._queued_public_refresh = False
        return changed

    @callback
    def _clear_queued_evaluations(self) -> None:
        """Discard every deferred runtime mutation at a lifecycle boundary."""
        self._queued_evaluation_entities.clear()
        self._queued_evaluation_collect_occurrences = False
        self._queued_expired_alert_ids.clear()
        self._queued_public_refresh = False

    @callback
    def _begin_shutdown(self) -> None:
        """Make the runtime read-only before integrations unload their entities."""
        if self._runtime_phase is RuntimePhase.STOPPING:
            self.notification_runtime.begin_shutdown()
            return
        self._runtime_phase = RuntimePhase.STOPPING
        self.notification_runtime.begin_shutdown()
        self._cancel_startup_reconciliation()
        self._cancel_all_timers()
        self._cancel_all_pack_rechecks()
        self._cancel_all_device_event_timers()
        self._cancel_template_dependency_timers()
        self._cancel_pending_persistence_timer()
        self._cancel_live_message_flush()
        self._cancel_config_backup_schedule()
        if self._coherence_schedule_unsubscribe is not None:
            self._coherence_schedule_unsubscribe()
            self._coherence_schedule_unsubscribe = None
        self._clear_queued_evaluations()
        self._registry_evaluation_dirty = False
        self._pending_entity_renames.clear()
        self._pack_refresh_dirty = False

    @callback
    def _state_changed(self, event: Event) -> None:
        """Queue only sources affected by a state or entity lifecycle event."""
        if (
            not self.monitoring_enabled
            or not self._runtime_phase.can_evaluate
            or self.hass.state is not CoreState.running
        ):
            return
        entity_id = event.data.get("entity_id")
        if not entity_id or not self._is_allowed_rule_source(entity_id):
            return

        if self._update_tracking_for_state_event(entity_id, event):
            self._queued_public_refresh = True

        affected_entities = {
            dependency_key[2]
            for dependency_key in self._template_dependents.get(entity_id, ())
        }
        lifecycle = (
            event.data.get("old_state") is None or event.data.get("new_state") is None
        ) and ("old_state" in event.data or "new_state" in event.data)
        for dependency_key, render_info in tuple(self._template_dynamic_infos.items()):
            if self._dynamic_dependency_matches(
                dependency_key,
                render_info,
                entity_id,
                lifecycle=lifecycle,
            ):
                affected_entities.add(dependency_key[2])
        if self._state_event_affects_source(event, entity_id):
            affected_entities.add(entity_id)
        self._queue_entity_evaluations(affected_entities, collect_occurrences=True)

    def _state_event_affects_source(self, event: Event, entity_id: str) -> bool:
        """Return whether this state transition can change source-owned output."""
        if "old_state" not in event.data or "new_state" not in event.data:
            return self._is_relevant_entity_id(entity_id)
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if (old_state is not None and not isinstance(old_state, State)) or (
            new_state is not None and not isinstance(new_state, State)
        ):
            return self._is_relevant_entity_id(entity_id)
        if (
            old_state is not None
            and new_state is not None
            and old_state.state == new_state.state
            and old_state.attributes == new_state.attributes
        ):
            return (
                entity_id in self._rules_by_entity
                or entity_id in self._record_ids_by_entity
            )
        automatic = self.config.get("automatic", {})
        pack_relevant = False
        automatic_eligible: bool | None = None
        for pack in PACKS:
            config = automatic.get(pack.id, {})
            if not config.get("enabled", False):
                continue
            if not self._pack_is_available(pack.id):
                continue
            if new_state is None or not pack.applies(self.hass, new_state):
                continue
            if pack.should_evaluate is not None and not pack.should_evaluate(
                self.hass, old_state, new_state, config
            ):
                continue
            pack_relevant = True
        if (
            entity_id in self._rules_by_entity
            or entity_id in self._record_ids_by_entity
        ):
            return True
        if not pack_relevant:
            return False
        if automatic_eligible is None:
            automatic_eligible = self._is_base_eligible(
                entity_id
            ) and self._is_automatic_eligible(entity_id)
        return automatic_eligible

    def _update_tracking_for_state_event(self, entity_id: str, event: Event) -> bool:
        """Update automatic tracked membership without evaluating alert candidates."""
        if "new_state" not in event.data:
            return False
        new_state = event.data.get("new_state")
        if new_state is not None and not isinstance(new_state, State):
            return False
        old_state = event.data.get("old_state")
        if (
            isinstance(old_state, State)
            and new_state is not None
            and self._has_applicable_automatic_pack(old_state)
            == self._has_applicable_automatic_pack(new_state)
        ):
            return False
        was_tracked = entity_id in self._automatic_tracked_entities
        is_tracked = new_state is not None and self._is_automatically_tracked(new_state)
        if is_tracked:
            self._automatic_tracked_entities.add(entity_id)
        else:
            self._automatic_tracked_entities.discard(entity_id)
        return was_tracked != is_tracked

    @callback
    def _queue_entity_evaluations(
        self,
        entity_ids: Iterable[str],
        *,
        collect_occurrences: bool = False,
    ) -> None:
        """Coalesce state bursts into one evaluation task and one Store write."""
        if (
            self._unloading
            or not self.monitoring_enabled
            or not self._runtime_phase.can_evaluate
            or self.hass.state is not CoreState.running
        ):
            return
        self._queued_evaluation_entities.update(
            entity_id
            for entity_id in entity_ids
            if entity_id and self._is_allowed_rule_source(entity_id)
        )
        if (
            not self._queued_evaluation_entities
            and not self._queued_public_refresh
            and not self._queued_expired_alert_ids
        ):
            return
        self._queued_evaluation_collect_occurrences |= collect_occurrences
        if self._runtime_phase is RuntimePhase.RECONCILING:
            return
        self._schedule_evaluation_flush()

    @callback
    def _schedule_evaluation_flush(self) -> None:
        """Schedule exactly one worker for the current state-change burst."""
        if (
            self._evaluation_flush_scheduled
            or self._unloading
            or self._runtime_phase is not RuntimePhase.RUNNING
        ):
            return
        self._evaluation_flush_scheduled = True
        self.entry.async_create_task(
            self.hass,
            self._async_flush_queued_evaluations(),
            name=f"{DOMAIN} state-change batch",
            eager_start=False,
        )

    async def _async_flush_queued_evaluations(self) -> None:
        """Evaluate the latest states and persist/publish the whole batch once."""
        try:
            async with self._config_mutation_lock:
                await self._async_process_queued_evaluations()
        finally:
            self._evaluation_flush_scheduled = False
            if (
                (
                    self._queued_evaluation_entities
                    or self._queued_public_refresh
                    or self._queued_expired_alert_ids
                )
                and not self._unloading
                and self.monitoring_enabled
                and self._runtime_phase is RuntimePhase.RUNNING
                and self.hass.state is CoreState.running
            ):
                self._schedule_evaluation_flush()

    async def _async_process_queued_evaluations(self) -> None:
        """Apply one queued batch while holding the mutation lock."""
        if (
            self._unloading
            or not self.monitoring_enabled
            or self._runtime_phase is not RuntimePhase.RUNNING
            or self.hass.state is not CoreState.running
        ):
            self._clear_queued_evaluations()
            return
        entity_ids = sorted(self._queued_evaluation_entities)
        self._queued_evaluation_entities.clear()
        collect_occurrences = self._queued_evaluation_collect_occurrences
        self._queued_evaluation_collect_occurrences = False
        public_refresh = self._queued_public_refresh
        self._queued_public_refresh = False
        tracked_count_before = self._tracked_count()
        occurrence_packs = (
            tuple(
                pack
                for pack in OCCURRENCE_PACKS
                if self.config["automatic"][pack.id]["enabled"]
                and self._pack_is_available(pack.id)
            )
            if collect_occurrences
            else ()
        )
        new_occurrences: list[PackOccurrence] | None = [] if occurrence_packs else None
        for entity_id in entity_ids:
            try:
                await self.async_evaluate_entity(
                    entity_id,
                    _new_occurrences=new_occurrences,
                    save=False,
                    publish=False,
                )
            except Exception:  # pragma: no cover - isolate one bad source
                _LOGGER.exception("Unable to evaluate %s", entity_id)
        if new_occurrences:
            batch = tuple(new_occurrences)
            for pack in occurrence_packs:
                for generated in pack.occurrence_batch_handler(
                    self.hass,
                    batch,
                    self.config,
                    self._pack_runtime.setdefault(pack.id, {}),
                ):
                    self._apply_generated_alert(pack.id, generated)
        self._resolve_expired_alerts(dt_util.now())
        immediate_save_required = self._immediate_state_save_required
        if immediate_save_required:
            await self._async_save_state()
        if (
            immediate_save_required
            or public_refresh
            or self._tracked_count() != tracked_count_before
        ):
            self._publish_if_changed()

    @callback
    def _registry_changed(self, event: Event) -> None:
        """Coalesce registry changes and preserve references across entity renames."""
        if self._unloading or self._runtime_phase is RuntimePhase.STOPPING:
            return
        self.notification_runtime.registry_changed()
        old_entity_id = event.data.get("old_entity_id")
        new_entity_id = event.data.get("entity_id")
        is_rename = (
            event.data.get("action") == "update"
            and isinstance(old_entity_id, str)
            and isinstance(new_entity_id, str)
            and old_entity_id != new_entity_id
        )
        if is_rename:
            self._pending_entity_renames[old_entity_id] = new_entity_id
        elif not self.monitoring_enabled:
            return
        # Templates can depend on registry metadata without an entity dependency.
        # Renames and broad registry events retain the complete reconciliation path.
        targets = None
        if (
            not is_rename
            and isinstance(new_entity_id, str)
            and self._runtime_phase is RuntimePhase.RUNNING
            and not self._rule_templates
            and not self._rule_message_templates
        ):
            targets = {new_entity_id}
        if not self._registry_evaluation_dirty:
            self._registry_evaluation_entities = targets
        elif self._registry_evaluation_entities is not None:
            if targets is None:
                self._registry_evaluation_entities = None
            else:
                self._registry_evaluation_entities.update(targets)
        self._registry_evaluation_dirty = True
        self._schedule_registry_evaluation()

    @callback
    def _schedule_registry_evaluation(self) -> None:
        """Schedule the registry worker once the runtime is authoritative."""
        if (
            not self._registry_evaluation_dirty
            or self._runtime_phase is not RuntimePhase.RUNNING
            or self.hass.state is not CoreState.running
            or self._unloading
        ):
            return
        if self._registry_evaluation_scheduled:
            return
        self._registry_evaluation_scheduled = True
        self.entry.async_create_task(
            self.hass,
            self._async_flush_registry_evaluation(),
            name=f"{DOMAIN} registry batch",
        )

    def _apply_pending_entity_renames(self) -> bool:
        """Migrate configured references and live records after entity renames."""
        if not self._pending_entity_renames:
            return False
        renames = dict(self._pending_entity_renames)
        self._pending_entity_renames.clear()

        def final_target(entity_id: str) -> str:
            seen: set[str] = set()
            while entity_id in renames and entity_id not in seen:
                seen.add(entity_id)
                entity_id = renames[entity_id]
            return entity_id

        reconciliation_transaction = self._startup_reconciliation_transaction
        durable_alert_ids = (
            set(self.storage.effective_durable_alert_ids)
            if reconciliation_transaction is None
            else None
        )
        durable_identity_changed = False
        changed = False
        for old_entity_id in tuple(renames):
            new_entity_id = final_target(old_entity_id)
            if old_entity_id == new_entity_id:
                continue

            for raw_rule in self.config.get("rules", []):
                entity_ids = raw_rule.get("entity_ids")
                if not isinstance(entity_ids, list) or old_entity_id not in entity_ids:
                    continue
                raw_rule["entity_ids"] = list(
                    dict.fromkeys(
                        new_entity_id if item == old_entity_id else item
                        for item in entity_ids
                    )
                )
                changed = True

            entity_delays = self.config.get("entity_delays", {})
            if old_entity_id in entity_delays:
                entity_delays.setdefault(new_entity_id, entity_delays[old_entity_id])
                entity_delays.pop(old_entity_id)
                changed = True

            excluded_entities = self.config.get("excluded_entities", [])
            if old_entity_id in excluded_entities:
                self.config["excluded_entities"] = list(
                    dict.fromkeys(
                        new_entity_id if item == old_entity_id else item
                        for item in excluded_entities
                    )
                )
                changed = True

            for alert_id in tuple(self._record_ids_by_entity.get(old_entity_id, ())):
                original_origin = (
                    reconciliation_transaction.live_origin(alert_id)
                    if reconciliation_transaction is not None
                    else None
                )
                was_unverified = alert_id in self._unverified_restored_alert_ids
                original_record = self._pop_record(alert_id)
                if original_record is None:
                    continue
                self._cancel_timer(alert_id)
                if alert_id.endswith(f":{old_entity_id}"):
                    new_alert_id = f"{alert_id[: -len(old_entity_id)]}{new_entity_id}"
                elif (
                    original_record.details.type == "rule"
                    and original_record.details.rule_id
                ):
                    new_alert_id = (
                        f"rule:{original_record.details.rule_id}:{new_entity_id}"
                    )
                else:
                    new_alert_id = f"{original_record.details.type}:{new_entity_id}"
                original_was_durable = (
                    durable_alert_ids is not None and alert_id in durable_alert_ids
                )
                existing_was_durable = (
                    durable_alert_ids is not None and new_alert_id in durable_alert_ids
                )
                existing_origin = (
                    reconciliation_transaction.live_origin(new_alert_id)
                    if reconciliation_transaction is not None
                    else None
                )
                existing_was_unverified = (
                    new_alert_id in self._unverified_restored_alert_ids
                )
                existing_record = self._pop_record(new_alert_id)
                if existing_record is not None:
                    self._cancel_timer(new_alert_id)
                if existing_record is None:
                    record, retained_origin = original_record, original_origin
                elif reconciliation_transaction is not None:
                    record, retained_origin = (
                        reconciliation_transaction.preferred_collision_record(
                            (
                                (original_record, original_origin),
                                (existing_record, existing_origin),
                            )
                        )
                    )
                else:
                    record, _retained_id = select_alert_collision(
                        (
                            (original_record, alert_id),
                            (existing_record, new_alert_id),
                        )
                    )
                    retained_origin = None
                if durable_alert_ids is not None:
                    durable_alert_ids.discard(alert_id)
                    durable_alert_ids.discard(new_alert_id)
                    retained_was_durable = (
                        original_was_durable
                        if record is original_record
                        else existing_was_durable
                    )
                    if retained_was_durable:
                        durable_alert_ids.add(new_alert_id)
                    durable_identity_changed = True
                record.details.entity_id = new_entity_id
                record.details.id = new_alert_id
                self._set_record(record)
                if reconciliation_transaction is not None:
                    reconciliation_transaction.record_stored(
                        new_alert_id,
                        retained_origin,
                    )
                retained_was_unverified = (
                    was_unverified
                    if record is original_record
                    else existing_was_unverified
                )
                if retained_was_unverified:
                    self._unverified_restored_alert_ids.add(new_alert_id)
                changed = True

            if old_entity_id in self._queued_evaluation_entities:
                self._queued_evaluation_entities.discard(old_entity_id)
                self._queued_evaluation_entities.add(new_entity_id)

        if changed:
            self._rebuild_rule_index()
            self._refresh_tracking()
            self._cancel_all_timers()
            self._reschedule_record_timers()
        if reconciliation_transaction is not None:
            reconciliation_transaction.record_entity_renames(renames)
        elif durable_identity_changed and durable_alert_ids is not None:
            self.storage.stage_durable_alert_ids(durable_alert_ids)
        return changed

    async def _async_flush_registry_evaluation(self) -> None:
        """Apply renames and run one durable scan for each registry burst."""
        async with self._config_mutation_lock:
            processed_registry_change = False
            try:
                while (
                    self._registry_evaluation_dirty
                    and not self._unloading
                    and self._runtime_phase is RuntimePhase.RUNNING
                    and self.hass.state is CoreState.running
                ):
                    targets = self._registry_evaluation_entities
                    self._registry_evaluation_entities = None
                    self._registry_evaluation_dirty = False
                    processed_registry_change = True
                    renamed = self._apply_pending_entity_renames()
                    evaluated = False
                    if self.monitoring_enabled:
                        if targets is None or renamed:
                            evaluated = await self.async_evaluate_all(
                                save=False, publish=False
                            )
                        else:
                            self._refresh_custom_tracking()
                            for index, entity_id in enumerate(targets, 1):
                                evaluated |= await self.async_evaluate_entity(
                                    entity_id, save=False, publish=False
                                )
                                if index % _EVALUATION_BATCH_SIZE == 0:
                                    await asyncio.sleep(0)
                    if renamed or evaluated:
                        await self._async_save_state()
                    if (
                        self.monitoring_enabled
                        and self._runtime_phase is RuntimePhase.RUNNING
                    ):
                        self._publish_if_changed()
                if (
                    processed_registry_change
                    and self._runtime_phase is RuntimePhase.RUNNING
                    and self.hass.state is CoreState.running
                ):
                    await self._async_refresh_notification_runtime()
            finally:
                self._registry_evaluation_scheduled = False
                if (
                    self._registry_evaluation_dirty
                    and not self._unloading
                    and self._runtime_phase is RuntimePhase.RUNNING
                    and self.hass.state is CoreState.running
                ):
                    self._schedule_registry_evaluation()

    @callback
    def _config_entry_changed(
        self, _change: ConfigEntryChange, changed_entry: ConfigEntry
    ) -> None:
        """Track added, removed and updated prerequisite integration entries."""
        if self._runtime_phase is RuntimePhase.STOPPING:
            return
        if changed_entry.domain not in self._pack_prerequisite_domains():
            return
        self._refresh_pack_entry_listeners()
        self._schedule_pack_availability_refresh()

    @callback
    def _pack_entry_state_changed(self) -> None:
        """Re-evaluate packs when a prerequisite entry loads or unloads."""
        self._schedule_pack_availability_refresh()

    @callback
    def _schedule_pack_availability_refresh(self) -> None:
        """Coalesce repeated config-entry state transitions."""
        if self._unloading or self._runtime_phase is RuntimePhase.STOPPING:
            return
        self._pack_refresh_dirty = True
        if (
            self._runtime_phase is not RuntimePhase.RUNNING
            or self.hass.state is not CoreState.running
        ):
            return
        if self._pack_refresh_scheduled:
            return
        self._pack_refresh_scheduled = True
        self.entry.async_create_task(
            self.hass,
            self._async_flush_pack_availability_refresh(),
            name=f"{DOMAIN} pack-availability batch",
        )

    async def _async_flush_pack_availability_refresh(self) -> None:
        """Refresh pack availability once per config-entry burst."""
        try:
            while (
                self._pack_refresh_dirty
                and not self._unloading
                and self._runtime_phase is RuntimePhase.RUNNING
                and self.hass.state is CoreState.running
            ):
                self._pack_refresh_dirty = False
                await self.async_refresh_pack_availability()
        finally:
            self._pack_refresh_scheduled = False
            if (
                self._pack_refresh_dirty
                and not self._unloading
                and self._runtime_phase is RuntimePhase.RUNNING
                and self.hass.state is CoreState.running
            ):
                self._schedule_pack_availability_refresh()

    async def async_refresh_pack_availability(self) -> bool:
        """Apply a changed availability snapshot and clean affected records."""
        async with self._config_mutation_lock:
            if (
                self._unloading
                or self._runtime_phase is not RuntimePhase.RUNNING
                or self.hass.state is not CoreState.running
            ):
                return False
            if not self._replace_pack_availability_snapshot():
                return False
            if self.monitoring_enabled:
                await self.async_evaluate_all()
            return True

    def _replace_pack_availability_snapshot(self) -> bool:
        """Refresh prerequisite listeners and replace a changed pack snapshot."""
        self._refresh_pack_entry_listeners()
        availability = self._current_pack_availability()
        if availability == self._pack_availability:
            return False
        self._pack_availability = availability
        return True

    def _pack_prerequisite_domains(self) -> set[str]:
        """Return every integration domain used as a pack prerequisite."""
        return {domain for pack in PACKS for domain in pack.prerequisites}

    def _refresh_pack_entry_listeners(self) -> None:
        """Subscribe to state changes of current prerequisite config entries."""
        current_entries = {
            entry.entry_id: entry
            for domain in self._pack_prerequisite_domains()
            for entry in self.hass.config_entries.async_entries(domain)
        }
        for entry_id in self._pack_entry_unsubscribers.keys() - current_entries.keys():
            self._pack_entry_unsubscribers.pop(entry_id)()
        for entry_id, config_entry in current_entries.items():
            if entry_id not in self._pack_entry_unsubscribers:
                self._pack_entry_unsubscribers[entry_id] = (
                    config_entry.async_on_state_change(self._pack_entry_state_changed)
                )

    def _current_pack_availability(self) -> dict[str, bool]:
        """Return current availability keyed by stable pack id."""
        return {pack.id: pack.available(self.hass) for pack in PACKS}

    def _pack_is_available(self, pack_id: str) -> bool:
        """Read the cached availability used by the state-change hot path."""
        return self._pack_availability.get(pack_id, False)

    async def async_evaluate_all(
        self,
        *,
        save: bool = True,
        publish: bool = True,
        emit_events: bool = True,
        archive_resolutions: bool = True,
    ) -> bool:
        """Evaluate all current and persisted relevant entities."""
        if (
            self._unloading
            or not self.monitoring_enabled
            or not self._runtime_phase.can_evaluate
            or self.hass.state is not CoreState.running
        ):
            return False
        self._refresh_custom_tracking()
        self._automatic_tracked_entities.clear()
        entity_ids = set()
        for index, state in enumerate(self.hass.states.async_all(), 1):
            # Read the current state after each yield, including removals.
            self._update_automatic_tracking_for_entity(
                state.entity_id, self.hass.states.get(state.entity_id)
            )
            if self._is_relevant_entity_id(state.entity_id):
                entity_ids.add(state.entity_id)
            if index % _EVALUATION_BATCH_SIZE == 0:
                await asyncio.sleep(0)
                if self._unloading or not self._runtime_phase.can_evaluate:
                    return False
        entity_ids.update(self._record_ids_by_entity)
        entity_ids.update(
            entity_id for rule in self.rules for entity_id in rule.entity_ids
        )
        if self._startup_reconciliation_transaction is not None:
            entity_ids.update(self._startup_reconciliation_transaction.entity_ids)
        persisted_changed = False
        for index, entity_id in enumerate(entity_ids, 1):
            persisted_changed |= await self.async_evaluate_entity(
                entity_id,
                save=False,
                publish=False,
                emit_events=emit_events,
                archive_resolutions=archive_resolutions,
            )
            if index % _EVALUATION_BATCH_SIZE == 0:
                await asyncio.sleep(0)
                if self._unloading or not self._runtime_phase.can_evaluate:
                    return persisted_changed
        for record in self.records.values():
            if record.expires_at is not None and record.details.id not in self._timers:
                self._schedule_timer(record)
        immediate_save_required = self._immediate_state_save_required
        if save and immediate_save_required:
            await self._async_save_state()
        if publish and (not persisted_changed or immediate_save_required):
            self._publish_if_changed()
        return persisted_changed

    async def async_evaluate_entity(
        self,
        entity_id: str,
        *,
        save: bool = True,
        publish: bool = True,
        emit_events: bool = True,
        archive_resolutions: bool = True,
        _new_occurrences: list[PackOccurrence] | None = None,
    ) -> bool:
        """Evaluate every automatic category and rule for one entity."""
        if (
            self._unloading
            or not self.monitoring_enabled
            or not self._runtime_phase.can_evaluate
            or self.hass.state is not CoreState.running
        ):
            return False
        restored_injected = self._inject_restored_entity_for_reconciliation(entity_id)
        now = dt_util.now()
        state = self.hass.states.get(entity_id)
        self._update_automatic_tracking_for_entity(entity_id, state)
        persisted_changed = restored_injected
        immediate_changed = restored_injected
        if state is not None and state.state not in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            inactivity_changed = self._reset_inactivity_records_after_update(
                state,
                now,
                emit_events=emit_events,
                archive_resolutions=archive_resolutions,
            )
            persisted_changed |= inactivity_changed
            immediate_changed |= inactivity_changed
        existing_ids = set(self._record_ids_by_entity.get(entity_id, ()))
        candidates, indeterminate_candidate_ids = (
            self._build_candidates(state) if state is not None else ({}, set())
        )
        preserved_ids = self._preserved_record_ids_for_observation(
            entity_id,
            state,
            existing_ids,
            candidates.keys() - indeterminate_candidate_ids,
            indeterminate_candidate_ids,
        )
        persisted_changed |= self._variation_baselines_dirty
        immediate_changed |= self._variation_baselines_dirty
        collect_occurrences = (
            _new_occurrences is not None and self._is_automatic_eligible(entity_id)
        )

        for alert_id, (details, delay) in candidates.items():
            record = self.records.get(alert_id)
            if record is None:
                detected_at = (
                    self._inactivity_detected_at(details.rule_id, state, now)
                    if details.source == "unchanged" or details.operator == "unchanged"
                    else now
                )
                record = AlertRecord.pending(details, delay, detected_at)
                record.visible_at = calculate_due_at(
                    detected_at,
                    min(self.config["pending_display_delay"], delay),
                )
                self._set_record(record)
                persisted_changed = True
                immediate_changed = True
                if collect_occurrences:
                    _new_occurrences.append(
                        PackOccurrence(
                            source=details,
                            occurred_at=now,
                            active_alert_ids=self.records.keys(),
                        )
                    )
            else:
                details.value = record.details.value
                if record.details != details:
                    live_message_only = self._is_live_message_only_change(
                        record, details
                    )
                    record.details = details
                    persisted_changed = True
                    if live_message_only:
                        self._schedule_live_message_flush()
                    else:
                        immediate_changed = True
                if record.delay != delay:
                    pending_was_visible = self._pending_is_visible(record, now)
                    record.delay = delay
                    record.due_at = calculate_due_at(
                        record.detected_at, delay
                    ) + timedelta(seconds=record.paused_seconds)
                    self._cancel_timer(alert_id)
                    if record.status is AlertStatus.ACTIVE and now.astimezone(
                        UTC
                    ) < record.due_at.astimezone(UTC):
                        record.status = AlertStatus.PENDING
                        record.active_since = None
                        record.visible_at = record.detected_at
                        record.clear_acknowledgement()
                    elif (
                        record.status is AlertStatus.PENDING and not pending_was_visible
                    ):
                        self._recalculate_hidden_pending_visibility(record, now)
                    persisted_changed = True
                    immediate_changed = True

            became_active = advance_record(record, now)
            if became_active:
                persisted_changed = True
                immediate_changed = True
                self._cancel_timer(alert_id)
                if emit_events:
                    self._fire_started(record)
            elif record.status is AlertStatus.PENDING and alert_id not in self._timers:
                self._schedule_timer(record)

        for alert_id in preserved_ids - candidates.keys():
            record = self.records.get(alert_id)
            if record is None:
                continue
            if advance_record(record, now):
                persisted_changed = True
                immediate_changed = True
                self._cancel_timer(alert_id)
                if emit_events:
                    self._fire_started(record)
            elif record.status is AlertStatus.PENDING and alert_id not in self._timers:
                self._schedule_timer(record)

        missing_candidate_ids = existing_ids - candidates.keys() - preserved_ids
        for alert_id in missing_candidate_ids:
            record = self.records.get(alert_id)
            if record is not None and record.expires_at is not None:
                pack_config = self.config["automatic"].get(record.details.type)
                if (
                    pack_config is not None
                    and pack_config["enabled"]
                    and self._pack_is_available(record.details.type)
                    and self._is_base_eligible(entity_id)
                    and self._is_automatic_eligible(entity_id)
                ):
                    continue
            record = self._pop_record(alert_id)
            if record is None:
                continue
            self._cancel_timer(alert_id)
            persisted_changed = True
            immediate_changed = True
            if record.status is AlertStatus.ACTIVE:
                if archive_resolutions:
                    self._pending_history.append(
                        AlertHistoryEntry.resolved(record, now)
                    )
                if emit_events:
                    self._fire_resolved(record, now)
        if immediate_changed:
            self._immediate_state_save_required = True
        state_save_required = self._immediate_state_save_required
        if save and state_save_required:
            await self._async_save_state()
        if publish and (
            not persisted_changed or immediate_changed or state_save_required
        ):
            self._publish_if_changed()
        return persisted_changed

    def _inject_restored_entity_for_reconciliation(self, entity_id: str) -> bool:
        """Revive missing restored identities without replacing live records."""
        transaction = self._startup_reconciliation_transaction
        if self._runtime_phase is not RuntimePhase.RECONCILING or transaction is None:
            return False
        injected = False
        for alert_id, (original_id, record) in transaction.records_for_entity(
            entity_id
        ).items():
            existing = self.records.get(alert_id)
            existing_origin = transaction.live_origin(alert_id)
            if existing is not None and existing_origin is None:
                # A genuinely new occurrence owns this stable id now.
                continue
            if (
                existing is not None
                and existing_origin == original_id
                and existing == record
            ):
                continue
            if existing is not None:
                self._pop_record(alert_id)
                self._cancel_timer(alert_id)
            self._set_record(record)
            transaction.record_stored(alert_id, original_id)
            injected = True
        return injected

    def _preserved_record_ids_for_observation(
        self,
        entity_id: str,
        state: State | None,
        existing_ids: set[str],
        confirmed_candidate_ids: Iterable[str],
        indeterminate_candidate_ids: set[str],
    ) -> set[str]:
        """Protect restored alerts until their source becomes authoritative."""
        transaction = self._startup_reconciliation_transaction
        if transaction is not None:
            restored_ids = (
                existing_ids & transaction.live_alert_ids_for_entity(entity_id)
            ) - set(confirmed_candidate_ids)
            if state is None or state.state == STATE_UNKNOWN:
                # The reconciliation deadline bounds startup-only protection.
                preserved_ids = set()
            elif state.state != STATE_UNAVAILABLE:
                preserved_ids = restored_ids & indeterminate_candidate_ids
            else:
                preserved_ids = {
                    alert_id
                    for alert_id in restored_ids
                    if transaction.original_was_active(alert_id)
                    or self.records[alert_id].details.type != CATEGORY_UNAVAILABLE
                }
            transaction.stage_unverified(entity_id, preserved_ids)
            return preserved_ids
        self._unverified_restored_alert_ids.difference_update(confirmed_candidate_ids)
        restored_ids = existing_ids & self._unverified_restored_alert_ids
        if state is not None and state.state not in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            preserved_ids = restored_ids & indeterminate_candidate_ids
            self._unverified_restored_alert_ids.difference_update(
                restored_ids - preserved_ids
            )
            return preserved_ids
        return {
            alert_id
            for alert_id in restored_ids
            if self.records[alert_id].status is AlertStatus.ACTIVE
            or self.records[alert_id].details.type != CATEGORY_UNAVAILABLE
        }

    def _is_live_message_only_change(
        self, record: AlertRecord, details: AlertDetails
    ) -> bool:
        """Return whether only an opted-in active message display has changed."""
        if record.status is not AlertStatus.ACTIVE or details.rule_id is None:
            return False
        rule = next(
            (
                candidate
                for candidate in self._rules_by_entity.get(details.entity_id, ())
                if candidate.id == details.rule_id
            ),
            None,
        )
        if rule is None or not rule.update_message_when_active:
            return False
        return (
            replace(
                record.details,
                message=details.message,
            )
            == details
        )

    def _reset_inactivity_records_after_update(
        self,
        state: State,
        now: datetime,
        *,
        emit_events: bool,
        archive_resolutions: bool,
    ) -> bool:
        """Restart whole-state or selected-value inactivity windows."""
        updated_at = state.last_updated.astimezone(UTC)
        changed = False
        for rule in self._rules_by_entity.get(state.entity_id, ()):
            if not rule.enabled or (
                rule.source != "unchanged" and rule.operator != "unchanged"
            ):
                continue
            alert_id = f"rule:{rule.id}:{state.entity_id}"
            record = self.records.get(alert_id)
            if record is None:
                continue
            if rule.source == "unchanged":
                reset = updated_at > record.detected_at.astimezone(UTC)
            else:
                found, current = self._rule_current_value(rule, state)
                reset = not found or current != record.details.value
            if not reset:
                continue
            self._pop_record(alert_id)
            self._cancel_timer(alert_id)
            changed = True
            if record.status is AlertStatus.ACTIVE:
                if archive_resolutions:
                    self._pending_history.append(
                        AlertHistoryEntry.resolved(record, now)
                    )
                if emit_events:
                    self._fire_resolved(record, now)
        return changed

    def _inactivity_detected_at(
        self,
        rule_id: str | None,
        state: State,
        now: datetime,
    ) -> datetime:
        """Anchor inactivity at the relevant change or a later Jinja match."""
        rule = next(
            (
                candidate
                for candidate in self._rules_by_entity.get(state.entity_id, ())
                if candidate.id == rule_id
            ),
            None,
        )
        if rule is None or rule.condition_template is not None:
            return now
        if rule.source == "unchanged":
            return state.last_updated
        if rule.source == "state":
            return getattr(state, "last_changed", state.last_updated)
        return now

    def _rule_current_value(self, rule: Rule, state: State) -> tuple[bool, Any]:
        """Read one rule source, including dotted list-wildcard attributes."""
        return rule_current_value(rule, state)

    @staticmethod
    def _variation_key(rule: Rule, entity_id: str) -> str:
        """Return the stable per-rule, per-entity reference key."""
        return f"{rule.id}:{entity_id}"

    def _clear_variation_baseline(self, rule: Rule, entity_id: str) -> bool:
        """End one variation window when its required Jinja gate is false."""
        key = self._variation_key(rule, entity_id)
        if key not in self._variation_baselines:
            return False
        self._variation_baselines.pop(key)
        self._variation_baselines_dirty = True
        return True

    def _clear_variation_baselines(self) -> bool:
        """Drop all references when monitoring can no longer observe a window."""
        if not self._variation_baselines:
            return False
        self._variation_baselines.clear()
        self._variation_baselines_dirty = True
        return True

    def _variation_value(
        self, rule: Rule, state: State, raw_current: Any
    ) -> tuple[bool, float | None]:
        """Capture or reuse the reference and return current minus reference."""
        current = safe_float(raw_current)
        if current is None:
            return False, None
        key = self._variation_key(rule, state.entity_id)
        baseline = self._variation_baselines.get(key)
        if baseline is None:
            baseline = current
            self._variation_baselines[key] = baseline
            self._variation_baselines_dirty = True
        variation = current - baseline
        return True, 0.0 if variation == 0 else variation

    def _evaluate_custom_rule(
        self,
        rule: Rule,
        state: State,
        *,
        dry_run: bool = False,
        allow_runtime_baseline: bool = True,
    ) -> RuleEvaluation:
        """Evaluate one custom rule through the shared runtime/tester engine."""
        variation = rule.source in VARIATION_SOURCES

        def evaluate_condition(current: Any) -> tuple[bool | None, str | None]:
            return self._evaluate_rule_condition_template(
                rule,
                state,
                current,
                track=not dry_run,
            )

        baseline = (
            self._variation_baselines.get(self._variation_key(rule, state.entity_id))
            if allow_runtime_baseline and variation
            else None
        )

        evaluation = evaluate_rule(
            rule,
            state,
            evaluate_condition=evaluate_condition,
            baseline=baseline,
            use_current_as_baseline=not dry_run and allow_runtime_baseline,
            evaluate_all_conditions=dry_run,
        )
        if not dry_run and variation:
            # An indeterminate render neither starts nor resets a variation window.
            if evaluation.jinja_result is False:
                self._clear_variation_baseline(rule, state.entity_id)
            elif baseline is None and evaluation.baseline is not None:
                self._variation_value(rule, state, evaluation.raw_value)
        return evaluation

    def _build_candidates(
        self, state: State
    ) -> tuple[dict[str, tuple[AlertDetails, int]], set[str]]:
        """Build current candidates and identify indeterminate observations."""
        if not self._is_base_eligible(state.entity_id):
            return {}, set()

        result: dict[str, tuple[AlertDetails, int]] = {}
        indeterminate_ids: set[str] = set()
        entity_id = state.entity_id
        automatic_eligible = self._is_automatic_eligible(entity_id)

        if state.state == STATE_UNAVAILABLE:
            if automatic_eligible:
                for pack in PACKS:
                    if self._add_pack_candidate(result, state, pack.id):
                        indeterminate_ids.add(f"{pack.id}:{entity_id}")
            return result, indeterminate_ids

        if state.state == STATE_UNKNOWN:
            return result, indeterminate_ids

        if automatic_eligible:
            for pack in PACKS:
                if pack.id != CATEGORY_UNAVAILABLE and self._add_pack_candidate(
                    result, state, pack.id
                ):
                    indeterminate_ids.add(f"{pack.id}:{entity_id}")

        for rule in self._rules_by_entity.get(entity_id, ()):
            if not rule.enabled:
                continue
            evaluation = self._evaluate_custom_rule(rule, state)
            alert_id = f"rule:{rule.id}:{entity_id}"
            if evaluation.error_code == "condition_template_error":
                # Reuse the last confirmed occurrence, as for neutral pack results.
                # Its existing pending deadline continues; no occurrence is created.
                indeterminate_ids.add(alert_id)
                record = self.records.get(alert_id)
                if record is not None:
                    result[alert_id] = (record.details, record.delay)
                continue
            if evaluation.result is not True:
                continue
            current = evaluation.value
            rendered_message = self._render_rule_message(rule, state, current)
            condition = self._rule_condition(rule, state)
            condition_key = (
                "rule.jinja"
                if rule.source == "jinja"
                else "rule.unchanged"
                if rule.source == "unchanged"
                else "rule.selected_unchanged"
                if rule.operator == "unchanged"
                else "rule.generated"
            )
            condition_params = self._rule_condition_params(rule, state)
            result[alert_id] = (
                self._details(
                    state,
                    alert_id,
                    "rule",
                    condition,
                    value=current,
                    condition_key=condition_key,
                    condition_params=condition_params,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    message=rendered_message,
                    source=rule.source,
                    operator=(
                        None if rule.source in ("jinja", "unchanged") else rule.operator
                    ),
                    comparison_value=(
                        None
                        if rule.source in ("jinja", "unchanged")
                        or rule.operator == "unchanged"
                        else rule.value
                    ),
                    attribute=rule.attribute,
                ),
                rule.duration,
            )
        return result, indeterminate_ids

    def _add_pack_candidate(
        self,
        result: dict[str, tuple[AlertDetails, int]],
        state: State,
        pack_id: str,
    ) -> bool:
        """Apply one pack result and report a non-authoritative observation."""
        config = self.config["automatic"][pack_id]
        pack = PACKS_BY_ID[pack_id]
        if not config["enabled"] or not self._pack_is_available(pack_id):
            self._cancel_pack_recheck(pack_id, state.entity_id)
            return False

        evaluation = pack.evaluate(self.hass, state, config)
        alert_id = f"{pack_id}:{state.entity_id}"
        if isinstance(evaluation, PackRecheck):
            self._schedule_pack_recheck(pack_id, state.entity_id, evaluation.delay)
        elif not isinstance(evaluation, PackNeutral):
            self._cancel_pack_recheck(pack_id, state.entity_id)
        if isinstance(evaluation, PackNeutral | PackRecheck):
            record = self.records.get(alert_id)
            if record is not None:
                result[alert_id] = (record.details, record.delay)
            return True
        if evaluation is None:
            return False

        condition = self._localized_pack_condition(
            evaluation.condition_key, evaluation.condition_params
        )
        result[alert_id] = (
            self._details(
                state,
                alert_id,
                pack_id,
                condition,
                value=evaluation.value,
                condition_key=evaluation.condition_key,
                condition_params=evaluation.condition_params,
                message=condition,
            ),
            self._delay_for(state, pack_id),
        )
        return False

    def _schedule_pack_recheck(
        self, pack_id: str, entity_id: str, delay: float
    ) -> None:
        """Schedule one deduplicated pack-requested entity evaluation."""
        if self._unloading or self._runtime_phase is RuntimePhase.STOPPING:
            return
        key = (pack_id, entity_id)
        if key in self._pack_recheck_timers:
            return

        @callback
        def timer_due(_now: datetime) -> None:
            self._pack_recheck_timers.pop(key, None)
            self._queue_entity_evaluations((entity_id,))

        self._pack_recheck_timers[key] = async_track_point_in_utc_time(
            self.hass,
            timer_due,
            dt_util.now() + timedelta(seconds=delay),
        )

    def _cancel_pack_recheck(self, pack_id: str, entity_id: str) -> None:
        """Cancel one obsolete pack-requested evaluation."""
        if cancel := self._pack_recheck_timers.pop((pack_id, entity_id), None):
            cancel()

    def _cancel_all_pack_rechecks(self) -> None:
        """Cancel every delayed pack-requested evaluation."""
        for cancel in self._pack_recheck_timers.values():
            cancel()
        self._pack_recheck_timers.clear()

    async def _async_load_condition_translations(self) -> None:
        """Cache configured-language pack messages with an English fallback."""
        resources: dict[str, str] = {}
        languages = dict.fromkeys((self.hass.config.language, "en"))
        for language in languages:
            try:
                catalog = await async_get_translations(
                    self.hass,
                    language,
                    "config_panel",
                    integrations=[DOMAIN],
                )
            except Exception:  # pragma: no cover - Home Assistant loader failure
                _LOGGER.exception(
                    "Unable to load Alert Manager translations for %s", language
                )
                continue
            for key, value in catalog.items():
                resources.setdefault(key, value)
        self._condition_translations = resources

    def _localized_pack_condition(
        self, condition_key: str, params: dict[str, Any]
    ) -> str:
        """Render one structured pack condition for sensors and event payloads."""
        resource_key = f"component.{DOMAIN}.config_panel.conditions.{condition_key}"
        template = self._condition_translations.get(
            resource_key,
            _PACK_CONDITION_FALLBACKS.get(condition_key, condition_key),
        )
        for key, value in params.items():
            template = template.replace(f"{{{key}}}", str(value))
        return template

    def _is_base_eligible(self, entity_id: str) -> bool:
        """Reject Alert Manager's own and registry-disabled entities."""
        entity_entry = self._entity_registry.async_get(entity_id)
        if not self._is_allowed_rule_source(entity_id):
            return False
        if entity_entry is not None and entity_entry.disabled_by is not None:
            return False

        device = None
        if entity_entry is not None and entity_entry.device_id:
            device = self._device_registry.async_get(entity_entry.device_id)
            if device is not None and device.disabled_by is not None:
                return False
        return True

    def _is_explicitly_excluded(self, entity_id: str) -> bool:
        """Apply the existing explicit entity and device exclusions."""
        if entity_id in self._excluded_entities:
            return True
        entity_entry = self._entity_registry.async_get(entity_id)
        return bool(
            entity_entry is not None
            and entity_entry.device_id in self._excluded_devices
        )

    def _is_automatic_eligible(self, entity_id: str) -> bool:
        """Apply explicit and selected-label exclusions to automatic packs only."""
        if self._is_own_entity(entity_id):
            return False
        if self._is_explicitly_excluded(entity_id):
            return False
        if not self._excluded_labels:
            return True
        entity_entry = self._entity_registry.async_get(entity_id)
        if entity_entry is None:
            return True
        if self._excluded_labels.intersection(entity_entry.labels):
            return False

        device = None
        if entity_entry.device_id:
            device = self._device_registry.async_get(entity_entry.device_id)
        return not (
            device is not None and self._excluded_labels.intersection(device.labels)
        )

    def _delay_for(self, state: State, category: str) -> int:
        """Resolve delay priority for automatic detections."""
        entity_id = state.entity_id
        if entity_id in self.config["entity_delays"]:
            return self.config["entity_delays"][entity_id]
        category_delay = self.config["automatic"][category].get("delay")
        if isinstance(category_delay, int):
            return category_delay
        return self.config["global_delay"]

    def _details(
        self,
        state: State,
        alert_id: str,
        alert_type: str,
        condition: str,
        *,
        value: Any | None = None,
        condition_key: str | None = None,
        condition_params: dict[str, Any] | None = None,
        rule_id: str | None = None,
        rule_name: str | None = None,
        message: str | None = None,
        source: str | None = None,
        operator: str | None = None,
        comparison_value: Any = None,
        attribute: str | None = None,
    ) -> AlertDetails:
        """Resolve names, device, area and integration once per evaluation."""
        entity_entry = self._entity_registry.async_get(state.entity_id)
        device = None
        if entity_entry is not None and entity_entry.device_id:
            device = self._device_registry.async_get(entity_entry.device_id)

        area_id = None
        if entity_entry is not None:
            area_id = entity_entry.area_id
        if area_id is None and device is not None:
            area_id = device.area_id
        area_entry = self._area_registry.async_get_area(area_id) if area_id else None

        return AlertDetails(
            id=alert_id,
            type=alert_type,
            entity_id=state.entity_id,
            name=state.attributes.get(ATTR_FRIENDLY_NAME, state.entity_id),
            device_id=(device.id if device is not None else None),
            device_name=(
                (device.name_by_user or device.name) if device is not None else None
            ),
            area=area_entry.name if area_entry is not None else None,
            integration=entity_entry.platform if entity_entry is not None else None,
            value=state.state if value is None else value,
            unit=state.attributes.get(ATTR_UNIT_OF_MEASUREMENT),
            condition=condition,
            condition_key=condition_key,
            condition_params=condition_params,
            rule_id=rule_id,
            rule_name=rule_name,
            message=message,
            source=source,
            operator=operator,
            comparison_value=comparison_value,
            attribute=attribute,
        )

    def _is_relevant_entity_id(self, entity_id: str) -> bool:
        """Return whether a state change can affect an alert or existing record."""
        if not self._is_base_eligible(entity_id):
            return False
        if entity_id in self._rules_by_entity:
            return True
        if entity_id in self._record_ids_by_entity:
            return True
        if not self._is_automatic_eligible(entity_id):
            return False
        state = self.hass.states.get(entity_id)
        return state is not None and self._has_applicable_automatic_pack(state)

    def _tracked_count(self) -> int:
        """Count enabled custom instances and unique automatic sources."""
        return self._custom_tracked_count + len(self._automatic_tracked_entities)

    def _refresh_tracking(self) -> None:
        """Refresh tracked-source caches during infrequent full evaluations."""
        self._refresh_custom_tracking()
        self._automatic_tracked_entities = {
            state.entity_id
            for state in self.hass.states.async_all()
            if self._is_automatically_tracked(state)
        }

    def _refresh_custom_tracking(self) -> None:
        """Refresh enabled custom rule/entity pairs after config changes."""
        self._custom_tracked_count = sum(
            1
            for rule in self._rules
            if rule.enabled
            for entity_id in rule.entity_ids
            if self._is_base_eligible(entity_id)
        )

    def _update_automatic_tracking_for_entity(
        self, entity_id: str, state: State | None
    ) -> None:
        """Update one automatic tracked-source membership in constant time."""
        if state is not None and self._is_automatically_tracked(state):
            self._automatic_tracked_entities.add(entity_id)
        else:
            self._automatic_tracked_entities.discard(entity_id)

    def _is_automatically_tracked(self, state: State) -> bool:
        """Return whether at least one enabled automatic pack monitors a state."""
        return (
            self._is_base_eligible(state.entity_id)
            and self._is_automatic_eligible(state.entity_id)
            and self._has_applicable_automatic_pack(state)
        )

    def _has_applicable_automatic_pack(self, state: State) -> bool:
        """Return whether an enabled and available pack applies to a state."""
        return any(
            self.config["automatic"][pack.id]["enabled"]
            and self._pack_is_available(pack.id)
            and pack.applies(self.hass, state)
            for pack in PACKS
        )
