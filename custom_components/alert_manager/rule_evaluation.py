"""Shared, side-effect-free custom-rule value evaluation."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from homeassistant.core import State

from .const import ATTRIBUTE_SOURCES, VARIATION_SOURCES
from .models import Rule, extract_attribute_value, safe_float

type ConditionEvaluator = Callable[[Rule, State, Any], tuple[bool | None, str | None]]
type BaselineResolver = Callable[[Rule, State, float], float | None]
type VariationGateCallback = Callable[[Rule, str], None]


@dataclass(slots=True)
class RuleEvaluation:
    """Diagnostic result produced by the same evaluator as the runtime."""

    raw_value: Any = None
    value: Any = None
    comparison_result: bool | None = None
    jinja_result: bool | None = None
    result: bool | None = None
    baseline: float | None = None
    error_code: str | None = None
    error_detail: str | None = None


def rule_current_value(rule: Rule, state: State) -> tuple[bool, Any]:
    """Read the configured state or attribute source."""
    if rule.source in ATTRIBUTE_SOURCES:
        return extract_attribute_value(state.attributes, rule.attribute or "")
    return True, state.state


def evaluate_rule(
    rule: Rule,
    state: State,
    *,
    evaluate_condition: ConditionEvaluator,
    resolve_baseline: BaselineResolver,
    on_variation_gate_false: VariationGateCallback | None = None,
    evaluate_all_conditions: bool = False,
) -> RuleEvaluation:
    """Evaluate one rule/entity pair without owning any runtime state."""
    found, raw_value = rule_current_value(rule, state)
    evaluation = RuleEvaluation(raw_value=raw_value, value=raw_value)
    if not found:
        evaluation.error_code = "attribute_not_found"
        return evaluation

    if rule.source in VARIATION_SOURCES:
        numeric_current = safe_float(raw_value)
        if numeric_current is None:
            evaluation.error_code = "numeric_source_required"
            return evaluation
        evaluation.raw_value = numeric_current
        evaluation.value = numeric_current
        jinja_result, error = evaluate_condition(rule, state, numeric_current)
        evaluation.jinja_result = jinja_result
        if error is not None:
            evaluation.error_code = "condition_template_error"
            evaluation.error_detail = error
            return evaluation
        if jinja_result is not True:
            if on_variation_gate_false is not None:
                on_variation_gate_false(rule, state.entity_id)
            evaluation.result = False
            return evaluation
        baseline = resolve_baseline(rule, state, numeric_current)
        evaluation.baseline = baseline
        if baseline is None:
            evaluation.value = None
            evaluation.error_code = "baseline_unavailable"
            return evaluation
        variation = numeric_current - baseline
        evaluation.value = 0.0 if variation == 0 else variation
        evaluation.comparison_result = rule.matches(evaluation.value)
        evaluation.result = evaluation.comparison_result
        return evaluation

    if rule.source not in ("jinja", "unchanged") and rule.operator != "unchanged":
        if rule.operator in ("above", "below", "between", "outside"):
            current_values = (
                list(raw_value)
                if isinstance(raw_value, Sequence)
                and not isinstance(raw_value, str | bytes)
                else [raw_value]
            )
            if not any(safe_float(value) is not None for value in current_values):
                evaluation.error_code = "numeric_source_required"
                return evaluation
        evaluation.comparison_result = rule.matches(raw_value)
        if not evaluate_all_conditions and evaluation.comparison_result is False:
            evaluation.result = False
            return evaluation

    jinja_result, error = evaluate_condition(rule, state, raw_value)
    evaluation.jinja_result = jinja_result
    if error is not None:
        evaluation.error_code = "condition_template_error"
        evaluation.error_detail = error
        return evaluation

    comparison_matches = evaluation.comparison_result is not False
    jinja_matches = evaluation.jinja_result is not False
    evaluation.result = comparison_matches and jinja_matches
    return evaluation
