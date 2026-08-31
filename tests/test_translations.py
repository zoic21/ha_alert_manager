"""Translation catalogs, frontend localization and branding tests."""

from __future__ import annotations

import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).parents[1]
INTEGRATION = ROOT / "custom_components" / "alert_manager"
TRANSLATIONS = INTEGRATION / "translations"


def _load(language: str) -> dict:
    return json.loads((TRANSLATIONS / f"{language}.json").read_text())


def _flatten(value: dict, prefix: str = "") -> dict[str, str]:
    result: dict[str, str] = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            result.update(_flatten(item, path))
        else:
            assert isinstance(item, str)
            result[path] = item
    return result


def _placeholders(value: str) -> set[str]:
    return set(re.findall(r"\{([a-zA-Z0-9_]+)\}", value))


def test_translation_files_are_complete_independent_catalogs() -> None:
    """French and English contain the same standalone keys and parameters."""
    english = _flatten(_load("en"))
    french = _flatten(_load("fr"))
    assert english.keys() == french.keys()
    assert all(english.values())
    assert all(french.values())
    assert all(value == value.strip() for value in english.values())
    assert all(value == value.strip() for value in french.values())
    assert "config.step.user.description" in english
    assert "config.abort.single_instance_allowed" in english
    assert "entity.sensor.main_active.name" in english
    assert "entity.sensor.main_pending.name" in english
    assert "entity.sensor.main_acknowledge.name" in english
    assert "entity.sensor.device_main_active.name" in english
    assert "entity.switch.main_monitoring.name" in english
    assert "config_panel.monitoring.notification_message" in english
    assert "services.acknowledge.fields.alert_id.description" in english
    assert "services.unacknowledge.fields.alert_id.description" in english
    assert "config_panel.overview.acknowledged_system" in english
    assert "config_panel.tabs.history" in english
    assert "config_panel.history.empty" in english
    assert "config_panel.history.disabled_title" in english
    assert "config_panel.settings.history_limit" in english
    assert "config_panel.settings.history_clear_confirm" in english
    assert (
        french["config_panel.settings.pending_display_delay"]
        == "Délai d\u2019affichage des alertes à venir"
    )
    assert "config_panel.settings.active_display_delay" not in french
    assert any(key.startswith("config_panel.") for key in english)
    for key in english:
        assert _placeholders(english[key]) == _placeholders(french[key]), key
        assert "[%key:" not in english[key]
        assert "[%key:" not in french[key]


def test_strings_json_is_removed() -> None:
    """Custom integration catalogs are the only translation sources."""
    assert not (INTEGRATION / "strings.json").exists()
    assert sorted(path.name for path in TRANSLATIONS.glob("*.json")) == [
        "en.json",
        "fr.json",
    ]


def test_acknowledgement_services_have_metadata_and_standard_icons() -> None:
    """Home Assistant can discover action fields, translations and icons."""
    services = (INTEGRATION / "services.yaml").read_text()
    assert "acknowledge:" in services
    assert "unacknowledge:" in services
    assert services.count("alert_id:") == 2
    assert services.count("text:") == 2
    icons = json.loads((INTEGRATION / "icons.json").read_text())
    assert set(icons["services"]) == {"acknowledge", "unacknowledge"}


def test_frontend_uses_backend_translation_resources() -> None:
    """The panel requests native backend resources and has no text catalog."""
    frontend = ROOT / "frontend-src"
    source = "\n".join(path.read_text() for path in sorted(frontend.rglob("*.js")))
    assert 'type: "frontend/get_translations"' in source
    assert 'category: "config_panel"' in source
    assert 'integration: "alert_manager"' in source
    assert "component.alert_manager.config_panel.${key}" in source
    assert "const TRANSLATIONS" not in source
    for legacy_text in (
        "Alertes actives",
        "Surveillance enregistrée",
        "Paramètres enregistrés",
        "Aucune règle personnalisée",
        "Redimensionner le volet",
    ):
        assert legacy_text not in source


def test_documented_brand_assets_exist_and_are_referenced() -> None:
    """Both README files use existing project-owned visual assets."""
    mark = ROOT / "docs" / "assets" / "alert-manager-mark.svg"
    logo = ROOT / "docs" / "assets" / "alert-manager-logo.svg"
    icon = INTEGRATION / "brand" / "icon.png"
    assert mark.is_file()
    assert logo.is_file()
    assert icon.is_file()
    assert "prefers-color-scheme: dark" in mark.read_text()
    assert "prefers-color-scheme: dark" in logo.read_text()
    for readme in (ROOT / "README.md", ROOT / "README.fr.md"):
        content = readme.read_text()
        assert "docs/assets/alert-manager-logo.svg" in content
        assert "🇫🇷" in content and "🇬🇧" in content
    with icon.open("rb") as stream:
        assert stream.read(8) == b"\x89PNG\r\n\x1a\n"
        length = struct.unpack(">I", stream.read(4))[0]
        assert stream.read(4) == b"IHDR"
        width, height = struct.unpack(">II", stream.read(length)[:8])
    assert (width, height) == (256, 256)
