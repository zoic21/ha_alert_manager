"""Notification profile and effective policy tests."""

from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest
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
from custom_components.alert_manager.yaml_io import dump_config_yaml, parse_config_yaml


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
                "selector_type": "rule",
                "selector_id": "freezer",
                "reminder_interval": 300,
            },
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
            {
                "selector_type": "pack",
                "selector_id": "battery",
                "notify_on_resolved": False,
            },
        ],
    }


def test_policy_resolution_is_partial_and_uses_documented_priority() -> None:
    """Rule wins over first label, pack and profile defaults field by field."""
    config = validate_config(
        {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [_profile()]}
    )
    profile = config["notification_profiles"][0]

    effective = resolve_notification_policy(
        profile,
        pack_id="battery",
        rule_id="freezer",
        label_ids={"important", "secondary"},
    )

    assert effective.as_dict() == {
        "notify_on_start": True,
        "notify_on_resolved": False,
        "reminder_interval": 300,
    }


def test_first_matching_label_exception_wins_in_explicit_list_order() -> None:
    """Several entity/device labels never introduce hidden scoring."""
    profile = validate_config(
        {**deepcopy(DEFAULT_CONFIG), "notification_profiles": [_profile()]}
    )["notification_profiles"][0]

    effective = resolve_notification_policy(
        profile,
        pack_id=None,
        rule_id=None,
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
            "not a known pack",
        ),
        (
            {"exceptions": [{"selector_type": "rule", "selector_id": "freezer"}]},
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


def test_rule_deletion_cleans_notification_runtime_and_exception(hass, entry) -> None:
    """Deleting a rule leaves no pending delivery, reminder or orphan override."""

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
        profile["exceptions"][0]["selector_id"] = rule["id"]
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

        await manager.async_delete_rule(rule["id"])

        configured_profile = manager.get_config()["notification_profiles"][0]
        assert all(
            exception.get("selector_id") != rule["id"]
            for exception in configured_profile["exceptions"]
        )
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


def test_yaml_round_trip_rebinds_rule_exceptions_to_new_rule_ids() -> None:
    """Portable exports omit internal rule ids without losing profile routing."""
    config = deepcopy(DEFAULT_CONFIG)
    config["rules"] = [
        {
            "id": "freezer",
            "name": "Freezer",
            "entity_ids": ["sensor.freezer"],
            "operator": "above",
            "value": 8,
            "duration": 60,
        }
    ]
    config["notification_profiles"] = [_profile()]

    exported = dump_config_yaml(config)
    imported = parse_config_yaml(exported)

    imported_rule_id = imported["rules"][0]["id"]
    rule_exception = imported["notification_profiles"][0]["exceptions"][0]
    assert "id: freezer" not in exported
    assert "selector_id: '@rule:0'" in exported
    assert imported_rule_id != "freezer"
    assert rule_exception["selector_id"] == imported_rule_id


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
    assert "/alert-manager" in attempted[0][2]


def test_mobile_app_delivery_keeps_click_target_in_transport_layer(
    hass, registry_entry
) -> None:
    """Companion targets use their existing service only for click metadata."""
    registry_entry(hass, "notify.phone", platform="mobile_app")
    received = []

    async def send(call):
        received.append(call.data)

    hass.services.async_register("notify", "phone", send)
    manager = NotificationManager(hass, lambda: [])

    result = asyncio.run(
        manager.async_send(
            targets=["notify.phone"],
            title="Title",
            message="Message",
            click_url="/alert-manager?alert=battery%3Asensor.test",
        )
    )

    assert result["success"] is True
    assert hass.services.calls[0]["service"] == "phone"
    assert received[0]["data"] == {
        "url": "/alert-manager?alert=battery%3Asensor.test",
        "clickAction": "/alert-manager?alert=battery%3Asensor.test",
    }


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
