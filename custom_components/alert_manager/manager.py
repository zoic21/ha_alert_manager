"""Event-driven alert detection manager composition root."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.config_entries import SIGNAL_CONFIG_ENTRY_CHANGED, ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_STATE_CHANGED
from homeassistant.core import CoreState, HassJob, HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

from .coherence import schedule_coherence_scans
from .manager_api import _ApiMixin
from .manager_recovery import _RecoveryMixin
from .manager_runtime import _RuntimeMixin
from .manager_state import _StateMixin
from .manager_templates import DependencyKey, _TemplatesMixin
from .models import AlertHistoryEntry, AlertRecord, Rule
from .notification_runtime import NotificationRuntime
from .notifications import NotificationManager
from .packs import OCCURRENCE_PACKS, reset_pack_runtimes
from .runtime_phase import RuntimePhase
from .storage import (
    AlertManagerConfigBackupStorage,
    AlertManagerHistoryStorage,
    AlertManagerStorage,
)
from .transactions import (
    StartupReconciliationTransaction,
    async_finish_non_interruptible,
)
from .validation import validate_config

_LOGGER = logging.getLogger(__name__)

_STOPPING_CORE_STATES = frozenset(
    (CoreState.stopping, CoreState.final_write, CoreState.stopped)
)


class AlertManager(
    _RuntimeMixin, _TemplatesMixin, _ApiMixin, _RecoveryMixin, _StateMixin
):
    """Own configuration, runtime records, listeners and timers."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the manager."""
        self.hass = hass
        self.entry = entry
        self.storage = AlertManagerStorage(hass)
        self.history_storage = AlertManagerHistoryStorage(hass)
        self.config_backup_storage = AlertManagerConfigBackupStorage(hass)
        self._startup_reconciliation_snapshot = None
        self.notifications = NotificationManager(
            hass, lambda: self.config.get("notification_profiles", [])
        )
        self.notification_runtime = NotificationRuntime(
            hass,
            entry,
            lambda: (
                self._startup_reconciliation_snapshot.config
                if self._startup_reconciliation_snapshot is not None
                else self.config
            ),
            lambda: (
                self._startup_reconciliation_snapshot.records
                if self._startup_reconciliation_snapshot is not None
                else self.records
            ),
            self.notifications,
        )
        self._entity_registry = er.async_get(hass)
        self._device_registry = dr.async_get(hass)
        self._area_registry = ar.async_get(hass)
        self._config_mutation_lock = asyncio.Lock()
        self.config: dict[str, Any] = {}
        self.records: dict[str, AlertRecord] = {}
        self._record_ids_by_entity: dict[str, set[str]] = {}
        self.history: list[AlertHistoryEntry] = []
        self._pending_history: list[AlertHistoryEntry] = []
        self._rules: list[Rule] = []
        self._rules_by_entity: dict[str, list[Rule]] = {}
        self._variation_baselines: dict[str, float] = {}
        self._variation_baselines_dirty = False
        self._pack_runtime: dict[str, dict[str, Any]] = {}
        self._unsubscribers: list[Callable[[], None]] = []
        self._pack_entry_unsubscribers: dict[str, Callable[[], None]] = {}
        self._timers: dict[str, Callable[[], None]] = {}
        self._pack_recheck_timers: dict[tuple[str, str], Callable[[], None]] = {}
        if self.hass.state is CoreState.running:
            self._runtime_phase = RuntimePhase.RUNNING
        elif self.hass.state in _STOPPING_CORE_STATES:
            self._runtime_phase = RuntimePhase.STOPPING
        else:
            self._runtime_phase = RuntimePhase.STARTING
        self._startup_reconciliation_timer: Callable[[], None] | None = None
        self._startup_reconciliation_deadline: datetime | None = None
        self._startup_reconciliation_scheduled = False
        self._startup_reconciliation_transaction: (
            StartupReconciliationTransaction | None
        ) = None
        self._automatic_tracked_entities: set[str] = set()
        self._custom_tracked_count = 0
        self._unloading = False
        self._last_public_snapshot: dict[str, Any] | None = None
        self._pack_availability: dict[str, bool] = {}
        self._excluded_entities: frozenset[str] = frozenset()
        self._excluded_devices: frozenset[str] = frozenset()
        self._excluded_labels: frozenset[str] = frozenset()
        self._active_device_group_ids: set[str] = set()
        self._device_event_timers: dict[str, Callable[[], None]] = {}
        self._device_event_alert_ids: dict[str, frozenset[str]] = {}
        self._rule_templates: dict[str, Template] = {}
        self._rule_template_render_info: dict[tuple[str, str], Any] = {}
        self._rule_message_templates: dict[str, Template] = {}
        self._rule_message_render_info: dict[tuple[str, str], Any] = {}
        self._condition_translations: dict[str, str] = {}
        self._template_dependents: dict[str, set[DependencyKey]] = {}
        self._template_dynamic_infos: dict[DependencyKey, Any] = {}
        self._template_entities_by_key: dict[DependencyKey, frozenset[str]] = {}
        self._template_time_dependencies: set[DependencyKey] = set()
        self._template_time_timer: Callable[[], None] | None = None
        self._template_rate_limit_until: dict[DependencyKey, datetime] = {}
        self._template_rate_limit_timers: dict[DependencyKey, Callable[[], None]] = {}
        self._queued_evaluation_entities: set[str] = set()
        self._queued_evaluation_collect_occurrences = False
        self._queued_expired_alert_ids: set[str] = set()
        self._queued_public_refresh = False
        self._evaluation_flush_scheduled = False
        self._registry_evaluation_scheduled = False
        self._registry_evaluation_dirty = False
        self._pending_entity_renames: dict[str, str] = {}
        self._pack_refresh_scheduled = False
        self._pack_refresh_dirty = False
        self._coherence_schedule_unsubscribe: Callable[[], None] | None = None
        self._live_message_flush_timer: Callable[[], None] | None = None
        self._live_message_flush_pending = False
        self._pending_persistence_timer: Callable[[], None] | None = None
        self._pending_persistence_deadline: datetime | None = None
        self._immediate_state_save_required = False
        self._recovery_active = False
        self._config_backup_schedule_unsubscribe: Callable[[], None] | None = None
        self._unverified_restored_alert_ids: set[str] = set()
        self._persistence_ready = False

    @property
    def monitoring_enabled(self) -> bool:
        """Return whether the main category currently evaluates anomalies."""
        return self.config.get("monitoring_enabled", True)

    @property
    def rules(self) -> list[Rule]:
        """Return validated rule objects."""
        return list(self._rules)

    async def async_setup(self) -> bool:
        """Load persisted state and start event-driven evaluation."""
        if self._runtime_phase is RuntimePhase.STOPPING:
            return False
        loaded_config: dict[str, Any] | None = None
        try:
            loaded_config, records, migrated = await self.storage.async_load()
            candidate = validate_config(loaded_config)
            self._validate_config_rule_sources(candidate)
        except Exception:
            _LOGGER.exception(
                "Stored configuration is unusable; starting with defaults without "
                "writing them"
            )
            self._enter_config_recovery()
            self.config = validate_config({})
            records = {}
            migrated = False
            self.storage.variation_baselines = {}
            self.storage.pack_runtime = {}
            history, history_migrated = [], False
        else:
            self.config = candidate
            try:
                history, history_migrated = await self.history_storage.async_load()
            except Exception:
                _LOGGER.exception(
                    "Unable to load alert history; starting with an empty view"
                )
                history, history_migrated = [], False
        self._variation_baselines = self.storage.variation_baselines
        self._pack_runtime = self.storage.pack_runtime
        runtime_pack_ids = {
            pack.id
            for pack in OCCURRENCE_PACKS
            if self.config["automatic"][pack.id]["enabled"]
        }
        if set(self._pack_runtime) - runtime_pack_ids:
            self._pack_runtime = {
                pack_id: data
                for pack_id, data in self._pack_runtime.items()
                if pack_id in runtime_pack_ids
            }
            self.storage.pack_runtime = self._pack_runtime
            migrated = True
        await self._async_load_condition_translations()
        self.notifications.set_translations(self._condition_translations)
        self.records = records
        self._unverified_restored_alert_ids = set(records)
        self._rebuild_record_index()
        self.history = history
        if self._trim_history():
            history_migrated = True
        if self._remove_own_rule_sources():
            migrated = True
        if self._remove_own_records():
            migrated = True
        self._rebuild_rule_index()
        if self._enrich_rule_metadata():
            migrated = True
        # From this point, config and records form a validated snapshot that can
        # safely compensate an in-flight startup write even if later setup work
        # is cancelled or fails.
        self._persistence_ready = not self.recovery_active
        if (
            self._runtime_phase is RuntimePhase.STOPPING
            or self.hass.state in _STOPPING_CORE_STATES
        ):
            self._begin_shutdown()
            return False
        self._refresh_pack_entry_listeners()
        self._pack_availability = self._current_pack_availability()
        self._refresh_tracking()
        self._active_device_group_ids = set(self._active_device_groups())
        if not self.monitoring_enabled and self._freeze_pending_alerts(dt_util.now()):
            migrated = True
        if self.hass.state is CoreState.running and (
            self._runtime_phase.is_startup
            or (self.storage.has_stored_snapshot and not self.recovery_active)
        ):
            # Establish the grace boundary before event listeners can schedule
            # registry or pack workers against a restored snapshot.
            self._runtime_phase = RuntimePhase.STARTUP_GRACE

        self._unsubscribers.extend(
            (
                self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._state_changed),
                self.hass.bus.async_listen(
                    er.EVENT_ENTITY_REGISTRY_UPDATED, self._registry_changed
                ),
                self.hass.bus.async_listen(
                    dr.EVENT_DEVICE_REGISTRY_UPDATED, self._registry_changed
                ),
                self.hass.bus.async_listen(
                    lr.EVENT_LABEL_REGISTRY_UPDATED, self._registry_changed
                ),
                self.hass.bus.async_listen(
                    ar.EVENT_AREA_REGISTRY_UPDATED, self._registry_changed
                ),
                async_dispatcher_connect(
                    self.hass,
                    SIGNAL_CONFIG_ENTRY_CHANGED,
                    self._config_entry_changed,
                ),
                self.hass.async_add_shutdown_job(
                    HassJob(self._begin_shutdown, "alert_manager shutdown")
                ),
            )
        )
        if self.hass.state is not CoreState.running:
            self._unsubscribers.append(
                self.hass.bus.async_listen_once(
                    EVENT_HOMEASSISTANT_STARTED, self._home_assistant_started
                )
            )

        async with self._config_mutation_lock:
            if (
                self._runtime_phase is RuntimePhase.STOPPING
                or self.hass.state in _STOPPING_CORE_STATES
            ):
                self._begin_shutdown()
            elif self.hass.state is CoreState.running:
                if self._runtime_phase.is_startup or (
                    self.storage.has_stored_snapshot and not self.recovery_active
                ):
                    self._begin_startup_grace()
                    if migrated and not self.recovery_active:
                        await self._async_save_state()
                    self._publish_if_changed(force=True)
                else:
                    changed = await self.async_evaluate_all(save=False)
                    if not self.recovery_active and (migrated or changed):
                        await self._async_save_state()
            else:
                if migrated and not self.recovery_active:
                    await self._async_save_state()
                if self.hass.state is CoreState.running:
                    self._begin_startup_grace()
                elif self.hass.state in _STOPPING_CORE_STATES:
                    self._begin_shutdown()
                self._publish_if_changed(force=True)
        if self._runtime_phase is RuntimePhase.STOPPING:
            return False
        if history_migrated and not self.recovery_active:
            try:
                await self.history_storage.async_save(self.history)
            except Exception:
                _LOGGER.exception("Unable to persist migrated alert history")
        if self._runtime_phase is RuntimePhase.STOPPING:
            return False
        await self._async_sync_recovery_notification()
        if self._runtime_phase is RuntimePhase.STOPPING:
            return False
        await self._async_sync_monitoring_notification()
        if self._runtime_phase is RuntimePhase.STOPPING:
            return False
        self._refresh_coherence_schedule()
        await self._async_initialize_config_backups()
        if self._runtime_phase is RuntimePhase.STOPPING:
            return False
        await self.notification_runtime.async_setup()
        return self._runtime_phase is not RuntimePhase.STOPPING

    def _refresh_coherence_schedule(self) -> None:
        """Replace the optional low-frequency coherence scan listener."""
        if self._coherence_schedule_unsubscribe is not None:
            self._coherence_schedule_unsubscribe()
            self._coherence_schedule_unsubscribe = None
        if self._runtime_phase is RuntimePhase.STOPPING:
            return
        self._coherence_schedule_unsubscribe = schedule_coherence_scans(
            self.hass, self.config["coherence_schedule"]
        )

    async def async_unload(self) -> None:
        """Remove listeners and timers, persisting a final snapshot."""
        self._begin_shutdown()
        self._unloading = True

        async def persist_final_snapshot() -> None:
            """Drain any in-flight mutation and persist its rolled-back result."""
            async with self._config_mutation_lock:
                if self._persistence_ready and not self.recovery_active:
                    await self._async_save_state()

        try:
            try:
                # Always drain an in-flight mutation before tearing listeners
                # down. A reconciliation may already own the lock even though
                # the final setup side effects have not completed yet.
                await async_finish_non_interruptible(persist_final_snapshot())
            except Exception:
                _LOGGER.exception("Unable to persist Alert Manager during unload")
        finally:
            try:
                await self.notification_runtime.async_unload()
            finally:
                self._cancel_template_dependency_timers()
                self._cancel_all_pack_rechecks()
                self._cancel_pending_persistence_timer()
                self._cancel_config_backup_schedule()
                if self._coherence_schedule_unsubscribe is not None:
                    self._coherence_schedule_unsubscribe()
                    self._coherence_schedule_unsubscribe = None
                for unsubscribe in self._unsubscribers:
                    unsubscribe()
                self._unsubscribers.clear()
                for unsubscribe in self._pack_entry_unsubscribers.values():
                    unsubscribe()
                self._pack_entry_unsubscribers.clear()
                for cancel in self._timers.values():
                    cancel()
                self._timers.clear()
                self._cancel_all_device_event_timers()
                reset_pack_runtimes(self.hass)
