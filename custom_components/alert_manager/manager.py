"""Event-driven alert detection manager."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Iterable
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from functools import wraps
from typing import Any

from homeassistant.components.persistent_notification import (
    async_create as async_create_persistent_notification,
)
from homeassistant.components.persistent_notification import (
    async_dismiss as async_dismiss_persistent_notification,
)
from homeassistant.config_entries import (
    SIGNAL_CONFIG_ENTRY_CHANGED,
    ConfigEntry,
    ConfigEntryChange,
)
from homeassistant.const import (
    ATTR_FRIENDLY_NAME,
    ATTR_UNIT_OF_MEASUREMENT,
    EVENT_HOMEASSISTANT_STARTED,
    EVENT_STATE_CHANGED,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.exceptions import TemplateError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.template import Template
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from .const import (
    ALERT_MANAGER_ENTITY_IDS,
    CATEGORY_UNAVAILABLE,
    DEVICE_EVENT_DEBOUNCE_SECONDS,
    DOMAIN,
    EVENT_ALERT_ACKNOWLEDGED,
    EVENT_ALERT_RESOLVED,
    EVENT_ALERT_STARTED,
    EVENT_ALERT_UNACKNOWLEDGED,
    EVENT_DEVICE_ALERT_STARTED,
    MAX_HISTORY_LIMIT,
    MIN_HISTORY_LIMIT,
    MONITORING_NOTIFICATION_ID,
    SIGNAL_ALERTS_UPDATED,
    SIGNAL_HISTORY_UPDATED,
    SIGNAL_MONITORING_UPDATED,
)
from .models import (
    AlertDetails,
    AlertHistoryEntry,
    AlertRecord,
    AlertStatus,
    Rule,
    advance_record,
    calculate_due_at,
)
from .packs import PACKS, PACKS_BY_ID, PackNeutral
from .storage import AlertManagerHistoryStorage, AlertManagerStorage, sort_history
from .validation import (
    validate_config,
    validate_config_update,
    validate_rule_payload,
    validate_rule_update_fields,
)
from .yaml_io import (
    dump_config_yaml,
    dump_rule_yaml,
    import_summary,
    parse_config_yaml,
    parse_rule_yaml,
    rule_to_yaml_data,
)

_LOGGER = logging.getLogger(__name__)

_LEGACY_OPERATOR_LABELS = {
    "equals": "Égal à",
    "not_equals": "Différent de",
    "contains": "Contient",
    "not_contains": "Ne contient pas",
    "above": "Supérieur à",
    "below": "Inférieur à",
}

_PACK_CONDITION_FALLBACKS = {
    "automatic.battery": "Battery less than or equal to {threshold}%",
    "automatic.connectivity": "Connectivity is off",
    "automatic.unavailable": "State is unavailable",
    "automatic.unifi": "UniFi device is away",
}

_JINJA_BLOCK_PATTERN = re.compile(r"{{(.*?)}}|{%(.*?)%}", re.DOTALL)
_ENTITY_ID_PATTERN = re.compile(
    r"(?<![a-z0-9_])([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)(?![a-z0-9_])",
    re.IGNORECASE,
)

type DependencyKey = tuple[str, str, str]


def _serialize_config_mutation(
    method: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
    """Serialize a complete configuration transaction on one manager."""

    @wraps(method)
    async def locked(self: Any, *args: Any, **kwargs: Any) -> Any:
        async with self._config_mutation_lock:
            return await method(self, *args, **kwargs)

    return locked


class AlertManager:
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

    @property
    def monitoring_enabled(self) -> bool:
        """Return whether the main category currently evaluates anomalies."""
        return self.config.get("monitoring_enabled", True)

    async def async_setup(self) -> None:
        """Load persisted state and start event-driven evaluation."""
        config, records, migrated = await self.storage.async_load()
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

    async def async_unload(self) -> None:
        """Remove listeners and timers, persisting a final snapshot."""
        self._cancel_template_dependency_timers()
        self._unloading = True
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

    @callback
    def _home_assistant_started(self, _event: Event) -> None:
        """Evaluate only after all startup states have had a chance to load."""
        self.entry.async_create_task(
            self.hass,
            self.async_evaluate_all(restoring=True),
            name=f"{DOMAIN} startup evaluation",
        )

    @callback
    def _state_changed(self, event: Event) -> None:
        """Queue only sources affected by a state or entity lifecycle event."""
        if not self.monitoring_enabled:
            return
        entity_id = event.data.get("entity_id")
        if not entity_id or self._is_own_entity(entity_id):
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
        self._queue_entity_evaluations(
            affected_entities,
            restoring=not self.hass.is_running,
        )

    def _state_event_affects_source(self, event: Event, entity_id: str) -> bool:
        """Return whether this state transition can change source-owned output."""
        if entity_id in self._rules_by_entity:
            return True
        if any(
            record.details.entity_id == entity_id for record in self.records.values()
        ):
            return True
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
            return False
        if not self._is_base_eligible(entity_id) or not self._is_automatic_eligible(
            entity_id
        ):
            return False

        automatic = self.config.get("automatic", {})
        for pack in PACKS:
            config = automatic.get(pack.id, {})
            if not config.get("enabled", False):
                continue
            if not self._pack_is_available(pack.id):
                continue
            if pack.should_evaluate(self.hass, new_state, config):
                return True
        return False

    def _update_tracking_for_state_event(self, entity_id: str, event: Event) -> bool:
        """Update automatic tracked membership without evaluating alert candidates."""
        if "new_state" not in event.data:
            return False
        new_state = event.data.get("new_state")
        if new_state is not None and not isinstance(new_state, State):
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
        self, entity_ids: Iterable[str], *, restoring: bool = False
    ) -> None:
        """Coalesce state bursts into one evaluation task and one Store write."""
        if self._unloading or not self.monitoring_enabled:
            return
        self._queued_evaluation_entities.update(
            entity_id
            for entity_id in entity_ids
            if entity_id and not self._is_own_entity(entity_id)
        )
        if not self._queued_evaluation_entities and not self._queued_public_refresh:
            return
        self._queued_evaluation_restoring |= restoring
        self._schedule_evaluation_flush()

    @callback
    def _schedule_evaluation_flush(self) -> None:
        """Schedule exactly one worker for the current state-change burst."""
        if self._evaluation_flush_scheduled or self._unloading:
            return
        self._evaluation_flush_scheduled = True
        self.entry.async_create_task(
            self.hass,
            self._async_flush_queued_evaluations(),
            name=f"{DOMAIN} state-change batch",
        )

    async def _async_flush_queued_evaluations(self) -> None:
        """Evaluate the latest states and persist/publish the whole batch once."""
        try:
            if self._unloading or not self.monitoring_enabled:
                self._queued_evaluation_entities.clear()
                self._queued_evaluation_restoring = False
                self._queued_public_refresh = False
                return
            entity_ids = sorted(self._queued_evaluation_entities)
            self._queued_evaluation_entities.clear()
            restoring = self._queued_evaluation_restoring
            self._queued_evaluation_restoring = False
            public_refresh = self._queued_public_refresh
            self._queued_public_refresh = False
            tracked_count_before = self._tracked_count()
            persisted_changed = False
            for entity_id in entity_ids:
                try:
                    persisted_changed |= await self.async_evaluate_entity(
                        entity_id,
                        restoring=restoring,
                        save=False,
                        publish=False,
                    )
                except Exception:  # pragma: no cover - isolate one bad source
                    _LOGGER.exception("Unable to evaluate %s", entity_id)
            if persisted_changed:
                await self._async_save_state()
            if (
                persisted_changed
                or public_refresh
                or self._tracked_count() != tracked_count_before
            ):
                self._publish_if_changed()
        finally:
            self._evaluation_flush_scheduled = False
            if (
                (self._queued_evaluation_entities or self._queued_public_refresh)
                and not self._unloading
                and self.monitoring_enabled
            ):
                self._schedule_evaluation_flush()

    @callback
    def _registry_changed(self, event: Event) -> None:
        """Coalesce registry changes and preserve references across entity renames."""
        if self._unloading:
            return
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
        self._registry_evaluation_dirty = True
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

            for alert_id, original_record in tuple(self.records.items()):
                if original_record.details.entity_id != old_entity_id:
                    continue
                self.records.pop(alert_id, None)
                self._cancel_timer(alert_id)
                if (
                    original_record.details.type == "rule"
                    and original_record.details.rule_id
                ):
                    new_alert_id = (
                        f"rule:{original_record.details.rule_id}:{new_entity_id}"
                    )
                else:
                    new_alert_id = f"{original_record.details.type}:{new_entity_id}"
                existing_record = self.records.pop(new_alert_id, None)
                if existing_record is not None:
                    self._cancel_timer(new_alert_id)
                record = (
                    min(
                        (original_record, existing_record),
                        key=lambda item: item.detected_at,
                    )
                    if existing_record is not None
                    else original_record
                )
                record.details.entity_id = new_entity_id
                record.details.id = new_alert_id
                self.records[new_alert_id] = record
                changed = True

            if old_entity_id in self._queued_evaluation_entities:
                self._queued_evaluation_entities.discard(old_entity_id)
                self._queued_evaluation_entities.add(new_entity_id)

        if changed:
            self._rebuild_rule_index()
            self._refresh_tracking()
            self._cancel_all_timers()
            self._reschedule_record_timers()
        return changed

    @_serialize_config_mutation
    async def _async_flush_registry_evaluation(self) -> None:
        """Apply renames and run one durable scan for each registry burst."""
        try:
            while self._registry_evaluation_dirty and not self._unloading:
                self._registry_evaluation_dirty = False
                renamed = self._apply_pending_entity_renames()
                evaluated = False
                if self.monitoring_enabled:
                    evaluated = await self.async_evaluate_all(
                        save=False,
                        publish=False,
                    )
                if renamed or evaluated:
                    await self._async_save_state()
                if self.monitoring_enabled:
                    self._publish_if_changed()
        finally:
            self._registry_evaluation_scheduled = False
            if self._registry_evaluation_dirty and not self._unloading:
                self._registry_evaluation_scheduled = True
                self.entry.async_create_task(
                    self.hass,
                    self._async_flush_registry_evaluation(),
                    name=f"{DOMAIN} registry batch",
                )

    @callback
    def _config_entry_changed(
        self, _change: ConfigEntryChange, changed_entry: ConfigEntry
    ) -> None:
        """Track added, removed and updated prerequisite integration entries."""
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
        if self._unloading:
            return
        self._pack_refresh_dirty = True
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
            while self._pack_refresh_dirty and not self._unloading:
                self._pack_refresh_dirty = False
                await self.async_refresh_pack_availability()
        finally:
            self._pack_refresh_scheduled = False
            if self._pack_refresh_dirty and not self._unloading:
                self._schedule_pack_availability_refresh()

    async def async_refresh_pack_availability(self) -> bool:
        """Apply a changed availability snapshot and clean affected records."""
        if self._unloading:
            return False
        self._refresh_pack_entry_listeners()
        availability = self._current_pack_availability()
        if availability == self._pack_availability:
            return False
        self._pack_availability = availability
        if self.monitoring_enabled:
            await self.async_evaluate_all()
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
        restoring: bool = False,
        save: bool = True,
        publish: bool = True,
        emit_events: bool = True,
    ) -> bool:
        """Evaluate all current and persisted relevant entities."""
        if self._unloading or not self.monitoring_enabled:
            return False
        self._refresh_tracking()
        entity_ids = {
            state.entity_id
            for state in self.hass.states.async_all()
            if self._is_relevant_entity_id(state.entity_id)
        }
        entity_ids.update(record.details.entity_id for record in self.records.values())
        entity_ids.update(
            entity_id for rule in self.rules for entity_id in rule.entity_ids
        )
        persisted_changed = False
        for entity_id in entity_ids:
            persisted_changed |= await self.async_evaluate_entity(
                entity_id,
                restoring=restoring,
                save=False,
                publish=False,
                emit_events=emit_events,
            )
        if save and persisted_changed:
            await self._async_save_state()
        if publish:
            self._publish_if_changed(
                force=restoring and self._last_public_snapshot is None
            )
        return persisted_changed

    async def async_evaluate_entity(
        self,
        entity_id: str,
        *,
        restoring: bool = False,
        save: bool = True,
        publish: bool = True,
        emit_events: bool = True,
    ) -> bool:
        """Evaluate every automatic category and rule for one entity."""
        if self._unloading or not self.monitoring_enabled:
            return False
        now = dt_util.now()
        state = self.hass.states.get(entity_id)
        self._update_automatic_tracking_for_entity(entity_id, state)
        existing_ids = {
            alert_id
            for alert_id, record in self.records.items()
            if record.details.entity_id == entity_id
        }
        if restoring and (state is None or state.state == STATE_UNKNOWN):
            for alert_id in existing_ids:
                record = self.records[alert_id]
                if record.status is AlertStatus.PENDING:
                    self._schedule_timer(record)
            if publish:
                self._publish_if_changed()
            return False

        candidates = self._build_candidates(state) if state is not None else {}
        persisted_changed = False

        for alert_id, (details, delay) in candidates.items():
            record = self.records.get(alert_id)
            if record is None:
                record = AlertRecord.pending(details, delay, now)
                record.visible_at = calculate_due_at(
                    now,
                    min(self.config["pending_display_delay"], delay),
                )
                self.records[alert_id] = record
                persisted_changed = True
            else:
                details.value = record.details.value
                if record.details != details:
                    record.details = details
                    persisted_changed = True
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

            became_active = advance_record(record, now)
            if became_active:
                persisted_changed = True
                self._cancel_timer(alert_id)
                if emit_events:
                    self._fire_started(record)
            elif record.status is AlertStatus.PENDING and alert_id not in self._timers:
                self._schedule_timer(record)

        for alert_id in existing_ids - candidates.keys():
            record = self.records.pop(alert_id)
            self._cancel_timer(alert_id)
            persisted_changed = True
            if record.status is AlertStatus.ACTIVE:
                self._pending_history.append(AlertHistoryEntry.resolved(record, now))
                if emit_events:
                    self._fire_resolved(record, now)
        if save and persisted_changed:
            await self._async_save_state()
        if publish:
            self._publish_if_changed()
        return persisted_changed

    def _build_candidates(self, state: State) -> dict[str, tuple[AlertDetails, int]]:
        """Build the deduplicated current alert candidates for one state."""
        if not self._is_base_eligible(state.entity_id):
            return {}

        result: dict[str, tuple[AlertDetails, int]] = {}
        entity_id = state.entity_id
        automatic_eligible = self._is_automatic_eligible(entity_id)

        if state.state == STATE_UNAVAILABLE:
            if automatic_eligible:
                for pack in PACKS:
                    self._add_pack_candidate(result, state, pack.id)
            return result

        if state.state == STATE_UNKNOWN:
            return result

        if automatic_eligible:
            for pack in PACKS:
                if pack.id != CATEGORY_UNAVAILABLE:
                    self._add_pack_candidate(result, state, pack.id)

        for rule in self._rules_by_entity.get(entity_id, ()):
            if not rule.enabled:
                continue
            if rule.source == "attribute" and rule.attribute not in state.attributes:
                continue
            current = (
                state.state
                if rule.source == "state"
                else state.attributes.get(rule.attribute or "")
            )
            if not rule.matches(current):
                continue
            if not self._rule_template_matches(rule, state, current):
                continue
            alert_id = f"rule:{rule.id}:{entity_id}"
            rendered_message = self._render_rule_message(rule, state, current)
            condition = rendered_message or self._rule_condition(rule, state)
            condition_key = None
            condition_params = None
            if rendered_message is None:
                condition_key = "rule.generated"
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
                    operator=rule.operator,
                    comparison_value=rule.value,
                    attribute=rule.attribute,
                ),
                rule.duration,
            )
        return result

    def _add_pack_candidate(
        self,
        result: dict[str, tuple[AlertDetails, int]],
        state: State,
        pack_id: str,
    ) -> None:
        """Apply one pack's Match, Neutral or None evaluation result."""
        config = self.config["automatic"][pack_id]
        pack = PACKS_BY_ID[pack_id]
        if not config["enabled"] or not self._pack_is_available(pack_id):
            return

        evaluation = pack.evaluate(self.hass, state, config)
        alert_id = f"{pack_id}:{state.entity_id}"
        if isinstance(evaluation, PackNeutral):
            record = self.records.get(alert_id)
            if record is not None:
                result[alert_id] = (record.details, record.delay)
            return
        if evaluation is None:
            return

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
        if entity_id in ALERT_MANAGER_ENTITY_IDS or (
            entity_entry is not None and entity_entry.platform == DOMAIN
        ):
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

    def _rule_condition_params(self, rule: Rule, state: State) -> dict[str, Any]:
        """Return stable structured parameters for a generated rule condition."""
        return {
            "source": rule.source,
            "attribute": rule.attribute,
            "operator": rule.operator,
            "expected": (
                " / ".join(str(value) for value in rule.value)
                if isinstance(rule.value, list)
                else str(rule.value)
            ),
            "unit": state.attributes.get(ATTR_UNIT_OF_MEASUREMENT),
            "duration": rule.duration,
        }

    def _rule_condition(self, rule: Rule, state: State) -> str:
        """Build a compact human-readable rule condition."""
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        source = f"Attribut {rule.attribute}" if rule.source == "attribute" else "État"
        suffix = f" {unit}" if unit else ""
        duration = f" pendant {rule.duration} s" if rule.duration else ""
        expected = (
            " / ".join(str(value) for value in rule.value)
            if isinstance(rule.value, list)
            else str(rule.value)
        )
        return (
            f"{source} {_LEGACY_OPERATOR_LABELS[rule.operator].lower()} "
            f"{expected}{suffix}{duration}"
        )

    @property
    def rules(self) -> list[Rule]:
        """Return validated rule objects."""
        return list(self._rules)

    def _rebuild_rule_index(self) -> None:
        """Cache enabled rules and rebuild template dependency indexes."""
        self._refresh_config_caches()
        self._rules = [Rule.from_dict(rule) for rule in self.config.get("rules", [])]
        self._rule_templates = {}
        self._rule_message_templates = {}
        for rule in self._rules:
            if not rule.enabled:
                continue
            if rule.condition_template is not None:
                template = Template(rule.condition_template, self.hass)
                template.ensure_valid()
                self._rule_templates[rule.id] = template
            if rule.message is not None:
                message_template = Template(rule.message, self.hass)
                message_template.ensure_valid()
                self._rule_message_templates[rule.id] = message_template
        valid_render_keys = {
            (rule.id, entity_id)
            for rule in self._rules
            if rule.enabled and rule.condition_template is not None
            for entity_id in rule.entity_ids
        }
        self._rule_template_render_info = {
            key: info
            for key, info in self._rule_template_render_info.items()
            if key in valid_render_keys
        }
        valid_message_render_keys = {
            (rule.id, entity_id)
            for rule in self._rules
            if rule.enabled and rule.message is not None
            for entity_id in rule.entity_ids
        }
        self._rule_message_render_info = {
            key: info
            for key, info in self._rule_message_render_info.items()
            if key in valid_message_render_keys
        }
        self._rules_by_entity = {}
        for rule in self._rules:
            for entity_id in rule.entity_ids:
                self._rules_by_entity.setdefault(entity_id, []).append(rule)
        self._refresh_custom_tracking()
        self._rebuild_template_dependency_index()

    def _rebuild_template_dependency_index(self) -> None:
        """Build reverse indexes so state events avoid scanning every template."""
        self._cancel_template_dependency_timers()
        self._template_dependents.clear()
        self._template_dynamic_infos.clear()
        self._template_entities_by_key.clear()
        self._template_time_dependencies.clear()
        self._template_rate_limit_until.clear()
        for kind, render_infos in (
            ("condition", self._rule_template_render_info),
            ("message", self._rule_message_render_info),
        ):
            for pair, render_info in render_infos.items():
                self._index_render_info(kind, pair, render_info)

    def _index_render_info(
        self, kind: str, pair: tuple[str, str], render_info: Any
    ) -> None:
        """Index explicit, dynamic and time-driven RenderInfo dependencies."""
        dependency_key = (kind, pair[0], pair[1])
        self._remove_dependency_key(dependency_key)
        entities = frozenset(getattr(render_info, "entities", ()) or ())
        self._template_entities_by_key[dependency_key] = entities
        for entity_id in entities:
            if self._is_own_entity(entity_id):
                continue
            self._template_dependents.setdefault(entity_id, set()).add(dependency_key)
        if self._render_info_is_dynamic(render_info):
            self._template_dynamic_infos[dependency_key] = render_info
            rate_limit = getattr(render_info, "rate_limit", None)
            if isinstance(rate_limit, int | float) and rate_limit > 0:
                self._template_rate_limit_until[dependency_key] = (
                    dt_util.now() + timedelta(seconds=float(rate_limit))
                )
        if getattr(render_info, "has_time", False):
            self._template_time_dependencies.add(dependency_key)
            self._schedule_template_time_tick()

    @staticmethod
    def _render_info_is_dynamic(render_info: Any) -> bool:
        """Return whether RenderInfo can match states beyond explicit entities."""
        return bool(
            getattr(render_info, "all_states", False)
            or getattr(render_info, "all_states_lifecycle", False)
            or getattr(render_info, "domains", ())
            or getattr(render_info, "domains_lifecycle", ())
        )

    def _remove_dependency_key(self, dependency_key: DependencyKey) -> None:
        """Remove one template instance from every reverse index and timer."""
        for entity_id in self._template_entities_by_key.pop(dependency_key, ()):
            dependents = self._template_dependents.get(entity_id)
            if dependents is None:
                continue
            dependents.discard(dependency_key)
            if not dependents:
                self._template_dependents.pop(entity_id, None)
        self._template_dynamic_infos.pop(dependency_key, None)
        self._template_rate_limit_until.pop(dependency_key, None)
        if cancel := self._template_rate_limit_timers.pop(dependency_key, None):
            cancel()
        self._template_time_dependencies.discard(dependency_key)
        if (
            not self._template_time_dependencies
            and self._template_time_timer is not None
        ):
            self._template_time_timer()
            self._template_time_timer = None

    def _cancel_template_dependency_timers(self) -> None:
        """Cancel time and rate-limit callbacks before rebuilding or unloading."""
        if self._template_time_timer is not None:
            self._template_time_timer()
            self._template_time_timer = None
        for cancel in self._template_rate_limit_timers.values():
            cancel()
        self._template_rate_limit_timers.clear()

    def _schedule_template_time_tick(self) -> None:
        """Refresh now()/utcnow() templates at the next minute boundary."""
        if (
            self._template_time_timer is not None
            or not self._template_time_dependencies
        ):
            return
        now = dt_util.now().astimezone(UTC)
        when = now.replace(second=0, microsecond=0) + timedelta(minutes=1)

        @callback
        def timer_due(_now: datetime) -> None:
            self._template_time_timer = None
            self._queue_entity_evaluations(
                {key[2] for key in self._template_time_dependencies}
            )
            if self._template_time_dependencies:
                self._schedule_template_time_tick()

        self._template_time_timer = async_track_point_in_utc_time(
            self.hass, timer_due, when
        )

    def _schedule_rate_limited_dependency(
        self, dependency_key: DependencyKey, when: datetime
    ) -> None:
        """Queue one trailing render when a broad Jinja rate limit expires."""
        if dependency_key in self._template_rate_limit_timers:
            return

        @callback
        def timer_due(_now: datetime) -> None:
            self._template_rate_limit_timers.pop(dependency_key, None)
            if dependency_key in self._template_dynamic_infos:
                self._queue_entity_evaluations((dependency_key[2],))

        self._template_rate_limit_timers[dependency_key] = (
            async_track_point_in_utc_time(self.hass, timer_due, when)
        )

    def _dynamic_dependency_matches(
        self,
        dependency_key: DependencyKey,
        render_info: Any,
        entity_id: str,
        *,
        lifecycle: bool,
    ) -> bool:
        """Apply Home Assistant's lifecycle filters and broad rate limits."""
        try:
            matches = bool(
                render_info.filter_lifecycle(entity_id)
                if lifecycle
                else render_info.filter(entity_id)
            )
        except Exception:  # pragma: no cover - defensive HA API guard
            _LOGGER.exception("Unable to filter Jinja dependency for %s", entity_id)
            return False
        if not matches:
            return False

        if entity_id in self._template_entities_by_key.get(dependency_key, ()):
            return True
        rate_limit = getattr(render_info, "rate_limit", None)
        if not isinstance(rate_limit, int | float) or rate_limit <= 0:
            return True
        now = dt_util.now()
        until = self._template_rate_limit_until.get(dependency_key)
        if until is None or now.astimezone(UTC) >= until.astimezone(UTC):
            self._template_rate_limit_until[dependency_key] = now + timedelta(
                seconds=float(rate_limit)
            )
            return True
        self._schedule_rate_limited_dependency(dependency_key, until)
        return False

    def _render_info_has_own_dependency(self, render_info: Any) -> set[str]:
        """Return runtime-discovered dependencies that belong to this integration."""
        return {
            entity_id
            for entity_id in (getattr(render_info, "entities", ()) or ())
            if self._is_own_entity(entity_id)
        }

    def _rule_template_matches(self, rule: Rule, state: State, current: Any) -> bool:
        """Render and index an optional Home Assistant Jinja condition."""
        if rule.condition_template is None:
            return True
        pair = (rule.id, state.entity_id)
        try:
            render_info = self._rule_templates[rule.id].async_render_to_info(
                {
                    "entity_id": state.entity_id,
                    "state": state,
                    "value": current,
                }
            )
            self._rule_template_render_info[pair] = render_info
            result = str(render_info.result()).lower() == "true"
        except TemplateError as err:
            _LOGGER.warning(
                "Jinja condition failed for rule %s and entity %s: %s",
                rule.id,
                state.entity_id,
                err,
            )
            return False

        dependency_key = ("condition", rule.id, state.entity_id)
        own_entities = self._render_info_has_own_dependency(render_info)
        if own_entities:
            self._rule_template_render_info.pop(pair, None)
            self._remove_dependency_key(dependency_key)
            _LOGGER.error(
                "Ignored unsafe Jinja condition for rule %s because it depends on "
                "Alert Manager entities: %s",
                rule.id,
                ", ".join(sorted(own_entities)),
            )
            return False
        self._index_render_info("condition", pair, render_info)
        return result

    def _render_rule_message(
        self,
        rule: Rule,
        state: State,
        current: Any,
        *,
        force: bool = False,
    ) -> str | None:
        """Render and track an optional Jinja message until activation."""
        if rule.message is None:
            return None
        pair = (rule.id, state.entity_id)
        dependency_key = ("message", rule.id, state.entity_id)
        alert_id = f"rule:{rule.id}:{state.entity_id}"
        record = self.records.get(alert_id)
        if record is not None and record.status is AlertStatus.ACTIVE:
            self._rule_message_render_info.pop(pair, None)
            self._remove_dependency_key(dependency_key)
            if not force:
                return record.details.message
            try:
                render_info = self._rule_message_templates[
                    rule.id
                ].async_render_to_info(
                    {
                        "entity_id": state.entity_id,
                        "state": state,
                        "value": current,
                    }
                )
                rendered = str(render_info.result()).strip()
                return rendered or None
            except TemplateError as err:
                _LOGGER.warning(
                    "Jinja message failed for rule %s and entity %s: %s",
                    rule.id,
                    state.entity_id,
                    err,
                )
                return None

        try:
            render_info = self._rule_message_templates[rule.id].async_render_to_info(
                {
                    "entity_id": state.entity_id,
                    "state": state,
                    "value": current,
                }
            )
            self._rule_message_render_info[pair] = render_info
            rendered = str(render_info.result()).strip()
        except TemplateError as err:
            _LOGGER.warning(
                "Jinja message failed for rule %s and entity %s: %s",
                rule.id,
                state.entity_id,
                err,
            )
            return None

        own_entities = self._render_info_has_own_dependency(render_info)
        if own_entities:
            self._rule_message_render_info.pop(pair, None)
            self._remove_dependency_key(dependency_key)
            _LOGGER.error(
                "Ignored unsafe Jinja message for rule %s because it depends on "
                "Alert Manager entities: %s",
                rule.id,
                ", ".join(sorted(own_entities)),
            )
            return None
        self._index_render_info("message", pair, render_info)
        return rendered or None

    def _refresh_active_rule_message(self, rule: Rule, entity_id: str) -> bool:
        """Apply an explicit message edit once to a still-active occurrence."""
        alert_id = f"rule:{rule.id}:{entity_id}"
        record = self.records.get(alert_id)
        state = self.hass.states.get(entity_id)
        if record is None or record.status is not AlertStatus.ACTIVE or state is None:
            return False
        current = (
            state.state
            if rule.source == "state"
            else state.attributes.get(rule.attribute or "")
        )
        rendered_message = self._render_rule_message(
            rule,
            state,
            current,
            force=True,
        )
        condition = rendered_message or self._rule_condition(rule, state)
        condition_key = None if rendered_message is not None else "rule.generated"
        condition_params = (
            None
            if rendered_message is not None
            else self._rule_condition_params(rule, state)
        )
        changed = (
            record.details.message != rendered_message
            or record.details.condition != condition
            or record.details.condition_key != condition_key
            or record.details.condition_params != condition_params
        )
        record.details.message = rendered_message
        record.details.condition = condition
        record.details.condition_key = condition_key
        record.details.condition_params = condition_params
        return changed

    def _refresh_config_caches(self) -> None:
        """Cache exclusion membership used for every state change."""
        self._excluded_entities = frozenset(self.config.get("excluded_entities", ()))
        self._excluded_devices = frozenset(self.config.get("excluded_devices", ()))
        self._excluded_labels = frozenset(self.config.get("excluded_labels", ()))

    def _enrich_rule_metadata(self) -> bool:
        """Add V1.5.5 rule identity fields to persisted runtime records."""
        changed = False
        for record in self.records.values():
            if record.details.type != "rule":
                continue
            prefix = "rule:"
            suffix = f":{record.details.entity_id}"
            if not record.details.id.startswith(
                prefix
            ) or not record.details.id.endswith(suffix):
                continue
            rule_id = record.details.id[len(prefix) : -len(suffix)]
            rule = next(
                (candidate for candidate in self._rules if candidate.id == rule_id),
                None,
            )
            if rule is None:
                continue
            if record.details.rule_id != rule.id:
                record.details.rule_id = rule.id
                changed = True
            if record.details.rule_name != rule.name:
                record.details.rule_name = rule.name
                changed = True
            metadata = [
                ("source", rule.source),
                ("operator", rule.operator),
                ("comparison_value", rule.value),
                ("attribute", rule.attribute),
            ]
            if record.status is not AlertStatus.ACTIVE:
                metadata.insert(0, ("message", rule.message))
            for field, value in metadata:
                if getattr(record.details, field) != value:
                    setattr(record.details, field, deepcopy(value))
                    changed = True
        return changed

    def _is_own_entity(self, entity_id: str) -> bool:
        """Identify every current or registry-renamed Alert Manager entity."""
        if entity_id in ALERT_MANAGER_ENTITY_IDS:
            return True
        entity_entry = self._entity_registry.async_get(entity_id)
        return entity_entry is not None and entity_entry.platform == DOMAIN

    def _validate_rule_sources(self, rule: Rule) -> None:
        """Reject custom rules targeting Alert Manager itself."""
        if any(self._is_own_entity(entity_id) for entity_id in rule.entity_ids):
            raise ValueError("Alert Manager entities cannot be monitored")

    def _validate_rule_template(self, rule: Rule) -> None:
        """Reject invalid or self-referential Jinja before configuration changes."""
        templates = (
            ("condition_template", rule.condition_template),
            ("message template", rule.message),
        )
        for field, source in templates:
            if source is None:
                continue
            try:
                Template(source, self.hass).ensure_valid()
            except TemplateError as err:
                raise ValueError(f"Invalid rule {field}: {err}") from err
        own_entities = self._own_template_entities(rule)
        if own_entities:
            joined = ", ".join(sorted(own_entities))
            raise ValueError(
                "Jinja templates cannot reference Alert Manager entities "
                f"({joined}) because this can create an infinite update loop"
            )

    def _own_template_entities(self, rule: Rule) -> set[str]:
        """Return literal Alert Manager entity ids used inside Jinja blocks."""
        referenced: set[str] = set()
        for source in (rule.condition_template, rule.message):
            if not source:
                continue
            for match in _JINJA_BLOCK_PATTERN.finditer(source):
                block = match.group(1) if match.group(1) is not None else match.group(2)
                if block is None:
                    continue
                referenced.update(
                    entity_match.group(1).lower()
                    for entity_match in _ENTITY_ID_PATTERN.finditer(block)
                )
        return {entity_id for entity_id in referenced if self._is_own_entity(entity_id)}

    def _validate_config_rule_sources(self, config: dict[str, Any]) -> None:
        """Apply self-monitoring rejection to a complete imported config."""
        for raw_rule in config["rules"]:
            rule = Rule.from_dict(raw_rule)
            self._validate_rule_sources(rule)
            self._validate_rule_template(rule)

    def _remove_own_rule_sources(self) -> bool:
        """Clean legacy self-references and disable unsafe Jinja rules."""
        changed = False
        cleaned_rules: list[dict[str, Any]] = []
        for raw_rule in self.config.get("rules", []):
            rule = Rule.from_dict(raw_rule)
            allowed = [
                entity_id
                for entity_id in rule.entity_ids
                if not self._is_own_entity(entity_id)
            ]
            if allowed != rule.entity_ids:
                changed = True
            if not allowed:
                continue
            rule.entity_ids = allowed
            own_entities = self._own_template_entities(rule)
            if own_entities and rule.enabled:
                rule.enabled = False
                changed = True
                _LOGGER.warning(
                    "Disabled rule %s because its Jinja references Alert Manager "
                    "entities: %s",
                    rule.id,
                    ", ".join(sorted(own_entities)),
                )
            cleaned_rules.append(rule.as_dict())
        if changed:
            self.config["rules"] = cleaned_rules
        return changed

    def _remove_own_records(self) -> bool:
        """Remove impossible self-alerts left by earlier runtime snapshots."""
        own_ids = [
            alert_id
            for alert_id, record in self.records.items()
            if self._is_own_entity(record.details.entity_id)
        ]
        for alert_id in own_ids:
            self.records.pop(alert_id)
        return bool(own_ids)

    def _is_relevant_entity_id(self, entity_id: str) -> bool:
        """Return whether a state change can affect an alert or existing record."""
        if not self._is_base_eligible(entity_id):
            return False
        if entity_id in self._rules_by_entity:
            return True
        if any(
            record.details.entity_id == entity_id for record in self.records.values()
        ):
            return True
        domain = entity_id.partition(".")[0]
        automatic = self.config.get("automatic", {})
        unavailable = automatic.get(CATEGORY_UNAVAILABLE, {})
        if unavailable.get("enabled"):
            return True
        pack_ids = {
            pack.id
            for pack in PACKS
            if automatic.get(pack.id, {}).get("enabled", False)
            and self._pack_is_available(pack.id)
        }
        return (
            (domain == "binary_sensor" and "connectivity" in pack_ids)
            or (domain == "device_tracker" and "unifi" in pack_ids)
            or (domain == "sensor" and "battery" in pack_ids)
        )

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
            },
            device_groups,
        )

    def public_snapshot(self) -> dict[str, Any]:
        """Return active and pending lists without resolved history."""
        return self._build_public_snapshot()[0]

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
            and any(
                self.config["automatic"][pack.id]["enabled"]
                and self._pack_is_available(pack.id)
                and pack.applies(self.hass, state)
                for pack in PACKS
            )
        )

    def get_config(self) -> dict[str, Any]:
        """Return a defensive copy for WebSocket clients."""
        return deepcopy(self.config)

    def history_snapshot(self) -> dict[str, Any]:
        """Return newest-first immutable history for the administrator panel."""
        return {
            "events": [entry.as_dict() for entry in sort_history(self.history)],
            "count": len(self.history),
            "retention_limit": self.config["history_limit"],
            "enabled": self.config["history_limit"] > 0,
        }

    def get_history_config(self) -> dict[str, int | bool]:
        """Return the bounded retention setting independently from YAML config."""
        limit = self.config["history_limit"]
        return {"retention_limit": limit, "enabled": limit > 0}

    @_serialize_config_mutation
    async def async_set_history_limit(self, limit: int) -> dict[str, int | bool]:
        """Persist a new retention limit and immediately remove oldest excess."""
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("retention_limit must be an integer")
        if not MIN_HISTORY_LIMIT <= limit <= MAX_HISTORY_LIMIT:
            raise ValueError(
                f"retention_limit must be between {MIN_HISTORY_LIMIT} and "
                f"{MAX_HISTORY_LIMIT}"
            )
        if limit == self.config["history_limit"]:
            return self.get_history_config()

        previous_config = deepcopy(self.config)
        previous_history = list(self.history)
        previous_pending = list(self._pending_history)
        self.config["history_limit"] = limit
        if limit == 0:
            self._pending_history = []
        history_changed = self._trim_history()
        history_saved = False
        try:
            if history_changed:
                await self.history_storage.async_save(self.history)
                history_saved = True
            await self.storage.async_save(self.config, self.records)
        except Exception:
            self.config = previous_config
            self.history = previous_history
            self._pending_history = previous_pending
            if history_saved:
                try:
                    await self.history_storage.async_save(previous_history)
                except Exception:
                    _LOGGER.exception(
                        "Unable to restore alert history after retention update failure"
                    )
            raise
        if history_changed:
            async_dispatcher_send(self.hass, SIGNAL_HISTORY_UPDATED)
        return self.get_history_config()

    async def async_clear_history(self) -> dict[str, Any]:
        """Delete history only, preserving every current runtime record."""
        previous_history = list(self.history)
        previous_pending = list(self._pending_history)
        self.history = []
        self._pending_history = []
        try:
            await self.history_storage.async_save([])
        except Exception:
            self.history = previous_history
            self._pending_history = previous_pending
            raise
        async_dispatcher_send(self.hass, SIGNAL_HISTORY_UPDATED)
        return self.history_snapshot()

    @_serialize_config_mutation
    async def async_set_monitoring(self, enabled: bool) -> bool:
        """Persistently suspend or resume the main monitoring category."""
        if not isinstance(enabled, bool):
            raise ValueError("Monitoring state must be a boolean")
        if enabled == self.monitoring_enabled:
            if enabled:
                async_dismiss_persistent_notification(
                    self.hass, MONITORING_NOTIFICATION_ID
                )
            return False

        previous_config = deepcopy(self.config)
        previous_records = deepcopy(self.records)
        previous_pending_history = list(self._pending_history)
        self.config["monitoring_enabled"] = enabled
        try:
            if enabled:
                self._resume_pending_alerts(dt_util.now())
                await self.async_evaluate_all(
                    save=False,
                    publish=False,
                    emit_events=False,
                )
            else:
                self._freeze_pending_alerts(dt_util.now())
            await self._async_save_state()
        except Exception:
            self.config = previous_config
            self.records = previous_records
            self._pending_history = previous_pending_history
            self._cancel_all_timers()
            self._reschedule_record_timers()
            raise

        if enabled:
            async_dismiss_persistent_notification(self.hass, MONITORING_NOTIFICATION_ID)
            self._emit_resume_events(previous_records)
        else:
            self._cancel_all_timers()
            self._cancel_all_device_event_timers()
        self._refresh_tracking()
        self._publish_if_changed(force=True)
        async_dispatcher_send(self.hass, SIGNAL_MONITORING_UPDATED)
        return True

    async def _async_sync_monitoring_notification(self) -> None:
        """Keep one localized persistent startup warning in sync."""
        if self.monitoring_enabled:
            async_dismiss_persistent_notification(self.hass, MONITORING_NOTIFICATION_ID)
            return
        try:
            resources = await async_get_translations(
                self.hass,
                self.hass.config.language,
                "config_panel",
                integrations=[DOMAIN],
            )
        except Exception:  # pragma: no cover - Home Assistant loader failure
            _LOGGER.exception("Unable to load persistent notification translations")
            resources = {}
        prefix = f"component.{DOMAIN}.config_panel.monitoring"
        title = resources.get(
            f"{prefix}.notification_title", "Alert Manager monitoring disabled"
        )
        message = resources.get(
            f"{prefix}.notification_message",
            "Alert Manager monitoring is disabled. Turn on “Alert Manager "
            "Monitoring” to resume alert detection.",
        )
        async_create_persistent_notification(
            self.hass,
            message,
            title=title,
            notification_id=MONITORING_NOTIFICATION_ID,
        )

    def _emit_resume_events(self, previous_records: dict[str, AlertRecord]) -> None:
        """Emit only lifecycle transitions caused by the resume evaluation."""
        now = dt_util.now()
        for alert_id, previous in previous_records.items():
            current = self.records.get(alert_id)
            if current is None:
                if previous.status is AlertStatus.ACTIVE:
                    self._fire_resolved(previous, now)
                continue
            if (
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

    def get_packs(self) -> list[dict[str, Any]]:
        """Return backend-owned pack metadata with current availability."""
        return [pack.as_public_dict(self.hass) for pack in PACKS]

    def get_rule_yaml(self, rule_id: str) -> str:
        """Return the editable YAML form of one existing rule."""
        return dump_rule_yaml(self.config["rules"][self._rule_index(rule_id)])

    def validate_rule_yaml(
        self, raw_yaml: str, *, rule_id: str | None = None
    ) -> dict[str, Any]:
        """Parse one YAML rule through the same validator as the visual form."""
        rule = parse_rule_yaml(raw_yaml, rule_id=rule_id)
        self._validate_rule_sources(rule)
        self._validate_rule_template(rule)
        return rule_to_yaml_data(rule)

    def export_config_yaml(self) -> str:
        """Return a deterministic, runtime-free YAML configuration export."""
        return dump_config_yaml(self.config)

    def preview_config_import(self, raw_yaml: str) -> dict[str, Any]:
        """Validate an import without touching the active configuration."""
        candidate = parse_config_yaml(raw_yaml)
        self._validate_config_rule_sources(candidate)
        return import_summary(candidate)

    async def async_acknowledge(self, alert_id: str, actor: str | None) -> bool:
        """Acknowledge one active alert and persist before publishing it."""
        record = self._active_record_for_service(alert_id)
        if record.acknowledged:
            return False
        now = dt_util.now()
        record.acknowledged = True
        record.acknowledged_at = now
        record.acknowledged_by = actor
        try:
            await self._async_save_state()
        except Exception:
            record.clear_acknowledgement()
            raise
        self._publish_if_changed()
        self._fire_acknowledged(record)
        return True

    async def async_unacknowledge(self, alert_id: str, actor: str | None) -> bool:
        """Remove acknowledgement from one active alert idempotently."""
        record = self._active_record_for_service(alert_id)
        if not record.acknowledged:
            return False
        now = dt_util.now()
        previous_at = record.acknowledged_at
        previous_by = record.acknowledged_by
        record.clear_acknowledgement()
        try:
            await self._async_save_state()
        except Exception:
            record.acknowledged = True
            record.acknowledged_at = previous_at
            record.acknowledged_by = previous_by
            raise
        self._publish_if_changed()
        self._fire_unacknowledged(record, now, actor, previous_at, previous_by)
        return True

    def _active_record_for_service(self, alert_id: str) -> AlertRecord:
        """Resolve an exact active alert or raise a clear service error."""
        record = self.records.get(alert_id)
        if record is None:
            raise ValueError(f"Unknown or resolved alert id: {alert_id}")
        if record.status is AlertStatus.PENDING:
            raise ValueError(f"Pending alert cannot be acknowledged: {alert_id}")
        return record

    @_serialize_config_mutation
    async def async_update_config(self, changes: dict[str, Any]) -> dict[str, Any]:
        """Validate, atomically persist and immediately apply config changes."""
        validate_config_update(changes)
        changes = dict(changes)
        if "active_display_delay" in changes:
            changes.setdefault(
                "pending_display_delay", changes.pop("active_display_delay")
            )
        if "rules" in changes:
            raise ValueError("Rules must be changed through the rules API")
        candidate = _deep_merge(self.get_config(), changes)
        if "entity_delays" in changes:
            candidate["entity_delays"] = deepcopy(changes["entity_delays"])
        for pack_id, pack_changes in changes.get("automatic", {}).items():
            for field in PACKS_BY_ID[pack_id].config_fields:
                if field.type == "device_number_map" and field.id in pack_changes:
                    candidate["automatic"][pack_id][field.id] = deepcopy(
                        pack_changes[field.id]
                    )
        candidate["rules"] = self.config["rules"]
        candidate = validate_config(candidate)
        previous = self._configuration_snapshot()
        try:
            self.config = candidate
            self._rebuild_rule_index()
            await self.async_evaluate_all(save=False, publish=False)
            if "pending_display_delay" in changes:
                self._reschedule_hidden_pending_visibility(dt_util.now())
            await self._async_save_state()
        except Exception:
            self._restore_configuration_snapshot(previous)
            raise
        self._publish_if_changed()
        return self.get_config()

    @_serialize_config_mutation
    async def async_import_config(self, raw_yaml: str) -> dict[str, Any]:
        """Atomically replace configuration after fully parsing its YAML document.

        Runtime records are never read from the import. They are reconciled
        against the newly valid configuration and persisted together with it in
        one Store write. A failed write restores the in-memory configuration,
        records and pending timers.
        """
        candidate = parse_config_yaml(raw_yaml)
        candidate["history_limit"] = self.config["history_limit"]
        self._validate_config_rule_sources(candidate)
        summary = import_summary(candidate)
        previous = self._configuration_snapshot()

        self._cancel_all_timers()
        self._cancel_all_device_event_timers()
        try:
            self.config = candidate
            self._rebuild_rule_index()
            if self.monitoring_enabled:
                self._resume_pending_alerts(dt_util.now())
            else:
                self._freeze_pending_alerts(dt_util.now())
            await self.async_evaluate_all(
                save=False,
                publish=False,
                emit_events=False,
            )
            self._reschedule_hidden_pending_visibility(dt_util.now())
            await self._async_save_state()
        except Exception:
            self._restore_configuration_snapshot(previous)
            raise

        monitoring_changed = (
            previous[0].get("monitoring_enabled", True) != self.monitoring_enabled
        )
        if monitoring_changed:
            if self.monitoring_enabled:
                async_dismiss_persistent_notification(
                    self.hass, MONITORING_NOTIFICATION_ID
                )
                self._emit_resume_events(previous[1])
            else:
                self._cancel_all_timers()
                self._cancel_all_device_event_timers()
            async_dispatcher_send(self.hass, SIGNAL_MONITORING_UPDATED)
        self._publish_if_changed(force=True)
        return {"config": self.get_config(), "summary": summary}

    @_serialize_config_mutation
    async def async_create_rule(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create and immediately evaluate a custom rule."""
        rule = validate_rule_payload(data)
        self._validate_rule_sources(rule)
        self._validate_rule_template(rule)
        previous = self._configuration_snapshot()
        try:
            self.config["rules"].append(rule.as_dict())
            self._rebuild_rule_index()
            for entity_id in rule.entity_ids:
                await self.async_evaluate_entity(entity_id, save=False, publish=False)
            await self._async_save_state()
        except Exception:
            self._restore_configuration_snapshot(previous)
            raise
        self._publish_if_changed()
        return rule.as_dict()

    async def async_create_rule_yaml(self, raw_yaml: str) -> dict[str, Any]:
        """Create a rule from YAML while keeping backend id generation."""
        rule = parse_rule_yaml(raw_yaml)
        return await self.async_create_rule(rule_to_yaml_data(rule))

    @_serialize_config_mutation
    async def async_update_rule(
        self, rule_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Update a rule without changing its identifier."""
        validate_rule_update_fields(data)
        index = self._rule_index(rule_id)
        existing = self.config["rules"][index]
        old_rule = Rule.from_dict(existing)
        rule = validate_rule_payload({**existing, **data}, rule_id=rule_id)
        self._validate_rule_sources(rule)
        self._validate_rule_template(rule)
        previous = self._configuration_snapshot()
        try:
            self.config["rules"][index] = rule.as_dict()
            self._rebuild_rule_index()

            removed_entities = set(old_rule.entity_ids) - set(rule.entity_ids)
            if not rule.enabled:
                removed_entities.update(old_rule.entity_ids)
            if self.monitoring_enabled:
                self._remove_rule_instances(rule_id, removed_entities)

            affected_entities = set(old_rule.entity_ids) | set(rule.entity_ids)
            for entity_id in affected_entities:
                await self.async_evaluate_entity(entity_id, save=False, publish=False)
            if old_rule.message != rule.message:
                for entity_id in rule.entity_ids:
                    self._refresh_active_rule_message(rule, entity_id)
            await self._async_save_state()
        except Exception:
            self._restore_configuration_snapshot(previous)
            raise
        self._publish_if_changed()
        return rule.as_dict()

    async def async_update_rule_yaml(
        self, rule_id: str, raw_yaml: str
    ) -> dict[str, Any]:
        """Update one rule from YAML while preserving its immutable id."""
        rule = parse_rule_yaml(raw_yaml, rule_id=rule_id)
        return await self.async_update_rule(rule_id, rule_to_yaml_data(rule))

    @_serialize_config_mutation
    async def async_delete_rule(self, rule_id: str) -> None:
        """Delete a rule and silently clean only the instances it owns."""
        index = self._rule_index(rule_id)
        rule = Rule.from_dict(self.config["rules"][index])
        previous = self._configuration_snapshot()
        try:
            del self.config["rules"][index]
            self._rebuild_rule_index()
            if self.monitoring_enabled:
                self._remove_rule_instances(rule_id, set(rule.entity_ids))
            for entity_id in rule.entity_ids:
                await self.async_evaluate_entity(entity_id, save=False, publish=False)
            await self._async_save_state()
        except Exception:
            self._restore_configuration_snapshot(previous)
            raise
        self._publish_if_changed()

    def _configuration_snapshot(
        self,
    ) -> tuple[dict[str, Any], dict[str, AlertRecord], list[AlertHistoryEntry]]:
        """Copy the state needed to roll back a failed configuration write."""
        return (
            deepcopy(self.config),
            deepcopy(self.records),
            list(self._pending_history),
        )

    def _restore_configuration_snapshot(
        self,
        snapshot: tuple[
            dict[str, Any], dict[str, AlertRecord], list[AlertHistoryEntry]
        ],
    ) -> None:
        """Restore configuration, records, indexes and pending timers."""
        self._cancel_all_timers()
        self.config, self.records, self._pending_history = snapshot
        self._rebuild_rule_index()
        self._refresh_tracking()
        self._reschedule_record_timers()

    def _remove_rule_instances(self, rule_id: str, entity_ids: set[str]) -> None:
        """Remove configuration-owned instances without user resolution events."""
        for entity_id in entity_ids:
            alert_id = f"rule:{rule_id}:{entity_id}"
            if self.records.pop(alert_id, None) is not None:
                self._cancel_timer(alert_id)

    def _cancel_all_timers(self) -> None:
        """Cancel each scheduled due transition before a full rebuild."""
        for cancel in self._timers.values():
            cancel()
        self._timers.clear()

    async def _async_save_state(self) -> None:
        """Persist runtime first, then archive without coupling business success."""
        await self.storage.async_save(self.config, self.records)
        await self._async_flush_history()

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
        if not self.monitoring_enabled:
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

    def _rule_index(self, rule_id: str) -> int:
        """Find a rule or raise a stable API error."""
        for index, rule in enumerate(self.config["rules"]):
            if rule["id"] == rule_id:
                return index
        raise ValueError(f"Unknown rule id: {rule_id}")

    def _schedule_timer(self, record: AlertRecord) -> None:
        """Schedule exactly one lifecycle or presentation timer for an alert."""
        if not self.monitoring_enabled:
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
        if not self.monitoring_enabled:
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
        self._cancel_device_event_timer(group_id)
        self._device_event_alert_ids[group_id] = alert_ids

        @callback
        def timer_due(_now: datetime) -> None:
            self._device_event_timers.pop(group_id, None)
            self._device_event_alert_ids.pop(group_id, None)
            if self._unloading or not self.monitoring_enabled:
                return
            device = self._active_device_groups().get(group_id)
            if device is not None:
                event_data = {
                    key: value for key, value in device.items() if key != "device_id"
                }
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
        for record in self.records.values():
            if record.status is not AlertStatus.ACTIVE or not record.details.rule_id:
                continue
            pair = (record.details.rule_id, record.details.entity_id)
            self._rule_message_render_info.pop(pair, None)
            self._remove_dependency_key(("message", pair[0], pair[1]))
        snapshot, device_groups = self._build_public_snapshot()
        if not force and snapshot == self._last_public_snapshot:
            return
        self._schedule_new_device_alerts(device_groups)
        self._last_public_snapshot = snapshot
        async_dispatcher_send(self.hass, SIGNAL_ALERTS_UPDATED)


def _deep_merge(base: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    """Merge a partial WebSocket configuration update."""
    for key, value in changes.items():
        if isinstance(base.get(key), dict) and isinstance(value, dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
