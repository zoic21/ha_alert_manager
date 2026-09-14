"""Native notification icon presentation regression tests."""

from __future__ import annotations

import asyncio

import pytest

from custom_components.alert_manager.notifications import NotificationManager


@pytest.mark.parametrize(
    ("kind", "icon", "emoji"),
    [
        ("started", "mdi:alert-circle", "🚨"),
        ("reminder", "mdi:bell-ring", "🔔"),
        ("resolved", "mdi:check-circle", "✅"),
    ],
)
def test_native_icon_for_mobile_and_emoji_fallback(
    hass, registry_entry, config_entry, kind, icon, emoji
) -> None:
    """Use native Companion icons while generic targets retain title emojis."""
    entry = config_entry(hass, "mobile_app")
    entry.data = {"device_name": "Phone"}
    registry_entry(
        hass,
        "notify.phone",
        platform="mobile_app",
        config_entry_id=entry.entry_id,
    )

    async def send(_call):
        pass

    hass.services.async_register("notify", "mobile_app_phone", send)
    hass.services.async_register("notify", "send_message", send)
    manager = NotificationManager(hass, lambda: [])

    result = asyncio.run(
        manager.async_send(
            targets=["notify.phone", "notify.generic"],
            title="Title",
            message="Message",
            click_url="/alert-manager",
            kind=kind,
        )
    )

    assert result["delivered_targets"] == ["notify.phone", "notify.generic"]
    calls = {call["service"]: call for call in hass.services.calls}
    mobile = calls["mobile_app_phone"]
    assert mobile["data"] == {
        "title": "Title",
        "message": "Message",
        "data": {
            "url": "/alert-manager",
            "clickAction": "/alert-manager",
            "notification_icon": icon,
        },
    }
    generic = calls["send_message"]
    assert generic["data"] == {"title": f"{emoji} Title", "message": "Message"}
    assert generic["target"] == {"entity_id": "notify.generic"}


def test_profile_test_uses_native_test_icon(hass, registry_entry, config_entry) -> None:
    """The profile test uses the same mobile presentation without an emoji title."""
    entry = config_entry(hass, "mobile_app")
    entry.data = {"device_name": "Phone"}
    registry_entry(
        hass,
        "notify.phone",
        platform="mobile_app",
        config_entry_id=entry.entry_id,
    )

    async def send(_call):
        pass

    hass.services.async_register("notify", "mobile_app_phone", send)
    manager = NotificationManager(
        hass,
        lambda: [{"id": "profile", "targets": ["notify.phone"]}],
    )

    result = asyncio.run(manager.async_test_profile("profile"))

    assert result["delivered_targets"] == ["notify.phone"]
    call = hass.services.calls[0]
    assert call["data"]["title"] == "Alert Manager — Test notification"
    assert call["data"]["data"]["notification_icon"] == "mdi:bell-check"
