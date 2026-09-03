"""Occurrence-driven automatic pack detecting repeated transient anomalies."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, State
from homeassistant.util.hass_dict import HassKey

from .base import (
    AutomaticPack,
    PackConfigField,
    PackGeneratedAlert,
    PackOccurrence,
    PackOccurrenceResult,
)

PACK_ID = "flapping"
DEFAULT_OCCURRENCES = 5
DEFAULT_WINDOW = 3600
DEFAULT_RECOVERY = 1800
MAX_SOURCES = 4096
_CLEANUP_INTERVAL = timedelta(hours=1)
_LAST_CLEANUP: HassKey[datetime] = HassKey("alert_manager_flapping_last_cleanup")


def _never_applies(_hass: HomeAssistant, _state: State) -> bool:
    """Keep the pack off the state-evaluation path; it consumes occurrences only."""
    return False


def _never_matches(
    _hass: HomeAssistant, _state: State, _config: dict[str, Any]
) -> None:
    """Return no state-based match for this occurrence-driven pack."""


def _settings(
    occurrence: PackOccurrence, config: dict[str, Any]
) -> tuple[int, int, int]:
    """Resolve global settings with an optional device-specific override."""
    values = {
        "occurrences": int(config.get("occurrences", DEFAULT_OCCURRENCES)),
        "window": int(config.get("window", DEFAULT_WINDOW)),
        "recovery": int(config.get("recovery", DEFAULT_RECOVERY)),
    }
    device_id = occurrence.source.device_id
    overrides = config.get("device_overrides", {})
    override = (
        overrides.get(device_id) if device_id and isinstance(overrides, dict) else None
    )
    if isinstance(override, dict):
        for key in values:
            if key in override:
                values[key] = int(override[key])
    return values["occurrences"], values["window"], values["recovery"]


def _parse_timestamps(raw: Any) -> list[datetime]:
    """Load valid aware timestamps from one small source bucket."""
    if not isinstance(raw, list):
        return []
    result: list[datetime] = []
    for value in raw:
        if not isinstance(value, str):
            continue
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            continue
        if parsed.tzinfo is not None:
            result.append(parsed.astimezone(UTC))
    return sorted(result)


def _compact_duration(seconds: int) -> str:
    """Return a short language-neutral duration for backend event payloads."""
    if seconds % 3600 == 0:
        return f"{seconds // 3600} h"
    if seconds % 60 == 0:
        return f"{seconds // 60} min"
    return f"{seconds} s"


def _largest_limits(config: dict[str, Any]) -> tuple[int, int]:
    """Return conservative retention limits across global and device settings."""
    max_count = int(config.get("occurrences", DEFAULT_OCCURRENCES))
    max_window = int(config.get("window", DEFAULT_WINDOW))
    overrides = config.get("device_overrides", {})
    if isinstance(overrides, dict):
        for override in overrides.values():
            if not isinstance(override, dict):
                continue
            max_count = max(max_count, int(override.get("occurrences", max_count)))
            max_window = max(max_window, int(override.get("window", max_window)))
    return max_count, max_window


def _cleanup(
    hass: HomeAssistant,
    data: dict[str, Any],
    config: dict[str, Any],
    now: datetime,
) -> None:
    """Periodically discard obsolete buckets and enforce a hard source bound."""
    previous = hass.data.get(_LAST_CLEANUP)
    sources = data.setdefault("sources", {})
    if not isinstance(sources, dict):
        sources = data["sources"] = {}
    if isinstance(previous, datetime) and now - previous < _CLEANUP_INTERVAL:
        return
    hass.data[_LAST_CLEANUP] = now
    max_count, max_window = _largest_limits(config)
    cutoff = now.astimezone(UTC) - timedelta(seconds=max_window)
    newest: dict[str, datetime] = {}
    for source_id, raw_timestamps in tuple(sources.items()):
        if not isinstance(source_id, str) or not source_id:
            sources.pop(source_id, None)
            continue
        timestamps = [
            item for item in _parse_timestamps(raw_timestamps) if item >= cutoff
        ]
        timestamps = timestamps[-max_count:]
        if not timestamps:
            sources.pop(source_id, None)
            continue
        sources[source_id] = [item.isoformat() for item in timestamps]
        newest[source_id] = timestamps[-1]
    if len(sources) <= MAX_SOURCES:
        return
    for source_id, _timestamp in sorted(newest.items(), key=lambda item: item[1])[
        : len(sources) - MAX_SOURCES
    ]:
        sources.pop(source_id, None)


def _observe(
    hass: HomeAssistant,
    occurrence: PackOccurrence,
    config: dict[str, Any],
    data: dict[str, Any],
) -> PackOccurrenceResult | None:
    """Record one source occurrence and emit an immediate alert at the threshold."""
    if occurrence.source.type == PACK_ID or occurrence.source.id.startswith(
        f"{PACK_ID}:"
    ):
        return None

    now = occurrence.occurred_at.astimezone(UTC)
    _cleanup(hass, data, config, now)
    sources = data["sources"]
    source_id = occurrence.source.id
    threshold, window, recovery = _settings(occurrence, config)
    cutoff = now - timedelta(seconds=window)
    timestamps = [
        item for item in _parse_timestamps(sources.get(source_id)) if item >= cutoff
    ]
    timestamps.append(now)
    timestamps = timestamps[-threshold:]
    sources[source_id] = [item.isoformat() for item in timestamps]

    alert_id = f"{PACK_ID}:{source_id}"
    if len(timestamps) < threshold and alert_id not in occurrence.active_alert_ids:
        return PackOccurrenceResult()

    return PackOccurrenceResult(
        alert=PackGeneratedAlert(
            key=source_id,
            condition_key="automatic.flapping",
            condition_params={
                "count": len(timestamps),
                "duration": _compact_duration(window),
                "duration_seconds": window,
                "source": occurrence.source.rule_name or occurrence.source.condition,
                "last_occurrence": now.isoformat(),
            },
            value=len(timestamps),
            resolve_at=now + timedelta(seconds=recovery),
            rule_name=occurrence.source.rule_name or occurrence.source.condition,
        )
    )


def _number_field(
    field_id: str,
    translation_key: str,
    default: int,
    *,
    minimum: int = 1,
) -> PackConfigField:
    """Build one integer flapping setting used globally and in overrides."""
    return PackConfigField(
        id=field_id,
        type="number",
        translation_key=translation_key,
        default=default,
        minimum=minimum,
        maximum=31_536_000,
        step=1,
        unit="s" if field_id != "occurrences" else None,
    )


_OCCURRENCES_FIELD = _number_field(
    "occurrences", "flapping_occurrences", DEFAULT_OCCURRENCES, minimum=2
)
_WINDOW_FIELD = _number_field("window", "flapping_window", DEFAULT_WINDOW)
_RECOVERY_FIELD = _number_field("recovery", "flapping_recovery", DEFAULT_RECOVERY)

PACK = AutomaticPack(
    id=PACK_ID,
    translation_key=PACK_ID,
    prerequisites=(),
    applies=_never_applies,
    evaluate=_never_matches,
    uses_delay=False,
    occurrence_handler=_observe,
    config_fields=(
        _OCCURRENCES_FIELD,
        _WINDOW_FIELD,
        _RECOVERY_FIELD,
        PackConfigField(
            id="device_overrides",
            type="device_settings_map",
            translation_key="flapping_device_overrides",
            default={},
            fields=(_OCCURRENCES_FIELD, _WINDOW_FIELD, _RECOVERY_FIELD),
        ),
    ),
)
