"""Constants for Alert Manager."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform
from homeassistant.util.hass_dict import HassKey

DOMAIN: Final = "alert_manager"
# This version is also used as the frontend module cache key. It must change
# whenever the distributed panel bundle changes.
INTEGRATION_VERSION: Final = "2.1.3"
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
