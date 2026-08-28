"""Regression tests for blueprint-backed coherence scan objects."""

from __future__ import annotations

from pathlib import Path

from custom_components.alert_manager.coherence import scan_configuration


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_scan_links_blueprint_automation_to_editor(tmp_path):
    """Blueprint automation inputs retain the automation editor target."""
    _write(
        tmp_path / "automations.yaml",
        """- id: '1762512757025'
  alias: 'Thermostat : bureau'
  description: ''
  use_blueprint:
    path: loic/thermostat.yaml
    input:
      thermostat: climate.tado_smart_radiator_thermostat_va2254125312
      mode_maison: input_select.mode_maison
      schedule: schedule.bureau_thermostat_planning
      temperature_night: 17
      temperature_away: 16
      temperature_idle: 18
      override_home_entity: light.bureau_prise
      capteurs_ouverture:
        - binary_sensor.bureau_fenetre
""",
    )

    result = scan_configuration(
        tmp_path,
        frozenset(
            {
                "climate.tado_smart_radiator_thermostat_va2254125312",
                "input_select.mode_maison",
                "schedule.bureau_thermostat_planning",
                "binary_sensor.bureau_fenetre",
            }
        ),
    )

    assert result["missing_count"] == 1
    row = result["results"][0]
    assert row["entity_id"] == "light.bureau_prise"
    assert row["source_type"] == "automation"
    assert row["source_name"] == "Thermostat : bureau"
    assert row["link"] == {
        "type": "navigate",
        "path": "/config/automation/edit/1762512757025",
    }
