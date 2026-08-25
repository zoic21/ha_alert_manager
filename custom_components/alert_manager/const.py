"""Constants for Alert Manager."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform
from homeassistant.util.hass_dict import HassKey

DOMAIN: Final = "alert_manager"
INTEGRATION_VERSION: Final = "1.0.1-beta.4"
PLATFORMS: Final = [Platform.SENSOR]

EVENT_ALERT_STARTED: Final = "alert_manager_alert_started"
EVENT_ALERT_RESOLVED: Final = "alert_manager_alert_resolved"
SIGNAL_ALERTS_UPDATED: Final = "alert_manager_alerts_updated"

PANEL_URL: Final = "alert-manager"
PANEL_TITLE: Final = "Alertes"
PANEL_ICON: Final = "mdi:alert-circle-outline"
PANEL_COMPONENT: Final = "alert-manager-panel"
PANEL_STATIC_URL: Final = "/alert_manager_static"

STORAGE_KEY: Final = DOMAIN
STORAGE_VERSION: Final = 1
STORAGE_MINOR_VERSION: Final = 2

DATA_MANAGER: HassKey = HassKey(f"{DOMAIN}_manager")
DATA_WEBSOCKET_REGISTERED: HassKey = HassKey(f"{DOMAIN}_websocket_registered")
DATA_STATIC_REGISTERED: HassKey = HassKey(f"{DOMAIN}_static_registered")

DEFAULT_DELAY: Final = 900
DEFAULT_BATTERY_THRESHOLD: Final = 15.0
DEFAULT_EXCLUSION_LABEL: Final = "pas_d_alerte"
DEFAULT_DOMAINS: Final = [
    "alarm_control_panel",
    "binary_sensor",
    "calendar",
    "camera",
    "climate",
    "cover",
    "device_tracker",
    "input_select",
    "light",
    "lock",
    "media_player",
    "number",
    "select",
    "sensor",
    "switch",
    "time",
    "vacuum",
    "water_heater",
    "weather",
]

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
    "exclusion_label": DEFAULT_EXCLUSION_LABEL,
    "excluded_entities": [],
    "excluded_devices": [],
    "entity_delays": {},
    "automatic": {
        CATEGORY_UNAVAILABLE: {
            "enabled": True,
            "delay": DEFAULT_DELAY,
            "domains": DEFAULT_DOMAINS,
        },
        CATEGORY_CONNECTIVITY: {"enabled": True, "delay": DEFAULT_DELAY},
        CATEGORY_UNIFI: {"enabled": True, "delay": DEFAULT_DELAY},
        CATEGORY_BATTERY: {
            "enabled": True,
            "delay": DEFAULT_DELAY,
            "threshold": DEFAULT_BATTERY_THRESHOLD,
        },
    },
    "rules": [],
}

MIN_DELAY: Final = 0
MAX_DELAY: Final = 31_536_000
MIN_THRESHOLD: Final = -1_000_000_000.0
MAX_THRESHOLD: Final = 1_000_000_000.0

OPERATORS: Final = ("equals", "not_equals", "above", "below")
VALUE_SOURCES: Final = ("state", "attribute")
