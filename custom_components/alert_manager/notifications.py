"""Notification profile validation and deterministic policy resolution."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from homeassistant.components.notify import (
    ATTR_MESSAGE,
    ATTR_TITLE,
    SERVICE_SEND_MESSAGE,
)
from homeassistant.components.notify import (
    DOMAIN as NOTIFY_DOMAIN,
)
from homeassistant.core import valid_entity_id
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    MAX_DELAY,
    MAX_NOTIFICATION_EXCEPTIONS,
    MAX_NOTIFICATION_LABELS,
    MAX_NOTIFICATION_PROFILE_NAME_LENGTH,
    MAX_NOTIFICATION_PROFILES,
    MAX_NOTIFICATION_TARGETS,
    MIN_NOTIFICATION_REMINDER_INTERVAL,
)

_POLICY_KEYS = {"notify_on_start", "notify_on_resolved", "reminder_interval"}
_PROFILE_KEYS = {
    "id",
    "name",
    "enabled",
    "targets",
    "label_ids",
    "default_policy",
    "exceptions",
}
_EXCEPTION_KEYS = {"selector_type", "selector_id", *_POLICY_KEYS}
_TEST_TITLE = "Alert Manager — Test notification"
_TEST_MESSAGE = "This confirms that the notification profile works."

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class NotificationPolicy:
    """Complete effective notification behavior for one alert and profile."""

    notify_on_start: bool
    notify_on_resolved: bool
    reminder_interval: int | None

    def as_dict(self) -> dict[str, bool | int | None]:
        """Return the JSON-safe policy representation."""
        return asdict(self)


class NotificationManager:
    """Own notification delivery independently from the alert state machine."""

    def __init__(
        self,
        hass: Any,
        profiles: Callable[[], list[dict[str, Any]]],
    ) -> None:
        """Initialize with a live, read-only profile provider."""
        self._hass = hass
        self._profiles = profiles
        self._entity_registry = er.async_get(hass)
        self._translations: dict[str, str] = {}

    def set_translations(self, translations: dict[str, str]) -> None:
        """Reuse the manager's already-loaded configured-language catalog."""
        self._translations = translations

    def text(self, key: str, fallback: str) -> str:
        """Return one localized delivery/runtime string."""
        return self._translations.get(
            f"component.{DOMAIN}.config_panel.notifications.{key}", fallback
        )

    async def async_test_profile(self, profile_id: str) -> dict[str, Any]:
        """Send a stateless test through the production delivery path."""
        profile = next(
            (item for item in self._profiles() if item.get("id") == profile_id),
            None,
        )
        if profile is None:
            raise ValueError(f"Unknown notification profile id: {profile_id}")
        return await self.async_send(
            targets=profile["targets"],
            title=self.text("test_title", _TEST_TITLE),
            message=self.text("test_message", _TEST_MESSAGE),
            click_url="/alert-manager",
        )

    async def async_send(
        self,
        *,
        targets: list[str],
        title: str,
        message: str,
        click_url: str | None = None,
    ) -> dict[str, Any]:
        """Send independently to every configured notification entity."""
        delivered, failed = await self._async_send_targets(
            targets,
            title=title,
            message=message,
            click_url=click_url,
        )
        return {
            "success": bool(delivered),
            "delivered_targets": delivered,
            "failed_targets": failed,
        }

    async def _async_send_targets(
        self,
        targets: list[str],
        *,
        title: str,
        message: str,
        click_url: str | None,
    ) -> tuple[list[str], list[dict[str, str]]]:
        """Deliver one batch concurrently and isolate known HA service failures."""
        results = await asyncio.gather(
            *(
                self._async_send_target(
                    target,
                    title=title,
                    message=message,
                    click_url=click_url,
                )
                for target in targets
            )
        )
        delivered: list[str] = []
        failed: list[dict[str, str]] = []
        for target, error in zip(targets, results, strict=True):
            if error is None:
                delivered.append(target)
            else:
                failed.append({"entity_id": target, "error": error})
        return delivered, failed

    async def _async_send_target(
        self,
        target: str,
        *,
        title: str,
        message: str,
        click_url: str | None,
    ) -> str | None:
        """Call one native notify entity and return a bounded known error."""
        try:
            entity_entry = self._entity_registry.async_get(target)
            legacy_service = target.partition(".")[2]
            if (
                click_url is not None
                and getattr(entity_entry, "platform", None) == "mobile_app"
                and hasattr(self._hass.services, "has_service")
                and self._hass.services.has_service(NOTIFY_DOMAIN, legacy_service)
            ):
                await self._hass.services.async_call(
                    NOTIFY_DOMAIN,
                    legacy_service,
                    {
                        ATTR_TITLE: title,
                        ATTR_MESSAGE: message,
                        "data": {"url": click_url, "clickAction": click_url},
                    },
                    blocking=True,
                )
                return None
            await self._hass.services.async_call(
                NOTIFY_DOMAIN,
                SERVICE_SEND_MESSAGE,
                {
                    ATTR_TITLE: title,
                    ATTR_MESSAGE: (
                        f"{message}\n\n{click_url}" if click_url else message
                    ),
                },
                blocking=True,
                target={"entity_id": target},
            )
        except HomeAssistantError as err:
            _LOGGER.warning("Notification delivery to %s failed: %s", target, err)
            return str(err)[:500]
        except Exception as err:  # Delivery must never leak into alert lifecycle tasks.
            _LOGGER.exception("Unexpected notification delivery failure to %s", target)
            return (str(err) or type(err).__name__)[:500]
        return None


def validate_notification_profiles(value: Any) -> list[dict[str, Any]]:
    """Validate notification profiles while preserving their explicit order."""
    if not isinstance(value, list):
        raise ValueError("notification_profiles must be a list")
    if len(value) > MAX_NOTIFICATION_PROFILES:
        raise ValueError(
            "notification_profiles must contain at most "
            f"{MAX_NOTIFICATION_PROFILES} items"
        )

    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_profile in enumerate(value):
        path = f"notification_profiles[{index}]"
        profile = _validate_profile(raw_profile, path)
        if profile["id"] in seen_ids:
            raise ValueError(f"Duplicate notification profile id: {profile['id']}")
        seen_ids.add(profile["id"])
        result.append(profile)
    return result


def profile_matches_labels(
    profile: dict[str, Any], label_ids: set[str] | frozenset[str]
) -> bool:
    """Return whether a profile's optional label filter accepts an alert."""
    configured = profile["label_ids"]
    return not configured or any(label_id in label_ids for label_id in configured)


def resolve_notification_policy(
    profile: dict[str, Any],
    *,
    label_ids: set[str] | frozenset[str],
) -> NotificationPolicy:
    """Apply the first matching label exception over the profile defaults."""
    effective = dict(profile["default_policy"])
    for exception in profile["exceptions"]:
        if exception["selector_id"] in label_ids:
            effective.update(
                {key: exception[key] for key in _POLICY_KEYS if key in exception}
            )
            break
    return NotificationPolicy(**effective)


def _validate_profile(value: Any, path: str) -> dict[str, Any]:
    """Normalize one complete notification profile."""
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    _reject_unknown(value, _PROFILE_KEYS, path)

    profile_id = _non_empty_string(value.get("id"), f"{path}.id", maximum=64)
    name = _non_empty_string(
        value.get("name"),
        f"{path}.name",
        maximum=MAX_NOTIFICATION_PROFILE_NAME_LENGTH,
    )
    enabled = value.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError(f"{path}.enabled must be a boolean")

    targets = _validate_notify_targets(value.get("targets"), f"{path}.targets")

    label_ids = _validate_string_list(
        value.get("label_ids", []),
        f"{path}.label_ids",
        maximum=MAX_NOTIFICATION_LABELS,
    )
    default_policy = _validate_policy(
        value.get("default_policy"), f"{path}.default_policy", partial=False
    )
    raw_exceptions = value.get("exceptions", [])
    if not isinstance(raw_exceptions, list):
        raise ValueError(f"{path}.exceptions must be a list")
    if len(raw_exceptions) > MAX_NOTIFICATION_EXCEPTIONS:
        raise ValueError(
            f"{path}.exceptions must contain at most "
            f"{MAX_NOTIFICATION_EXCEPTIONS} items"
        )
    exceptions = [
        _validate_exception(item, f"{path}.exceptions[{index}]")
        for index, item in enumerate(raw_exceptions)
    ]
    duplicate_selectors: set[tuple[str, str]] = set()
    for exception in exceptions:
        selector = (exception["selector_type"], exception["selector_id"])
        if selector in duplicate_selectors:
            raise ValueError(
                f"{path}.exceptions contains duplicate selector: "
                f"{selector[0]}:{selector[1]}"
            )
        duplicate_selectors.add(selector)

    return {
        "id": profile_id,
        "name": name,
        "enabled": enabled,
        "targets": targets,
        "label_ids": label_ids,
        "default_policy": default_policy,
        "exceptions": exceptions,
    }


def _validate_exception(value: Any, path: str) -> dict[str, Any]:
    """Normalize one partial policy override."""
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    _reject_unknown(value, _EXCEPTION_KEYS, path)
    selector_type = value.get("selector_type")
    if selector_type != "label":
        raise ValueError(f"{path}.selector_type is invalid")
    selector_id = _non_empty_string(
        value.get("selector_id"), f"{path}.selector_id", maximum=255
    )
    policy = _validate_policy(value, path, partial=True)
    if not policy:
        raise ValueError(f"{path} must override at least one policy field")
    return {
        "selector_type": selector_type,
        "selector_id": selector_id,
        **policy,
    }


def _validate_policy(value: Any, path: str, *, partial: bool) -> dict[str, Any]:
    """Normalize a complete policy or a partial inherited override."""
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    allowed = _POLICY_KEYS | ({"selector_type", "selector_id"} if partial else set())
    _reject_unknown(value, allowed, path)
    if not partial and (missing := _POLICY_KEYS - value.keys()):
        raise ValueError(f"Missing {path} field: {sorted(missing)[0]}")

    result: dict[str, Any] = {}
    for key in ("notify_on_start", "notify_on_resolved"):
        if key not in value:
            continue
        if not isinstance(value[key], bool):
            raise ValueError(f"{path}.{key} must be a boolean")
        result[key] = value[key]
    if "reminder_interval" in value:
        reminder = value["reminder_interval"]
        if reminder is not None and (
            isinstance(reminder, bool)
            or not isinstance(reminder, int)
            or not MIN_NOTIFICATION_REMINDER_INTERVAL <= reminder <= MAX_DELAY
        ):
            raise ValueError(
                f"{path}.reminder_interval must be null or an integer between "
                f"{MIN_NOTIFICATION_REMINDER_INTERVAL} and {MAX_DELAY} seconds"
            )
        result["reminder_interval"] = reminder
    return result


def _validate_notify_targets(value: Any, path: str) -> list[str]:
    """Validate a bounded ordered list of native notify entity ids."""
    targets = _validate_string_list(value, path, maximum=MAX_NOTIFICATION_TARGETS)
    if not targets:
        raise ValueError(f"{path} must contain at least one notify entity")
    for entity_id in targets:
        if not valid_entity_id(entity_id) or not entity_id.startswith("notify."):
            raise ValueError(f"{path} contains an invalid notify entity id")
    return targets


def _validate_string_list(value: Any, path: str, *, maximum: int) -> list[str]:
    """Validate, trim and deduplicate an ordered list of identifiers."""
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    if len(value) > maximum:
        raise ValueError(f"{path} must contain at most {maximum} items")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = _non_empty_string(item, path, maximum=255)
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _non_empty_string(value: Any, path: str, *, maximum: int) -> str:
    """Return one trimmed bounded string identifier."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise ValueError(f"{path} must contain at most {maximum} characters")
    return normalized


def _reject_unknown(value: dict[Any, Any], allowed: set[str], path: str) -> None:
    """Reject unknown and non-string configuration keys."""
    invalid = [key for key in value if not isinstance(key, str)]
    if invalid:
        raise ValueError(f"{path} field names must be strings")
    if unknown := set(value) - allowed:
        raise ValueError(f"Unknown {path} field: {sorted(unknown)[0]}")
