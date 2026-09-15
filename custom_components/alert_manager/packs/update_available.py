"""Available updates, using Home Assistant's native availability state."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, State

from .base import AutomaticPack, PackConfigField, PackMatch, PackNeutral

# Exclusion-only override: keep the shared "enabled" key for stored/YAML config
# and generic pack resolution. Remove the entity override to monitor it again;
# enabling an individual entity is deliberately not supported by this pack.
ENTITY_EXCLUSION_FIELD = PackConfigField(
    "enabled", "boolean", "monitoring", False, options=(False,)
)


def _applies(_hass: HomeAssistant, state: State) -> bool:
    """Monitor update entities without maintaining a separate subscription."""
    return state.entity_id.partition(".")[0] == "update"


def _evaluate(
    hass: HomeAssistant, state: State, _config: dict[str, Any]
) -> PackMatch | PackNeutral | None:
    """Keep uncertain availability neutral; versions only enrich the message."""
    if not _applies(hass, state):
        return None
    if state.state in ("unknown", "unavailable"):
        return PackNeutral()
    if state.state != "on":
        return None
    installed = state.attributes.get("installed_version")
    latest = state.attributes.get("latest_version")
    params = {}
    key = "automatic.update_available"
    if latest:
        params["latest_version"] = latest
        key += "_version"
        if installed:
            params["installed_version"] = installed
            key += "_installed"
    return PackMatch(condition_key=key, condition_params=params, value=latest)


PACK = AutomaticPack(
    id="update_available",
    translation_key="update_available",
    prerequisites=(),
    applies=_applies,
    evaluate=_evaluate,
    default_delay=0,
    order=5,
    target_filter={"domain": "update"},
    exception_targets=("entity",),
    config_fields=(
        PackConfigField(
            "entity_overrides",
            "entity_settings_map",
            "excluded_update_entities",
            {},
            entity_domains=("update",),
            fields=(ENTITY_EXCLUSION_FIELD,),
        ),
    ),
)
