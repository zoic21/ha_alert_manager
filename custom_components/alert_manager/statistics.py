"""Bounded, event-loop-owned diagnostic aggregates; never persisted."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from homeassistant.util import dt as dt_util

Activity = Literal["pending", "activations", "acknowledgments", "resolutions"]
_ACTIVITY_KEYS = ("pending", "activations", "acknowledgments", "resolutions")


@dataclass(slots=True)
class _Bucket:
    hour: int | None = None
    evaluation_count: int = 0
    evaluation_total_ns: int = 0
    evaluation_max_ns: int = 0
    activity: dict[str, int] = field(default_factory=dict)
    notifications: int = 0
    profiles: dict[str, int] = field(default_factory=dict)


class RuntimeStatistics:
    """Keep the current UTC hour and previous 23 hours, without a rotation task."""

    def __init__(self) -> None:
        self.started_at = dt_util.now().astimezone(UTC)
        self._buckets = [_Bucket() for _ in range(24)]
        self._deferred_activity: dict[str, int] | None = None

    def _current_bucket(self) -> _Bucket:
        hour = int(dt_util.now().timestamp() // 3600)
        bucket = self._buckets[hour % 24]
        if bucket.hour != hour:
            bucket.hour = hour
            bucket.evaluation_count = 0
            bucket.evaluation_total_ns = 0
            bucket.evaluation_max_ns = 0
            bucket.activity.clear()
            bucket.notifications = 0
            bucket.profiles.clear()
        return bucket

    def record_evaluation(self, duration_ns: int) -> None:
        """Record one synchronous custom-rule/entity evaluation (no awaits)."""
        bucket = self._current_bucket()
        bucket.evaluation_count += 1
        bucket.evaluation_total_ns += duration_ns
        bucket.evaluation_max_ns = max(bucket.evaluation_max_ns, duration_ns)

    def record_activity(self, kind: Activity) -> None:
        """Count an actual transition, deferring configuration transactions."""
        counts = self._deferred_activity
        if counts is None:
            counts = self._current_bucket().activity
        counts[kind] = counts.get(kind, 0) + 1

    @contextmanager
    def activity_transaction(self) -> Iterator[None]:
        """Discard activity if a configuration mutation rolls back."""
        previous = self._deferred_activity
        counts: dict[str, int] = {}
        self._deferred_activity = counts
        try:
            yield
            if counts:
                target = (
                    previous
                    if previous is not None
                    else self._current_bucket().activity
                )
                for kind, count in counts.items():
                    target[kind] = target.get(kind, 0) + count
        finally:
            self._deferred_activity = previous

    def record_notification(self, profile_id: str) -> None:
        """Count one successful profile batch, regardless of target count."""
        bucket = self._current_bucket()
        bucket.notifications += 1
        bucket.profiles[profile_id] = bucket.profiles.get(profile_id, 0) + 1

    def retain_profiles(self, profile_ids: set[str]) -> None:
        """Drop deleted profile keys on configuration changes only."""
        for bucket in self._buckets:
            for profile_id in bucket.profiles.keys() - profile_ids:
                del bucket.profiles[profile_id]

    def snapshot(self) -> dict[str, Any]:
        """Ignore expired/future buckets even after an arbitrarily long idle."""
        now = dt_util.now().astimezone(UTC)
        hour = int(now.timestamp() // 3600)
        count = total = maximum = notifications = 0
        activity = dict.fromkeys(_ACTIVITY_KEYS, 0)
        profiles: dict[str, int] = {}
        for bucket in self._buckets:
            if bucket.hour is None or not hour - 23 <= bucket.hour <= hour:
                continue
            count += bucket.evaluation_count
            total += bucket.evaluation_total_ns
            maximum = max(maximum, bucket.evaluation_max_ns)
            notifications += bucket.notifications
            for kind, value in bucket.activity.items():
                activity[kind] += value
            for profile_id, value in bucket.profiles.items():
                profiles[profile_id] = profiles.get(profile_id, 0) + value
        window_start = datetime.fromtimestamp((hour - 23) * 3600, UTC)
        return {
            "started_at": self.started_at.isoformat(),
            "observed_from": max(self.started_at, window_start).isoformat(),
            "observed_until": now.isoformat(),
            "evaluation_count": count,
            "evaluation_total_ms": total / 1_000_000,
            "evaluation_average_ms": total / count / 1_000_000 if count else 0,
            "evaluation_max_ms": maximum / 1_000_000,
            **activity,
            "notifications": notifications,
            "notification_profiles": profiles,
        }
