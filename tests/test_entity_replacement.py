"""Focused replacement tests for preview selection, HA APIs and YAML rollback."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
import yaml
from homeassistant.exceptions import HomeAssistantError

from custom_components.alert_manager.entity_replacement import EntityReplacement
from custom_components.alert_manager.websocket import (
    websocket_entity_replacement_apply,
    websocket_entity_replacement_prepare,
    websocket_entity_replacement_preview,
)


@pytest.fixture
def replacement(hass, tmp_path):
    hass.config.path = lambda *parts: str(tmp_path.joinpath(*parts))
    hass.states.set("light.new", "unavailable")
    return EntityReplacement(hass)


def write(tmp_path, filename, content):
    path = tmp_path / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    return path


def selected(preview):
    return [row["id"] for row in preview["replacements"]]


async def apply(replacement, preview, ids=None):
    ids = ids if ids is not None else selected(preview)
    await replacement.async_prepare_apply(preview["preview_id"], ids)
    return await replacement.async_apply(preview["preview_id"], ids)


def test_preview_uses_coherence_names_including_both_blueprint_types(
    replacement, tmp_path
):
    write(
        tmp_path,
        "automations.yaml",
        """- id: heating
  alias: Chauffage bureau
  use_blueprint:
    path: home/heating.yaml
    input:
      lights: [light.old, light.old]
""",
    )
    write(
        tmp_path,
        "scripts.yaml",
        """office:
  alias: Éclairage bureau
  use_blueprint:
    path: home/light.yaml
    input:
      entity: light.old
""",
    )
    write(
        tmp_path,
        "esphome/device.yaml",
        """sensor:
  - platform: homeassistant
    entity_id: light.old
""",
    )
    preview = asyncio.run(replacement.async_preview("light.old", "light.new"))
    assert preview["replacement_count"] == 4
    assert preview["file_count"] == 3
    rows = preview["replacements"]
    assert rows[0]["source_name"] == rows[1]["source_name"] == "Chauffage bureau"
    assert rows[0]["source_type"] == "automation"
    assert rows[0]["line"] == rows[1]["line"] == 6
    assert rows[0]["column"] != rows[1]["column"]
    assert rows[-1]["source_name"] == "Éclairage bureau"
    assert rows[-1]["source_type"] == "script"
    assert len(set(selected(preview))) == 4


def test_selection_preserves_yaml_comments_tags_crlf_and_other_occurrences(
    replacement, tmp_path
):
    original = (
        "# light.old\r\nentities: [light.old, light.old]\r\n"
        "automation: !include automations.yaml\r\npassword: !secret password\r\n"
    )
    path = write(tmp_path, "configuration.yaml", original)

    async def run():
        preview = await replacement.async_preview("light.old", "light.new")
        assert preview["replacement_count"] == 2
        result = await apply(replacement, preview, selected(preview)[:1])
        assert result["replacement_count"] == 1
        assert result["yaml_changed"]

    asyncio.run(run())
    assert path.read_bytes() == original.replace("[light.old", "[light.new").encode()


def test_exact_static_references_and_physical_yaml_aliases(replacement, tmp_path):
    write(
        tmp_path,
        "templates.yaml",
        """entity: &target light.old
entities: [*target, light.old_extra]
state: >-
  {{ states.light.old.state }} {{ states('light.old') }}
description: light.old
url: https://example.org/light.old
file: light.old.yaml
dynamic: "{{ 'light.old' ~ '_extra' }}"
""",
    )
    preview = asyncio.run(replacement.async_preview("light.old", "light.new"))
    assert preview["replacement_count"] == 3
    assert [row["line"] for row in preview["replacements"]] == [1, 4, 4]


@pytest.mark.parametrize(
    "old,new,code",
    [
        ("light.old", "light.missing", "replacement_entity_missing"),
        ("light.old", "light.old", "replacement_entity_invalid"),
        ("invalid", "light.new", "replacement_entity_invalid"),
        ("light.old", "light.new\n", "replacement_entity_invalid"),
    ],
)
def test_target_validation_before_preview(replacement, old, new, code):
    with pytest.raises(ValueError, match=code):
        asyncio.run(replacement.async_preview(old, new))


def test_target_deleted_after_preview_prevents_all_writes(replacement, hass, tmp_path):
    path = write(tmp_path, "esphome/device.yaml", "entity_id: light.old\n")

    async def run():
        preview = await replacement.async_preview("light.old", "light.new")
        hass.states.data.pop("light.new")
        with pytest.raises(ValueError, match="replacement_entity_missing"):
            await apply(replacement, preview)

    asyncio.run(run())
    assert path.read_text() == "entity_id: light.old\n"


def test_registered_entity_without_state_is_a_valid_target(replacement, hass):
    hass.entity_registry.entries["light.registered"] = SimpleNamespace(
        entity_id="light.registered", platform="test"
    )
    preview = asyncio.run(replacement.async_preview("light.old", "light.registered"))
    assert preview["replacement_count"] == 0


def test_changed_file_and_forged_selection_are_rejected(replacement, tmp_path):
    path = write(tmp_path, "config.yaml", "entity_id: light.old\n")

    async def run():
        preview = await replacement.async_preview("light.old", "light.new")
        with pytest.raises(ValueError, match="replacement_selection_invalid"):
            await apply(replacement, preview, ["../../outside:0"])
        path.write_text("entity_id: light.old\nname: edited\n")
        with pytest.raises(ValueError, match="replacement_preview_stale"):
            await apply(replacement, preview)

    asyncio.run(run())
    assert path.read_text().endswith("name: edited\n")


def test_mapping_key_collision_invalidates_entire_batch(replacement, tmp_path):
    first = write(tmp_path, "a.yaml", "entity_id: light.old\n")
    scene = write(
        tmp_path,
        "scene_custom.yaml",
        """- name: Lights
  entities:
    light.old: on
    light.new: off
""",
    )
    original = scene.read_bytes()

    async def run():
        preview = await replacement.async_preview("light.old", "light.new")
        with pytest.raises(ValueError, match="replacement_yaml_invalid"):
            await apply(replacement, preview)

    asyncio.run(run())
    assert first.read_text() == "entity_id: light.old\n"
    assert scene.read_bytes() == original


def test_post_write_yaml_failure_restores_every_file(
    replacement, tmp_path, monkeypatch
):
    from custom_components.alert_manager import entity_replacement as module

    paths = [
        write(tmp_path, f"{name}.yaml", "entity_id: light.old\n") for name in ("a", "b")
    ]
    real_write = module.write_utf8_file
    calls = []

    def corrupt_second(filename, content, **kwargs):
        calls.append(filename)
        if len(calls) == 2:
            content = b"entities: [\n"
        real_write(filename, content, **kwargs)

    monkeypatch.setattr(module, "write_utf8_file", corrupt_second)

    async def run():
        preview = await replacement.async_preview("light.old", "light.new")
        with pytest.raises(ValueError, match="replacement_failed"):
            await apply(replacement, preview)

    asyncio.run(run())
    assert len(calls) == 4
    assert all(path.read_text() == "entity_id: light.old\n" for path in paths)


def test_native_editor_plan_and_final_yaml_verification(
    replacement, tmp_path, monkeypatch
):
    from custom_components.alert_manager import entity_replacement as module

    files = {
        "automations.yaml": [
            {
                "id": "office",
                "alias": "Office",
                "use_blueprint": {
                    "path": "home/test.yaml",
                    "input": {"entity": "light.old"},
                },
            }
        ],
        "scripts.yaml": {
            "test": {
                "alias": "Test",
                "sequence": [
                    {"action": "light.turn_on", "target": {"entity_id": "light.old"}}
                ],
            }
        },
        "scenes.yaml": [
            {"id": "office", "name": "Office", "entities": {"light.old": "on"}}
        ],
    }
    for filename, value in files.items():
        write(tmp_path, filename, yaml.safe_dump(value, sort_keys=False))

    async def run():
        preview = await replacement.async_preview("light.old", "light.new")
        plan = await replacement.async_prepare_apply(
            preview["preview_id"], selected(preview)
        )
        assert {update["domain"] for update in plan["native_updates"]} == {
            "automation",
            "script",
            "scene",
        }
        for update in plan["native_updates"]:
            filename = {
                "automation": "automations.yaml",
                "script": "scripts.yaml",
                "scene": "scenes.yaml",
            }[update["domain"]]
            value = files[filename]
            if update["domain"] == "script":
                value[update["key"]] = update["after"]
            else:
                value[0] = update["after"]
            write(tmp_path, filename, yaml.safe_dump(value, sort_keys=False))
        monkeypatch.setattr(
            module,
            "save_yaml",
            lambda *_args: pytest.fail(
                "Native editor files must only be saved through HA REST"
            ),
        )
        result = await replacement.async_apply(preview["preview_id"], selected(preview))
        assert result["replacement_count"] == 3
        assert result["yaml_changed"] is False
        with pytest.raises(ValueError, match="replacement_preview_stale"):
            await replacement.async_apply(preview["preview_id"], selected(preview))

    asyncio.run(run())


class Dashboard:
    mode = "storage"
    config = {"id": "office", "title": "Bureau"}

    def __init__(self):
        self.value = {
            "views": [{"title": "Lumières", "cards": [{"entity": "light.old"}]}]
        }
        self.saved = []
        self.fail = False

    async def async_get_info(self):
        return {"mode": "storage"}

    async def async_load(self, force):
        return self.value

    async def async_save(self, value):
        self.value = value
        self.saved.append(deepcopy(value))
        if self.fail and len(self.saved) == 1:
            raise HomeAssistantError("write failed")


def test_storage_dashboard_uses_live_native_api(replacement, hass, tmp_path):
    dashboard = Dashboard()
    hass.data["lovelace"] = SimpleNamespace(dashboards={"office": dashboard})
    storage_path = write(
        tmp_path,
        ".storage/lovelace.office",
        json.dumps({"data": {"config": {"entity": "light.disk_stale"}}}),
    )
    original = storage_path.read_bytes()

    async def run():
        preview = await replacement.async_preview("light.old", "light.new")
        assert preview["replacements"][0]["source_name"] == "Bureau · Lumières"
        assert preview["replacements"][0]["file"] == ".storage/lovelace.office"
        result = await apply(replacement, preview)
        assert not result["yaml_changed"]

    asyncio.run(run())
    assert len(dashboard.saved) == 1
    assert dashboard.value["views"][0]["cards"][0]["entity"] == "light.new"
    assert storage_path.read_bytes() == original


def test_dashboard_failure_rolls_back_yaml_and_live_dashboard(
    replacement, hass, tmp_path
):
    dashboard = Dashboard()
    dashboard.fail = True
    original = deepcopy(dashboard.value)
    hass.data["lovelace"] = SimpleNamespace(dashboards={"office": dashboard})
    path = write(tmp_path, "esphome/device.yaml", "entity_id: light.old\n")

    async def run():
        preview = await replacement.async_preview("light.old", "light.new")
        with pytest.raises(ValueError, match="replacement_failed"):
            await apply(replacement, preview)

    asyncio.run(run())
    assert dashboard.value == original
    assert path.read_text() == "entity_id: light.old\n"


def test_esphome_exclusions_invalid_files_and_read_only_storage(replacement, tmp_path):
    write(tmp_path, "esphome/device.yaml", "entity_id: light.old\n")
    write(tmp_path, "custom_components/config.yaml", "entity_id: light.old\n")
    write(tmp_path, "blueprints/automation/test.yaml", "entity_id: light.old\n")
    write(tmp_path, "bad.yaml", "entities: [\n")
    write(
        tmp_path, ".storage/core.config_entries", json.dumps({"entity_id": "light.old"})
    )
    preview = asyncio.run(
        replacement.async_preview("light.old", "light.new", scan_esphome=False)
    )
    assert not preview["replacements"]
    assert preview["files_skipped"] == 1
    preview = asyncio.run(replacement.async_preview("light.old", "light.new"))
    assert preview["replacement_count"] == 1
    assert preview["replacements"][0]["file"] == "esphome/device.yaml"


@pytest.mark.parametrize(
    "handler,payload",
    [
        (
            websocket_entity_replacement_preview,
            {"old_entity_id": "light.old", "new_entity_id": "light.new"},
        ),
        (
            websocket_entity_replacement_prepare,
            {"preview_id": "a" * 32, "occurrence_ids": ["test:0"]},
        ),
        (
            websocket_entity_replacement_apply,
            {"preview_id": "a" * 32, "occurrence_ids": ["test:0"]},
        ),
    ],
)
def test_all_replacement_endpoints_require_admin(hass, handler, payload):
    from test_websocket import Connection

    connection = Connection(admin=False)
    asyncio.run(handler(hass, connection, {"id": 1, **payload}))
    assert connection.errors[0][1] == "unauthorized"
    assert not connection.results


def test_references_do_not_rename_definitions(replacement, tmp_path):
    path = write(
        tmp_path,
        "templates.yaml",
        """template:
  - sensor:
      - name: light.old
        unique_id: light.old
        state: "{{ states('light.old') }}"
""",
    )

    async def run():
        preview = await replacement.async_preview("light.old", "light.new")
        assert preview["replacement_count"] == 1
        await apply(replacement, preview)

    asyncio.run(run())
    value = yaml.safe_load(path.read_text())["template"][0]["sensor"][0]
    assert value["name"] == value["unique_id"] == "light.old"
    assert value["state"] == "{{ states('light.new') }}"


def test_literal_entity_id_ending_in_underscore_is_not_a_dynamic_prefix(
    replacement, tmp_path
):
    write(tmp_path, "config.yaml", "entity_id: light.old_\n")
    preview = asyncio.run(replacement.async_preview("light.old_", "light.new"))
    assert preview["replacement_count"] == 1


@pytest.mark.parametrize("tag", ["!secret", "!input", "!include", "!env_var"])
def test_tagged_scalars_are_not_entity_references(replacement, tmp_path, tag):
    original = f"entity_id: light.old\nvalue: {tag} light.old\n"
    path = write(tmp_path, "configuration.yaml", original)

    async def run():
        preview = await replacement.async_preview("light.old", "light.new")
        assert preview["replacement_count"] == 1
        await apply(replacement, preview)

    asyncio.run(run())
    assert path.read_text() == original.replace(
        "entity_id: light.old", "entity_id: light.new"
    )


@pytest.mark.parametrize(
    "filename,content",
    [
        (
            "automations.yaml",
            "- id: changed\n  triggers:\n    - trigger: state\n"
            "      entity_id: light.old\n- id: untouched\n  variables:\n"
            "    token: !secret missing\n    input: !input light.old\n"
            "    sequence: !include missing.yaml\n",
        ),
        (
            "scripts.yaml",
            "changed:\n  sequence:\n    - action: light.turn_on\n"
            "      target:\n        entity_id: light.old\nuntouched:\n"
            "  variables:\n    token: !secret missing\n"
            "  sequence: !include missing.yaml\n",
        ),
        (
            "scenes.yaml",
            "- id: changed\n  name: Lights\n  entities:\n    light.old: on\n"
            "- id: untouched\n  name: Other\n  entities: !include missing.yaml\n",
        ),
    ],
)
def test_tags_in_untouched_native_objects_use_text_saves(
    replacement, tmp_path, monkeypatch, filename, content
):
    from custom_components.alert_manager import entity_replacement as module

    original = content.replace("\n", "\r\n")
    path = write(tmp_path, filename, original)
    monkeypatch.setattr(
        module, "parse_yaml", lambda *_args: pytest.fail("Tags must not be resolved")
    )

    async def run():
        preview = await replacement.async_preview("light.old", "light.new")
        assert preview["replacement_count"] == 1
        plan = await replacement.async_prepare_apply(
            preview["preview_id"], selected(preview)
        )
        assert plan["native_updates"] == []
        result = await replacement.async_apply(preview["preview_id"], selected(preview))
        assert result["yaml_changed"] is True

    asyncio.run(run())
    assert path.read_bytes() == original.replace("light.old", "light.new", 1).encode()


def test_exclamation_marks_in_comments_and_strings_keep_native_editor_path(
    replacement, tmp_path
):
    write(
        tmp_path,
        "automations.yaml",
        '# !secret missing\n- id: test\n  alias: "Literal !include example"\n'
        "  triggers:\n    - trigger: state\n      entity_id: light.old\n",
    )

    async def run():
        preview = await replacement.async_preview("light.old", "light.new")
        plan = await replacement.async_prepare_apply(
            preview["preview_id"], selected(preview)
        )
        assert len(plan["native_updates"]) == 1
        assert plan["native_updates"][0]["domain"] == "automation"

    asyncio.run(run())


def test_unexpected_write_error_rolls_back_and_preserves_original_error(
    replacement, tmp_path, monkeypatch
):
    from custom_components.alert_manager import entity_replacement as module

    paths = [
        write(tmp_path, f"{name}.yaml", "entity_id: light.old\n") for name in ("a", "b")
    ]
    real_write = module.write_utf8_file
    failure = RuntimeError("unexpected persistence failure")
    calls = []

    def fail_after_second_write(filename, content, **kwargs):
        calls.append(filename)
        real_write(filename, content, **kwargs)
        if len(calls) == 2:
            raise failure

    monkeypatch.setattr(module, "write_utf8_file", fail_after_second_write)

    async def run():
        preview = await replacement.async_preview("light.old", "light.new")
        with pytest.raises(ValueError, match=r"^replacement_failed$") as caught:
            await apply(replacement, preview)
        assert caught.value.__cause__ is failure

    asyncio.run(run())
    assert len(calls) == 4
    assert all(path.read_text() == "entity_id: light.old\n" for path in paths)


def test_failed_restore_does_not_stop_other_restores(
    replacement, tmp_path, monkeypatch, caplog
):
    from custom_components.alert_manager import entity_replacement as module

    original = "entity_id: light.old\n"
    paths = [write(tmp_path, f"{name}.yaml", original) for name in ("a", "b", "c")]
    real_save = module.save_yaml
    failure = RuntimeError("apply failed")
    calls = []

    def failing_save(item, content):
        calls.append(item.source.relative_path)
        if item.source.relative_path == "c.yaml" and content == original:
            raise OSError("restore failed")
        real_save(item, content)
        if len(calls) == 3:
            raise failure

    monkeypatch.setattr(module, "save_yaml", failing_save)

    async def run():
        preview = await replacement.async_preview("light.old", "light.new")
        with pytest.raises(
            ValueError, match=r"^replacement_rollback_failed$"
        ) as caught:
            await apply(replacement, preview)
        assert caught.value.__cause__ is failure

    asyncio.run(run())
    assert calls == ["a.yaml", "b.yaml", "c.yaml", "c.yaml", "b.yaml", "a.yaml"]
    assert all(path.read_text() == original for path in paths[:2])
    assert paths[2].read_text() == "entity_id: light.new\n"
    assert "Could not restore replacement source c.yaml" in caplog.text


def test_socket_cancellation_during_rollback_finishes_restoring(
    replacement, hass, tmp_path, monkeypatch
):
    from custom_components.alert_manager import entity_replacement as module

    paths = [
        write(tmp_path, f"{name}.yaml", "entity_id: light.old\n") for name in ("a", "b")
    ]

    async def run():
        preview = await replacement.async_preview("light.old", "light.new")
        ids = selected(preview)
        await replacement.async_prepare_apply(preview["preview_id"], ids)
        executor = hass.async_add_executor_job
        restoring = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def interrupted_executor(target, *args):
            nonlocal calls
            if target is module.save_yaml:
                calls += 1
                if calls == 2:
                    raise OSError("write failed")
                if calls == 3:
                    restoring.set()
                    await release.wait()
            return await executor(target, *args)

        monkeypatch.setattr(hass, "async_add_executor_job", interrupted_executor)
        task = asyncio.create_task(replacement.async_apply(preview["preview_id"], ids))
        await asyncio.wait_for(restoring.wait(), timeout=2)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert calls == 4

    asyncio.run(run())
    assert all(path.read_text() == "entity_id: light.old\n" for path in paths)
