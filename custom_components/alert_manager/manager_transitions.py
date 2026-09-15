"""Indexed edge observations and hold confirmation for custom transition rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.core import State, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .const import TRANSITION_SOURCES
from .models import AlertRecord, AlertStatus, Rule, advance_record, normalize_scalar
from .packs.base import PackOccurrence
from .rule_evaluation import transition_value
from .runtime_phase import RuntimePhase
from .sequences import SequenceProgress, sequence_comparison, sequence_final_step


@dataclass(frozen=True, slots=True)
class TransitionObservation:
    """One unpersisted edge; unrelated updates never move its hold deadline."""

    rule: Rule
    state: State
    departed: Any
    arrived: Any
    observed_at: datetime
    due_at: datetime
    evidence: list[dict[str, Any]] | None = None


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
            if rule.source == "value_sequence":
                if old is None:
                    continue
                self._observe_sequence(rule, entity_id, new, now, previous=old)
                continue
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

    def _clear_sequences(self) -> None:
        for _token, cancel, _due in self._sequence_timers.values():
            cancel()
        self._sequence_timers.clear()
        self._sequence_progress.clear()

    def _drop_sequence(self, alert_id: str) -> None:
        timer = self._sequence_timers.pop(alert_id, None)
        if timer is not None:
            timer[1]()
        self._sequence_progress.pop(alert_id, None)

    def _observe_sequence(
        self,
        rule: Rule,
        entity_id: str,
        state: State | None,
        now: datetime,
        *,
        previous: State | None = None,
    ) -> None:
        alert_id = f"rule:{rule.id}:{entity_id}"
        progress = self._sequence_progress.get(alert_id)
        if progress is None or progress.rule != rule:
            progress = SequenceProgress(rule)
            self._sequence_progress[alert_id] = progress
        progress.observed_state = state
        evidence = progress.observe(state, now, previous=previous)
        if evidence is not None and state is not None:
            self._transition_confirmed[alert_id] = TransitionObservation(
                rule, state, None, transition_value(rule, state), now, now, evidence
            )
        self._schedule_sequence(alert_id, entity_id, progress)

    def _schedule_sequence(
        self, alert_id: str, entity_id: str, progress: SequenceProgress
    ) -> None:
        due = progress.deadline()
        timer = self._sequence_timers.get(alert_id)
        if timer is not None and timer[2] == due:
            return
        if timer is not None:
            self._sequence_timers.pop(alert_id)
            timer[1]()
        if due is None:
            return
        token = object()

        @callback
        def reached(_now: datetime) -> None:
            current = self._sequence_timers.get(alert_id)
            if current is None or current[0] is not token:
                return
            self._sequence_timers.pop(alert_id, None)
            if (
                not self.monitoring_enabled
                or self._runtime_phase is not RuntimePhase.RUNNING
                or not self._is_base_eligible(entity_id)
                or self._transition_rules_by_id.get(progress.rule.id) != progress.rule
            ):
                self._drop_sequence(alert_id)
                return
            state = self.hass.states.get(entity_id)
            observed = progress.observed_state
            now = dt_util.now()
            expired = (
                progress.started_at is not None
                and progress.rule.sequence_timeout
                and now
                >= progress.started_at
                + timedelta(seconds=progress.rule.sequence_timeout)
            )
            if (
                not expired
                and state is not observed
                and (
                    state is None
                    or observed is None
                    or state.last_updated != observed.last_updated
                    or state.state != observed.state
                    or state.attributes != observed.attributes
                )
            ):
                # StateMachine already changed, but its event callback is queued.
                # Let that edge prove/interrupt the hold before touching progress.
                return
            self._observe_sequence(progress.rule, entity_id, state, now)
            self._queue_entity_evaluations((entity_id,), collect_occurrences=True)

        cancel = async_track_point_in_utc_time(self.hass, reached, due.astimezone(UTC))
        self._sequence_timers[alert_id] = (token, cancel, due)

    def _prune_transition_observations(self) -> None:
        self._transition_rules_by_id = {
            rule.id: rule
            for rule in self._rules
            if rule.enabled and rule.source in TRANSITION_SOURCES
        }
        for alert_id, progress in tuple(self._sequence_progress.items()):
            entity_id = alert_id.rsplit(":", 1)[1]
            if (
                self._transition_rules_by_id.get(progress.rule.id) != progress.rule
                or entity_id not in progress.rule.entity_ids
            ):
                self._drop_sequence(alert_id)
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
        if rule is not None and record.status is AlertStatus.ACTIVE:
            state = self.hass.states.get(record.details.entity_id)
            if rule.resolve_mode == "condition":
                if sequence_comparison(rule, rule.resolve_condition, state) is True:
                    return False
            elif rule.resolve_mode == "state":
                if rule.source == "value_sequence":
                    final_step = sequence_final_step(rule)
                    if (
                        final_step is None
                        or sequence_comparison(rule, final_step, state) is False
                    ):
                        return False
                else:
                    value = transition_value(rule, state)
                    if value is not None and normalize_scalar(
                        value
                    ) != normalize_scalar(rule.to_value):
                        return False
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
                self._drop_sequence(alert_id)
                self._transition_confirmed.pop(alert_id, None)
                self._transition_observations.pop(alert_id, None)
                continue
            record = self.records.get(alert_id)
            if record is not None and record.status is AlertStatus.ACTIVE:
                # Apply mode edits to the existing episode and cancel stale deadlines.
                if rule.resolve_mode != "duration" and record.expires_at is not None:
                    record.expires_at = None
                    self._schedule_timer(record)
                    changed = True
                elif rule.resolve_mode == "duration" and record.expires_at is None:
                    record.expires_at = now + timedelta(seconds=rule.auto_resolve)
                    self._schedule_timer(record)
                    changed = True
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
            repeated_sequence = observation.evidence is not None and record is not None
            if record is None:
                details = self._details(
                    observation.state,
                    alert_id,
                    "rule",
                    self._localized_pack_condition(
                        "rule.sequence", {"count": len(observation.evidence)}
                    )
                    if observation.evidence is not None
                    else f"{observation.departed} → {observation.arrived}",
                    value=observation.arrived,
                    condition_key="rule.sequence"
                    if observation.evidence
                    else "rule.transition",
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
                record.expires_at = (
                    now + timedelta(seconds=rule.auto_resolve)
                    if rule.resolve_mode == "duration"
                    else None
                )
                record.details.condition_params = {
                    "from_value": observation.departed,
                    "to_value": observation.arrived,
                    "last_occurrence": observation.observed_at.isoformat(),
                }
                if observation.evidence is not None:
                    record.details.condition_params = {
                        "count": len(observation.evidence),
                        "steps": rule.steps,
                        "evidence": observation.evidence,
                        "last_occurrence": observation.observed_at.isoformat(),
                    }
                if (
                    repeated_sequence
                    and new_occurrences is not None
                    and self._is_automatic_eligible(entity_id)
                ):
                    new_occurrences.append(
                        PackOccurrence(source=record.details, occurred_at=now)
                    )
                if self._transition_observations.get(alert_id) is observation:
                    self._transition_observations.pop(alert_id, None)
                if became_active and emit_events:
                    self._fire_started(record)
                changed = True
            self._schedule_timer(record)
        return changed
