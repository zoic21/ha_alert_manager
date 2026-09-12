"""Pure, field-by-field resolution of automatic monitoring exceptions."""

from __future__ import annotations

from typing import Any


def resolve_settings(
    config: dict[str, Any],
    entity_id: str,
    device_id: str | None,
    *,
    source_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Resolve sparse fields without expanding devices or modifying configuration.

    The caller owns global monitoring, label exclusion and eligibility gates.
    A target's enabled override never enables a disabled pack. Source-specific
    flapping exceptions are applied only in that automatic source's context.
    """
    values = {
        key: value
        for key, value in config.items()
        if key not in ("entity_overrides", "device_overrides", "source_packs")
    }
    origins = dict.fromkeys(values, "pack")
    scopes = [(config, "")]
    if source_id is not None:
        source = config.get("source_packs", {}).get(source_id)
        if source is None or source.get("enabled") is False:
            values["enabled"] = False
            origins["enabled"] = "source"
            return values, origins
        for key, value in source.items():
            if (
                key not in ("entity_overrides", "device_overrides")
                and value is not None
            ):
                values[key] = value
                origins[key] = "source"
        scopes.append((source, "source_"))
    # Entity priority is field-by-field, including across source/default scopes.
    for kind, target_id in (("device", device_id), ("entity", entity_id)):
        if target_id is None:
            continue
        for scope, prefix in scopes:
            for key, value in (
                scope.get(f"{kind}_overrides", {}).get(target_id, {}).items()
            ):
                # A more specific exception cannot reactivate a disabled parent.
                if key == "enabled" and values.get("enabled") is False:
                    continue
                values[key] = value
                origins[key] = f"{prefix}{kind}"
    if not config.get("enabled", False):
        values["enabled"] = False
        origins["enabled"] = "pack"
    return values, origins
