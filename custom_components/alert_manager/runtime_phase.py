"""Explicit Alert Manager runtime lifecycle phases."""

from __future__ import annotations

from enum import StrEnum


class RuntimePhase(StrEnum):
    """Describe which state transitions the manager may currently apply."""

    STARTING = "starting"
    STARTUP_GRACE = "startup_grace"
    RECONCILING = "reconciling"
    RUNNING = "running"
    STOPPING = "stopping"

    @property
    def is_startup(self) -> bool:
        """Return whether persisted state is still protected from startup churn."""
        return self in (
            RuntimePhase.STARTING,
            RuntimePhase.STARTUP_GRACE,
            RuntimePhase.RECONCILING,
        )

    @property
    def can_evaluate(self) -> bool:
        """Return whether current Home Assistant state is authoritative."""
        return self in (RuntimePhase.RECONCILING, RuntimePhase.RUNNING)
