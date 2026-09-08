"""Notification profile and effective policy tests."""

from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest
import yaml
from homeassistant.exceptions import HomeAssistantError

from custom_components.alert_manager.const import (
    DEFAULT_CONFIG,
    EVENT_ALERT_STARTED,
    MAX_NOTIFICATION_LABELS,
    MAX_NOTIFICATION_TARGETS,
)
from custom_components.alert_manager.manager import AlertManager
from custom_components.alert_manager.notifications import (
    NotificationManager,
    profile_matches_labels,
    resolve_notification_policy,
)
from custom_components.alert_manager.validation import validate_config
from custom_components.alert_manager.yaml_io import (
    dump_config_yaml,
    parse_config_yaml,
    parse_notification_profile_yaml,
)


def _profile() -> dict:
    return {
        "id": "loic",
        "name": "Loïc",
        "enabled": True,
        "targets": ["notify.mobile_app_phone", "notify.mobile_app_tablet"],
        "label_ids": ["important"],
        "default_policy": {
            "notify_on_start": True,
            "notify_on_resolved": True,
            "reminder_interval": None,
        },
        "exceptions": [
            {
                "selector_type": "label",
                "selector_id": "important",
                "reminder_interval": 1800,
            },
            {
                "selector_type": "label",
                "selector_id": "secondary",
                "reminder_interval": 3600,
            },
        ],
    }


def test_policy_resolution_is_partial_and_uses_documented_priority() -> None:
    """First matching label overrides profile defaults field by field."""
    config = validate_config(
        {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [_profile()]}
    )
    profile = config["notification_profiles"][0]

    effective = resolve_notification_policy(
        profile,
        label_ids={"important", "secondary"},
    )

    assert effective.as_dict() == {
        "notify_on_start": True,
        "notify_on_resolved": True,
        "reminder_interval": 1800,
    }


def test_first_matching_label_exception_wins_in_explicit_list_order() -> None:
    """Several entity/device labels never introduce hidden scoring."""
    profile = validate_config(
        {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [_profile()]}
    )["notification_profiles"][0]

    effective = resolve_notification_policy(
        profile,
        label_ids={"secondary", "important"},
    )

    assert effective.reminder_interval == 1800


def test_profile_label_filter_matches_entity_or_device_labels() -> None:
    """The resolver accepts the cached union supplied by the runtime."""
    profile = validate_config(
        {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [_profile()]}
    )["notification_profiles"][0]

    assert profile_matches_labels(profile, {"important"})
    assert profile_matches_labels(profile, {"unrelated", "important"})
    assert not profile_matches_labels(profile, {"unrelated"})


def test_identical_notification_profile_update_is_a_no_op(hass, entry) -> None:
    """Resubmitting unchanged profiles avoids persistence and reevaluation."""

    async def scenario() -> None:
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        saves_before = hass.store_save_count

        result = await manager.async_update_config({"notification_profiles": []})

        assert result["notification_profiles"] == []
        assert hass.store_save_count == saves_before
        assert manager.notification_runtime._accept_events is True
        await manager.async_unload()

    asyncio.run(scenario())


def test_profile_only_update_skips_alert_reevaluation(hass, entry) -> None:
    """Saving profiles updates their runtime without scanning all entities."""

    async def scenario() -> None:
        manager = AlertManager(hass, entry)
        await manager.async_setup()

        async def unexpected_evaluation(**_kwargs) -> bool:
            raise AssertionError("notification profile update reevaluated alerts")

        manager.async_evaluate_all = unexpected_evaluation
        result = await manager.async_update_config(
            {"notification_profiles": [_profile()]}
        )

        assert result["notification_profiles"][0]["id"] == "loic"
        assert manager.notification_runtime._accept_events is True
        assert manager.notification_runtime._events_pause_depth == 0
        await manager.async_unload()

    asyncio.run(scenario())


def test_profile_update_failure_always_resumes_notification_events(hass, entry) -> None:
    """A failed profile update resumes delivery without losing a pending batch."""

    async def scenario() -> None:
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        profile = _profile()
        profile["label_ids"] = []
        await manager.async_update_config({"notification_profiles": [profile]})
        alert_id = "unavailable:sensor.test"
        await manager.notification_runtime._async_handle_event(
            EVENT_ALERT_STARTED,
            {
                "id": alert_id,
                "entity_id": "sensor.test",
                "name": "Test",
                "type": "unavailable",
                "condition": "Unavailable",
            },
        )
        assert (
            alert_id in manager.notification_runtime._batches[("loic", "started")].items
        )

        async def fail_save(*_args, **_kwargs) -> None:
            raise RuntimeError("storage unavailable")

        original_save = manager.storage.async_save
        manager.storage.async_save = fail_save
        changed_profile = deepcopy(profile)
        changed_profile["name"] = "Changed"
        with pytest.raises(RuntimeError, match="storage unavailable"):
            await manager.async_update_config(
                {"notification_profiles": [changed_profile]}
            )

        assert manager.notification_runtime._accept_events is True
        assert manager.notification_runtime._events_pause_depth == 0
        assert (
            alert_id in manager.notification_runtime._batches[("loic", "started")].items
        )
        manager.storage.async_save = original_save
        await manager.async_unload()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"targets": ["sensor.invalid"]}, "invalid notify entity"),
        ({"primary_targets": ["notify.legacy"]}, "Unknown .*primary_targets"),
        ({"fallback_targets": ["notify.legacy"]}, "Unknown .*fallback_targets"),
        (
            {
                "exceptions": [
                    {
                        "selector_type": "pack",
                        "selector_id": "unknown",
                        "notify_on_start": False,
                    }
                ]
            },
            "selector_type is invalid",
        ),
        (
            {"exceptions": [{"selector_type": "label", "selector_id": "freezer"}]},
            "at least one policy field",
        ),
    ],
)
def test_invalid_profiles_are_rejected(change: dict, message: str) -> None:
    """Untrusted WebSocket and YAML profile data is bounded and strict."""
    profile = {**_profile(), **change}
    with pytest.raises(ValueError, match=message):
        validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [profile]}
        )


@pytest.mark.parametrize(
    ("field", "value", "maximum"),
    [
        (
            "targets",
            "notify.mobile_app_phone",
            MAX_NOTIFICATION_TARGETS,
        ),
        ("label_ids", "important", MAX_NOTIFICATION_LABELS),
    ],
)
def test_profile_list_limits_apply_before_deduplication(
    field: str, value: str, maximum: int
) -> None:
    """Duplicate values cannot bypass raw input complexity limits."""
    profile = _profile()
    profile[field] = [value] * (maximum + 1)

    with pytest.raises(ValueError, match=f"at most {maximum} items"):
        validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [profile]}
        )


def test_policy_rejects_non_string_field_names_with_stable_error() -> None:
    """Malformed YAML mappings raise a validation error instead of TypeError."""
    profile = _profile()
    profile["default_policy"][1] = True

    with pytest.raises(ValueError, match="field names must be strings"):
        validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [profile]}
        )


def test_rule_deletion_cleans_runtime_and_preserves_label_exceptions(
    hass, entry
) -> None:
    """Deleting a rule clears pending delivery and reminders, preserving labels."""

    async def scenario() -> None:
        hass.states.set("sensor.test", "10")
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        rule = await manager.async_create_rule(
            {
                "name": "Hot sensor",
                "entity_ids": ["sensor.test"],
                "operator": "above",
                "value": 8,
                "duration": 0,
            }
        )
        profile = _profile()
        profile["label_ids"] = []
        profile["default_policy"]["reminder_interval"] = 300
        await manager.async_update_config({"notification_profiles": [profile]})
        alert_id = f"rule:{rule['id']}:sensor.test"
        await manager.notification_runtime._async_handle_event(
            EVENT_ALERT_STARTED,
            {
                "id": alert_id,
                "entity_id": "sensor.test",
                "name": "Hot sensor",
                "type": "custom_rule",
                "rule_id": rule["id"],
                "condition": "Above 8",
            },
        )
        assert alert_id in manager.notification_runtime._runtime["loic"]
        assert (
            alert_id in manager.notification_runtime._batches[("loic", "started")].items
        )

        exceptions_before_deletion = deepcopy(
            manager.get_config()["notification_profiles"][0]["exceptions"]
        )
        await manager.async_delete_rule(rule["id"])

        configured_profile = manager.get_config()["notification_profiles"][0]
        assert configured_profile["exceptions"] == exceptions_before_deletion
        assert all(
            alert_id not in profile_runtime
            for profile_runtime in manager.notification_runtime._runtime.values()
        )
        assert all(
            alert_id not in batch.items
            for batch in manager.notification_runtime._batches.values()
        )
        await manager.async_unload()

    asyncio.run(scenario())


def test_yaml_round_trip_preserves_rule_labels_and_label_exceptions() -> None:
    """Portable exports omit internal rule ids without losing profile routing."""
    config = deepcopy(DEFAULT_CONFIG)
    config["rules"] = [
        {
            "id": "freezer",
            "name": "Freezer",
            "label_ids": ["important"],
            "entity_ids": ["sensor.freezer"],
            "operator": "above",
            "value": 8,
            "duration": 60,
        }
    ]
    config["notification_profiles"] = [_profile()]
    config["automatic"]["battery"]["label_ids"] = ["important"]

    exported = dump_config_yaml(config)
    imported = parse_config_yaml(exported)

    imported_rule_id = imported["rules"][0]["id"]
    label_exception = imported["notification_profiles"][0]["exceptions"][0]
    assert "id: freezer" not in exported
    assert "@rule:" not in exported
    assert imported_rule_id != "freezer"
    assert imported["rules"][0]["label_ids"] == ["important"]
    assert imported["automatic"]["battery"]["label_ids"] == ["important"]
    assert label_exception["selector_ids"] == ["important"]


def test_delivery_attempts_every_target_when_one_fails(hass) -> None:
    """One broken notification entity does not block the other recipients."""
    attempted: list[str] = []

    async def send(_domain, _service, _data, **kwargs):
        target = kwargs["target"]["entity_id"]
        attempted.append(target)
        if target == "notify.failed":
            raise HomeAssistantError("destination unavailable")

    hass.services.async_call = send
    manager = NotificationManager(hass, lambda: [])
    result = asyncio.run(
        manager.async_send(
            targets=["notify.failed", "notify.ok"],
            title="Title",
            message="Message",
        )
    )

    assert result["success"] is True
    assert result["delivered_targets"] == ["notify.ok"]
    assert attempted == ["notify.failed", "notify.ok"]


def test_test_notification_attempts_all_targets_without_creating_runtime_state(
    hass,
) -> None:
    """The profile test follows real delivery behavior and remains stateless."""
    profile = validate_config(
        {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [_profile()]}
    )["notification_profiles"][0]
    attempted: list[tuple[str, str, str]] = []

    async def send(_domain, _service, data, **kwargs):
        target = kwargs["target"]["entity_id"]
        attempted.append((target, data["title"], data["message"]))
        if target == "notify.mobile_app_phone":
            raise HomeAssistantError("phone unavailable")

    hass.services.async_call = send
    manager = NotificationManager(hass, lambda: [profile])
    result = asyncio.run(manager.async_test_profile("loic"))

    assert result["success"] is True
    assert result["delivered_targets"] == ["notify.mobile_app_tablet"]
    assert [item[0] for item in attempted] == [
        "notify.mobile_app_phone",
        "notify.mobile_app_tablet",
    ]
    assert attempted[0][1] == "Alert Manager — Test notification"
    assert attempted[0][2] == "This confirms that the notification profile works."


def test_profile_test_does_not_increment_recent_usage(hass, entry) -> None:
    """Successful test deliveries stay outside production profile statistics."""

    async def scenario() -> None:
        profile = _profile()
        profile["label_ids"] = []
        profile["exceptions"] = []
        manager = AlertManager(hass, entry)
        await manager.async_setup()
        await manager.async_update_config({"notification_profiles": [profile]})

        before = manager.statistics.snapshot()
        await manager.async_test_notification_profile("loic")
        assert manager.statistics.snapshot() == before

        assert manager.notification_runtime.usage_snapshot() == {
            "last_24h": {"loic": 0}
        }
        await manager.async_unload()

    asyncio.run(scenario())


@pytest.mark.parametrize("target", ["notify.iphone_de_loic", "notify.renamed_phone"])
@pytest.mark.parametrize(
    "click_url",
    ["/alert-manager?alert=battery%3Asensor.test", "/alert-manager/history"],
)
def test_mobile_app_delivery_keeps_click_target_in_transport_layer(
    hass, registry_entry, config_entry, target, click_url
) -> None:
    """Resolve the mobile action even when the entity has been renamed."""
    entry = config_entry(hass, "mobile_app")
    entry.data = {"device_name": "iPhone de Loïc"}
    registry_entry(hass, target, platform="mobile_app", config_entry_id=entry.entry_id)
    received = []

    async def send(call):
        received.append(call.data)

    hass.services.async_register("notify", "mobile_app_iphone_de_loic", send)
    # An unrelated action matching the entity must never receive the message.
    hass.services.async_register("notify", target.partition(".")[2], send)
    manager = NotificationManager(hass, lambda: [])

    result = asyncio.run(
        manager.async_send(
            targets=[target], title="Title", message="Message", click_url=click_url
        )
    )

    assert result["delivered_targets"] == [target]
    assert len(hass.services.calls) == 1
    assert hass.services.calls[0]["service"] == "mobile_app_iphone_de_loic"
    assert received == [
        {
            "title": "Title",
            "message": "Message",
            "data": {"url": click_url, "clickAction": click_url},
        }
    ]


@pytest.mark.parametrize(
    "case",
    [
        "unregistered",
        "other_platform",
        "no_config_id",
        "missing_entry",
        "wrong_domain",
        "missing_name",
        "missing_service",
    ],
)
def test_notification_fallback_preserves_message_without_link(
    hass, registry_entry, config_entry, case
) -> None:
    """Unavailable mobile routing uses the selected entity with plain text only."""

    async def send(_call):
        pass

    hass.services.async_register("notify", "send_message", send)
    entry = config_entry(hass, "other" if case == "wrong_domain" else "mobile_app")
    entry.data = {} if case == "missing_name" else {"device_name": "iPhone de Loïc"}
    if case != "unregistered":
        registry_entry(
            hass,
            "notify.iphone_de_loic",
            platform="other" if case == "other_platform" else "mobile_app",
            config_entry_id=(
                None
                if case == "no_config_id"
                else "missing"
                if case == "missing_entry"
                else entry.entry_id
            ),
        )
    manager = NotificationManager(hass, lambda: [])
    result = asyncio.run(
        manager.async_send(
            targets=["notify.iphone_de_loic"],
            title="Title",
            message="Message",
            click_url="/alert-manager/history",
        )
    )
    assert result["delivered_targets"] == ["notify.iphone_de_loic"]
    assert len(hass.services.calls) == 1
    call = hass.services.calls[0]
    assert call["service"] == "send_message"
    assert call["target"] == {"entity_id": "notify.iphone_de_loic"}
    assert call["data"] == {"title": "Title", "message": "Message"}


def test_unexpected_target_failure_is_isolated(hass) -> None:
    """A broken notify integration cannot leak into alert lifecycle tasks."""

    async def send(_domain, _service, _data, **kwargs):
        if kwargs["target"]["entity_id"] == "notify.broken":
            raise RuntimeError("broken integration")

    hass.services.async_call = send
    manager = NotificationManager(hass, lambda: [])

    result = asyncio.run(
        manager.async_send(
            targets=["notify.broken", "notify.working"],
            title="Title",
            message="Message",
        )
    )

    assert result["success"] is True
    assert result["delivered_targets"] == ["notify.working"]


def test_rule_notification_exceptions_are_no_longer_supported():
    """Removed development-only selectors are rejected by the API and YAML boundary."""
    profile = _profile()
    profile["exceptions"] = [
        {
            "selector_type": "rule",
            "selector_id": "freezer",
            "notify_on_start": True,
        }
    ]
    with pytest.raises(ValueError, match="selector_type"):
        validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [profile]}
        )


@pytest.mark.parametrize("labels", ["cold", [None], [123], [""]])
def test_pack_labels_reject_invalid_values(labels):
    """Pack labels use the same backend validation as rule labels."""
    with pytest.raises(ValueError):
        validate_config({"automatic": {"battery": {"label_ids": labels}}})


def test_legacy_configuration_without_pack_labels_still_imports():
    """Existing detector configuration remains compatible without a migration."""
    config = deepcopy(DEFAULT_CONFIG)
    for pack in config["automatic"].values():
        pack.pop("label_ids", None)
    # dump_config_yaml normalizes defaults, so remove labels from the export itself.
    exported = dump_config_yaml(config).replace("      label_ids: []\n", "")
    imported = parse_config_yaml(exported)
    assert all(pack["label_ids"] == [] for pack in imported["automatic"].values())


@pytest.mark.parametrize("delay", [10, 30, 300])
def test_notification_batch_delay_valid(delay):
    assert (
        validate_config({"notification_batch_delay": delay})["notification_batch_delay"]
        == delay
    )


@pytest.mark.parametrize("delay", [9, 301, True, None, "30", 30.5])
def test_notification_batch_delay_invalid(delay):
    with pytest.raises(ValueError, match="notification_batch_delay"):
        validate_config({"notification_batch_delay": delay})


def test_notification_batch_delay_default_and_yaml_roundtrip():
    from custom_components.alert_manager.yaml_io import (
        dump_config_yaml,
        parse_config_yaml,
    )

    assert validate_config({})["notification_batch_delay"] == 30
    config = validate_config({"notification_batch_delay": 120})
    assert (
        parse_config_yaml(dump_config_yaml(config))["notification_batch_delay"] == 120
    )


@pytest.mark.parametrize(
    ("labels", "interval"),
    [
        ({"important", "cold"}, 1800),
        ({"important", "cold", "secondary"}, 1800),
        ({"important"}, None),
        ({"cold"}, None),
        ({"cold", "secondary"}, 3600),
        ({"secondary"}, 3600),
        ({"unrelated"}, None),
        (set(), None),
    ],
)
def test_exception_requires_all_selected_labels(labels, interval):
    profile = _profile()
    first = profile["exceptions"][0]
    del first["selector_id"]
    first["selector_ids"] = ["important", "cold"]
    config = validate_config(
        {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [profile]}
    )
    normalized = config["notification_profiles"][0]
    assert (
        resolve_notification_policy(normalized, label_ids=labels).reminder_interval
        == interval
    )
    assert validate_config(config) == config
    assert (
        parse_config_yaml(dump_config_yaml(config))["notification_profiles"]
        == config["notification_profiles"]
    )


@pytest.mark.parametrize(
    "ids", [[], "important", [123], [""], ["a"] * (MAX_NOTIFICATION_LABELS + 1)]
)
def test_exception_label_list_is_validated(ids):
    profile = _profile()
    first = profile["exceptions"][0]
    del first["selector_id"]
    first["selector_ids"] = ids
    with pytest.raises(ValueError, match="selector_ids"):
        validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [profile]}
        )


def test_exception_labels_deduplicate_and_reject_overlaps_or_ambiguous_legacy_input():
    profile = _profile()
    first = profile["exceptions"][0]
    first["selector_ids"] = ["important", "important", "cold"]
    with pytest.raises(ValueError, match="cannot mix"):
        validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [profile]}
        )
    del first["selector_id"]
    config = validate_config(
        {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [profile]}
    )
    assert config["notification_profiles"][0]["exceptions"][0]["selector_ids"] == [
        "important",
        "cold",
    ]
    first["selector_ids"].append("secondary")
    with pytest.raises(ValueError, match="duplicate selector"):
        validate_config(
            {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [profile]}
        )


def test_notification_yaml_roundtrip_and_executor(hass, entry, monkeypatch):
    """The complete profile uses the shared validator, off the event loop."""
    manager = AlertManager(hass, entry)
    asyncio.run(manager.async_setup())
    profile = _profile()
    profile["enabled"] = False
    profile["exceptions"][0]["notify_on_start"] = False
    profile["exceptions"][1]["reminder_interval"] = None
    expected = validate_config(
        {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [profile]}
    )["notification_profiles"][0]
    del profile["id"]
    original = hass.async_add_executor_job
    calls = []

    async def executor(target, *args):
        calls.append(target)
        return await original(target, *args)

    monkeypatch.setattr(hass, "async_add_executor_job", executor)
    result = asyncio.run(
        manager.async_validate_notification_profile_yaml(
            yaml.safe_dump(profile), "loic"
        )
    )
    assert result == expected
    assert calls == [parse_notification_profile_yaml]
    assert manager.config["notification_profiles"] == []


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "[]",
        "name: [",
        "name: A\nname: B",
        "id: other",
        "name: !!python/object:builtins.object {}",
        "enabled: true\nenabled: false",
    ],
)
def test_notification_yaml_rejects_invalid_documents(raw):
    """Unsafe, malformed, duplicate and identity-changing YAML cannot be saved."""
    with pytest.raises(ValueError):
        parse_notification_profile_yaml(raw, "loic")


@pytest.mark.parametrize(
    "change",
    [
        {"enabled": "false"},
        {"targets": ["light.test"]},
        {"unexpected": True},
        {"default_policy": {"notify_on_start": True, "unexpected": True}},
        {"exceptions": [{"selector_type": "label", "selector_ids": ["test"]}]},
    ],
)
def test_notification_yaml_uses_complete_profile_validation(change):
    """YAML must satisfy the same nested constraints as visual configuration."""
    with pytest.raises(ValueError):
        parse_notification_profile_yaml(
            yaml.safe_dump({**_profile(), **change}), "loic"
        )
