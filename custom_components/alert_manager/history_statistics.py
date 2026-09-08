"""On-demand recurrence summaries of retained, completed alert occurrences."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .models import AlertHistoryEntry


def aggregate_history(
    entries: tuple[AlertHistoryEntry, ...], days: int, now: datetime
) -> dict[str, Any]:
    """Sum active overlap with the period, including acknowledged time.

    Only completed occurrences are available in history. Durations are sums per
    occurrence, not device downtime: simultaneous alerts can overlap.
    """
    if days not in (7, 30):
        raise ValueError("Unsupported history statistics period")
    start = now - timedelta(days=days)
    groups: dict[str, dict[str, dict[str, Any]]] = {
        key: {} for key in ("alert", "entity", "device", "integration", "rule")
    }
    count = 0
    total = 0.0
    for entry in entries:
        # Half-open period; retain instantaneous occurrences within the period.
        if entry.resolved_at < start or entry.active_at >= now:
            continue
        duration = max(
            0.0,
            (min(entry.resolved_at, now) - max(entry.active_at, start)).total_seconds(),
        )
        if entry.resolved_at == start and entry.active_at < start:
            continue
        count += 1
        total += duration
        identities = {
            "alert": (entry.id, entry.entity_name, entry.rule_name),
            "entity": (entry.entity_id, entry.entity_name, None),
            "device": (entry.device_id or "", entry.device_name, None),
            "integration": (entry.integration or "", entry.integration, None),
            "rule": (entry.rule_id, entry.rule_name, None),
        }
        for kind, (key, name, rule_name) in identities.items():
            row = groups[kind].setdefault(
                key,
                {
                    "id": key,
                    "name": name,
                    "rule_name": rule_name,
                    "type": entry.type,
                    "occurrences": 0,
                    "total_duration_seconds": 0.0,
                },
            )
            row["occurrences"] += 1
            row["total_duration_seconds"] += duration
    result = {}
    for kind, rows in groups.items():
        for row in rows.values():
            row["average_duration_seconds"] = (
                row["total_duration_seconds"] / row["occurrences"]
            )
        result[kind] = sorted(
            rows.values(),
            key=lambda row: (
                -row["occurrences"],
                -row["total_duration_seconds"],
                row["id"],
            ),
        )
    return {
        "days": days,
        "from": start.isoformat(),
        "to": now.isoformat(),
        "occurrences": count,
        "total_duration_seconds": total,
        "groups": result,
    }
