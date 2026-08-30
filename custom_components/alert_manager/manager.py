"""Event-driven alert detection manager composition root."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.config_entries import SIGNAL_CONFIG_ENTRY_CHANGED, ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_STATE_CHANGED
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

from .coherence import schedule_coherence_scans
from .manager_api import _ApiMixin
from .manager_runtime import _RuntimeMixin
from .manager_state import _StateMixin
from .manager_templates import DependencyKey, _TemplatesMixin
from .models import AlertHistoryEntry, AlertRecord, Rule
from .storage import AlertManagerHistoryStorage, AlertManagerStorage
from .validation import validate_config

_LOGGER = logging.getLogger(__name__)


class AlertManager(_RuntimeMixin, _TemplatesMixin, _ApiMixin, _StateMixin):
    """Own configuration, runtime records, listeners and timers."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the manager."""
        self.hass = hass
        self.entry = entry
        self.storage = AlertManagerStorage(hass)
        self.history_storage = AlertManagerHistoryStorage(hass)
        self._entity_registry = er.async_get(hass)
        self._device_registry = dr.async_get(hass)
        self._area_registry = ar.async_get(hass)
        self._config_mutation_lock = asyncio.Lock()
        self.config: dict[str, Any] = {}
        self.records: dict[str, AlertRecord] = {}
        self.history: list[AlertHistoryEntry] = []
        self._pending_history: list[AlertHistoryEntry] = []
        self._rules: list[Rule] = []
        self._rules_by_entity: dict[str, list[Rule]] = {}
        self._variation_baselines: dict[str, float] = {}
        self._variation_baselines_dirty = False
        self._unsubscribers: list[Callable[[], None]] = []
        self._pack_entry_unsubscribers: dict[str, Callable[[], None]] = {}
        self._timers: dict[str, Callable[[], None]] = {}
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
        self._coherence_schedule_unsubscribe: Callable[[], None] | None = None
        self._live_message_flush_timer: Callable[[], None] | None = None
        self._live_message_flush_pending = False
        self._immediate_state_save_required = False

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
        config, records, migrated = await self.storage.async_load()
        self._variation_baselines = self.storage.variation_baselines
        try:
            history, history_migrated = await self.history_storage.async_load()
        except Exception:
            _LOGGER.exception(
                "Unable to load alert history; starting with an empty view"
            )
            history, history_migrated = [], False
        try:
            self.config = validate_config(config)
        except ValueError:
            _LOGGER.exception("Stored configuration is invalid; using defaults")
            self.config = validate_config({})
            migrated = True
        await self._async_load_condition_translations()
        self.records = records
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

        if self.hass.is_running:
            changed = await self.async_evaluate_all(restoring=True, save=False)
            if migrated or changed:
                await self._async_save_state()
        else:
            if migrated:
                await self._async_save_state()
            self._unsubscribers.append(
                self.hass.bus.async_listen_once(
                    EVENT_HOMEASSISTANT_STARTED, self._home_assistant_started
                )
            )
            self._publish_if_changed(force=True)
        if history_migrated:
            try:
                await self.history_storage.async_save(self.history)
            except Exception:
                _LOGGER.exception("Unable to persist migrated alert history")
        await self._async_sync_monitoring_notification()
        self._refresh_coherence_schedule()

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
        self._unloading = True
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
        await self._async_save_state()
