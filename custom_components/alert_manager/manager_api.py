"""Public Alert Manager API and configuration mutations."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from copy import deepcopy
from functools import wraps
from typing import Any

from homeassistant.components.persistent_notification import (
    async_create as async_create_persistent_notification,
)
from homeassistant.components.persistent_notification import (
    async_dismiss as async_dismiss_persistent_notification,
)
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    MAX_HISTORY_LIMIT,
    MIN_HISTORY_LIMIT,
    MONITORING_NOTIFICATION_ID,
    SIGNAL_HISTORY_UPDATED,
    SIGNAL_MONITORING_UPDATED,
    VARIATION_SOURCES,
)
from .models import AlertHistoryEntry, AlertRecord, AlertStatus, Rule
from .packs import PACKS, PACKS_BY_ID
from .storage import sort_history
from .validation import (
    validate_config,
    validate_config_update,
    validate_rule_payload,
    validate_rule_update_fields,
)
from .yaml_io import (
    dump_config_yaml,
    dump_rule_yaml,
    import_summary,
    parse_config_yaml,
    parse_rule_yaml,
    rule_to_yaml_data,
)

_LOGGER = logging.getLogger(__name__)


def _serialize_config_mutation(
    method: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
    """Serialize a complete configuration transaction on one manager."""

    @wraps(method)
    async def locked(self: Any, *args: Any, **kwargs: Any) -> Any:
        if self.recovery_active and method.__name__ != "async_import_config":
            raise ValueError("Configuration recovery is required before making changes")
        async with self._config_mutation_lock:
            return await method(self, *args, **kwargs)

    return locked


class _ApiMixin:
    """Expose the manager contract consumed by WebSocket, services and sensors."""

    def get_config(self) -> dict[str, Any]:
        """Return a defensive copy for WebSocket clients."""
        return deepcopy(self.config)

    def public_snapshot(self) -> dict[str, Any]:
        """Return active and pending lists without resolved history."""
        return self._build_public_snapshot()[0]

    def history_snapshot(self) -> dict[str, Any]:
        """Return newest-first immutable history for the administrator panel."""
        return {
            "events": [entry.as_dict() for entry in sort_history(self.history)],
            "count": len(self.history),
            "retention_limit": self.config["history_limit"],
            "enabled": self.config["history_limit"] > 0,
        }

    def get_history_config(self) -> dict[str, int | bool]:
        """Return the bounded retention setting independently from YAML config."""
        limit = self.config["history_limit"]
        return {"retention_limit": limit, "enabled": limit > 0}

    @_serialize_config_mutation
    async def async_set_history_limit(self, limit: int) -> dict[str, int | bool]:
        """Persist a new retention limit and immediately remove oldest excess."""
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("retention_limit must be an integer")
        if not MIN_HISTORY_LIMIT <= limit <= MAX_HISTORY_LIMIT:
            raise ValueError(
                f"retention_limit must be between {MIN_HISTORY_LIMIT} and "
                f"{MAX_HISTORY_LIMIT}"
            )
        if limit == self.config["history_limit"]:
            return self.get_history_config()

        previous_config = deepcopy(self.config)
        previous_history = list(self.history)
        previous_pending = list(self._pending_history)
        self.config["history_limit"] = limit
        if limit == 0:
            self._pending_history = []
        history_changed = self._trim_history()
        history_saved = False
        try:
            if history_changed:
                await self.history_storage.async_save(self.history)
                history_saved = True
            await self.storage.async_save(self.config, self.records)
        except Exception:
            self.config = previous_config
            self.history = previous_history
            self._pending_history = previous_pending
            if history_saved:
                try:
                    await self.history_storage.async_save(previous_history)
                except Exception:
                    _LOGGER.exception(
                        "Unable to restore alert history after retention update failure"
                    )
            raise
        if history_changed:
            async_dispatcher_send(self.hass, SIGNAL_HISTORY_UPDATED)
        return self.get_history_config()

    async def async_clear_history(self) -> dict[str, Any]:
        """Delete history only, preserving every current runtime record."""
        previous_history = list(self.history)
        previous_pending = list(self._pending_history)
        self.history = []
        self._pending_history = []
        try:
            await self.history_storage.async_save([])
        except Exception:
            self.history = previous_history
            self._pending_history = previous_pending
            raise
        async_dispatcher_send(self.hass, SIGNAL_HISTORY_UPDATED)
        return self.history_snapshot()

    @_serialize_config_mutation
    async def async_set_monitoring(self, enabled: bool) -> bool:
        """Persistently suspend or resume the main monitoring category."""
        if not isinstance(enabled, bool):
            raise ValueError("Monitoring state must be a boolean")
        if enabled == self.monitoring_enabled:
            if enabled:
                async_dismiss_persistent_notification(
                    self.hass, MONITORING_NOTIFICATION_ID
                )
            return False

        previous_config = deepcopy(self.config)
        previous_records = deepcopy(self.records)
        previous_pending_history = list(self._pending_history)
        previous_variation_baselines = dict(self._variation_baselines)
        previous_variation_dirty = self._variation_baselines_dirty
        self.config["monitoring_enabled"] = enabled
        try:
            if enabled:
                self._resume_pending_alerts(dt_util.now())
                await self.async_evaluate_all(
                    save=False,
                    publish=False,
                    emit_events=False,
                )
            else:
                self._freeze_pending_alerts(dt_util.now())
                self._clear_variation_baselines()
            await self._async_save_state()
        except Exception:
            self.config = previous_config
            self.records = previous_records
            self._pending_history = previous_pending_history
            self._variation_baselines = previous_variation_baselines
            self.storage.variation_baselines = self._variation_baselines
            self._variation_baselines_dirty = previous_variation_dirty
            self._cancel_all_timers()
            self._reschedule_record_timers()
            raise

        if enabled:
            async_dismiss_persistent_notification(self.hass, MONITORING_NOTIFICATION_ID)
            self._emit_resume_events(previous_records)
        else:
            self._cancel_all_timers()
            self._cancel_all_device_event_timers()
        self._refresh_tracking()
        self._publish_if_changed(force=True)
        async_dispatcher_send(self.hass, SIGNAL_MONITORING_UPDATED)
        return True

    async def _async_sync_monitoring_notification(self) -> None:
        """Keep one localized persistent startup warning in sync."""
        if self.recovery_active:
            async_dismiss_persistent_notification(self.hass, MONITORING_NOTIFICATION_ID)
            return
        if self.monitoring_enabled:
            async_dismiss_persistent_notification(self.hass, MONITORING_NOTIFICATION_ID)
            return
        try:
            resources = await async_get_translations(
                self.hass,
                self.hass.config.language,
                "config_panel",
                integrations=[DOMAIN],
            )
        except Exception:  # pragma: no cover - Home Assistant loader failure
            _LOGGER.exception("Unable to load persistent notification translations")
            resources = {}
        prefix = f"component.{DOMAIN}.config_panel.monitoring"
        title = resources.get(
            f"{prefix}.notification_title", "Alert Manager monitoring disabled"
        )
        message = resources.get(
            f"{prefix}.notification_message",
            "Alert Manager monitoring is disabled. Turn on “Alert Manager "
            "Monitoring” to resume alert detection.",
        )
        async_create_persistent_notification(
            self.hass,
            message,
            title=title,
            notification_id=MONITORING_NOTIFICATION_ID,
        )

    def _emit_resume_events(self, previous_records: dict[str, AlertRecord]) -> None:
        """Emit only lifecycle transitions caused by the resume evaluation."""
        now = dt_util.now()
        for alert_id, previous in previous_records.items():
            current = self.records.get(alert_id)
            if current is None:
                if previous.status is AlertStatus.ACTIVE:
                    self._fire_resolved(previous, now)
                continue
            if (
                previous.status is AlertStatus.PENDING
                and current.status is AlertStatus.ACTIVE
            ):
                self._fire_started(current)
        for alert_id, current in self.records.items():
            if (
                alert_id not in previous_records
                and current.status is AlertStatus.ACTIVE
            ):
                self._fire_started(current)

    def get_packs(self) -> list[dict[str, Any]]:
        """Return backend-owned pack metadata with current availability."""
        return [pack.as_public_dict(self.hass) for pack in PACKS]

    def get_rule_yaml(self, rule_id: str) -> str:
        """Return the editable YAML form of one existing rule."""
        return dump_rule_yaml(self.config["rules"][self._rule_index(rule_id)])

    def validate_rule_yaml(
        self, raw_yaml: str, *, rule_id: str | None = None
    ) -> dict[str, Any]:
        """Parse one YAML rule through the same validator as the visual form."""
        rule = parse_rule_yaml(raw_yaml, rule_id=rule_id)
        self._validate_rule_sources(rule)
        self._validate_rule_template(rule)
        return rule_to_yaml_data(rule)

    def export_config_yaml(self) -> str:
        """Return a deterministic, runtime-free YAML configuration export."""
        if self.recovery_active:
            raise ValueError("Restore or import a configuration before exporting")
        return dump_config_yaml(self.config)

    def preview_config_import(self, raw_yaml: str) -> dict[str, Any]:
        """Validate an import without touching the active configuration."""
        candidate = parse_config_yaml(raw_yaml)
        self._validate_config_rule_sources(candidate)
        return import_summary(candidate)

    async def async_acknowledge(self, alert_id: str, actor: str | None) -> bool:
        """Acknowledge one active alert and persist before publishing it."""
        record = self._active_record_for_service(alert_id)
        if record.acknowledged:
            return False
        now = dt_util.now()
        record.acknowledged = True
        record.acknowledged_at = now
        record.acknowledged_by = actor
        try:
            await self._async_save_state()
        except Exception:
            record.clear_acknowledgement()
            raise
        self._publish_if_changed()
        self._fire_acknowledged(record)
        return True

    async def async_unacknowledge(self, alert_id: str, actor: str | None) -> bool:
        """Remove acknowledgement from one active alert idempotently."""
        record = self._active_record_for_service(alert_id)
        if not record.acknowledged:
            return False
        now = dt_util.now()
        previous_at = record.acknowledged_at
        previous_by = record.acknowledged_by
        record.clear_acknowledgement()
        try:
            await self._async_save_state()
        except Exception:
            record.acknowledged = True
            record.acknowledged_at = previous_at
            record.acknowledged_by = previous_by
            raise
        self._publish_if_changed()
        self._fire_unacknowledged(record, now, actor, previous_at, previous_by)
        return True

    def _active_record_for_service(self, alert_id: str) -> AlertRecord:
        """Resolve an exact active alert or raise a clear service error."""
        record = self.records.get(alert_id)
        if record is None:
            raise ValueError(f"Unknown or resolved alert id: {alert_id}")
        if record.status is AlertStatus.PENDING:
            raise ValueError(f"Pending alert cannot be acknowledged: {alert_id}")
        return record

    @_serialize_config_mutation
    async def async_update_config(self, changes: dict[str, Any]) -> dict[str, Any]:
        """Validate, atomically persist and immediately apply config changes."""
        validate_config_update(changes)
        changes = dict(changes)
        if "active_display_delay" in changes:
            changes.setdefault(
                "pending_display_delay", changes.pop("active_display_delay")
            )
        if "rules" in changes:
            raise ValueError("Rules must be changed through the rules API")
        candidate = _deep_merge(self.get_config(), changes)
        if "entity_delays" in changes:
            candidate["entity_delays"] = deepcopy(changes["entity_delays"])
        for pack_id, pack_changes in changes.get("automatic", {}).items():
            for field in PACKS_BY_ID[pack_id].config_fields:
                if field.type == "device_number_map" and field.id in pack_changes:
                    candidate["automatic"][pack_id][field.id] = deepcopy(
                        pack_changes[field.id]
                    )
        candidate["rules"] = self.config["rules"]
        candidate = validate_config(candidate)
        coherence_schedule_changed = (
            candidate["coherence_schedule"] != self.config["coherence_schedule"]
        )
        previous = self._configuration_snapshot()
        try:
            self.config = candidate
            if not self.monitoring_enabled and previous[0].get(
                "monitoring_enabled", True
            ):
                self._clear_variation_baselines()
            self._rebuild_rule_index()
            await self.async_evaluate_all(save=False, publish=False)
            if "pending_display_delay" in changes:
                self._reschedule_hidden_pending_visibility(dt_util.now())
            await self._async_save_state()
        except Exception:
            self._restore_configuration_snapshot(previous)
            raise
        if coherence_schedule_changed:
            self._refresh_coherence_schedule()
        self._publish_if_changed()
        return self.get_config()

    @_serialize_config_mutation
    async def async_import_config(self, raw_yaml: str) -> dict[str, Any]:
        """Replace configuration through one validated, recoverable transaction."""
        candidate = parse_config_yaml(raw_yaml)
        candidate["history_limit"] = self.config["history_limit"]
        self._validate_config_rule_sources(candidate)
        summary = import_summary(candidate)
        previous = self._configuration_snapshot()
        previous_history = list(self.history)
        previous_recovery_active = self.recovery_active
        previous_monitoring_enabled = self.monitoring_enabled
        history_cleared = False

        self._cancel_all_timers()
        self._cancel_all_device_event_timers()
        try:
            self._recovery_active = False
            self.config = candidate
            self.records = {}
            self.history = []
            self._pending_history = []
            self._clear_variation_baselines()
            self._rebuild_rule_index()
            self._refresh_pack_entry_listeners()
            self._pack_availability = self._current_pack_availability()
            await self.async_evaluate_all(
                save=False,
                publish=False,
                emit_events=False,
            )
            self._reschedule_hidden_pending_visibility(dt_util.now())
            await self.history_storage.async_save([])
            history_cleared = True
            await self.storage.async_save(self.config, self.records)
            self._immediate_state_save_required = False
            self._variation_baselines_dirty = False
        except Exception:
            self._recovery_active = previous_recovery_active
            self._restore_configuration_snapshot(previous)
            self.history = previous_history
            if history_cleared:
                try:
                    await self.history_storage.async_save(previous_history)
                except Exception:
                    _LOGGER.exception(
                        "Unable to restore alert history after failed config import"
                    )
            raise

        monitoring_changed = previous_monitoring_enabled != self.monitoring_enabled
        coherence_schedule_changed = (
            previous[0].get("coherence_schedule", "none")
            != self.config["coherence_schedule"]
        )
        if monitoring_changed:
            if self.monitoring_enabled:
                async_dismiss_persistent_notification(
                    self.hass, MONITORING_NOTIFICATION_ID
                )
                self._emit_resume_events(previous[1])
            else:
                self._cancel_all_timers()
                self._cancel_all_device_event_timers()
            async_dispatcher_send(self.hass, SIGNAL_MONITORING_UPDATED)
        if coherence_schedule_changed or previous_recovery_active:
            self._refresh_coherence_schedule()
        self._refresh_tracking()
        async_dispatcher_send(self.hass, SIGNAL_HISTORY_UPDATED)
        await self._async_sync_monitoring_notification()
        if previous_recovery_active:
            await self._async_resolve_config_recovery()
        self._publish_if_changed(force=True)
        return {"config": self.get_config(), "summary": summary}

    @_serialize_config_mutation
    async def async_create_rule(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create and immediately evaluate a custom rule."""
        rule = validate_rule_payload(data)
        self._validate_rule_sources(rule)
        self._validate_rule_template(rule)
        previous = self._configuration_snapshot()
        try:
            self.config["rules"].append(rule.as_dict())
            self._rebuild_rule_index()
            for entity_id in rule.entity_ids:
                await self.async_evaluate_entity(entity_id, save=False, publish=False)
            await self._async_save_state()
        except Exception:
            self._restore_configuration_snapshot(previous)
            raise
        self._publish_if_changed()
        return rule.as_dict()

    async def async_create_rule_yaml(self, raw_yaml: str) -> dict[str, Any]:
        """Create a rule from YAML while keeping backend id generation."""
        rule = parse_rule_yaml(raw_yaml)
        return await self.async_create_rule(rule_to_yaml_data(rule))

    @_serialize_config_mutation
    async def async_update_rule(
        self, rule_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Update a rule without changing its identifier."""
        validate_rule_update_fields(data)
        index = self._rule_index(rule_id)
        existing = self.config["rules"][index]
        old_rule = Rule.from_dict(existing)
        rule = validate_rule_payload({**existing, **data}, rule_id=rule_id)
        self._validate_rule_sources(rule)
        self._validate_rule_template(rule)
        previous = self._configuration_snapshot()
        try:
            self.config["rules"][index] = rule.as_dict()
            variation_definition_changed = (
                old_rule.source in VARIATION_SOURCES or rule.source in VARIATION_SOURCES
            ) and (
                old_rule.enabled,
                old_rule.source,
                old_rule.attribute,
                old_rule.condition_template,
            ) != (
                rule.enabled,
                rule.source,
                rule.attribute,
                rule.condition_template,
            )
            if variation_definition_changed:
                for entity_id in set(old_rule.entity_ids) | set(rule.entity_ids):
                    key = f"{rule_id}:{entity_id}"
                    if self._variation_baselines.pop(key, None) is not None:
                        self._variation_baselines_dirty = True
            self._rebuild_rule_index()

            removed_entities = set(old_rule.entity_ids) - set(rule.entity_ids)
            if not rule.enabled:
                removed_entities.update(old_rule.entity_ids)
            old_inactivity = (
                old_rule.source == "unchanged" or old_rule.operator == "unchanged"
            )
            new_inactivity = rule.source == "unchanged" or rule.operator == "unchanged"
            inactivity_changed = (old_inactivity or new_inactivity) and (
                old_rule.source,
                old_rule.attribute,
                old_rule.operator,
                old_rule.condition_template,
            ) != (
                rule.source,
                rule.attribute,
                rule.operator,
                rule.condition_template,
            )
            if inactivity_changed:
                removed_entities.update(set(old_rule.entity_ids) & set(rule.entity_ids))
            if self.monitoring_enabled:
                self._remove_rule_instances(rule_id, removed_entities)

            affected_entities = set(old_rule.entity_ids) | set(rule.entity_ids)
            for entity_id in affected_entities:
                await self.async_evaluate_entity(entity_id, save=False, publish=False)
            if old_rule.message != rule.message:
                for entity_id in rule.entity_ids:
                    self._refresh_active_rule_message(rule, entity_id)
            await self._async_save_state()
        except Exception:
            self._restore_configuration_snapshot(previous)
            raise
        self._publish_if_changed()
        return rule.as_dict()

    async def async_update_rule_yaml(
        self, rule_id: str, raw_yaml: str
    ) -> dict[str, Any]:
        """Update one rule from YAML while preserving its immutable id."""
        rule = parse_rule_yaml(raw_yaml, rule_id=rule_id)
        return await self.async_update_rule(rule_id, rule_to_yaml_data(rule))

    @_serialize_config_mutation
    async def async_delete_rule(self, rule_id: str) -> None:
        """Delete a rule and silently clean only the instances it owns."""
        index = self._rule_index(rule_id)
        rule = Rule.from_dict(self.config["rules"][index])
        previous = self._configuration_snapshot()
        try:
            del self.config["rules"][index]
            self._rebuild_rule_index()
            if self.monitoring_enabled:
                self._remove_rule_instances(rule_id, set(rule.entity_ids))
            for entity_id in rule.entity_ids:
                await self.async_evaluate_entity(entity_id, save=False, publish=False)
            await self._async_save_state()
        except Exception:
            self._restore_configuration_snapshot(previous)
            raise
        self._publish_if_changed()

    def _configuration_snapshot(
        self,
    ) -> tuple[
        dict[str, Any],
        dict[str, AlertRecord],
        list[AlertHistoryEntry],
        dict[str, float],
        bool,
    ]:
        """Copy the state needed to roll back a failed configuration write."""
        return (
            deepcopy(self.config),
            deepcopy(self.records),
            list(self._pending_history),
            dict(self._variation_baselines),
            self._variation_baselines_dirty,
        )

    def _restore_configuration_snapshot(
        self,
        snapshot: tuple[
            dict[str, Any],
            dict[str, AlertRecord],
            list[AlertHistoryEntry],
            dict[str, float],
            bool,
        ],
    ) -> None:
        """Restore configuration, records, indexes and pending timers."""
        self._cancel_all_timers()
        (
            self.config,
            self.records,
            self._pending_history,
            self._variation_baselines,
            self._variation_baselines_dirty,
        ) = snapshot
        self.storage.variation_baselines = self._variation_baselines
        self._rebuild_rule_index()
        self._refresh_tracking()
        self._reschedule_record_timers()

    def _remove_rule_instances(self, rule_id: str, entity_ids: set[str]) -> None:
        """Remove configuration-owned instances without user resolution events."""
        for entity_id in entity_ids:
            alert_id = f"rule:{rule_id}:{entity_id}"
            if self.records.pop(alert_id, None) is not None:
                self._cancel_timer(alert_id)

    def _rule_index(self, rule_id: str) -> int:
        """Find a rule or raise a stable API error."""
        for index, rule in enumerate(self.config["rules"]):
            if rule["id"] == rule_id:
                return index
        raise ValueError(f"Unknown rule id: {rule_id}")


def _deep_merge(base: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    """Merge a partial WebSocket configuration update."""
    for key, value in changes.items():
        if isinstance(base.get(key), dict) and isinstance(value, dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
