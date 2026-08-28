"""Runtime safety and event coalescing for Alert Manager."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import Event, HomeAssistant, State, callback

from .const import DOMAIN
from .manager import AlertManager as BaseAlertManager
from .models import AlertStatus, Rule
from .packs import PACKS, PACK_NEUTRAL

_LOGGER = logging.getLogger(__name__)

_JINJA_BLOCK_PATTERN = re.compile(r"{{(.*?)}}|{%(.*?)%}", re.DOTALL)
_ENTITY_ID_PATTERN = re.compile(
    r"(?<![a-z0-9_])([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)(?![a-z0-9_])",
    re.IGNORECASE,
)

type DependencyKey = tuple[str, str, str]


class AlertManager(BaseAlertManager):
    """Add loop guards and coalesced event processing to the core manager."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize runtime indexes and coalescing queues."""
        super().__init__(hass, entry)
        self._template_dependents: dict[str, set[DependencyKey]] = {}
        self._template_dynamic_infos: dict[DependencyKey, Any] = {}
        self._template_entities_by_key: dict[DependencyKey, frozenset[str]] = {}
        self._queued_evaluation_entities: set[str] = set()
        self._queued_evaluation_restoring = False
        self._queued_public_refresh = False
        self._evaluation_flush_scheduled = False
        self._registry_evaluation_scheduled = False
        self._registry_evaluation_dirty = False
        self._pack_refresh_scheduled = False
        self._pack_refresh_dirty = False

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
        self._template_dependents.clear()
        self._template_dynamic_infos.clear()
        self._template_entities_by_key.clear()
        for kind, render_infos in (
            ("condition", self._rule_template_render_info),
            ("message", self._rule_message_render_info),
        ):
            for pair, render_info in render_infos.items():
                self._index_render_info(kind, pair, render_info)

    def _index_render_info(
        self, kind: str, pair: tuple[str, str], render_info: Any
    ) -> None:
        """Index one RenderInfo by explicit entities with a dynamic fallback."""
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
        """Remove one template instance from every reverse index."""
        for entity_id in self._template_entities_by_key.pop(dependency_key, ()):
            dependents = self._template_dependents.get(entity_id)
            if dependents is None:
                continue
            dependents.discard(dependency_key)
            if not dependents:
                self._template_dependents.pop(entity_id, None)
        self._template_dynamic_infos.pop(dependency_key, None)

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

    def _build_candidates(self, state: State) -> dict[str, Any]:
        """Let each pack evaluate unavailable, including neutral outcomes."""
        if state.state != STATE_UNAVAILABLE:
            return super()._build_candidates(state)
        if not self._is_base_eligible(state.entity_id):
            return {}

        result: dict[str, Any] = {}
        if self._is_automatic_eligible(state.entity_id):
            automatic = self.config.get("automatic", {})
            for pack in PACKS:
                config = automatic.get(pack.id, {})
                if not config.get("enabled", False):
                    continue
                if not self._pack_is_available(pack.id):
                    continue
                evaluation = pack.evaluate(self.hass, state, config)
                if evaluation is PACK_NEUTRAL:
                    alert_id = f"{pack.id}:{state.entity_id}"
                    record = self.records.get(alert_id)
                    if record is not None:
                        result[alert_id] = (record.details, record.delay)
                    continue
                if evaluation is not None:
                    super()._add_pack_candidate(result, state, pack.id)
        # Keep the existing rule semantics: custom rules are not evaluated while
        # their source itself is unavailable.
        return result

    def _state_event_affects_source(self, event: Event, entity_id: str) -> bool:
        """Return whether this state transition can change source-owned output."""
        if entity_id in self._rules_by_entity:
            return True

        # Once any alert occurrence exists for this source, always evaluate the
        # entity. Candidate generation/evaluate() owns all keep/resolve decisions.
        if any(
            record.details.entity_id == entity_id for record in self.records.values()
        ):
            return True

        # Home Assistant state_changed events include both states. Keep a
        # conservative fallback for synthetic events or future HA API changes.
        if "old_state" not in event.data or "new_state" not in event.data:
            return self._is_relevant_entity_id(entity_id)
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if (old_state is not None and not isinstance(old_state, State)) or (
            new_state is not None and not isinstance(new_state, State)
        ):
            return self._is_relevant_entity_id(entity_id)

        # Exact duplicate events are irrelevant only while the entity has no
        # current alert occurrence. Jinja dependencies are queued independently.
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
    def _state_changed(self, event: Event) -> None:
        """Queue only sources affected by a state event, never our own entities."""
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
        for dependency_key, render_info in tuple(self._template_dynamic_infos.items()):
            try:
                if render_info.filter(entity_id):
                    affected_entities.add(dependency_key[2])
            except Exception:  # pragma: no cover - defensive HA API guard
                _LOGGER.exception("Unable to filter Jinja dependency for %s", entity_id)
        if self._state_event_affects_source(event, entity_id):
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
        # A timer may exist only to expose a still-pending alert. That changes
        # the public snapshot without changing persisted record data.
        self._queued_public_refresh = True
        self._queue_entity_evaluations((record.details.entity_id,))

    @callback
    def _registry_changed(self, _event: Event) -> None:
        """Coalesce registry bursts into one full evaluation."""
        if not self.monitoring_enabled or self._unloading:
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

    async def _async_flush_registry_evaluation(self) -> None:
        """Run one full scan for all registry changes seen before each pass."""
        try:
            while self._registry_evaluation_dirty and not self._unloading:
                self._registry_evaluation_dirty = False
                if self.monitoring_enabled:
                    await self.async_evaluate_all()
        finally:
            self._registry_evaluation_scheduled = False
            if (
                self._registry_evaluation_dirty
                and not self._unloading
                and self.monitoring_enabled
            ):
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
