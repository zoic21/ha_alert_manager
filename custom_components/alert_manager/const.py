"""Constants for Alert Manager."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform
from homeassistant.util.hass_dict import HassKey

DOMAIN: Final = "alert_manager"
# This version is also used as the frontend module cache key. It must change
# whenever the distributed panel bundle changes.
INTEGRATION_VERSION: Final = "1.4.0-dev3"
PLATFORMS: Final = [Platform.SENSOR]

EVENT_ALERT_STARTED: Final = "alert_manager_alert_started"
EVENT_ALERT_RESOLVED: Final = "alert_manager_alert_resolved"
EVENT_ALERT_ACKNOWLEDGED: Final = "alert_manager_alert_acknowledged"
EVENT_ALERT_UNACKNOWLEDGED: Final = "alert_manager_alert_unacknowledged"
SIGNAL_ALERTS_UPDATED: Final = "alert_manager_alerts_updated"

SERVICE_ACKNOWLEDGE: Final = "acknowledge"
SERVICE_UNACKNOWLEDGE: Final = "unacknowledge"
ATTR_ALERT_ID: Final = "alert_id"

PANEL_URL: Final = "alert-manager"
PANEL_TITLE: Final = "Alert Manager"
PANEL_ICON: Final = "mdi:alert-circle-outline"
PANEL_COMPONENT: Final = "alert-manager-panel"
PANEL_STATIC_URL: Final = "/alert_manager_static"

STORAGE_KEY: Final = DOMAIN
STORAGE_VERSION: Final = 1
STORAGE_MINOR_VERSION: Final = 4

DATA_MANAGER: HassKey = HassKey(f"{DOMAIN}_manager")
DATA_WEBSOCKET_REGISTERED: HassKey = HassKey(f"{DOMAIN}_websocket_registered")
DATA_STATIC_REGISTERED: HassKey = HassKey(f"{DOMAIN}_static_registered")

DEFAULT_DELAY: Final = 900
DEFAULT_BATTERY_THRESHOLD: Final = 15.0
DEFAULT_EXCLUSION_LABEL: Final = "pas_d_alerte"

CATEGORY_UNAVAILABLE: Final = "unavailable"
CATEGORY_CONNECTIVITY: Final = "connectivity"
CATEGORY_UNIFI: Final = "unifi"
CATEGORY_BATTERY: Final = "battery"
CATEGORIES: Final = (
    CATEGORY_UNAVAILABLE,
    CATEGORY_CONNECTIVITY,
    CATEGORY_UNIFI,
    CATEGORY_BATTERY,
)

DEFAULT_CONFIG: Final = {
    "global_delay": DEFAULT_DELAY,
    "excluded_labels": [],
    "excluded_entities": [],
    "excluded_devices": [],
    "entity_delays": {},
    "automatic": {
        CATEGORY_UNAVAILABLE: {
            "enabled": True,
            "delay": None,
        },
        CATEGORY_CONNECTIVITY: {"enabled": True, "delay": None},
        CATEGORY_UNIFI: {"enabled": True, "delay": None},
        CATEGORY_BATTERY: {
            "enabled": True,
            "delay": None,
            "threshold": DEFAULT_BATTERY_THRESHOLD,
        },
    },
    "rules": [],
}

MIN_DELAY: Final = 0
MAX_DELAY: Final = 31_536_000
MIN_THRESHOLD: Final = -1_000_000_000.0
MAX_THRESHOLD: Final = 1_000_000_000.0

OPERATORS: Final = (
    "equals",
    "not_equals",
    "contains",
    "not_contains",
    "above",
    "below",
)
VALUE_SOURCES: Final = ("state", "attribute")
