"""Event-driven alert detection manager composition root."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.config_entries import SIGNAL_CONFIG_ENTRY_CHANGED, ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

from .coherence import schedule_coherence_scans
from .const import RECENT_RESTORED_PENDING_SECONDS
from .manager_api import _ApiMixin
from .manager_recovery import _RecoveryMixin
from .manager_runtime import _RuntimeMixin
from .manager_state import _StateMixin
from .manager_templates import DependencyKey, _TemplatesMixin
from .models import AlertHistoryEntry, AlertRecord, AlertStatus, Rule
from .packs import reset_pack_runtimes
from .storage import (
    AlertManagerConfigBackupStorage,
    AlertManagerHistoryStorage,
    AlertManagerStorage,
)
from .validation import validate_config

_LOGGER = logging.getLogger(__name__)


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
        self._unsubscribers: list[Callable[[], None]] = []
        self._pack_entry_unsubscribers: dict[str, Callable[[], None]] = {}
        self._timers: dict[str, Callable[[], None]] = {}
        self._pack_recheck_timers: dict[tuple[str, str], Callable[[], None]] = {}
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
        self._queued_evaluation_restoring = False
        self._queued_public_refresh = False
        self._evaluation_flush_scheduled = False
        self._registry_evaluation_scheduled = False
        self._registry_evaluation_dirty = False
        self._pending_entity_renames: dict[str, str] = {}
        self._pack_refresh_scheduled = False
        self._pack_refresh_dirty = False
        self._startup_buffering = not hass.is_running
        self._startup_state_events: dict[str, Event] = {}
        self._startup_grace_timer: Callable[[], None] | None = None
        self._startup_stabilization_until: datetime | None = None
        self._coherence_schedule_unsubscribe: Callable[[], None] | None = None
        self._live_message_flush_timer: Callable[[], None] | None = None
        self._live_message_flush_pending = False
        self._immediate_state_save_required = False
        self._recovery_active = False
        self._config_backup_schedule_unsubscribe: Callable[[], None] | None = None

    @property
    def monitoring_enabled(self) -> bool:
        """Return whether the main category currently evaluates anomalies."""
        return self.config.get("monitoring_enabled", True)

    @property
    def rules(self) -> list[Rule]:
        """Return validated rule objects."""
        return list(self._rules)

    async def async_setup(self) -> None:
        """Load persisted state and start event-driven evaluation."""
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
        await self._async_load_condition_translations()
        cutoff = dt_util.now().astimezone(UTC) - timedelta(
            seconds=RECENT_RESTORED_PENDING_SECONDS
        )
        recent_pending_ids = (
            {
                alert_id
                for alert_id, record in records.items()
                if record.status is AlertStatus.PENDING
                and record.detected_at.astimezone(UTC) > cutoff
            }
            if self._startup_buffering
            else set()
        )
        if recent_pending_ids:
            records = {
                alert_id: record
                for alert_id, record in records.items()
                if alert_id not in recent_pending_ids
            }
            migrated = True
        self.records = records
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
        self._refresh_pack_entry_listeners()
        self._pack_availability = self._current_pack_availability()
        self._refresh_tracking()
        self._active_device_group_ids = set(self._active_device_groups())
        if not self.monitoring_enabled and self._freeze_pending_alerts(dt_util.now()):
            migrated = True

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
            )
        )

        if not self._startup_buffering:
            changed = await self.async_evaluate_all(restoring=True, save=False)
            if not self.recovery_active and (migrated or changed):
                await self._async_save_state()
        else:
            if migrated and not self.recovery_active:
                await self._async_save_state()
            if self.hass.is_running:
                self._home_assistant_started(None)
            else:
                self._unsubscribers.append(
                    self.hass.bus.async_listen_once(
                        EVENT_HOMEASSISTANT_STARTED, self._home_assistant_started
                    )
                )
            self._publish_if_changed(force=True)
        if history_migrated and not self.recovery_active:
            try:
                await self.history_storage.async_save(self.history)
            except Exception:
                _LOGGER.exception("Unable to persist migrated alert history")
        await self._async_sync_recovery_notification()
        await self._async_sync_monitoring_notification()
        self._refresh_coherence_schedule()
        await self._async_initialize_config_backups()

    def _refresh_coherence_schedule(self) -> None:
        """Replace the optional low-frequency coherence scan listener."""
        if self._coherence_schedule_unsubscribe is not None:
            self._coherence_schedule_unsubscribe()
            self._coherence_schedule_unsubscribe = None
        self._coherence_schedule_unsubscribe = schedule_coherence_scans(
            self.hass, self.config["coherence_schedule"]
        )

    async def async_unload(self) -> None:
        """Remove listeners and timers, persisting a final snapshot."""
        self._cancel_template_dependency_timers()
        self._cancel_all_pack_rechecks()
        self._unloading = True
        self._cancel_startup_stabilization()
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
        if not self.recovery_active:
            await self._async_save_state()
