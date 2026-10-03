"""Build-time frontend identity prevents stale panel and dashboard caches."""

import hashlib
import json
from pathlib import Path

from custom_components.alert_manager.const import (
    FRONTEND_CACHE_VERSION,
    INTEGRATION_VERSION,
)

ROOT = Path(__file__).parents[1]


def test_cache_version_matches_both_distributed_bundles():
    """A changed bundle requires its generated cache identity in the same commit."""
    digest = hashlib.sha256()
    frontend = ROOT / "custom_components/alert_manager/frontend"
    for name in ("alert-manager-panel.js", "alert-manager-card.js"):
        digest.update(name.encode() + b"\0")
        digest.update((frontend / name).read_bytes())
        digest.update(b"\0")
    assert f"{INTEGRATION_VERSION}.{digest.hexdigest()[:16]}" == FRONTEND_CACHE_VERSION


def test_hacs_enforces_documented_minimum_home_assistant_version():
    """HACS must reject unsupported installations before loading Python code."""
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert hacs["homeassistant"] == "2026.8.0"
    for filename in ("README.md", "README.fr.md"):
        assert "**Home Assistant 2026.8" in (ROOT / filename).read_text()
