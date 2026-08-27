"""Runtime safety and event coalescing for Alert Manager."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    EVENT_ALERT_ACKNOWLEDGED,
    EVENT_ALERT_RESOLVED,
    EVENT_ALERT_STARTED,
    EVENT_ALERT_UNACKNOWLEDGED,
)
from .manager import AlertManager as BaseAlertManager
from .models import AlertHistoryEntry, AlertRecord, AlertStatus, Rule

_LOGGER = logging.getLogger(__name__)

_JINJA_BLOCK_PATTERN = re.compile(r"{{(.*?)}}|{%(.*?)%}", re.DOTALL)
_ENTITY_ID_PATTERN = re.compile(
    r"(?<![a-z0-9_])([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)(?![a-z0-9_])",
    re.IGNORECASE,
)

type DependencyKey = tuple[str, str, str]


class AlertManager(BaseAlertManager):
    """Add loop guards, durable lifecycle events and coalesced processing."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize runtime indexes, transactions and coalescing queues."""
        super().__init__(hass, entry)
        self._template_dependents: dict[str, set[DependencyKey]] = {}
        self._template_dynamic_infos: dict[DependencyKey, Any] = {}
        self._template_entities_by_key: dict[DependencyKey, frozenset[str]] = {}
        self._template_time_dependencies: set[DependencyKey] = set()
        self._template_time_timer: Callable[[], None] | None = None
        self._template_rate_limit_until: dict[DependencyKey, datetime] = {}
        self._template_rate_limit_timers: dict[DependencyKey, Callable[[], None]] = {}
        self._queued_evaluation_entities: set[str] = set()
        self._queued_evaluation_restoring = False
        self._evaluation_flush_scheduled = False
        self._registry_evaluation_scheduled = False
        self._registry_evaluation_dirty = False
        self._pending_entity_renames: dict[str, str] = {}
        self._pack_refresh_scheduled = False
        self._pack_refresh_dirty = False
        self._mutation_lock = asyncio.Lock()
        self._mutation_owner: asyncio.Task[Any] | None = None
        self._mutation_depth = 0
        self._deferred_lifecycle_events: list[tuple[str, dict[str, Any]]] = []

    @asynccontextmanager
    async def _mutation_transaction(self) -> AsyncIterator[None]:
        """Serialize mutations, roll back failures and defer events until durable."""
        task = asyncio.current_task()
        if task is None:  # pragma: no cover - Home Assistant always runs in a task
            raise RuntimeError("Alert Manager mutation requires an asyncio task")
        if self._mutation_owner is task:
            self._mutation_depth += 1
            try:
                yield
            finally:
                self._mutation_depth -= 1
            return

        deferred: list[tuple[str, dict[str, Any]]] = []
        async with self._mutation_lock:
            self._mutation_owner = task
            self._mutation_depth = 1
            snapshot = self._runtime_snapshot()
            self._deferred_lifecycle_events = []
            try:
                yield
            except Exception:
                self._restore_runtime_snapshot(snapshot)
                self._deferred_lifecycle_events.clear()
                raise
            else:
                deferred = self._deferred_lifecycle_events
            finally:
                self._deferred_lifecycle_events = []
                self._mutation_depth = 0
                self._mutation_owner = None

        # Fire outside the mutation lock. Event listeners may call back into the
        # integration and must see a completely committed runtime snapshot.
        for event_type, data in deferred:
            self.hass.bus.async_fire(event_type, data)

    def _runtime_snapshot(self) -> dict[str, Any]:
        """Capture mutable business state needed for a failed-write rollback."""
        return {
            "config": deepcopy(self.config),
            "records": deepcopy(self.records),
            "history": list(self.history),
            "pending_history": list(self._pending_history),
            "rule_render_info": dict(self._rule_template_render_info),
            "message_render_info": dict(self._rule_message_render_info),
            "pack_availability": dict(self._pack_availability),
            "last_public_snapshot": deepcopy(self._last_public_snapshot),
            "active_device_group_ids": set(self._active_device_group_ids),
            "unloading": self._unloading,
        }

    def _restore_runtime_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Restore a failed transaction without retaining timers or indexes."""
        self._cancel_all_timers()
        self._cancel_all_device_event_timers()
        self._cancel_template_dependency_timers()
        self.config = snapshot["config"]
        self.records = snapshot["records"]
        self.history = snapshot["history"]
        self._pending_history = snapshot["pending_history"]
        self._rule_template_render_info = snapshot["rule_render_info"]
        self._rule_message_render_info = snapshot["message_render_info"]
        self._pack_availability = snapshot["pack_availability"]
        self._last_public_snapshot = snapshot["last_public_snapshot"]
        self._active_device_group_ids = snapshot["active_device_group_ids"]
        self._unloading = snapshot["unloading"]
        self._rebuild_rule_index()
        self._refresh_tracking()
        self._reschedule_record_timers()

    def _defer_or_fire(self, event_type: str, data: dict[str, Any]) -> None:
        """Queue lifecycle events while a persistence transaction is in flight."""
        if self._mutation_owner is not None:
            self._deferred_lifecycle_events.append((event_type, deepcopy(data)))
            return
        self.hass.bus.async_fire(event_type, data)

    def _fire_started(self, record: AlertRecord) -> None:
        """Emit a start event only after the surrounding mutation commits."""
        self._defer_or_fire(EVENT_ALERT_STARTED, record.as_public_dict())

    def _fire_resolved(self, record: AlertRecord, now: datetime) -> None:
        """Emit a resolved event only after the surrounding mutation commits."""
        data = record.as_public_dict()
        data["resolved_at"] = now.isoformat()
        self._defer_or_fire(EVENT_ALERT_RESOLVED, data)

    def _fire_acknowledged(self, record: AlertRecord) -> None:
        """Emit acknowledgement only after its durable transaction commits."""
        self._defer_or_fire(EVENT_ALERT_ACKNOWLEDGED, record.as_public_dict())

    def _fire_unacknowledged(
        self,
        record: AlertRecord,
        now: datetime,
        actor: str | None,
        previous_at: datetime | None,
        previous_by: str | None,
    ) -> None:
        """Emit removal metadata only after its durable transaction commits."""
        data = record.as_public_dict()
        data["unacknowledged_at"] = now.isoformat()
        if actor is not None:
            data["unacknowledged_by"] = actor
        if previous_at is not None:
            data["previous_acknowledged_at"] = previous_at.isoformat()
        if previous_by is not None:
            data["previous_acknowledged_by"] = previous_by
        self._defer_or_fire(EVENT_ALERT_UNACKNOWLEDGED, data)

    async def async_evaluate_all(
        self,
        *,
        restoring: bool = False,
        save: bool = True,
        publish: bool = True,
        emit_events: bool = True,
    ) -> bool:
        """Serialize a full evaluation with every other runtime mutation."""
        async with self._mutation_transaction():
            return await super().async_evaluate_all(
                restoring=restoring,
                save=save,
                publish=publish,
                emit_events=emit_events,
            )

    async def async_evaluate_entity(
        self,
        entity_id: str,
        *,
        restoring: bool = False,
        save: bool = True,
        publish: bool = True,
        emit_events: bool = True,
    ) -> bool:
        """Serialize one source evaluation and roll it back on write failure."""
        async with self._mutation_transaction():
            return await super().async_evaluate_entity(
                entity_id,
                restoring=restoring,
                save=save,
                publish=publish,
                emit_events=emit_events,
            )

    async def async_refresh_pack_availability(self) -> bool:
        """Serialize prerequisite changes with state/config mutations."""
        async with self._mutation_transaction():
            return await super().async_refresh_pack_availability()

    async def async_set_history_limit(self, limit: int) -> dict[str, int | bool]:
        """Serialize history configuration with runtime persistence."""
        async with self._mutation_transaction():
            return await super().async_set_history_limit(limit)

    async def async_clear_history(self) -> dict[str, Any]:
        """Serialize history clearing with runtime persistence."""
        async with self._mutation_transaction():
            return await super().async_clear_history()

    async def async_set_monitoring(self, enabled: bool) -> bool:
        """Serialize monitoring suspension/resume with state transitions."""
        async with self._mutation_transaction():
            return await super().async_set_monitoring(enabled)

    async def async_acknowledge(self, alert_id: str, actor: str | None) -> bool:
        """Serialize acknowledgement against simultaneous resolution."""
        async with self._mutation_transaction():
            return await super().async_acknowledge(alert_id, actor)

    async def async_unacknowledge(self, alert_id: str, actor: str | None) -> bool:
        """Serialize acknowledgement removal against simultaneous resolution."""
        async with self._mutation_transaction():
            return await super().async_unacknowledge(alert_id, actor)

    async def async_update_config(self, changes: dict[str, Any]) -> dict[str, Any]:
        """Serialize configuration updates with all evaluations."""
        async with self._mutation_transaction():
            return await super().async_update_config(changes)

    async def async_import_config(self, raw_yaml: str) -> dict[str, Any]:
        """Import atomically and emit lifecycle changes after persistence."""
        async with self._mutation_transaction():
            previous_records = deepcopy(self.records)
            was_monitoring = self.monitoring_enabled
            result = await super().async_import_config(raw_yaml)
            if was_monitoring and self.monitoring_enabled:
                # Base import suppresses evaluation events while reconciling the
                # complete configuration. Recreate exactly the resulting lifecycle
                # delta once the imported state has been durably saved.
                self._emit_resume_events(previous_records)
            return result

    async def async_create_rule(self, data: dict[str, Any]) -> dict[str, Any]:
        """Serialize rule creation and its initial evaluations."""
        async with self._mutation_transaction():
            return await super().async_create_rule(data)

    async def async_update_rule(
        self, rule_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Serialize rule edits and lifecycle reconciliation."""
        async with self._mutation_transaction():
            return await super().async_update_rule(rule_id, data)

    async def async_delete_rule(self, rule_id: str) -> None:
        """Serialize rule deletion and lifecycle reconciliation."""
        async with self._mutation_transaction():
            await super().async_delete_rule(rule_id)

    async def async_unload(self) -> None:
        """Wait for in-flight mutations before persisting the final snapshot."""
        self._cancel_template_dependency_timers()
        async with self._mutation_transaction():
            await super().async_unload()

    def _build_candidates(self, state: State) -> dict[str, tuple[Any, int]]:
        """Freeze the effective delay once an occurrence has become active."""
        candidates = super()._build_candidates(state)
        for alert_id, (details, _delay) in tuple(candidates.items()):
            record = self.records.get(alert_id)
            if record is not None and record.status is AlertStatus.ACTIVE:
                # A configuration delay applies to future/pending activation only.
                # Moving an already active occurrence back to pending corrupts its
                # history and can emit a second start event for the same occurrence.
                candidates[alert_id] = (details, record.delay)
        return candidates

    def _remove_rule_instances(self, rule_id: str, entity_ids: set[str]) -> None:
        """Resolve active instances removed by disabling/editing/deleting a rule."""
        now = dt_util.now()
        for entity_id in entity_ids:
            alert_id = f"rule:{rule_id}:{entity_id}"
            record = self.records.pop(alert_id, None)
            if record is None:
                continue
            self._cancel_timer(alert_id)
            if record.status is AlertStatus.ACTIVE:
                self._pending_history.append(AlertHistoryEntry.resolved(record, now))
                self._fire_resolved(record, now)

    def _validate_rule_template(self, rule: Rule) -> None:
        """Reject self-referential Jinja in addition to invalid syntax."""
        super()._validate_rule_template(rule)
        own_entities = self._own_template_entities(rule)
        if not own_entities:
            return
        joined = ", ".join(sorted(own_entities))
        raise ValueError(
            "Jinja templates cannot reference Alert Manager entities "
            f"({joined}) because this can create an infinite update loop"
        )

    def _remove_own_rule_sources(self) -> bool:
        """Disable legacy rules whose Jinja references Alert Manager itself."""
        changed = super()._remove_own_rule_sources()
        for raw_rule in self.config.get("rules", []):
            rule = Rule.from_dict(raw_rule)
            own_entities = self._own_template_entities(rule)
            if not own_entities or not raw_rule.get("enabled", True):
                continue
            raw_rule["enabled"] = False
            changed = True
            _LOGGER.warning(
                "Disabled rule %s because its Jinja references Alert Manager "
                "entities: %s",
                rule.id,
                ", ".join(sorted(own_entities)),
            )
        return changed

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

    def _rebuild_rule_index(self) -> None:
        """Rebuild rules and compact dependency indexes for enabled templates."""
        super()._rebuild_rule_index()
        enabled_rule_ids = {rule.id for rule in self._rules if rule.enabled}
        self._rule_templates = {
            rule_id: template
            for rule_id, template in self._rule_templates.items()
            if rule_id in enabled_rule_ids
        }
        self._rule_message_templates = {
            rule_id: template
            for rule_id, template in self._rule_message_templates.items()
            if rule_id in enabled_rule_ids
        }
        self._rule_template_render_info = {
            key: info
            for key, info in self._rule_template_render_info.items()
            if key[0] in enabled_rule_ids
        }
        self._rule_message_render_info = {
            key: info
            for key, info in self._rule_message_render_info.items()
            if key[0] in enabled_rule_ids
        }
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
        """Match Home Assistant's now()/utcnow() refresh at each minute boundary."""
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
            sources = {key[2] for key in self._template_time_dependencies}
            self._queue_entity_evaluations(sources)
            if self._template_time_dependencies:
                self._schedule_template_time_tick()

        self._template_time_timer = async_track_point_in_utc_time(
            self.hass,
            timer_due,
            when,
        )

    def _schedule_rate_limited_dependency(
        self, dependency_key: DependencyKey, when: datetime
    ) -> None:
        """Guarantee a coalesced re-render when a dynamic Jinja limit expires."""
        if dependency_key in self._template_rate_limit_timers:
            return

        @callback
        def timer_due(_now: datetime) -> None:
            self._template_rate_limit_timers.pop(dependency_key, None)
            if dependency_key not in self._template_dynamic_infos:
                return
            self._queue_entity_evaluations((dependency_key[2],))

        self._template_rate_limit_timers[dependency_key] = (
            async_track_point_in_utc_time(
                self.hass,
                timer_due,
                when,
            )
        )

    def _dynamic_dependency_matches(
        self,
        dependency_key: DependencyKey,
        render_info: Any,
        entity_id: str,
        *,
        lifecycle: bool,
    ) -> bool:
        """Apply HA RenderInfo state/lifecycle filters and dynamic rate limits."""
        try:
            matches = bool(render_info.filter(entity_id))
            if lifecycle:
                matches |= bool(render_info.filter_lifecycle(entity_id))
        except Exception:  # pragma: no cover - defensive HA API guard
            _LOGGER.exception("Unable to filter Jinja dependency for %s", entity_id)
            return False
        if not matches:
            return False

        # Explicit entity references are precise dependencies and Home Assistant
        # does not need broad-domain/all-state throttling for those changes.
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
        """Index condition dependencies and reject runtime self-dependencies."""
        pair = (rule.id, state.entity_id)
        previous = self._rule_template_render_info.get(pair)
        result = super()._rule_template_matches(rule, state, current)
        render_info = self._rule_template_render_info.get(pair)
        dependency_key = ("condition", rule.id, state.entity_id)
        if render_info is previous:
            if render_info is None:
                self._remove_dependency_key(dependency_key)
            return result
        if render_info is None:
            self._remove_dependency_key(dependency_key)
            return result
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
        """Index message dependencies only while the occurrence can still change."""
        pair = (rule.id, state.entity_id)
        dependency_key = ("message", rule.id, state.entity_id)
        alert_id = f"rule:{rule.id}:{state.entity_id}"
        record = self.records.get(alert_id)
        if record is not None and record.status is AlertStatus.ACTIVE:
            self._rule_message_render_info.pop(pair, None)
            self._remove_dependency_key(dependency_key)
            rendered = super()._render_rule_message(
                rule,
                state,
                current,
                force=force,
            )
            self._rule_message_render_info.pop(pair, None)
            self._remove_dependency_key(dependency_key)
            return rendered

        previous = self._rule_message_render_info.get(pair)
        rendered = super()._render_rule_message(
            rule,
            state,
            current,
            force=force,
        )
        render_info = self._rule_message_render_info.get(pair)
        if render_info is previous:
            if render_info is None:
                self._remove_dependency_key(dependency_key)
            return rendered
        if render_info is None:
            self._remove_dependency_key(dependency_key)
            return rendered
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
        return rendered

    @callback
    def _state_changed(self, event: Event) -> None:
        """Queue only sources affected by a state or entity lifecycle event."""
        if not self.monitoring_enabled:
            return
        entity_id = event.data.get("entity_id")
        if not entity_id or self._is_own_entity(entity_id):
            return

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
        if self._is_relevant_entity_id(entity_id):
            affected_entities.add(entity_id)
        self._queue_entity_evaluations(
            affected_entities,
            restoring=not self.hass.is_running,
        )

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
        if not self._queued_evaluation_entities:
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
            async with self._mutation_transaction():
                if self._unloading or not self.monitoring_enabled:
                    self._queued_evaluation_entities.clear()
                    self._queued_evaluation_restoring = False
                    return
                entity_ids = sorted(self._queued_evaluation_entities)
                self._queued_evaluation_entities.clear()
                restoring = self._queued_evaluation_restoring
                self._queued_evaluation_restoring = False
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
                self._publish_if_changed()
        finally:
            self._evaluation_flush_scheduled = False
            if (
                self._queued_evaluation_entities
                and not self._unloading
                and self.monitoring_enabled
            ):
                self._schedule_evaluation_flush()

    def _publish_if_changed(self, *, force: bool = False) -> None:
        """Drop frozen message dependencies before publishing a new snapshot."""
        for record in self.records.values():
            if record.status is not AlertStatus.ACTIVE or not record.details.rule_id:
                continue
            pair = (record.details.rule_id, record.details.entity_id)
            self._rule_message_render_info.pop(pair, None)
            self._remove_dependency_key(("message", pair[0], pair[1]))
        super()._publish_if_changed(force=force)

    @callback
    def _timer_due(self, alert_id: str) -> None:
        """Fold due timers into the same batched evaluation path."""
        self._timers.pop(alert_id, None)
        if not self.monitoring_enabled:
            return
        record = self.records.get(alert_id)
        if record is None:
            return
        self._queue_entity_evaluations((record.details.entity_id,))

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
        """Migrate config and live record identities for registry entity renames."""
        if not self._pending_entity_renames:
            return False
        renames = dict(self._pending_entity_renames)
        self._pending_entity_renames.clear()

        def final_target(entity_id: str) -> str:
            seen: set[str] = set()
            target = entity_id
            while target in renames and target not in seen:
                seen.add(target)
                target = renames[target]
            return target

        changed = False
        for old_entity_id in tuple(renames):
            new_entity_id = final_target(old_entity_id)
            if old_entity_id == new_entity_id:
                continue

            for raw_rule in self.config.get("rules", []):
                entity_ids = raw_rule.get("entity_ids")
                if not isinstance(entity_ids, list) or old_entity_id not in entity_ids:
                    continue
                replaced: list[str] = []
                for entity_id in entity_ids:
                    entity_id = (
                        new_entity_id if entity_id == old_entity_id else entity_id
                    )
                    if entity_id not in replaced:
                        replaced.append(entity_id)
                raw_rule["entity_ids"] = replaced
                changed = True

            entity_delays = self.config.get("entity_delays", {})
            if old_entity_id in entity_delays:
                if new_entity_id not in entity_delays:
                    entity_delays[new_entity_id] = entity_delays[old_entity_id]
                entity_delays.pop(old_entity_id, None)
                changed = True

            excluded_entities = self.config.get("excluded_entities", [])
            if old_entity_id in excluded_entities:
                replaced_exclusions: list[str] = []
                for entity_id in excluded_entities:
                    entity_id = (
                        new_entity_id if entity_id == old_entity_id else entity_id
                    )
                    if entity_id not in replaced_exclusions:
                        replaced_exclusions.append(entity_id)
                self.config["excluded_entities"] = replaced_exclusions
                changed = True

            for alert_id, record in tuple(self.records.items()):
                if record.details.entity_id != old_entity_id:
                    continue
                if record.details.type == "rule" and record.details.rule_id:
                    new_alert_id = f"rule:{record.details.rule_id}:{new_entity_id}"
                else:
                    new_alert_id = f"{record.details.type}:{new_entity_id}"
                self._cancel_timer(alert_id)
                self.records.pop(alert_id, None)
                existing = self.records.pop(new_alert_id, None)
                if existing is not None:
                    self._cancel_timer(new_alert_id)
                    # A rename should preserve the oldest occurrence rather than
                    # silently replacing its lifecycle with a freshly-created one.
                    if existing.detected_at < record.detected_at:
                        record = existing
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

    async def _async_flush_registry_evaluation(self) -> None:
        """Apply renames and run one durable full scan for each registry burst."""
        try:
            while self._registry_evaluation_dirty and not self._unloading:
                self._registry_evaluation_dirty = False
                async with self._mutation_transaction():
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
