"""Configuration defaults assembled from independent pack declarations."""

from typing import Final

from .const import (
    DEFAULT_COHERENCE_SCAN_ESPHOME,
    DEFAULT_COHERENCE_SCHEDULE,
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_PENDING_DISPLAY_DELAY,
    NOTIFICATION_BATCH_SECONDS,
)
from .packs import PACKS

CATEGORIES: Final = tuple(pack.id for pack in PACKS)

DEFAULT_CONFIG: Final = {
    "monitoring_enabled": True,
    "history_limit": DEFAULT_HISTORY_LIMIT,
    "coherence_schedule": DEFAULT_COHERENCE_SCHEDULE,
    "coherence_scan_esphome": DEFAULT_COHERENCE_SCAN_ESPHOME,
    "coherence_alert_enabled": False,
    "coherence_ignored_entity_references": [],
    "pack_config_version": 2,
    "pending_display_delay": DEFAULT_PENDING_DISPLAY_DELAY,
    "excluded_labels": [],
    "automatic": {pack.id: pack.default_config() for pack in PACKS},
    "rules": [],
    "notification_profiles": [],
    "notification_batch_delay": NOTIFICATION_BATCH_SECONDS,
}
