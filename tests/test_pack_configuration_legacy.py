"""Capture pre-2.4 effective settings before changing the migration boundary.

These expectations describe legacy input semantics, not the future override
contract. Move the same examples to migration-output assertions when wiring the
new schema; do not silently replace them with the new precedence rules.
"""

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from custom_components.alert_manager.const import DEFAULT_CONFIG
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.models import AlertDetails
from custom_components.alert_manager.packs.base import PackOccurrence
from custom_components.alert_manager.packs.flapping import _settings


@pytest.mark.parametrize(
    "pack_id", ["unavailable", "connectivity", "unifi", "battery", "execution_errors"]
)
def test_legacy_entity_delay_beats_pack_default_even_when_disabled(
    hass, entry, pack_id
):
    manager = AlertManager(hass, entry)
    manager.config = deepcopy(DEFAULT_CONFIG)
    state = hass.states.set("sensor.example", "unavailable")
    manager.config["global_delay"] = 900
    manager.config["automatic"][pack_id].update(enabled=False, delay=1800)
    manager.config["entity_delays"][state.entity_id] = 0
    assert manager._delay_for(state, pack_id) == 0
    del manager.config["entity_delays"][state.entity_id]
    assert manager._delay_for(state, pack_id) == 1800
    manager.config["automatic"][pack_id]["delay"] = None
    assert manager._delay_for(state, pack_id) == 900


def test_legacy_execution_errors_have_an_independent_immediate_default(hass, entry):
    manager = AlertManager(hass, entry)
    manager.config = deepcopy(DEFAULT_CONFIG)
    manager.config["global_delay"] = 900
    state = hass.states.set("automation.example", "on")
    assert manager._delay_for(state, "execution_errors") == 0
    manager.config["entity_delays"][state.entity_id] = 60
    assert manager._delay_for(state, "execution_errors") == 60


@pytest.mark.parametrize("custom_rule", [False, True])
def test_legacy_flapping_source_fields_beat_entity_fields(custom_rule):
    config = deepcopy(DEFAULT_CONFIG)
    config["automatic"]["flapping"].update(
        enabled=True,
        occurrences=5,
        window=7200,
        recovery=300,
        entity_overrides={
            "sensor.example": {
                "enabled": True,
                "occurrences": 3,
                "window": 1800,
                "recovery": 120,
            }
        },
        source_packs={
            "unavailable": {"occurrences": 8, "window": None, "recovery": 600}
        },
    )
    source = AlertDetails(
        id="rule:test:sensor.example" if custom_rule else "unavailable:sensor.example",
        type="rule" if custom_rule else "unavailable",
        entity_id="sensor.example",
        name="Example",
        value="unavailable",
        condition="Example condition",
        rule_id="test" if custom_rule else None,
    )
    occurrence = PackOccurrence(
        source=source, occurred_at=datetime(2026, 9, 12, tzinfo=UTC)
    )
    rules = {
        "test": {
            "flapping_enabled": True,
            "flapping_occurrences": 8,
            "flapping_recovery": 600,
        }
    }
    assert _settings(occurrence, config, rules) == (8, 1800, 600)
    config["automatic"]["flapping"]["entity_overrides"]["sensor.example"]["enabled"] = (
        False
    )
    assert _settings(occurrence, config, rules) is None
