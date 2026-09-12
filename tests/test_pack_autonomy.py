"""A new pack owns its defaults, schema and selectors without central edits."""

import shutil
import subprocess
import sys
from pathlib import Path


def test_drop_in_pack_validates_inherits_and_round_trips_without_central_edits(
    tmp_path,
):
    """Import a clean process with only one extra pack file in the integration."""
    root = Path(__file__).parents[1]
    package = tmp_path / "alert_manager"
    shutil.copytree(
        root / "custom_components/alert_manager",
        package,
        ignore=shutil.ignore_patterns("__pycache__", "frontend", "translations"),
    )
    (package / "packs/sample.py").write_text(
        """from .base import AutomaticPack, PackConfigField, configuration_fields

PACK = AutomaticPack(
    id="sample", translation_key="sample", prerequisites=(),
    applies=lambda hass, state: True,
    evaluate=lambda hass, state, config: None,
    default_delay=42, default_enabled=False,
    target_filter={"domain": "sensor"},
    config_fields=configuration_fields(
        PackConfigField("strict", "boolean", "strict", True),
        PackConfigField("message", "text", "message", "check"),
        PackConfigField("mode", "select", "mode", "fast", options=("fast", "slow")),
    ),
)
"""
    )
    script = """
import runpy, sys
runpy.run_path("tests/conftest.py")
sys.modules["custom_components.alert_manager"].__path__ = [sys.argv[1]]
from custom_components.alert_manager.config_defaults import DEFAULT_CONFIG
from custom_components.alert_manager.packs import PACKS_BY_ID
from custom_components.alert_manager.pack_migration import migrate_pack_config
from custom_components.alert_manager.pack_settings import resolve_settings
from custom_components.alert_manager.validation import validate_config
from custom_components.alert_manager.yaml_io import dump_config_yaml, parse_config_yaml

pack = PACKS_BY_ID["sample"]
assert pack.as_public_dict(None)["target_filter"] == {"domain": "sensor"}
assert pack.default_config() == DEFAULT_CONFIG["automatic"]["sample"]
assert pack.default_config()["delay"] == 42
config = validate_config({"automatic": {"sample": {
    "enabled": True, "strict": False, "message": "test", "mode": "slow",
    "device_overrides": {"a" * 32: {"strict": True, "message": "device"}},
    "entity_overrides": {"sensor.test": {"strict": False, "mode": "fast"}},
}}})
values, origins = resolve_settings(
    config["automatic"]["sample"], "sensor.test", "a" * 32
)
assert values["strict"] is False
assert values["message"] == "device" and origins["message"] == "device"
assert values["mode"] == "fast" and origins["mode"] == "entity"
assert parse_config_yaml(dump_config_yaml(config)) == config
# Existing exports can omit packs added after they were exported.
import yaml
export = yaml.safe_load(dump_config_yaml(config))
del export["config"]["automatic"]["sample"]
restored = parse_config_yaml(yaml.safe_dump(export))["automatic"]["sample"]
assert restored == pack.default_config()
# V1 migration applies only to packs that existed in that schema.
legacy = validate_config(migrate_pack_config({"global_delay": 600}))
assert legacy["automatic"]["sample"]["delay"] == 42
for key, value in (("strict", "false"), ("message", 5), ("mode", "invalid")):
    for scope in ({key: value}, {"entity_overrides": {"sensor.test": {key: value}}}):
        try:
            validate_config({"automatic": {"sample": scope}})
        except ValueError:
            pass
        else:
            raise AssertionError((key, value))
# No field/default alias can mutate the pack or another configuration.
config["automatic"]["sample"]["device_overrides"].clear()
assert pack.default_config()["device_overrides"] == {}
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(package)],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
