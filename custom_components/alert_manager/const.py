"""Constants for Alert Manager."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform
from homeassistant.util.hass_dict import HassKey

DOMAIN: Final = "alert_manager"
# This version is also used as the frontend module cache key. It must change
# whenever the distributed panel bundle changes.
INTEGRATION_VERSION: Final = "2.1.6-beta.1"
FRONTEND_CACHE_VERSION: Final = f"{INTEGRATION_VERSION}.12"
PLATFORMS: Final = [Platform.BUTTON, Platform.SENSOR, Platform.SWITCH]

EVENT_ALERT_STARTED: Final = "alert_manager_alert_started"
EVENT_ALERT_RESOLVED: Final = "alert_manager_alert_resolved"
EVENT_ALERT_ACKNOWLEDGED: Final = "alert_manager_alert_acknowledged"
EVENT_ALERT_UNACKNOWLEDGED: Final = "alert_manager_alert_unacknowledged"
EVENT_DEVICE_ALERT_STARTED: Final = "alert_manager_device_alert_started"
DEVICE_EVENT_DEBOUNCE_SECONDS: Final = 10
LIVE_MESSAGE_FLUSH_INTERVAL_SECONDS: Final = 30
SIGNAL_ALERTS_UPDATED: Final = "alert_manager_alerts_updated"
SIGNAL_MONITORING_UPDATED: Final = "alert_manager_monitoring_updated"
SIGNAL_HISTORY_UPDATED: Final = "alert_manager_history_updated"
SIGNAL_COHERENCE_UPDATED: Final = "alert_manager_coherence_updated"

MAIN_DEVICE_IDENTIFIER: Final = "main"
MAIN_DEVICE_NAME: Final = "Alert Manager - Général"
MONITORING_NOTIFICATION_ID: Final = "alert_manager_main_monitoring_disabled"
RECOVERY_NOTIFICATION_ID: Final = "alert_manager_configuration_recovery"
ALERT_MANAGER_ENTITY_IDS: Final = frozenset(
    {
        "sensor.alert_manager",
        "sensor.alert_manager_main_active",
        "sensor.alert_manager_main_pending",
        "sensor.alert_manager_main_acknowledge",
        "sensor.alert_manager_device_main_active",
        "sensor.alert_manager_coherence_issue",
        "button.alert_manager_check_coherence",
        "switch.alert_manager_main_monitoring",
    }
)
CUSTOM_RULE_ALLOWED_ENTITY_IDS: Final = frozenset(
    {"sensor.alert_manager_coherence_issue"}
)

SERVICE_ACKNOWLEDGE: Final = "acknowledge"
SERVICE_UNACKNOWLEDGE: Final = "unacknowledge"
ATTR_ALERT_ID: Final = "alert_id"

PANEL_URL: Final = "alert-manager"
PANEL_TITLE: Final = "Alert Manager"
PANEL_ICON: Final = "mdi:alert-circle-outline"
PANEL_COMPONENT: Final = "alert-manager-panel"
PANEL_STATIC_URL: Final = "/alert_manager_static"

STORAGE_KEY: Final = DOMAIN
HISTORY_STORAGE_KEY: Final = f"{DOMAIN}.history"
COHERENCE_STORAGE_KEY: Final = f"{DOMAIN}.coherence"
CONFIG_BACKUP_STORAGE_KEY: Final = f"{DOMAIN}.config_backups"
STORAGE_VERSION: Final = 1
STORAGE_MINOR_VERSION: Final = 15
HISTORY_STORAGE_VERSION: Final = 1
COHERENCE_STORAGE_VERSION: Final = 1
CONFIG_BACKUP_STORAGE_VERSION: Final = 1
CONFIG_BACKUP_LIMIT: Final = 3
CONFIG_BACKUP_INTERVAL_SECONDS: Final = 24 * 60 * 60
CONFIG_BACKUP_RETRY_SECONDS: Final = 60 * 60

DATA_MANAGER: HassKey = HassKey(f"{DOMAIN}_manager")
DATA_WEBSOCKET_REGISTERED: HassKey = HassKey(f"{DOMAIN}_websocket_registered")
DATA_STATIC_REGISTERED: HassKey = HassKey(f"{DOMAIN}_static_registered")
DATA_COHERENCE_RESULT: HassKey = HassKey(f"{DOMAIN}_coherence_result")
DATA_COHERENCE_SCAN_TASK: HassKey = HassKey(f"{DOMAIN}_coherence_scan_task")

DEFAULT_DELAY: Final = 900
DEFAULT_PENDING_DISPLAY_DELAY: Final = 10
DEFAULT_BATTERY_THRESHOLD: Final = 15.0
DEFAULT_EXCLUSION_LABEL: Final = "pas_d_alerte"
DEFAULT_HISTORY_LIMIT: Final = 100
DEFAULT_COHERENCE_SCHEDULE: Final = "none"
DEFAULT_COHERENCE_SCAN_ESPHOME: Final = True
COHERENCE_SCHEDULES: Final = ("none", "daily", "weekly", "monthly")
COHERENCE_SCHEDULE_HOUR: Final = 3
COHERENCE_SCHEDULE_MINUTE: Final = 5
MIN_HISTORY_LIMIT: Final = 0
MAX_HISTORY_LIMIT: Final = 1000
MAX_RULES: Final = 500
MAX_RULE_ENTITY_IDS: Final = 50
MAX_RULE_NAME_LENGTH: Final = 255
MAX_RULE_MESSAGE_LENGTH: Final = 1024
MAX_RULE_CONDITION_TEMPLATE_LENGTH: Final = 65_536

CATEGORY_UNAVAILABLE: Final = "unavailable"
CATEGORY_CONNECTIVITY: Final = "connectivity"
CATEGORY_UNIFI: Final = "unifi"
CATEGORY_BATTERY: Final = "battery"
CATEGORIES: Final = (
    CATEGORY_UNAVAILABLE,
    CATEGORY_CONNECTIVITY,
    CATEGORY_UNIFI,
    CATEGORY_BATTERY,
    "execution_errors",
)

DEFAULT_CONFIG: Final = {
    "monitoring_enabled": True,
    "history_limit": DEFAULT_HISTORY_LIMIT,
    "coherence_schedule": DEFAULT_COHERENCE_SCHEDULE,
    "coherence_scan_esphome": DEFAULT_COHERENCE_SCAN_ESPHOME,
    "coherence_ignored_entity_references": [],
    "global_delay": DEFAULT_DELAY,
    "pending_display_delay": DEFAULT_PENDING_DISPLAY_DELAY,
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
            "device_thresholds": {},
        },
        "execution_errors": {
            "enabled": True,
            "delay": 0,
            "failure_thresholds": {},
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
    "between",
    "outside",
    "unchanged",
)
VALUE_SOURCES: Final = (
    "state",
    "attribute",
    "state_variation",
    "attribute_variation",
    "unchanged",
    "jinja",
)
ATTRIBUTE_SOURCES: Final = ("attribute", "attribute_variation")
VARIATION_SOURCES: Final = ("state_variation", "attribute_variation")
