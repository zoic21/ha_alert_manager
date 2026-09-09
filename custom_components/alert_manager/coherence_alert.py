"""Translate completed coherence reports into one ordinary alert candidate."""

from __future__ import annotations

from typing import Any

from .models import AlertDetails

COHERENCE_ALERT_ID = "coherence:configuration"
COHERENCE_ENTITY_ID = "sensor.alert_manager_coherence_issue"


def prepare_alert_report(
    result: dict[str, Any], previous: dict[str, Any] | None, scan_esphome: bool
) -> None:
    """Record recovery coverage in the executor, without retaining old findings.

    A skipped category must remain required across successive partial reports.
    File errors conservatively block recovery until a complete scan succeeds.
    """
    previous = previous or {}
    old_findings = previous.get("results", [])
    required = set(previous.get("alert_required_checks", []))
    required.update(item.get("reference_type", "entity_id") for item in old_findings)
    required.discard("entity_id")
    checks = result.get("checks", {})
    unchecked = {key for key in required if checks.get(key) != "executed"}
    needs_esphome = previous.get("alert_requires_esphome", False) or any(
        str(item.get("file", "")).casefold().startswith("esphome/")
        for item in old_findings
    )
    # Unknown coverage from an earlier failed file must not be hidden by later
    # turning off ESPHome traversal.
    needs_esphome |= bool(previous.get("files_skipped"))
    complete = not (
        result.get("files_skipped", 0)
        or unchecked
        or (needs_esphome and not scan_esphome)
        or any(status in {"not_loaded", "metadata_error"} for status in checks.values())
    )
    result["alert_complete"] = complete
    result["alert_required_checks"] = sorted(unchecked)
    result["alert_requires_esphome"] = bool(needs_esphome and not scan_esphome)


def report_observation(report: Any) -> tuple[int, bool] | None:
    """Return findings and recovery authority, rejecting malformed/legacy reports."""
    if not isinstance(report, dict) or not isinstance(report.get("scanned_at"), str):
        return None
    findings = report.get("results")
    if not isinstance(findings, list):
        return None
    # Older reports can confirm findings, but lack explicit recovery coverage.
    return len(findings), report.get("alert_complete") is True


def alert_details(count: int, message: str, name: str) -> AlertDetails:
    """Use a distinct source and the existing coherence sensor as its target."""
    return AlertDetails(
        id=COHERENCE_ALERT_ID,
        type="coherence",
        entity_id=COHERENCE_ENTITY_ID,
        name=name,
        rule_name=name,
        value=count,
        condition=message,
        condition_key="coherence.issues",
        condition_params={"count": count},
        message=message,
        source="coherence",
        integration="alert_manager",
    )
