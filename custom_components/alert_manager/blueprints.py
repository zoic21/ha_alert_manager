"""Built-in rule recipes and pure, on-demand entity discovery (no runtime)."""

from __future__ import annotations

from copy import deepcopy
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

import yaml

from .const import MAX_RULE_ENTITY_IDS
from .models import Rule, normalize_scalar, safe_float
from .validation import validate_rule_payload

BLUEPRINT_DIRECTORY = Path(__file__).parent / "blueprint"
_FIELDS = {
    "integration",
    "domain",
    "entity_id",
    "unique_id",
    "original_name",
    "translation_key",
    "device_class",
    "unit_of_measurement",
}


def validate_discovery(expression: Any, depth: int = 0) -> None:
    """Validate a small bounded predicate tree; fail closed on unknown syntax."""
    if depth > 8 or not isinstance(expression, dict) or not expression:
        raise ValueError("Invalid blueprint discovery")
    if len(expression) == 1 and (kind := next(iter(expression))) in {
        "all",
        "any",
        "not",
    }:
        children = [expression[kind]] if kind == "not" else expression[kind]
        if not isinstance(children, list) or not 1 <= len(children) <= 32:
            raise ValueError("Invalid blueprint discovery composition")
        for child in children:
            validate_discovery(child, depth + 1)
        return
    field = expression.get("field")
    operators = set(expression) - {"field"}
    if (
        not isinstance(field, str)
        or not (
            field in _FIELDS or (field.startswith("attributes.") and len(field) > 11)
        )
        or len(operators) != 1
    ):
        raise ValueError("Invalid blueprint discovery field")
    operator = operators.pop()
    value = expression[operator]
    if operator == "exists" and isinstance(value, bool):
        return
    if operator == "equals" and isinstance(value, (str, int, float, bool)):
        return
    if operator == "glob" and isinstance(value, str) and 0 < len(value) <= 255:
        return
    if (
        operator == "in"
        and isinstance(value, list)
        and 1 <= len(value) <= 32
        and all(isinstance(item, (str, int, float, bool)) for item in value)
    ):
        return
    raise ValueError("Invalid blueprint discovery operator")


def explain_match(expression: dict[str, Any], entity: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a validated predicate with structured reasons for every criterion."""
    kind = next(iter(expression))
    if kind in {"all", "any", "not"}:
        children = [expression[kind]] if kind == "not" else expression[kind]
        reasons = [explain_match(child, entity) for child in children]
        matches = [reason["matched"] for reason in reasons]
        matched = (
            not matches[0]
            if kind == "not"
            else (all(matches) if kind == "all" else any(matches))
        )
        return {"operator": kind, "matched": matched, "criteria": reasons}
    field = expression["field"]
    operator = next(key for key in expression if key != "field")
    expected = expression[operator]
    actual = entity.get(field)
    if operator == "exists":
        matched = (actual is not None) == expected
    elif operator == "glob":
        matched = isinstance(actual, str) and fnmatchcase(actual, expected)
    elif operator == "in":
        matched = actual in expected
    else:
        matched = actual == expected
    return {
        "field": field,
        "operator": operator,
        "expected": expected,
        "matched": matched,
    }


def load_blueprints(directory: Path = BLUEPRINT_DIRECTORY) -> list[dict[str, Any]]:
    """Read trusted bundled files in an executor, isolating malformed recipes."""
    catalog = []
    seen: set[str] = set()
    for path in sorted(directory.rglob("*.yaml")):
        data: dict[str, Any] = {"blueprint_id": path.stem, "category": "other"}
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("Blueprint must be an object")
            data = raw
            for field in ("blueprint_id", "category", "name_key", "description_key"):
                if not isinstance(data.get(field), str) or not data[field].strip():
                    raise ValueError(f"Missing blueprint {field}")
            if (
                type(data.get("schema_version")) is not int
                or data["schema_version"] != 1
            ):
                raise ValueError("Unsupported blueprint schema version")
            if (
                type(data.get("blueprint_version")) is not int
                or data["blueprint_version"] < 1
            ):
                raise ValueError("Invalid blueprint version")
            requirements = data.get("requirements", {})
            if not isinstance(requirements, dict) or set(requirements) - {
                "integrations",
                "entity_domains",
            }:
                raise ValueError("Invalid blueprint requirements")
            for values in requirements.values():
                if not isinstance(values, list) or not all(
                    isinstance(v, str) and v for v in values
                ):
                    raise ValueError("Invalid blueprint requirements")
            if not isinstance(data.get("deprecated", False), bool):
                raise ValueError("Invalid blueprint lifecycle")
            if "replaced_by" in data and not isinstance(data["replaced_by"], str):
                raise ValueError("Invalid blueprint replacement")
            validate_discovery(data.get("discovery"))
            validate_rule_payload(
                {**data["rule"], "entity_ids": ["sensor.blueprint_validation"]}
            )
            if data["blueprint_id"] in seen:
                for existing in catalog:
                    if existing["blueprint_id"] == data["blueprint_id"]:
                        existing["error"] = "Duplicate blueprint identifier"
                raise ValueError("Duplicate blueprint identifier")
        except (ValueError, TypeError, KeyError, OSError, yaml.YAMLError) as err:
            data = {
                "blueprint_id": str(data.get("blueprint_id", path.stem)),
                "category": str(data.get("category", "other")),
                "name_key": str(data.get("name_key", "generator.invalid")),
                "description_key": str(
                    data.get("description_key", "generator.invalid")
                ),
                "error": str(err),
            }
        seen.add(data["blueprint_id"])
        catalog.append(data)
    return catalog


def discovery_attributes(catalog: list[dict[str, Any]]) -> set[str]:
    """Collect only attributes referenced by validated discovery predicates."""
    attributes = set()
    pending = [item["discovery"] for item in catalog if "error" not in item]
    while pending:
        expression = pending.pop()
        field = expression.get("field", "")
        if field.startswith("attributes."):
            attributes.add(field.removeprefix("attributes."))
        for kind in ("all", "any"):
            pending.extend(expression.get(kind, []))
        if "not" in expression:
            pending.append(expression["not"])
    return attributes


def snapshot_installation(
    hass: Any, registry: Any, attributes: set[str]
) -> dict[str, Any]:
    """Copy HA metadata on the event loop; state values never determine membership."""
    entries = {entry.entry_id: entry for entry in hass.config_entries.async_entries()}
    integrations = {
        entry.domain
        for entry in entries.values()
        if not entry.disabled_by and entry.source != "ignore"
    }
    states = {state.entity_id: state for state in hass.states.async_all()}
    entities = []
    for entity_id in set(registry.entities) | set(states):
        entry = registry.async_get(entity_id)
        config_entry = entries.get(getattr(entry, "config_entry_id", None))
        if getattr(entry, "disabled_by", None) or getattr(
            config_entry, "disabled_by", None
        ):
            continue
        attrs = states[entity_id].attributes if entity_id in states else {}
        entity = {
            "entity_id": entity_id,
            "domain": entity_id.partition(".")[0],
            "integration": getattr(entry, "platform", None),
            **{
                field: getattr(entry, field, None)
                for field in (
                    "unique_id",
                    "original_name",
                    "translation_key",
                )
            },
            "device_class": getattr(entry, "device_class", None)
            or getattr(entry, "original_device_class", None)
            or attrs.get("device_class"),
            "unit_of_measurement": getattr(entry, "unit_of_measurement", None)
            or attrs.get("unit_of_measurement"),
            **{
                f"attributes.{key}": deepcopy(attrs[key])
                for key in attributes
                if key in attrs
            },
        }
        if config_entry:
            entity["integration"] = config_entry.domain
        # YAML integrations may have registry entities without config entries.
        if entity["integration"]:
            integrations.add(entity["integration"])
        entities.append(entity)
    return {"integrations": integrations, "entities": entities}


def discover_blueprint(
    blueprint: dict[str, Any], installation: dict[str, Any]
) -> dict[str, Any]:
    """Return deterministic membership and an explicit installation-level status."""
    result = {"entity_ids": [], "status": "available"}
    if "error" in blueprint:
        return {**result, "status": "invalid", "reason": blueprint["error"]}
    if blueprint.get("deprecated"):
        return {
            **result,
            "status": "deprecated",
            "replaced_by": blueprint.get("replaced_by"),
        }
    requirements = blueprint.get("requirements", {})
    missing = sorted(
        set(requirements.get("integrations", [])) - installation["integrations"]
    )
    if missing:
        return {**result, "status": "missing_integration", "missing": missing}
    domains = {entity["domain"] for entity in installation["entities"]}
    missing = sorted(set(requirements.get("entity_domains", [])) - domains)
    if missing:
        return {**result, "status": "missing_domain", "missing": missing}
    entity_ids = sorted(
        {
            entity["entity_id"]
            for entity in installation["entities"]
            if explain_match(blueprint["discovery"], entity)["matched"]
        }
    )
    status = "available" if entity_ids else "no_entities"
    if len(entity_ids) > MAX_RULE_ENTITY_IDS:
        status = "too_many_entities"
    return {"entity_ids": entity_ids, "status": status}


def prepare_blueprints(
    catalog: list[dict[str, Any]],
    installation: dict[str, Any],
    rules: list[dict[str, Any]],
    translations: dict[str, str],
) -> list[dict[str, Any]]:
    """Build validated normal-rule candidates and UI summaries from one snapshot."""
    rows = []
    signatures = [rule_signature(Rule.from_dict(rule)) for rule in rules]
    generated: dict[str, list[str]] = {}
    for rule in rules:
        if blueprint_id := rule.get("blueprint", {}).get("id"):
            generated.setdefault(blueprint_id, []).append(rule["id"])
    for blueprint in catalog:
        row = {
            key: blueprint.get(key)
            for key in (
                "blueprint_id",
                "category",
                "name_key",
                "description_key",
            )
        }
        row.update(discover_blueprint(blueprint, installation))
        row["entity_count"] = len(row["entity_ids"])
        existing_ids = generated.get(blueprint["blueprint_id"], [])
        row["existing_rule_ids"] = existing_ids
        if row["status"] == "available":
            payload = deepcopy(blueprint["rule"])
            payload["name"] = translations.get(
                f"component.alert_manager.config_panel.{blueprint['name_key']}",
                payload["name"],
            )
            payload["entity_ids"] = row["entity_ids"]
            payload["blueprint"] = {
                "id": blueprint["blueprint_id"],
                "version": blueprint["blueprint_version"],
                "managed": False,
            }
            try:
                candidate = validate_rule_payload(payload)
                row["rule"] = candidate.as_dict()
                # Same effective configuration, regardless of display name/provenance.
                signature = rule_signature(candidate)
                if len(existing_ids) > 1:
                    row["status"] = "multiple_generated"
                elif existing_ids:
                    row["status"] = "already_generated"
                elif signature in signatures:
                    row["status"] = "matching_rule"
            except ValueError as err:
                row.update(status="invalid", reason=str(err))
        rows.append(row)
    return sorted(
        rows,
        key=lambda row: (
            row["status"] not in {"available", "already_generated"},
            row["category"],
            row["blueprint_id"],
        ),
    )


def rule_signature(rule: Rule) -> dict[str, Any]:
    """Compare effective rule configuration without identity or presentation."""
    data = rule.as_dict()
    for key in (
        "id",
        "name",
        "blueprint",
        "version",
        "message",
        "label_ids",
        "enabled",
    ):
        data.pop(key, None)
    data["entity_ids"] = sorted(data["entity_ids"])
    if "value" in data:
        values = rule.value if isinstance(rule.value, list) else [rule.value]
        if rule.operator in ("above", "below", "between", "outside"):
            data["value"] = [safe_float(value) for value in values]
        else:
            data["value"] = sorted({normalize_scalar(value) for value in values})
    return data
