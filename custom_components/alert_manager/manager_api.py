"""Public Alert Manager API and configuration mutations."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import UTC
from functools import wraps
from typing import Any

from homeassistant.components.persistent_notification import (
    async_create as async_create_persistent_notification,
)
from homeassistant.components.persistent_notification import (
    async_dismiss as async_dismiss_persistent_notification,
)
from homeassistant.const import (
    ATTR_FRIENDLY_NAME,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
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
from .packs import PACKS, PACKS_BY_ID, reset_pack_runtimes
from .storage import sort_history
from .validation import (
    validate_config,
    validate_config_update,
    validate_rule_count,
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

_DELETED_ENTITIES_LIMIT = 50


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


def _variation_reference_signature(
    rule: Rule,
) -> tuple[bool, str, str | None, str | None]:
    """Return the rule fields that define one variation reference window."""
    return rule.enabled, rule.source, rule.attribute, rule.condition_template


def _inactivity_reference_signature(
    rule: Rule,
) -> tuple[bool, str, str | None, str, str | None]:
    """Return the rule fields that define one inactivity window."""
    return (
        rule.enabled,
        rule.source,
        rule.attribute,
        rule.operator,
        rule.condition_template,
    )


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

    async def async_test_notification_profile(self, profile_id: str) -> dict[str, Any]:
        """Send a test without creating or changing any alert state."""
        return await self.notifications.async_test_profile(profile_id)

    async def _async_refresh_notification_runtime(
        self, *, reset_reminders: bool = False
    ) -> None:
        """Apply config changes without coupling them to alert persistence."""
        try:
            await self.notification_runtime.async_config_updated(
                reset_reminders=reset_reminders
            )
        except Exception:
            _LOGGER.exception("Unable to refresh Alert Manager notification runtime")

    async def async_test_rule(
        self, data: dict[str, Any], *, rule_id: str | None = None
    ) -> dict[str, Any]:
        """Evaluate a complete draft rule without mutating manager state."""
        existing_rule: Rule | None = None
        if rule_id is None:
            validate_rule_count(len(self.config["rules"]) + 1)
            rule = validate_rule_payload(data)
        else:
            validate_rule_update_fields(data)
            existing = self.config["rules"][self._rule_index(rule_id)]
            existing_rule = Rule.from_dict(existing)
            rule = validate_rule_payload({**existing, **data}, rule_id=rule_id)
        self._validate_rule_sources(rule)
        self._validate_rule_template(rule)

        baseline_compatible = existing_rule is not None and (
            _variation_reference_signature(existing_rule)
            == _variation_reference_signature(rule)
        )
        inactivity_compatible = existing_rule is not None and (
            _inactivity_reference_signature(existing_rule)
            == _inactivity_reference_signature(rule)
        )

        results = [
            self._test_rule_entity(
                rule,
                entity_id,
                allow_runtime_baseline=baseline_compatible,
                allow_runtime_inactivity=inactivity_compatible,
            )
            for entity_id in rule.entity_ids
        ]
        return {
            "enabled": rule.enabled,
            "duration": rule.duration,
            "total": len(results),
            "matched_count": sum(item["status"] == "match" for item in results),
            "not_matched_count": sum(item["status"] == "no_match" for item in results),
            "indeterminate_count": sum(
                item["status"] == "indeterminate" for item in results
            ),
            "error_count": sum(item["status"] == "error" for item in results),
            "results": results,
        }

    def _test_rule_entity(
        self,
        rule: Rule,
        entity_id: str,
        *,
        allow_runtime_baseline: bool,
        allow_runtime_inactivity: bool,
    ) -> dict[str, Any]:
        """Return one compact rule test result for one selected entity."""
        state = self.hass.states.get(entity_id)
        base = {
            "entity_id": entity_id,
            "name": (
                state.attributes.get(ATTR_FRIENDLY_NAME, entity_id)
                if state is not None
                else entity_id
            ),
            "state": state.state if state is not None else None,
            "source": rule.source,
            "attribute": rule.attribute,
            "operator": (
                None if rule.source in ("jinja", "unchanged") else rule.operator
            ),
            "comparison_value": (
                None
                if rule.source in ("jinja", "unchanged") or rule.operator == "unchanged"
                else rule.value
            ),
            "duration": rule.duration,
            "unit": (
                state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
                if state is not None
                else None
            ),
        }
        if state is None:
            return {**base, "status": "error", "reason": "entity_not_found"}
        if not self._is_base_eligible(entity_id):
            return {**base, "status": "error", "reason": "entity_disabled"}
        if state.state == STATE_UNAVAILABLE:
            return {**base, "status": "no_match", "reason": "state_unavailable"}
        if state.state == STATE_UNKNOWN:
            return {**base, "status": "no_match", "reason": "state_unknown"}

        evaluation = self._evaluate_custom_rule(
            rule,
            state,
            dry_run=True,
            allow_runtime_baseline=allow_runtime_baseline,
        )
        message, message_error = (None, None)
        if evaluation.error_code is None and (
            rule.source not in VARIATION_SOURCES or evaluation.baseline is not None
        ):
            message, message_error = self._render_rule_message_for_test(
                rule, state, evaluation.value
            )
        status = (
            "indeterminate"
            if evaluation.error_code == "baseline_unavailable"
            else "error"
            if evaluation.error_code is not None
            else "match"
            if evaluation.result is True
            else "no_match"
        )
        result = {
            **base,
            "status": status,
            "raw_value": evaluation.raw_value,
            "value": evaluation.value,
            "comparison_result": evaluation.comparison_result,
            "jinja_result": evaluation.jinja_result,
            "final_result": evaluation.result,
            "baseline": evaluation.baseline,
            "message": message,
            "message_error": message_error,
            "reason": evaluation.error_code,
            "error_detail": evaluation.error_detail,
        }
        if rule.source in VARIATION_SOURCES:
            result["current_value"] = evaluation.raw_value
            result["variation"] = (
                evaluation.value if evaluation.baseline is not None else None
            )
        if rule.source == "unchanged" or rule.operator == "unchanged":
            result.update(
                self._test_rule_inactivity(
                    rule,
                    state,
                    allow_runtime=allow_runtime_inactivity,
                )
            )
        return result

    def _test_rule_inactivity(
        self, rule: Rule, state: Any, *, allow_runtime: bool
    ) -> dict[str, Any]:
        """Read the same inactivity reference available to normal evaluation."""
        reference = None
        if allow_runtime:
            record = self.records.get(f"rule:{rule.id}:{state.entity_id}")
            if record is not None:
                reference = record.detected_at
        if reference is None and rule.condition_template is None:
            if rule.source == "unchanged":
                reference = state.last_updated
            elif rule.source == "state":
                reference = getattr(state, "last_changed", state.last_updated)
        if reference is None:
            return {
                "unchanged_since": None,
                "unchanged_seconds": None,
                "duration_reached": None,
            }
        elapsed = max(
            0,
            int(
                (
                    dt_util.now().astimezone(UTC) - reference.astimezone(UTC)
                ).total_seconds()
            ),
        )
        return {
            "unchanged_since": reference.isoformat(),
            "unchanged_seconds": elapsed,
            "duration_reached": elapsed >= rule.duration,
        }

    def deleted_entities_snapshot(self) -> dict[str, Any]:
        """Return the newest deleted entities still retained by Home Assistant."""
        entries = sorted(
            self._entity_registry.deleted_entities.values(),
            key=lambda entry: entry.modified_at,
            reverse=True,
        )
        return {
            "entities": [
                {
                    "entity_id": entry.entity_id,
                    "name": entry.name,
                    "platform": entry.platform,
                    "deleted_at": entry.modified_at.isoformat(),
                }
                for entry in entries[:_DELETED_ENTITIES_LIMIT]
            ],
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

        self.notification_runtime.pause_events()
        self.notification_runtime.discard_batches()
        previous_config = deepcopy(self.config)
        previous_records = deepcopy(self.records)
        previous_pending_history = list(self._pending_history)
        previous_variation_baselines = dict(self._variation_baselines)
        previous_variation_dirty = self._variation_baselines_dirty
        previous_pack_runtime = deepcopy(self._pack_runtime)
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
                self._pack_runtime.clear()
            await self._async_save_state()
        except Exception:
            self.config = previous_config
            self._replace_records(previous_records)
            self._pending_history = previous_pending_history
            self._variation_baselines = previous_variation_baselines
            self.storage.variation_baselines = self._variation_baselines
            self._variation_baselines_dirty = previous_variation_dirty
            self._pack_runtime = previous_pack_runtime
            self.storage.pack_runtime = self._pack_runtime
            self._cancel_all