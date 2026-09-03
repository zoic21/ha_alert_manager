"""Notification profile and effective policy tests."""

from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.alert_manager.const import DEFAULT_CONFIG
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
        "primary_targets": ["notify.mobile_app_phone"],
        "fallback_targets": ["notify.mobile_app_tablet"],
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


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"primary_targets": ["sensor.invalid"]}, "invalid notify entity"),
        (
            {"fallback_targets": ["notify.mobile_app_phone"]},
            "duplicates primary target",
        ),
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


def test_delivery_does_not_use_fallback_when_any_primary_succeeds(hass) -> None:
    """Fallback is a technical last resort, not a second recipient group."""
    attempted: list[str] = []

    async def send(_domain, _service, _data, **kwargs):
        target = kwargs["target"]["entity_id"]
        attempted.append(target)
        if target == "notify.primary_failed":
            raise HomeAssistantError("primary unavailable")

    hass.services.async_call = send
    manager = NotificationManager(hass, lambda: [])
    result = asyncio.run(
        manager.async_send(
            primary_targets=["notify.primary_failed", "notify.primary_ok"],
            fallback_targets=["notify.fallback"],
            title="Title",
            message="Message",
        )
    )

    assert result["success"] is True
    assert result["used_fallback"] is False
    assert result["delivered_targets"] == ["notify.primary_ok"]
    assert attempted == ["notify.primary_failed", "notify.primary_ok"]


def test_test_notification_uses_fallback_without_creating_runtime_state(
    hass,
) -> None:
    """The V1 test follows real fallback behavior and remains stateless."""
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
    assert result["used_fallback"] is True
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
            primary_targets=["notify.phone"],
            fallback_targets=[],
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


def test_unexpected_primary_failure_is_isolated_and_uses_fallback(hass) -> None:
    """A broken notify integration cannot leak into alert lifecycle tasks."""

    async def send(_domain, _service, _data, **kwargs):
        if kwargs["target"]["entity_id"] == "notify.primary":
            raise RuntimeError("broken integration")

    hass.services.async_call = send
    manager = NotificationManager(hass, lambda: [])

    result = asyncio.run(
        manager.async_send(
            primary_targets=["notify.primary"],
            fallback_targets=["notify.fallback"],
            title="Title",
            message="Message",
        )
    )

    assert result["success"] is True
    assert result["used_fallback"] is True
    assert result["delivered_targets"] == ["notify.fallback"]
