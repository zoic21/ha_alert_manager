"""Configuration backup scheduling and explicit recovery operations."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.components.persistent_notification import (
    async_create as async_create_persistent_notification,
)
from homeassistant.components.persistent_notification import (
    async_dismiss as async_dismiss_persistent_notification,
)
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from .const import (
    CONFIG_BACKUP_INTERVAL_SECONDS,
    CONFIG_BACKUP_RETRY_SECONDS,
    DOMAIN,
    RECOVERY_NOTIFICATION_ID,
    SIGNAL_MONITORING_UPDATED,
)
from .validation import validate_config
from .yaml_io import dump_config_yaml

_LOGGER = logging.getLogger(__name__)


class _RecoveryMixin:
    """Protect configuration exports and expose voluntary recovery actions."""

    @property
    def recovery_active(self) -> bool:
        """Return whether startup rejected the persisted configuration."""
        return self._recovery_active

    def _enter_config_recovery(self) -> None:
        """Protect the rejected store until an administrator restores a backup."""
        self._recovery_active = True

    async def _async_list_config_backups(self) -> list[dict[str, Any]]:
        """Isolate backup-store failures from the administrator panel."""
        try:
            return await self.config_backup_storage.async_list()
        except Exception:
            _LOGGER.exception("Unable to read Alert Manager configuration backups")
            return []

    async def async_get_recovery_status(self) -> dict[str, Any]:
        """Return the storage guard state and shared backup list."""
        return {
            "active": self.recovery_active,
            "backups": await self._async_list_config_backups(),
        }

    async def async_get_config_backup_download(self, backup_id: str) -> dict[str, str]:
        """Return one validated YAML export through the admin transport."""
        backup = await self.config_backup_storage.async_get(backup_id)
        if backup is None:
            raise ValueError("Unknown or invalid configuration backup")
        timestamp = backup["created_at"].replace(":", "").replace("+00:00", "Z")
        return {
            "content": backup["yaml"],
            "content_type": "application/yaml;charset=utf-8",
            "filename": f"alert-manager-backup-{timestamp}.yaml",
        }

    async def async_restore_config_backup(self, backup_id: str) -> dict[str, Any]:
        """Restore through the exact complete-import transaction."""
        backup = await self.config_backup_storage.async_get(backup_id)
        if backup is None:
            raise ValueError("Unknown or invalid configuration backup")
        return await self.async_import_config(backup["yaml"])

    async def async_create_config_backup_if_due(self) -> dict[str, Any] | None:
        """Create one daily export only from the fully validated live config."""
        if self.recovery_active or self._unloading:
            return None
        async with self._config_mutation_lock:
            if self.recovery_active or self._unloading:
                return None
            backups = await self.config_backup_storage.async_list()
            now = dt_util.now().astimezone(UTC)
            if backups:
                latest = datetime.fromisoformat(backups[0]["created_at"]).astimezone(
                    UTC
                )
                if (now - latest).total_seconds() < CONFIG_BACKUP_INTERVAL_SECONDS:
                    return None
            candidate = await self.hass.async_add_executor_job(
                validate_config, self.get_config()
            )
            self._validate_config_rule_sources(candidate)
            raw_yaml = await self.hass.async_add_executor_job(
                dump_config_yaml, candidate
            )
            return await self.config_backup_storage.async_create(
                raw_yaml, created_at=now
            )

    async def _async_initialize_config_backups(self) -> None:
        """Catch up after downtime, then keep one event-driven daily deadline."""
        self._cancel_config_backup_schedule()
        if self.recovery_active:
            return
        try:
            await self.async_create_config_backup_if_due()
        except Exception:
            _LOGGER.exception("Unable to create Alert Manager configuration backup")
            self._schedule_config_backup(retry=True)
            return
        backups = await self._async_list_config_backups()
        delay = CONFIG_BACKUP_INTERVAL_SECONDS
        if backups:
            latest = datetime.fromisoformat(backups[0]["created_at"]).astimezone(UTC)
            age = (dt_util.now().astimezone(UTC) - latest).total_seconds()
            delay = max(1, CONFIG_BACKUP_INTERVAL_SECONDS - age)
        self._schedule_config_backup(delay_seconds=delay)

    def _schedule_config_backup(
        self, *, retry: bool = False, delay_seconds: float | None = None
    ) -> None:
        """Schedule one deadline instead of polling for backup age."""
        self._cancel_config_backup_schedule()
        if self.recovery_active or self._unloading:
            return
        delay = (
            CONFIG_BACKUP_RETRY_SECONDS
            if retry
            else (delay_seconds or CONFIG_BACKUP_INTERVAL_SECONDS)
        )
        when = dt_util.now().astimezone(UTC) + timedelta(seconds=delay)

        @callback
        def backup_due(_now: datetime) -> None:
            self._config_backup_schedule_unsubscribe = None
            if self._unloading or self.recovery_active:
                return
            self.entry.async_create_task(
                self.hass,
                self._async_run_scheduled_config_backup(),
                name=f"{DOMAIN} configuration backup",
            )

        self._config_backup_schedule_unsubscribe = async_track_point_in_utc_time(
            self.hass, backup_due, when
        )

    async def _async_run_scheduled_config_backup(self) -> None:
        """Create a due backup and retain a bounded retry after I/O failure."""
        try:
            await self.async_create_config_backup_if_due()
        except Exception:
            _LOGGER.exception("Unable to create Alert Manager configuration backup")
            self._schedule_config_backup(retry=True)
            return
        self._schedule_config_backup()

    def _cancel_config_backup_schedule(self) -> None:
        """Cancel the single outstanding daily backup deadline."""
        if self._config_backup_schedule_unsubscribe is not None:
            self._config_backup_schedule_unsubscribe()
            self._config_backup_schedule_unsubscribe = None

    async def _async_sync_recovery_notification(self) -> None:
        """Keep one localized persistent recovery notification in sync."""
        if not self.recovery_active:
            async_dismiss_persistent_notification(self.hass, RECOVERY_NOTIFICATION_ID)
            return
        try:
            resources = await async_get_translations(
                self.hass,
                self.hass.config.language,
                "config_panel",
                integrations=[DOMAIN],
            )
        except Exception:  # pragma: no cover - Home Assistant loader failure
            _LOGGER.exception("Unable to load recovery notification translations")
            resources = {}
        prefix = f"component.{DOMAIN}.config_panel.recovery"
        title = resources.get(
            f"{prefix}.notification_title",
            "Alert Manager configuration problem",
        )
        message = resources.get(
            f"{prefix}.notification_message",
            "Alert Manager could not load its configuration and started with the "
            "default configuration. No backup was restored automatically. Open "
            "Alert Manager settings, then Export / Import, to choose a backup.",
        )
        async_create_persistent_notification(
            self.hass,
            message,
            title=title,
            notification_id=RECOVERY_NOTIFICATION_ID,
        )

    async def _async_resolve_config_recovery(self) -> None:
        """Resume normal persistence and scheduling after a valid import."""
        async_dismiss_persistent_notification(self.hass, RECOVERY_NOTIFICATION_ID)
        async_dispatcher_send(self.hass, SIGNAL_MONITORING_UPDATED)
        self._schedule_config_backup(delay_seconds=1)
