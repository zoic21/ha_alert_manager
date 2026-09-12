"""Compact canonical fixtures for scenarios involving several automatic packs."""

from copy import deepcopy

from custom_components.alert_manager.packs import PACKS


def automatic_settings(*, delay=None, delays=None, automatic=None):
    """Configure state packs together without a shared runtime fallback."""
    values = deepcopy(automatic or {})
    for pack in PACKS:
        if not pack.uses_delay:
            continue
        settings = values.setdefault(pack.id, {})
        if delay is not None and pack.id != "execution_errors":
            settings.setdefault("delay", delay)
        if delays is not None:
            settings["entity_overrides"] = {
                entity_id: {"delay": value} for entity_id, value in delays.items()
            }
    return {"automatic": values}
