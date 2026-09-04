"""Custom rule and Jinja handling for Alert Manager."""

from __future__ import annotations

import logging
import re
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import CoreState, State, callback
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

from .const import (
    ALERT_MANAGER_ENTITY_IDS,
    ATTRIBUTE_SOURCES,
    CUSTOM_RULE_ALLOWED_ENTITY_IDS,
    DOMAIN,
    VARIATION_SOURCES,
)
from .models import AlertStatus, Rule, extract_attribute_value
from .runtime_phase import RuntimePhase

_LOGGER = logging.getLogger(__name__)

_LEGACY_OPERATOR_LABELS = {
    "equals": "Égal à",
    "not_equals": "Différent de",
    "contains": "Contient",
    "not_contains": "Ne contient pas",
    "above": "Supérieur à",
    "below": "Inférieur à",
    "between": "Entre",
    "outside": "En dehors de",
    "unchanged": "Aucun changement",
}


def _legacy_rule_source(rule: Rule) -> str:
    """Return the source label used only by the non-localized fallback text."""
    if rule.source == "attribute":
        return f"Attribut {rule.attribute}"
    if rule.source == "state_variation":
        return "Variation de l'etat"
    if rule.source == "attribute_variation":
        return f"Variation de l'attribut {rule.attribute}"
    return "État"


_JINJA_BLOCK_PATTERN = re.compile(r"{{(.*?)}}|{%(.*?)%}", re.DOTALL)
_ENTITY_ID_PATTERN = re.compile(
    r"(?<![a-z0-9_])([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)(?![a-z0-9_])",
    re.IGNORECASE,
)

type DependencyKey = tuple[str, str, str]


class _TemplatesMixin:
    """Maintain custom rules, Jinja templates and their dependencies."""

    def _rule_condition_params(self, rule: Rule, state: State) -> dict[str, Any]:
        """Return stable structured parameters for a generated rule condition."""
        if rule.source in ("jinja", "unchanged"):
            return {"duration": rule.duration}
        if rule.operator == "unchanged":
            return {
                "source": rule.source,
                "attribute": rule.attribute,
                "duration": rule.duration,
            }
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
        if rule.source == "jinja":
            duration = f" pendant {rule.duration} s" if rule.duration else ""
            return f"Condition Jinja{duration}"
        if rule.source == "unchanged":
            duration = f" pendant {rule.duration} s" if rule.duration else ""
            return f"État et attributs inchangés{duration}"
        if rule.operator == "unchanged":
            source = _legacy_rule_source(rule)
            duration = f" pendant {rule.duration} s" if rule.duration else ""
            return f"{source} inchangé{duration}"
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        source = _legacy_rule_source(rule)
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

    def _rebuild_rule_index(self) -> None:
        """Cache enabled rules and rebuild template dependency indexes."""
        self._refresh_config_caches()
        self._rules = [Rule.from_dict(rule) for rule in self.config.get("rules", [])]
        valid_variation_keys = {
            f"{rule.id}:{entity_id}"
            for rule in self._rules
            if rule.enabled and rule.source in VARIATION_SOURCES
            for entity_id in rule.entity_ids
        }
        stale_variation_keys = self._variation_baselines.keys() - valid_variation_keys
        if stale_variation_keys:
            for key in stale_variation_keys:
                self._variation_baselines.pop(key, None)
            self._variation_baselines_dirty = True
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
            or not self.monitoring_enabled
            or self._unloading
            or not self._runtime_phase.can_evaluate
            or self.hass.state is not CoreState.running
        ):
            return
        now = dt_util.now().astimezone(UTC)
        when = now.replace(second=0, microsecond=0) + timedelta(minutes=1)

        @callback
        def timer_due(_now: datetime) -> None:
            self._template_time_timer = None
            if (
                not self.monitoring_enabled
                or self._unloading
                or not self._runtime_phase.can_evaluate
                or self.hass.state is not CoreState.running
            ):
                return
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
        if (
            dependency_key in self._template_rate_limit_timers
            or not self.monitoring_enabled
            or self._unloading
            or self._runtime_phase is not RuntimePhase.RUNNING
            or self.hass.state is not CoreState.running
        ):
            return

        @callback
        def timer_due(_now: datetime) -> None:
            self._template_rate_limit_timers.pop(dependency_key, None)
            if (
                dependency_key in self._template_dynamic_infos
                and self.monitoring_enabled
                and not self._unloading
                and self._runtime_phase is RuntimePhase.RUNNING
                and self.hass.state is CoreState.running
            ):
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
        if self._runtime_phase is RuntimePhase.RECONCILING:
            # The startup queue already coalesces dependency bursts. Deferring a
            # dynamic match to a runtime timer here could lose the only change
            # observed between the authoritative scan and its final Store write.
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
        """Return runtime dependencies that can feed back into Alert Manager."""
        return {
            entity_id
            for entity_id in (getattr(render_info, "entities", ()) or ())
            if not self._is_allowed_rule_source(entity_id)
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
        """Render an optional message and track it for as long as configured."""
        if rule.message is None:
            return None
        pair = (rule.id, state.entity_id)
        dependency_key = ("message", rule.id, state.entity_id)
        alert_id = f"rule:{rule.id}:{state.entity_id}"
        record = self.records.get(alert_id)
        if (
            record is not None
            and record.status is AlertStatus.ACTIVE
            and not rule.update_message_when_active
        ):
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
        current = state.state
        if rule.source in ATTRIBUTE_SOURCES:
            _found, current = extract_attribute_value(
                state.attributes, rule.attribute or ""
            )
        if rule.source in VARIATION_SOURCES:
            found, variation = self._variation_value(rule, state, current)
            if found:
                current = variation
        rendered_message = self._render_rule_message(
            rule,
            state,
            current,
            force=True,
        )
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
                (
                    "operator",
                    None if rule.source in ("jinja", "unchanged") else rule.operator,
                ),
                (
                    "comparison_value",
                    None
                    if rule.source in ("jinja", "unchanged")
                    or rule.operator == "unchanged"
                    else rule.value,
                ),
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

    def _is_allowed_rule_source(self, entity_id: str) -> bool:
        """Allow normal entities and the loop-safe coherence issue sensor."""
        return entity_id in CUSTOM_RULE_ALLOWED_ENTITY_IDS or not self._is_own_entity(
            entity_id
        )

    def _validate_rule_sources(self, rule: Rule) -> None:
        """Reject custom rules targeting Alert Manager itself."""
        if any(
            not self._is_allowed_rule_source(entity_id) for entity_id in rule.entity_ids
        ):
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
        return {
            entity_id
            for entity_id in referenced
            if not self._is_allowed_rule_source(entity_id)
        }

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
                if self._is_allowed_rule_source(entity_id)
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
            if not self._is_allowed_rule_source(record.details.entity_id)
        ]
        for alert_id in own_ids:
            self._pop_record(alert_id)
        return bool(own_ids)
