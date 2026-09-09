"""Indexed edge observations and hold confirmation for custom transition rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import State
from homeassistant.util import dt as dt_util

from .const import TRANSITION_SOURCES
from .models import AlertRecord, AlertStatus, Rule, advance_record, normalize_scalar
from .packs.base import PackOccurrence
from .rule_evaluation import rule_current_value
from .runtime_phase import RuntimePhase


@dataclass(frozen=True, slots=True)
class TransitionObservation:
    """One unpersisted edge; unrelated updates never move its hold deadline."""

    rule: Rule
    state: State
    departed: Any
    arrived: Any
    observed_at: datetime
    due_at: datetime


def transition_value(rule: Rule, state: State | None) -> Any:
    """Missing and unavailable observations are never arbitrary edge values."""
    if not isinstance(state, State) or state.state in (
        STATE_UNKNOWN,
        STATE_UNAVAILABLE,
    ):
        return None
    found, value = rule_current_value(rule, state)
    if not found or not isinstance(value, str | int | float | bool):
        return None
    if normalize_scalar(value) in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    return value


class _TransitionsMixin:
    """Reuse records, lifecycle timers and history without a second alert engine."""

    def _observe_transitions(
        self, entity_id: str, old: State | None, new: State | None
    ) -> None:
        # Startup reconciliation and initial discovery must not arm an edge.
        if (
            self._runtime_phase is not RuntimePhase.RUNNING
            or entity_id not in self._rules_by_entity
            or not self._is_base_eligible(entity_id)
        ):
            return
        now = dt_util.now()
        for rule in self._rules_by_entity.get(entity_id, ()):
            if not rule.enabled or rule.source not in TRANSITION_SOURCES:
                continue
            alert_id = f"rule:{rule.id}:{entity_id}"
            departed, arrived = transition_value(rule, old), transition_value(rule, new)
            observation = self._transition_observations.get(alert_id)
            if (
                observation is not None
                and now >= observation.due_at
                and departed is not None
                and normalize_scalar(departed) == normalize_scalar(rule.to_value)
            ):
                # An outgoing edge proves continuity despite coalesced evaluation.
                self._transition_confirmed[alert_id] = observation
                self._transition_observations.pop(alert_id, None)
                observation = None
            if (
                observation is not None
                and rule.duration
                and (
                    arrived is None
                    or normalize_scalar(arrived) != normalize_scalar(rule.to_value)
                )
            ):
                self._transition_observations.pop(alert_id, None)
            if departed is None or arrived is None:
                continue
            if normalize_scalar(departed) != normalize_scalar(
                rule.from_value
            ) or normalize_scalar(arrived) != normalize_scalar(rule.to_value):
                continue
            condition, _ = self._evaluate_rule_condition_template(
                rule, new, arrived, track=True
            )
            if rule.condition_template is not None and condition is not True:
                continue
            target = (
                self._transition_observations
                if rule.duration
                else self._transition_confirmed
            )
            target[alert_id] = TransitionObservation(
                rule,
                new,
                departed,
                arrived,
                now,
                now + timedelta(seconds=rule.duration),
            )

    def _prune_transition_observations(self) -> None:
        self._transition_rules_by_id = {
            rule.id: rule
            for rule in self._rules
            if rule.enabled and rule.source in TRANSITION_SOURCES
        }
        for observations in (self._transition_observations, self._transition_confirmed):
            for alert_id, observation in tuple(observations.items()):
                if (
                    self._transition_rules_by_id.get(observation.rule.id)
                    != observation.rule
                ):
                    observations.pop(alert_id, None)

    def _preserve_transition_record(self, alert_id: str) -> bool:
        record = self.records.get(alert_id)
        if record is None or record.details.source not in TRANSITION_SOURCES:
            return False
        if not self._is_base_eligible(record.details.entity_id):
            return False
        rule = self._transition_rules_by_id.get(record.details.rule_id)
        return (
            rule is not None
            and rule.enabled
            and record.details.entity_id in rule.entity_ids
            and rule.source == record.details.source
            and (
                record.status is AlertStatus.ACTIVE
                or alert_id in self._transition_observations
            )
        )

    def _evaluate_transitions(
        self,
        entity_id: str,
        now: datetime,
        *,
        emit_events: bool,
        new_occurrences: list[PackOccurrence] | None = None,
    ) -> bool:
        changed = False
        for rule in self._rules_by_entity.get(entity_id, ()):
            if not rule.enabled or rule.source not in TRANSITION_SOURCES:
                continue
            alert_id = f"rule:{rule.id}:{entity_id}"
            if not self._is_base_eligible(entity_id):
                self._transition_confirmed.pop(alert_id, None)
                self._transition_observations.pop(alert_id, None)
                continue
            record = self.records.get(alert_id)
            if (
                record is not None
                and record.status is AlertStatus.ACTIVE
                and rule.update_message_when_active
                and self._refresh_active_rule_message(rule, entity_id)
            ):
                self._schedule_live_message_flush()
            confirmed = self._transition_confirmed.pop(alert_id, None)
            observation = confirmed or self._transition_observations.get(alert_id)
            if observation is None or observation.rule != rule:
                continue
            if rule.duration and confirmed is None:
                state = self.hass.states.get(entity_id)
                value = transition_value(rule, state)
                condition = (
                    self._evaluate_rule_condition_template(
                        rule, state, value, track=True
                    )[0]
                    if state is not None
                    else False
                )
                if (
                    value is None
                    or normalize_scalar(value) != normalize_scalar(rule.to_value)
                    or (rule.condition_template is not None and condition is not True)
                ):
                    self._transition_observations.pop(alert_id, None)
                    continue
            record = self.records.get(alert_id)
            if (
                record is not None
                and record.expires_at is not None
                and now >= record.expires_at
                and observation.due_at > record.expires_at
            ):
                changed |= self._resolve_expired_alerts(
                    now, alert_ids=(alert_id,), emit_events=emit_events
                )
                record = None
            if (
                record is not None
                and record.status is AlertStatus.PENDING
                and record.detected_at != observation.observed_at
            ):
                self._pop_record(alert_id)
                self._cancel_timer(alert_id)
                record = None
            if record is None:
                details = self._details(
                    observation.state,
                    alert_id,
                    "rule",
                    f"{observation.departed} → {observation.arrived}",
                    value=observation.arrived,
                    condition_key="rule.transition",
                    condition_params={
                        "from_value": observation.departed,
                        "to_value": observation.arrived,
                    },
                    rule_id=rule.id,
                    rule_name=rule.name,
                    labels=rule.label_ids,
                    message=self._render_rule_message(
                        rule, observation.state, observation.arrived
                    ),
                    source=rule.source,
                    attribute=rule.attribute,
                )
                record = AlertRecord.pending(
                    details, rule.duration, observation.observed_at
                )
                record.visible_at = observation.observed_at + timedelta(
                    seconds=min(self.config["pending_display_delay"], rule.duration)
                )
                self._set_record(record)
                if new_occurrences is not None and self._is_automatic_eligible(
                    entity_id
                ):
                    new_occurrences.append(
                        PackOccurrence(source=details, occurred_at=now)
                    )
                if emit_events and rule.duration:
                    self._count_pending_transition(record, None)
                changed = True
            if now.astimezone(UTC) >= observation.due_at.astimezone(UTC):
                became_active = advance_record(record, now)
                record.expires_at = now + timedelta(seconds=rule.auto_resolve)
                record.details.condition_params = {
                    "from_value": observation.departed,
                    "to_value": observation.arrived,
                    "last_occurrence": observation.observed_at.isoformat(),
                }
                if self._transition_observations.get(alert_id) is observation:
                    self._transition_observations.pop(alert_id, None)
                if became_active and emit_events:
                    self._fire_started(record)
                changed = True
            self._schedule_timer(record)
        return changed
