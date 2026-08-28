"""Tests for explicit coherence scanner reference exclusions."""

from __future__ import annotations

from pathlib import Path

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
