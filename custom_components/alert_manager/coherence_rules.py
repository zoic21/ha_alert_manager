"""Immutable custom-rule inputs for the on-demand coherence scanner."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

import yaml
from yaml.nodes import Node

from .models import Rule


@dataclass(frozen=True, slots=True)
class RuleSnapshot:
    """Only reference-bearing fields; safe to read in the scan executor."""

    id: str
    name: str
    entity_ids: tuple[str, ...]
    condition_template: str | None
    message: str | None


def snapshot_rules(rules: Iterable[Rule]) -> tuple[RuleSnapshot, ...]:
    """Copy bounded rule inputs on the event loop, without serialization."""
    return tuple(
        RuleSnapshot(
            rule.id,
            rule.name,
            tuple(rule.entity_ids) if rule.source != "jinja" else (),
            rule.condition_template,
            rule.message,
        )
        for rule in rules
    )


def reference_nodes(rule: RuleSnapshot) -> Iterator[tuple[str, Node]]:
    """Build marked nodes in the executor for the shared reference scanner.

    Paths identify rule fields, not storage files. Plain notification text and
    comparison values are not entity references. Never evaluate user templates.
    """
    fields = {"entity_ids": list(rule.entity_ids)}
    fields.update(
        (field, value)
        for field, value in (
            ("condition_template", rule.condition_template),
            ("message", rule.message),
        )
        if value and ("{{" in value or "{%" in value)
    )
    for field, value in fields.items():
        node = yaml.compose(yaml.safe_dump(value, allow_unicode=True))
        if node is not None:
            yield field, node
