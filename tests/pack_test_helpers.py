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
        if delay is not None and pack.default_delay != 0:
            settings.setdefault("delay", delay)
        if delays is not None and any(
            field.id == "entity_overrides"
            and any(setting.id == "delay" for setting in field.fields)
            for field in pack.config_fields
        ):
            settings["entity_overrides"] = {
                entity_id: {"delay": value} for entity_id, value in delays.items()
            }
    return {"automatic": values}
