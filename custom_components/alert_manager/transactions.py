"""Atomic runtime transaction helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Iterable
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from homeassistant.util.async_ import create_eager_task

from .models import AlertRecord, AlertStatus


async def async_finish_non_interruptible(operation: Awaitable[Any]) -> Any:
    """Finish one admitted operation before propagating caller cancellation."""
    transaction = create_eager_task(operation)
    cancellation: asyncio.CancelledError | None = None
    while not transaction.done():
        try:
            await asyncio.shield(transaction)
        except asyncio.CancelledError as err:
            if transaction.cancelled():
                raise
            cancellation = cancellation or err
        except BaseException:
            break

    try:
        result = transaction.result()
    except BaseException as err:
        if cancellation is not None:
            raise cancellation from err
        raise
    if cancellation is not None:
        raise cancellation
    return result


def select_alert_collision(
    candidates: Iterable[tuple[AlertRecord, str | None]],
    *,
    restored_records: dict[str, AlertRecord] | None = None,
) -> tuple[AlertRecord, str | None]:
    """Select one identity collision with a single deterministic policy.

    A genuinely live occurrence wins over startup-restored state. Candidates
    with the same provenance class then keep the oldest clock, prefer an active
    lifecycle at an identical clock, and finally use their stable origin id.
    """
    restored_records = restored_records if restored_records is not None else {}

    def collision_key(
        candidate: tuple[AlertRecord, str | None],
    ) -> tuple[bool, Any, bool, str]:
        record, origin_id = candidate
        restored = origin_id is not None and origin_id in restored_records
        lifecycle = restored_records[origin_id] if restored else record
        return (
            restored,
            record.detected_at,
            lifecycle.status is not AlertStatus.ACTIVE,
            origin_id or record.details.id,
        )

    return min(candidates, key=collision_key)


@dataclass(slots=True)
class StartupReconciliationTransaction:
    """Keep restored occurrence identity stable across speculative scans.

    Reconciliation may yield to Store I/O more than once. States received during
    those yields are evaluated against the same immutable restored occurrences,
    so an intermediate observation cannot consume their provenance or reset
    their clocks. Only the final, stable observation remains in manager state.
    """

    _restored_records: dict[str, AlertRecord]
    _entity_renames: dict[str, str] = field(default_factory=dict)
    _unverified_original_ids: set[str] = field(default_factory=set)
    _live_original_ids: dict[str, str] = field(default_factory=dict)

    @classmethod
    def capture(
        cls,
        records: dict[str, AlertRecord],
        restored_alert_ids: set[str],
    ) -> StartupReconciliationTransaction:
        """Capture an independent immutable-by-convention restored shadow."""
        restored_records = {
            alert_id: deepcopy(records[alert_id])
            for alert_id in restored_alert_ids
            if alert_id in records
        }
        return cls(
            restored_records,
            _unverified_original_ids=set(restored_records),
            _live_original_ids={alert_id: alert_id for alert_id in restored_records},
        )

    @property
    def entity_ids(self) -> set[str]:
        """Return every current entity owning a restored occurrence."""
        return {
            self._final_entity_id(record.details.entity_id)
            for record in self._restored_records.values()
        }

    def records_for_entity(self, entity_id: str) -> dict[str, tuple[str, AlertRecord]]:
        """Return retained originals and fresh records for one current entity."""
        return self._retained_records(entity_id)

    def live_alert_ids_for_entity(self, entity_id: str) -> set[str]:
        """Return current records that still originate from restored state."""
        return {
            alert_id
            for alert_id, original_id in self._live_original_ids.items()
            if original_id in self._restored_records
            and self._final_entity_id(
                self._restored_records[original_id].details.entity_id
            )
            == entity_id
            and self._current_alert_id(self._restored_records[original_id]) == alert_id
        }

    def live_origin(self, alert_id: str) -> str | None:
        """Return the restored occurrence currently backing one live record."""
        return self._live_original_ids.get(alert_id)

    def record_removed(self, alert_id: str) -> None:
        """Forget restored provenance when a live record is removed."""
        self._live_original_ids.pop(alert_id, None)

    def record_stored(self, alert_id: str, original_id: str | None) -> None:
        """Describe whether a stored live record comes from restored state."""
        if original_id is None:
            self._live_original_ids.pop(alert_id, None)
            return
        self._live_original_ids[alert_id] = original_id

    def original_was_active(self, alert_id: str) -> bool:
        """Return whether the restored occurrence was active before startup."""
        original_id = self._live_original_ids.get(alert_id)
        return (
            original_id in self._restored_records
            and self._restored_records[original_id].status is AlertStatus.ACTIVE
        )

    def stage_unverified(self, entity_id: str, alert_ids: set[str]) -> None:
        """Replace one entity's provisional provenance with its latest result."""
        original_ids = {
            original_id
            for original_id, record in self._restored_records.items()
            if self._final_entity_id(record.details.entity_id) == entity_id
        }
        self._unverified_original_ids.difference_update(original_ids)
        for alert_id in alert_ids:
            original_id = self._live_original_ids.get(alert_id)
            if original_id in original_ids:
                self._unverified_original_ids.add(original_id)

    def record_entity_renames(self, renames: dict[str, str]) -> None:
        """Record identity mapping and discard provenance lost in collisions."""
        self._entity_renames.update(renames)
        retained_original_ids = {
            original_id
            for entity_id in self.entity_ids
            for original_id, _record in self._retained_records(entity_id).values()
        }
        self._unverified_original_ids.intersection_update(retained_original_ids)

    def preferred_collision_record(
        self,
        candidates: Iterable[tuple[AlertRecord, str | None]],
    ) -> tuple[AlertRecord, str | None]:
        """Choose one rename collision with the shared provenance policy."""
        return select_alert_collision(
            candidates,
            restored_records=self._restored_records,
        )

    def reconciled_original_records(self) -> dict[str, AlertRecord]:
        """Return the pre-startup lifecycle after applying identity changes.

        The same retained-record path used by live rename handling also owns
        lifecycle normalization. This keeps collisions deterministic and avoids
        reporting a restored active occurrence as newly started.
        """
        return {
            alert_id: record
            for entity_id in sorted(self.entity_ids)
            for alert_id, (_original_id, record) in self._retained_records(
                entity_id
            ).items()
        }

    def committed_unverified_alert_ids(
        self, records: dict[str, AlertRecord]
    ) -> set[str]:
        """Materialize provenance from only the final staged observations."""
        return {
            alert_id
            for alert_id, original_id in self._live_original_ids.items()
            if original_id in self._unverified_original_ids
            and alert_id in records
            and self._current_alert_id(self._restored_records[original_id]) == alert_id
        }

    def _retained_records(self, entity_id: str) -> dict[str, tuple[str, AlertRecord]]:
        """Resolve rename collisions deterministically to the oldest occurrence."""
        retained: dict[str, tuple[str, AlertRecord]] = {}
        for original_id, original in self._restored_records.items():
            target_entity_id = self._final_entity_id(original.details.entity_id)
            if target_entity_id != entity_id:
                continue
            candidate = deepcopy(original)
            candidate.details.entity_id = target_entity_id
            candidate.details.id = self._alert_id(candidate, target_entity_id)
            existing = retained.get(candidate.details.id)
            if existing is None:
                retained[candidate.details.id] = (original_id, candidate)
                continue
            selected, selected_original_id = select_alert_collision(
                ((candidate, original_id), (existing[1], existing[0])),
                restored_records=self._restored_records,
            )
            assert selected_original_id is not None
            retained[candidate.details.id] = (selected_original_id, selected)
        return retained

    def _current_alert_id(self, record: AlertRecord) -> str:
        """Return a restored record id after every rename seen so far."""
        entity_id = self._final_entity_id(record.details.entity_id)
        return self._alert_id(record, entity_id)

    def _final_entity_id(self, entity_id: str) -> str:
        """Follow chained renames while remaining safe against malformed cycles."""
        seen: set[str] = set()
        while entity_id in self._entity_renames and entity_id not in seen:
            seen.add(entity_id)
            entity_id = self._entity_renames[entity_id]
        return entity_id

    @staticmethod
    def _alert_id(record: AlertRecord, entity_id: str) -> str:
        """Build the stable id for a restored automatic or rule occurrence."""
        if record.details.type == "rule" and record.details.rule_id:
            return f"rule:{record.details.rule_id}:{entity_id}"
        return f"{record.details.type}:{entity_id}"
