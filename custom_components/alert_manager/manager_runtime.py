"""Runtime evaluation pipeline for Alert Manager."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryChange
from homeassistant.const import (
    ATTR_FRIENDLY_NAME,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, State, callback
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from .const import (
    CATEGORY_UNAVAILABLE,
    DOMAIN,
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
from .packs import OCCURRENCE_PACKS, PACKS, PACKS_BY_ID, PackNeutral, PackOccurrence
from .rule_evaluation import RuleEvaluation, evaluate_rule, rule_current_value

_LOGGER = logging.getLogger(__name__)

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


class _RuntimeMixin:
    """Handle Home Assistant events and turn current states into alerts."""

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
        self._queue_entity_evaluations(
            affected_entities,
            restoring=not self.hass.is_running,
            collect_occurrences=self.hass.is_running,
        )

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
        restoring: bool = False,
        collect_occurrences: bool = False,
    ) -> None:
        """Coalesce state bursts into one evaluation task and one Store write."""
        if self._unloading or not self.monitoring_enabled:
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
        self._queued_evaluation_restoring |= restoring
        self._queued_evaluation_collect_occurrences |= collect_occurrences
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
            eager_start=False,
        )

    async def _async_flush_queued_evaluations(self) -> None:
        """Evaluate the latest states and persist/publish the whole batch once."""
        try:
            if self._unloading or not self.monitoring_enabled:
                self._queued_evaluation_entities.clear()
                self._queued_evaluation_restoring = False
                self._queued_evaluation_collect_occurrences = False
                self._queued_expired_alert_ids.clear()
                self._queued_public_refresh = False
                return
            entity_ids = sorted(self._queued_evaluation_entities)
            self._queued_evaluation_entities.clear()
            restoring = self._queued_evaluation_restoring
            self._queued_evaluation_restoring = False
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
                if collect_occurrences and not restoring
                else ()
            )
            new_occurrences: list[PackOccurrence] | None = (
                [] if occurrence_packs else None
            )
            for entity_id in entity_ids:
                try:
                    await self.async_evaluate_entity(
                        entity_id,
                        restoring=restoring,
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

            for alert_id in tuple(self._record_ids_by_entity.get(old_entity_id, ())):
                original_record = self._pop_record(alert_id)
                if original_record is None:
                    continue
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
                existing_record = self._pop_record(new_alert_id)
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
                self._set_record(record)
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

    async def _async_flush_registry_evaluation(self) -> None:
        """Apply renames and run one durable scan for each registry burst."""
        async with self._config_mutation_lock:
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
        entity_ids.update(self._record_ids_by_entity)
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
        for record in self.records.values():
            if record.expires_at is not None and record.details.id not in self._timers:
                self._schedule_timer(record)
        immediate_save_required = self._immediate_state_save_required
        if save and immediate_save_required:
            await self._async_save_state()
        if publish and (not persisted_changed or immediate_save_required):
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
        _new_occurrences: list[PackOccurrence] | None = None,
    ) -> bool:
        """Evaluate every automatic category and rule for one entity."""
        if self._unloading or not self.monitoring_enabled:
            return False
        now = dt_util.now()
        state = self.hass.states.get(entity_id)
        self._update_automatic_tracking_for_entity(entity_id, state)
        existing_ids = set(self._record_ids_by_entity.get(entity_id, ()))
        if restoring and (state is None or state.state == STATE_UNKNOWN):
            for alert_id in existing_ids:
                record = self.records[alert_id]
                if record.status is AlertStatus.PENDING:
                    self._schedule_timer(record)
            if publish:
                self._publish_if_changed()
            return False

        persisted_changed = False
        immediate_changed = False
        if state is not None:
            persisted_changed = self._reset_inactivity_records_after_update(
                state,
                now,
                emit_events=emit_events,
            )
            immediate_changed = persisted_changed
        existing_ids = set(self._record_ids_by_entity.get(entity_id, ()))
        candidates = self._build_candidates(state) if state is not None else {}
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

        for alert_id in existing_ids - candidates.keys():
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
                self._pending_history.append(AlertHistoryEntry.resolved(record, now))
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
                self._pending_history.append(AlertHistoryEntry.resolved(record, now))
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
            if (
                evaluation.jinja_result is False
                or evaluation.error_code == "condition_template_error"
            ):
                self._clear_variation_baseline(rule, state.entity_id)
            elif baseline is None and evaluation.baseline is not None:
                self._variation_value(rule, state, evaluation.raw_value)
        return evaluation

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
            evaluation = self._evaluate_custom_rule(rule, state)
            if evaluation.result is not True:
                continue
            current = evaluation.value
            alert_id = f"rule:{rule.id}:{entity_id}"
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
