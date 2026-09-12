"""Occurrence-driven automatic pack detecting repeated transient anomalies."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import Any

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.util.hass_dict import HassKey

from ..const import (
    DEFAULT_FLAPPING_OCCURRENCES,
    DEFAULT_FLAPPING_RECOVERY,
    DEFAULT_FLAPPING_WINDOW,
)
from ..pack_settings import resolve_settings
from .base import (
    AutomaticPack,
    PackConfigField,
    PackGeneratedAlert,
    PackOccurrence,
)

PACK_ID = "flapping"
MAX_SOURCES = 4096
MAX_OCCURRENCES = 1000
MAX_DURATION = 31_536_000
_CLEANUP_INTERVAL = timedelta(hours=1)
_LAST_CLEANUP: HassKey[datetime] = HassKey("alert_manager_flapping_last_cleanup")


def _never_applies(_hass: HomeAssistant, _state: State) -> bool:
    """Keep the pack off the state-evaluation path; it consumes occurrences only."""
    return False


def _never_matches(
    _hass: HomeAssistant, _state: State, _config: dict[str, Any]
) -> None:
    """Return no state-based match for this occurrence-driven pack."""


def _reset(hass: HomeAssistant) -> None:
    """Discard the pack's only transient cleanup marker."""
    hass.data.pop(_LAST_CLEANUP, None)


def _source_overrides(
    occurrence: PackOccurrence,
    config: dict[str, Any],
    rules_by_id: dict[str, dict[str, Any]],
) -> dict[str, int | None] | None:
    """Return enabled source overrides, or None when this source is not watched."""
    if occurrence.source.rule_id is not None:
        rule = rules_by_id.get(occurrence.source.rule_id)
        if rule is None or not rule.get("flapping_enabled", False):
            return None
        return {
            "occurrences": rule.get("flapping_occurrences"),
            "window": rule.get("flapping_window"),
            "recovery": rule.get("flapping_recovery"),
        }
    settings = config["automatic"][PACK_ID]["source_packs"].get(occurrence.source.type)
    return (
        None if settings is not None and settings.get("enabled") is False else settings
    )


def _settings(
    occurrence: PackOccurrence,
    config: dict[str, Any],
    rules_by_id: dict[str, dict[str, Any]],
    device_id: str | None = None,
) -> tuple[int, int, int] | None:
    """Resolve source, entity and global settings in descending priority."""
    source_settings = _source_overrides(occurrence, config, rules_by_id)
    if source_settings is None:
        return None
    pack_config = config["automatic"][PACK_ID]
    if occurrence.source.rule_id is not None:
        # Explicit custom rule settings retain their own opt-in and priority.
        defaults, _ = resolve_settings(
            pack_config, occurrence.source.entity_id, device_id
        )
        if not defaults["enabled"]:
            return None
        return tuple(
            source_settings.get(key) or defaults[key]
            for key in ("occurrences", "window", "recovery")
        )
    defaults, _ = resolve_settings(
        pack_config,
        occurrence.source.entity_id,
        device_id,
        source_id=occurrence.source.type,
    )
    if not defaults["enabled"]:
        return None
    return tuple(defaults[key] for key in ("occurrences", "window", "recovery"))


def _timestamps(raw: Any) -> list[float]:
    """Load valid timestamps from one small persisted source bucket."""
    if not isinstance(raw, list):
        return []
    return sorted(
        float(value)
        for value in raw
        if not isinstance(value, bool)
        and isinstance(value, int | float)
        and isfinite(value)
    )


def _compact_duration(seconds: int) -> str:
    """Return a short language-neutral duration for backend event payloads."""
    if seconds % 3600 == 0:
        return f"{seconds // 3600} h"
    if seconds % 60 == 0:
        return f"{seconds // 60} min"
    return f"{seconds} s"


def _largest_limits(config: dict[str, Any]) -> tuple[int, int]:
    """Return conservative retention limits across all possible overrides."""
    pack_config = config["automatic"][PACK_ID]
    settings = [pack_config]
    for scope in (pack_config, *pack_config["source_packs"].values()):
        settings.append(scope)
        for kind in ("device", "entity"):
            settings.extend(scope.get(f"{kind}_overrides", {}).values())
    settings.extend(
        {
            "occurrences": rule.get("flapping_occurrences"),
            "window": rule.get("flapping_window"),
        }
        for rule in config["rules"]
        if rule.get("flapping_enabled", False)
    )
    return (
        max(item.get("occurrences") or pack_config["occurrences"] for item in settings),
        max(item.get("window") or pack_config["window"] for item in settings),
    )


def _cleanup(
    hass: HomeAssistant,
    data: dict[str, Any],
    config: dict[str, Any],
    now: datetime,
) -> None:
    """Periodically discard timestamps no configuration can still use."""
    previous = hass.data.get(_LAST_CLEANUP)
    if isinstance(previous, datetime) and now - previous < _CLEANUP_INTERVAL:
        return
    hass.data[_LAST_CLEANUP] = now
    max_count, max_window = _largest_limits(config)
    cutoff = now.timestamp() - max_window
    for source_id, raw_timestamps in tuple(data.items()):
        if not isinstance(source_id, str) or not source_id:
            data.pop(source_id, None)
            continue
        timestamps = [item for item in _timestamps(raw_timestamps) if item >= cutoff][
            -max_count:
        ]
        if not timestamps:
            data.pop(source_id, None)
            continue
        data[source_id] = timestamps


def _limit_sources(data: dict[str, Any]) -> None:
    """Keep only the most recently observed source buckets."""
    excess = len(data) - MAX_SOURCES
    if excess <= 0:
        return
    newest = {
        source_id: timestamps[-1] if (timestamps := _timestamps(raw)) else float("-inf")
        for source_id, raw in data.items()
    }
    for source_id, _timestamp in sorted(newest.items(), key=lambda item: item[1])[
        :excess
    ]:
        data.pop(source_id, None)


def _process_occurrences(
    hass: HomeAssistant,
    occurrences: tuple[PackOccurrence, ...],
    config: dict[str, Any],
    data: dict[str, Any],
) -> tuple[PackGeneratedAlert, ...]:
    """Record one evaluation batch and emit alerts reaching the threshold."""
    relevant = tuple(
        occurrence for occurrence in occurrences if occurrence.source.type != PACK_ID
    )
    if not relevant:
        return ()

    _cleanup(
        hass,
        data,
        config,
        max(occurrence.occurred_at for occurrence in relevant).astimezone(UTC),
    )
    generated_alerts: list[PackGeneratedAlert] = []
    rules_by_id = (
        {rule["id"]: rule for rule in config["rules"]}
        if any(occurrence.source.rule_id is not None for occurrence in relevant)
        else {}
    )
    for occurrence in relevant:
        now = occurrence.occurred_at.astimezone(UTC)
        now_timestamp = now.timestamp()
        source_id = occurrence.source.id
        entry = er.async_get(hass).async_get(occurrence.source.entity_id)
        settings = _settings(
            occurrence, config, rules_by_id, entry.device_id if entry else None
        )
        if settings is None:
            data.pop(source_id, None)
            continue
        threshold, window, recovery = settings
        cutoff = now_timestamp - window
        timestamps = [
            item for item in _timestamps(data.get(source_id)) if item >= cutoff
        ]
        timestamps.append(now_timestamp)
        timestamps = timestamps[-threshold:]
        data[source_id] = timestamps

        alert_id = f"{PACK_ID}:{source_id}"
        if len(timestamps) < threshold and alert_id not in occurrence.active_alert_ids:
            continue
        source_name = occurrence.source.rule_name or occurrence.source.condition
        generated_alerts.append(
            PackGeneratedAlert(
                occurrence=occurrence,
                key=source_id,
                condition_key="automatic.flapping",
                condition_params={
                    "count": len(timestamps),
                    "threshold": threshold,
                    "occurrences": list(timestamps),
                    "duration": _compact_duration(window),
                    "duration_seconds": window,
                    "source": source_name,
                    "last_occurrence": now.isoformat(),
                },
                value=len(timestamps),
                resolve_at=now + timedelta(seconds=recovery),
                rule_name=source_name,
            )
        )
    _limit_sources(data)
    return tuple(generated_alerts)


def _number_field(
    field_id: str,
    translation_key: str,
    default: int,
    *,
    minimum: int = 1,
    maximum: int = MAX_DURATION,
) -> PackConfigField:
    """Build one integer flapping setting used globally and in overrides."""
    return PackConfigField(
        id=field_id,
        type="number",
        translation_key=translation_key,
        default=default,
        minimum=minimum,
        maximum=maximum,
        step=1,
        unit="s" if field_id != "occurrences" else None,
    )


_OCCURRENCES_FIELD = _number_field(
    "occurrences",
    "flapping_occurrences",
    DEFAULT_FLAPPING_OCCURRENCES,
    minimum=2,
    maximum=MAX_OCCURRENCES,
)
_WINDOW_FIELD = _number_field("window", "flapping_window", DEFAULT_FLAPPING_WINDOW)
_RECOVERY_FIELD = _number_field(
    "recovery", "flapping_recovery", DEFAULT_FLAPPING_RECOVERY
)
_SOURCE_FIELDS = tuple(
    replace(field, default=None)
    for field in (_OCCURRENCES_FIELD, _WINDOW_FIELD, _RECOVERY_FIELD)
)
_ENABLED_FIELD = PackConfigField(
    id="enabled",
    type="boolean",
    translation_key="flapping_enabled",
    default=True,
)

PACK = AutomaticPack(
    id=PACK_ID,
    translation_key=PACK_ID,
    prerequisites=(),
    applies=_never_applies,
    evaluate=_never_matches,
    reset_handler=_reset,
    uses_delay=False,
    occurrence_batch_handler=_process_occurrences,
    config_fields=(
        _OCCURRENCES_FIELD,
        _WINDOW_FIELD,
        _RECOVERY_FIELD,
        PackConfigField(
            id="source_packs",
            type="pack_settings_map",
            translation_key="flapping_source_packs",
            default={
                "unavailable": dict.fromkeys(("occurrences", "window", "recovery")),
                "connectivity": dict.fromkeys(("occurrences", "window", "recovery")),
            },
            fields=_SOURCE_FIELDS,
        ),
    ),
)
