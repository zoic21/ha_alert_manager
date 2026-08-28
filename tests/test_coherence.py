"""Tests for the on-demand configuration coherence scanner."""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.alert_manager.coherence import scan_configuration


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_scan_finds_missing_entities_with_editable_object_context(tmp_path):
    """Automations, scripts and templates retain useful editor targets."""
    _write(
        tmp_path / "automations.yaml",
        """- id: kettle_check
  alias: Bouilloire
  trigger:
    - trigger: state
      entity_id: sensor.present
  condition: "{{ states('sensor.removed_temperature') != '0' }}"
  action:
    - choose:
        - conditions: "{{ is_state('binary_sensor.removed_nested', 'on') }}"
          sequence:
            - action: light.turn_on
              target:
                entity_id: light.kitchen
            - variables:
                direct_state: "{{ states.sensor.removed_direct.state }}"
                direct_attribute: "{{ states.sensor.gone_attr.attributes.unit }}"
""",
    )
    _write(
        tmp_path / "scripts.yaml",
        """notify_fault:
  alias: Notifier le défaut
  sequence:
    - action: notify.send_message
      data:
        message: "{{ states('binary_sensor.removed_fault') }}"
""",
    )
    _write(
        tmp_path / "templates.yaml",
        """template:
  - sensor:
      - name: Température calculée
        unique_id: calculated_temperature
        state: "{{ states('sensor.removed_source') }}"
""",
    )

    result = scan_configuration(
        tmp_path,
        frozenset({"sensor.present", "light.kitchen"}),
        template_by_unique_id={
            "calculated_temperature": "sensor.calculated_temperature"
        },
    )

    rows = {row["entity_id"]: row for row in result["results"]}
    assert set(rows) == {
        "binary_sensor.removed_fault",
        "binary_sensor.removed_nested",
        "sensor.removed_direct",
        "sensor.gone_attr",
        "sensor.removed_source",
        "sensor.removed_temperature",
    }
    assert rows["sensor.removed_temperature"]["source_type"] == "automation"
    assert rows["sensor.removed_temperature"]["source_name"] == "Bouilloire"
    assert rows["sensor.removed_temperature"]["line"] == 6
    assert rows["sensor.removed_temperature"]["link"] == {
        "type": "navigate",
        "path": "/config/automation/edit/kettle_check",
    }
    assert rows["binary_sensor.removed_nested"]["source_type"] == "automation"
    assert rows["binary_sensor.removed_fault"]["source_type"] == "script"
    assert rows["binary_sensor.removed_fault"]["link"]["path"] == (
        "/config/script/edit/notify_fault"
    )
    assert rows["sensor.removed_source"]["source_type"] == "template"
    assert rows["sensor.removed_source"]["link"] == {
        "type": "more_info",
        "entity_id": "sensor.calculated_temperature",
    }
    assert "light.turn_on" not in rows
    assert all(row["line"] > 0 for row in rows.values())


def test_scan_links_storage_dashboards_and_ui_template_entries(tmp_path):
    """Storage dashboards and template helpers get their direct HA targets."""
    storage = tmp_path / ".storage"
    _write(
        storage / "lovelace_dashboards",
        json.dumps(
            {
                "data": {
                    "items": [
                        {
                            "id": "wall-panel",
                            "url_path": "wall",
                            "title": "Écran mural",
                        }
                    ]
                }
            }
        ),
    )
    _write(
        storage / "lovelace.wall-panel",
        json.dumps(
            {
                "data": {
                    "config": {
                        "views": [
                            {
                                "title": "État",
                                "path": "status",
                                "cards": [
                                    {
                                        "type": "entity",
                                        "entity": "sensor.removed_dashboard",
                                    }
                                ],
                            }
                        ]
                    }
                }
            },
            indent=2,
        ),
    )
    _write(
        storage / "core.config_entries",
        json.dumps(
            {
                "data": {
                    "entries": [
                        {
                            "entry_id": "template-entry",
                            "domain": "template",
                            "title": "Capteur UI",
                            "options": {
                                "state": "{{ states('sensor.removed_ui_source') }}"
                            },
                        }
                    ]
                }
            },
            indent=2,
        ),
    )
    _write(
        tmp_path / "dashboards" / "mobile.yaml",
        """views:
  - title: Mobile
    path: home
    cards:
      - type: entity
        entity: sensor.removed_yaml_dashboard
""",
    )

    result = scan_configuration(
        tmp_path,
        frozenset(),
        template_by_config_entry={"template-entry": "sensor.ui_template"},
        yaml_dashboards={
            "dashboards/mobile.yaml": ("Dashboard mobile", "/mobile-dashboard")
        },
    )

    rows = {row["entity_id"]: row for row in result["results"]}
    dashboard = rows["sensor.removed_dashboard"]
    assert dashboard["source_type"] == "dashboard"
    assert dashboard["source_name"] == "Écran mural · État"
    assert dashboard["file"] == ".storage/lovelace.wall-panel"
    assert dashboard["link"] == {
        "type": "navigate",
        "path": "/wall/status",
    }
    yaml_dashboard = rows["sensor.removed_yaml_dashboard"]
    assert yaml_dashboard["source_name"] == "Dashboard mobile · Mobile"
    assert yaml_dashboard["link"]["path"] == "/mobile-dashboard/home"
    template = rows["sensor.removed_ui_source"]
    assert template["source_type"] == "template"
    assert template["source_name"] == "Capteur UI"
    assert template["link"] == {
        "type": "more_info",
        "entity_id": "sensor.ui_template",
    }


def test_scan_ignores_unrelated_trees_descriptions_and_invalid_files(tmp_path):
    """The scan remains bounded and reports malformed configuration separately."""
    _write(
        tmp_path / "configuration.yaml",
        """description: sensor.example_only
sensor:
  - platform: command_line
    command: echo sensor.removed_command
""",
    )
    _write(tmp_path / "broken.yaml", "sensor: [broken")
    _write(
        tmp_path / "custom_components" / "demo" / "config.yaml",
        "entity_id: sensor.must_not_be_scanned\n",
    )

    result = scan_configuration(tmp_path, frozenset())

    assert [row["entity_id"] for row in result["results"]] == ["sensor.removed_command"]
    assert result["files_scanned"] == 1
    assert result["files_skipped"] == 1


def test_scan_does_not_report_current_or_disabled_entities(tmp_path):
    """Callers can treat live and deliberately disabled registry entities as valid."""
    _write(
        tmp_path / "groups.yaml",
        """entities:
  - sensor.live
  - sensor.disabled
  - sensor.gone
""",
    )

    result = scan_configuration(
        tmp_path,
        frozenset({"sensor.live", "sensor.disabled"}),
    )

    assert [row["entity_id"] for row in result["results"]] == ["sensor.gone"]


def test_missing_entity_count_is_distinct_from_reference_count(tmp_path):
    """The entity sensor count does not grow for repeated references."""
    _write(
        tmp_path / "groups.yaml",
        """first:
  entities: [sensor.gone, binary_sensor.gone]
second:
  entities: [sensor.gone]
""",
    )

    result = scan_configuration(tmp_path, frozenset())

    assert result["missing_count"] == 3
    assert result["missing_entity_count"] == 2


def test_scan_ignores_function_calls_that_resemble_entity_ids(tmp_path):
    """Method calls such as date.getTime() are not Home Assistant entities."""
    _write(
        tmp_path / "templates.yaml",
        "value: \"{{ date.getTime() }} {{ states('sensor.gone') }}\"\n",
    )

    result = scan_configuration(tmp_path, frozenset())

    assert [row["entity_id"] for row in result["results"]] == ["sensor.gone"]
    assert result["references_checked"] == 1
