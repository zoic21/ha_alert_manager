"""Tests for explicit coherence scanner reference exclusions."""

from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.alert_manager.coherence import scan_configuration


def test_scan_ignores_explicit_entity_like_references(tmp_path: Path) -> None:
    """Configured false positives are ignored without hiding real missing entities."""
    (tmp_path / "configuration.yaml").write_text(
        'value: "script.run script.execute sensor.missing"\n',
        encoding="utf-8",
    )

    result = scan_configuration(tmp_path, frozenset())

    assert [row["entity_id"] for row in result["results"]] == ["sensor.missing"]
    assert result["references_checked"] == 1


def test_scan_applies_custom_ignored_references(tmp_path: Path) -> None:
    """User-configured exact references extend the built-in exclusions."""
    (tmp_path / "configuration.yaml").write_text(
        'value: "toto.plop sensor.missing"\n',
        encoding="utf-8",
    )

    result = scan_configuration(
        tmp_path,
        frozenset({"toto.present"}),
        ignored_entity_references=frozenset({"toto.plop"}),
    )

    assert [row["entity_id"] for row in result["results"]] == ["sensor.missing"]
    assert result["references_checked"] == 1


def test_scan_can_skip_only_the_root_esphome_folder(tmp_path: Path) -> None:
    """The ESPHome option excludes its source tree without hiding other YAML."""
    (tmp_path / "configuration.yaml").write_text(
        "entity_id: sensor.root_missing\n", encoding="utf-8"
    )
    esphome = tmp_path / "esphome"
    esphome.mkdir()
    (esphome / "device.yaml").write_text(
        "entity_id: sensor.esphome_missing\n", encoding="utf-8"
    )

    enabled = scan_configuration(tmp_path, frozenset(), scan_esphome=True)
    disabled = scan_configuration(tmp_path, frozenset(), scan_esphome=False)

    assert {row["entity_id"] for row in enabled["results"]} == {
        "sensor.esphome_missing",
        "sensor.root_missing",
    }
    assert [row["entity_id"] for row in disabled["results"]] == ["sensor.root_missing"]


@pytest.mark.parametrize("scan_esphome", [False, True])
def test_scan_skips_esphome_builds_and_keeps_hidden_configuration(
    tmp_path: Path, scan_esphome: bool
) -> None:
    files = {
        "configuration.yaml": "entity_id: sensor.root_missing\n",
        ".packages/hidden.yaml": "entity_id: sensor.hidden_missing\n",
        "esphome/device.yaml": "entity_id: sensor.device_missing\n",
        "esphome/.esphome/build/dependency/.github/ci.yml": (
            "entity_id: sensor.generated_missing\n"
        ),
        "esphome/.esphome/broken.yml": "entities: [\n",
    }
    for filename, content in files.items():
        path = tmp_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    result = scan_configuration(tmp_path, frozenset(), scan_esphome=scan_esphome)

    expected = {"sensor.root_missing", "sensor.hidden_missing"}
    if scan_esphome:
        expected.add("sensor.device_missing")
    assert {row["entity_id"] for row in result["results"]} == expected
    assert result["files_scanned"] == len(expected)
    assert result["files_skipped"] == 0
