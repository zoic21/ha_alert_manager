"""ZHA registry references reuse the existing coherence scan and report."""

import asyncio
from types import SimpleNamespace

import pytest
from homeassistant.config_entries import ConfigEntryState

from custom_components.alert_manager.coherence import (
    async_scan_configuration,
    scan_configuration,
)
from custom_components.alert_manager.validation import (
    validate_coherence_ignored_entity_references,
)

IEEE = "5c:02:72:ff:fe:d9:be:ec"


def write_trigger(tmp_path, trigger, section="triggers"):
    (tmp_path / "automations.yaml").write_text(
        f"- id: remote\n  alias: Remote\n  {section}:\n    - "
        + trigger.replace("\n", "\n      ")
        + "\n  actions: []\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize("section", ["trigger", "triggers"])
@pytest.mark.parametrize("syntax", ["trigger", "platform"])
@pytest.mark.parametrize("event_type", ["zha_event", "[other_event, zha_event]"])
def test_static_trigger_source_case_exclusions(tmp_path, syntax, event_type, section):
    write_trigger(
        tmp_path,
        f"{syntax}: event\nevent_type: {event_type}\nevent_data:\n"
        f'  device_ieee: "{IEEE.upper()}"',
        section,
    )
    report = scan_configuration(
        tmp_path,
        frozenset(),
        check_snapshots={"zha_device_ieee": (frozenset(), "executed")},
    )
    assert report["missing_count"] == 1
    assert report["missing_entity_count"] == 0
    row = report["results"][0]
    assert row["reference"] == IEEE.upper()
    assert row["reference_type"] == "zha_device_ieee"
    assert "entity_id" not in row
    assert row["source_name"] == "Remote"
    assert row["line"] == 7
    assert row["link"]["path"] == "/config/automation/edit/remote"
    assert not scan_configuration(
        tmp_path,
        frozenset(),
        check_snapshots={"zha_device_ieee": (frozenset({IEEE}), "executed")},
    )["results"]
    assert not scan_configuration(
        tmp_path,
        frozenset(),
        check_snapshots={"zha_device_ieee": (frozenset(), "executed")},
        ignored_entity_references=frozenset({IEEE}),
    )["results"]


@pytest.mark.parametrize(
    "value",
    [
        '"{{ ieee }}"',
        "!input ieee",
        "!secret ieee",
        "12",
        "null",
        '"invalid"',
        "[one, two]",
    ],
)
def test_nonliteral_and_malformed_ieee_ignored(tmp_path, value):
    write_trigger(
        tmp_path,
        f"trigger: event\nevent_type: zha_event\nevent_data:\n  device_ieee: {value}",
    )
    assert not scan_configuration(
        tmp_path,
        frozenset(),
        check_snapshots={"zha_device_ieee": (frozenset(), "executed")},
    )["results"]


@pytest.mark.parametrize(
    "trigger",
    [
        f'trigger: event\nevent_type: other\nevent_data: {{device_ieee: "{IEEE}"}}',
        "trigger: event\nevent_type: zha_event\nevent_data: {}",
        "trigger: event\nevent_type: !input event\n"
        f'event_data: {{device_ieee: "{IEEE}"}}',
        f'trigger: state\nevent_type: zha_event\nevent_data: {{device_ieee: "{IEEE}"}}',
    ],
)
def test_non_zha_subscriptions_ignored(tmp_path, trigger):
    write_trigger(tmp_path, trigger)
    assert not scan_configuration(
        tmp_path,
        frozenset(),
        check_snapshots={"zha_device_ieee": (frozenset(), "executed")},
    )["results"]


def test_script_wait_and_distinct_locations_not_actions_or_data(tmp_path):
    event = (
        "{trigger: event, event_type: zha_event, "
        f'event_data: {{device_ieee: "{IEEE}"}}}}'
    )
    (tmp_path / "scripts.yaml").write_text(
        f'''remote:
  alias: Waiting remote
  sequence:
    - event: zha_event
      event_data: {{device_ieee: "{IEEE}"}}
    - variables:
        example: {event}
        wait_for_trigger: [{event}]
    - choose:
        - conditions: []
          sequence:
            - wait_for_trigger: [{event}, {event}]
    - wait_for_trigger:
        - {event}
''',
        encoding="utf-8",
    )
    report = scan_configuration(
        tmp_path,
        frozenset(),
        check_snapshots={"zha_device_ieee": (frozenset(), "executed")},
    )
    assert len(report["results"]) == 3
    assert [r["line"] for r in report["results"]] == [12, 12, 14]
    assert all(
        r["link"]["path"] == "/config/script/edit/remote" for r in report["results"]
    )


def test_metadata_snapshot_and_registry_ownership(hass, tmp_path):
    write_trigger(
        tmp_path,
        f'trigger: event\nevent_type: zha_event\nevent_data: {{device_ieee: "{IEEE}"}}',
    )
    hass.config.path = lambda: str(tmp_path)
    entries = [SimpleNamespace(entry_id="zha1", state=ConfigEntryState.LOADED)]
    hass.config_entries.async_entries = lambda domain: entries
    hass.device_registry.devices = {
        "remote": SimpleNamespace(
            config_entries={"zha1"},
            identifiers={("zha", IEEE.upper())},
            disabled_by="user",
        )
    }

    def scan():
        return asyncio.run(async_scan_configuration(hass))

    assert not scan()["results"]  # Disabled, no entities or state required.
    entries.append(SimpleNamespace(entry_id="zha2", state=ConfigEntryState.LOADED))
    hass.device_registry.devices["remote"].config_entries = {"zha2"}
    assert not scan()["results"]  # Combine all loaded entries.
    entries.pop()

    hass.device_registry.devices["remote"].config_entries = {"other"}
    assert scan()["missing_count"] == 1
    hass.device_registry.devices["remote"].config_entries = {"zha1"}
    hass.device_registry.devices["remote"].identifiers = {("zigbee", IEEE)}
    assert scan()["missing_count"] == 1
    entries.append(SimpleNamespace(entry_id="zha2", state="setup_error"))
    result = scan()
    assert result["checks"]["zha_device_ieee"] == "not_loaded"
    assert not result["results"]
    entries.clear()
    assert scan()["checks"]["zha_device_ieee"] == "not_applicable"
    entries.append(SimpleNamespace(entry_id="zha1", state=ConfigEntryState.LOADED))
    hass.device_registry.devices = None
    result = scan()
    assert result["checks"]["zha_device_ieee"] == "metadata_error"
    assert not result["results"]


def test_exclusion_validation_remains_exact():
    assert validate_coherence_ignored_entity_references(
        [IEEE.upper(), IEEE, "sensor.test"]
    ) == [IEEE, "sensor.test"]
    for value in ["5c:*", "sensor.*", "5c:02", 12]:
        with pytest.raises(ValueError):
            validate_coherence_ignored_entity_references([value])


def test_zha_counts_reach_existing_sensor(tmp_path):
    from custom_components.alert_manager.sensor import AlertManagerCoherenceIssueSensor

    write_trigger(
        tmp_path,
        f'trigger: event\nevent_type: zha_event\nevent_data:\n  device_ieee: "{IEEE}"',
    )
    report = scan_configuration(
        tmp_path,
        frozenset(),
        check_snapshots={"zha_device_ieee": (frozenset(), "executed")},
    )
    sensor = AlertManagerCoherenceIssueSensor()
    sensor.async_write_ha_state = lambda: None
    sensor._async_coherence_updated(report)
    assert sensor.native_value == 1


def test_check_snapshot_and_analysis_use_their_expected_threads(
    hass, tmp_path, monkeypatch
):
    """Registry access stays on the event loop; reference parsing is offloaded."""
    from threading import get_ident

    from custom_components.alert_manager.coherence_checks import zha

    write_trigger(
        tmp_path,
        f'trigger: event\nevent_type: zha_event\nevent_data:\n  device_ieee: "{IEEE}"',
    )
    hass.config.path = lambda: str(tmp_path)
    event_loop_thread = get_ident()
    calls = []
    original_references = zha.references

    def snapshot(_hass):
        assert get_ident() == event_loop_thread
        calls.append("snapshot")
        return frozenset(), "executed"

    def references(node, scope):
        assert get_ident() != event_loop_thread
        result = original_references(node, scope)
        if result:
            calls.append("references")
        return result

    monkeypatch.setattr(zha, "snapshot", snapshot)
    monkeypatch.setattr(zha, "references", references)
    report = asyncio.run(async_scan_configuration(hass))
    assert calls == ["snapshot", "references"]
    assert report["missing_reference_count"] == 1


@pytest.mark.parametrize("container", ["choose", "repeat", "if", "parallel"])
def test_zha_scope_stays_in_executable_branches(tmp_path, container):
    """Nested waits are scanned without leaking their scope into sibling data."""
    import yaml

    event = {
        "trigger": "event",
        "event_type": "zha_event",
        "event_data": {"device_ieee": IEEE},
    }
    wait = {"wait_for_trigger": [event]}
    nested = {
        "choose": {"choose": [{"conditions": [], "sequence": [wait]}]},
        "repeat": {"repeat": {"count": 2, "sequence": [wait]}},
        "if": {"if": [], "then": [wait], "else": []},
        "parallel": {"parallel": [{"sequence": [wait]}]},
    }[container]
    (tmp_path / "automations.yaml").write_text(
        yaml.safe_dump(
            [
                {
                    "id": "remote",
                    "triggers": [event],
                    "actions": [
                        nested,
                        {"variables": {"wait_for_trigger": [event]}},
                        {"event": "zha_event", "event_data": {"device_ieee": IEEE}},
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    report = scan_configuration(
        tmp_path,
        frozenset(),
        check_snapshots={"zha_device_ieee": (frozenset(), "executed")},
    )
    # safe_dump aliases the shared event: one source location, two real visits.
    assert report["references_checked"] == 2
    assert report["missing_count"] == 1
