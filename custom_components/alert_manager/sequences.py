"""Transient, linear sequence progress; no I/O, timers or alert lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import State

from .models import Rule
from .rule_evaluation import evaluate_rule, transition_value


def sequence_comparison(
    rule: Rule, step: dict[str, Any], state: State | None
) -> bool | None:
    """Unknown observations never become a negative comparison or a valid exit."""
    if transition_value(rule, state) is None:
        return None
    comparison = replace(
        rule,
        source="value",
        operator=step["operator"],
        value=step["value"],
        condition_template=None,
    )
    return evaluate_rule(
        comparison, state, evaluate_condition=lambda _: (None, None)
    ).result


@dataclass(slots=True)
class SequenceProgress:
    """One progression per rule/entity, bounded by the configured step count."""

    rule: Rule
    observed_state: State | None = field(default=None, repr=False)
    index: int = 0
    started_at: datetime | None = None
    hold_since: datetime | None = None
    started_value: Any = None
    completed: list[dict[str, Any]] = field(default_factory=list)
    waiting_for_exit: bool = False
    reason: str = "waiting"

    def copy(self) -> SequenceProgress:
        """Copy mutable timing evidence without copying immutable HA State objects."""
        return replace(self, completed=[dict(item) for item in self.completed])

    def reset(self, reason: str = "waiting") -> None:
        self.index = 0
        self.started_at = None
        self.hold_since = None
        self.started_value = None
        self.completed = []
        self.reason = reason

    def deadline(self) -> datetime | None:
        """Only a live minimum hold or the whole-sequence limit needs a timer."""
        deadlines = []
        if self.started_at is not None and self.rule.sequence_timeout:
            deadlines.append(
                self.started_at + timedelta(seconds=self.rule.sequence_timeout)
            )
        step = self.rule.steps[self.index]
        if (
            self.hold_since is not None
            and step.get("duration_mode", "at_least") == "at_least"
        ):
            deadlines.append(
                self.hold_since + timedelta(seconds=step.get("duration", 0))
            )
        return min(deadlines) if deadlines else None

    def observe(
        self, state: State | None, now: datetime, *, previous: State | None = None
    ) -> list[dict[str, Any]] | None:
        """Consume one observation; never backdate the next step's hold."""
        if (
            self.started_at is not None
            and self.rule.sequence_timeout
            and now >= self.started_at + timedelta(seconds=self.rule.sequence_timeout)
        ):
            self.reset("expired")
            # The deadline discards progress; a later real observation may rearm.
            return None
        if self.waiting_for_exit:
            if sequence_comparison(self.rule, self.rule.steps[-1], state) is not False:
                return None
            self.waiting_for_exit = False
        step = self.rule.steps[self.index]
        mode = step.get("duration_mode", "at_least")
        if sequence_comparison(self.rule, step, state) is None:
            self.hold_since = None
            self.reason = "invalid"
            return None
        # An outgoing event at the deadline still proves the old continuous hold.
        if (
            self.hold_since is not None
            and mode == "at_least"
            and now >= self.hold_since + timedelta(seconds=step.get("duration", 0))
            and previous is not None
            and sequence_comparison(self.rule, step, previous) is True
        ):
            evidence = self._complete(now, state)
            if evidence is not None:
                return evidence
            step = self.rule.steps[self.index]
            mode = step.get("duration_mode", "at_least")
        matches = sequence_comparison(self.rule, step, state)
        if matches is None:
            self.hold_since = None
            self.reason = "invalid"
            return None
        if matches:
            if self.hold_since is None:
                self.hold_since = now
                self.started_value = transition_value(self.rule, state)
                if self.started_at is None:
                    self.started_at = now
            self.reason = "holding" if mode == "at_least" else "awaiting_exit"
            if mode == "at_least" and now >= self.hold_since + timedelta(
                seconds=step.get("duration", 0)
            ):
                evidence = self._complete(now, state)
                if evidence is not None:
                    return evidence
                return self.observe(state, now)
            return None
        if self.hold_since is not None:
            elapsed = (now - self.hold_since).total_seconds()
            if (mode == "less_than" and elapsed < step["duration"]) or (
                mode == "between"
                and step.get("duration", 0) <= elapsed <= step["duration_max"]
            ):
                evidence = self._complete(now, state)
                if evidence is not None:
                    return evidence
                # The exit observation may start the next step, from now only.
                return self.observe(state, now)
            self.hold_since = None
            self.reason = "interrupted"
        return None

    def _complete(self, now: datetime, state: State) -> list[dict[str, Any]] | None:
        self.completed.append(
            {
                "step": self.index + 1,
                "started_at": self.hold_since.isoformat(),
                "completed_at": now.isoformat(),
                "seconds": (now - self.hold_since).total_seconds(),
                "started_value": self.started_value,
                "completed_value": transition_value(self.rule, state),
            }
        )
        self.hold_since = None
        self.index += 1
        self.reason = "waiting"
        if self.index < len(self.rule.steps):
            return None
        evidence = self.completed
        self.reset("completed")
        self.waiting_for_exit = True
        return evidence

    def snapshot(self, state: State | None, now: datetime) -> dict[str, Any]:
        """Read-only diagnostics, including comparison versus proven progress."""
        due = self.deadline()
        return {
            "step": self.index + 1,
            "total": len(self.rule.steps),
            "matching": sequence_comparison(
                self.rule, self.rule.steps[self.index], state
            ),
            "elapsed": max(0, (now - self.hold_since).total_seconds())
            if self.hold_since
            else 0,
            "remaining": max(0, (due - now).total_seconds()) if due else None,
            "reason": self.reason,
            "completed": [dict(item) for item in self.completed],
        }
