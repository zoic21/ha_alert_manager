"""Event-driven alert detection manager."""

from __future__ import annotations

import logging
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.components.persistent_notification import (
    async_create as async_create_persistent_notification,
)
from homeassistant.components.persistent_notification import (
    async_dismiss as async_dismiss_persistent_notification,
)
from homeassistant.config_entries import (
    SIGNAL_CONFIG_ENTRY_CHANGED,
    ConfigEntry,
    ConfigEntryChange,
)
from homeassistant.const import (
    ATTR_FRIENDLY_NAME,
    ATTR_UNIT_OF_MEASUREMENT,
    EVENT_HOMEASSISTANT_STARTED,
    EVENT_STATE_CHANGED,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers import (
    area_registry as ar,
)
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    entity_registry as er,
)
from homeassistant.helpers import (
    label_registry as lr,
)
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from .const import (
    ALERT_MANAGER_ENTITY_IDS,
    CATEGORY_UNAVAILABLE,
    DOMAIN,
    EVENT_ALERT_ACKNOWLEDGED,
    EVENT_ALERT_RESOLVED,
    EVENT_ALERT_STARTED,
    EVENT_ALERT_UNACKNOWLEDGED,
    EVENT_DEVICE_ALERT_STARTED,
    MAX_HISTORY_LIMIT,
    MIN_HISTORY_LIMIT,
    MONITORING_NOTIFICATION_ID,
    SIGNAL_ALERTS_UPDATED,
    SIGNAL_HISTORY_UPDATED,
    SIGNAL_MONITORING_UPDATED,
)
from .models import (
    AlertDetails,
    AlertHistoryEntry,
    AlertRecord,
    AlertStatus,
    Rule,
    advance_record,
    calculate_due_at,
)
from .packs import PACKS, PACKS_BY_ID
from .storage import AlertManagerHistoryStorage, AlertManagerStorage, sort_history
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

_LEGACY_OPERATOR_LABELS = {
    "equals": "Égal à",
    "not_equals": "Différent de",
    "contains": "Contient",
    "not_contains": "Ne contient pas",
    "above": "Supérieur à",
    "below": "Inférieur à",
}


class AlertManager:
    """Own configuration, runtime records, listeners and timers."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the manager."""
        self.hass = hass
        self.entry = entry
        self.storage = AlertManagerStorage(hass)
        self.history_storage = AlertManagerHistoryStorage(hass)
        self._entity_registry = er.async_get(hass)
        self._device_registry = dr.async_get(hass)
        self._area_registry = ar.async_get(hass)
        self.config: dict[str, Any] = {}
        self.records: dict[str, AlertRecord] = {}
        self.history: list[AlertHistoryEntry] = []
        self._pending_history: list[AlertHistoryEntry] = []
        self._rules: list[Rule] = []
        self._rules_by_entity: dict[str, list[Rule]] = {}
        self._unsubscribers: list[Callable[[], None]] = []
        self._pack_entry_unsubscribers: dict[str, Callable[[], None]] = {}
        self._timers: dict[str, Callable[[], None]] = {}
        self._automatic_tracked_entities: set[str] = set()
        self._custom_tracked_count = 0
        self._unloading = False
        self._last_public_snapshot: dict[str, Any] | None = None
        self._pack_availability: dict[str, bool] = {}
        self._excluded_entities: frozenset[str] = frozenset()
        self._excluded_devices: frozenset[str] = frozenset()
        self._excluded_labels: frozenset[str] = frozenset()
        self._active_device_ids: set[str] = set()

    @property
    def monitoring_enabled(self) -> bool:
        """Return whether the main category currently evaluates anomalies."""
        return self.config.get("monitoring_enabled", True)

    async def async_setup(self) -> None:
        """Load persisted state and start event-driven evaluation."""
        config, records, migrated = await self.storage.async_load()
        try:
            history, history_migrated = await self.history_storage.async_load()
        except Exception:
            _LOGGER.exception(
                "Unable to load alert history; starting with an empty view"
            )
            history, history_migrated = [], False
        try:
            self.config = validate_config(config)
        except ValueError:
            _LOGGER.exception("Stored configuration is invalid; using defaults")
            self.config = validate_config({})
            migrated = True
        self.records = records
        self.history = history
        if self._trim_history():
            history_migrated = True
        if self._remove_own_rule_sources():
            migrated = True
        if self._remove_own_records():
            migrated = True
        self._rebuild_rule_index()
        if self._enrich_rule_metadata():
            migrated = True
        self._refresh_pack_entry_listeners()
        self._pack_availability = self._current_pack_availability()
        self._refresh_tracking()
        self._active_device_ids = {
            device["device_id"] for device in self._active_devices()
        }
        if not self.monitoring_enabled and self._freeze_pending_alerts(dt_util.now()):
            migrated = True

        self._unsubscribers.extend(
            (
                self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._state_changed),
                self.hass.bus.async_listen(
                    er.EVENT_ENTITY_REGISTRY_UPDATED, self._registry_changed
                ),
                self.hass.bus.async_listen(
                    dr.EVENT_DEVICE_REGISTRY_UPDATED, self._registry_changed
                ),
                self.hass.bus.async_listen(
                    lr.EVENT_LABEL_REGISTRY_UPDATED, self._registry_changed
                ),
                self.hass.bus.async_listen(
                    ar.EVENT_AREA_REGISTRY_UPDATED, self._registry_changed
                ),
                async_dispatcher_connect(
                    self.hass,
                    SIGNAL_CONFIG_ENTRY_CHANGED,
                    self._config_entry_changed,
                ),
            )
        )

        if self.hass.is_running:
            changed = await self.async_evaluate_all(restoring=True, save=False)
            if migrated or changed:
                await self._async_save_state()
        else:
            if migrated:
                await self._async_save_state()
            self._unsubscribers.append(
                self.hass.bus.async_listen_once(
                    EVENT_HOMEASSISTANT_STARTED, self._home_assistant_started
                )
            )
            self._publish_if_changed(force=True)
        if history_migrated:
            try:
                await self.history_storage.async_save(self.history)
            except Exception:
                _LOGGER.exception("Unable to persist migrated alert history")
        await self._async_sync_monitoring_notification()

    async def async_unload(self) -> None:
        """Remove listeners and timers, persisting a final snapshot."""
        self._unloading = True
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        for unsubscribe in self._pack_entry_unsubscribers.values():
            unsubscribe()
        self._pack_entry_unsubscribers.clear()
        for cancel in self._timers.values():
            cancel()
        self._timers.clear()
        await self._async_save_state()

    @callback
    def _home_assistant_started(self, _event: Event) -> None:
        """Evaluate only after all startup states have had a chance to load."""
        self.entry.async_create_task(
            self.hass,
            self.async_evaluate_all(restoring=True),
            name=f"{DOMAIN} startup evaluation",
        )

    @callback
    def _state_changed(self, event: Event) -> None:
        """Evaluate only the entity whose state changed."""
        if not self.monitoring_enabled:
            return
        entity_id = event.data.get("entity_id")
        if not entity_id or not self._is_relevant_entity_id(entity_id):
            return
        self.entry.async_create_task(
            self.hass,
            self.async_evaluate_entity(entity_id, restoring=not self.hass.is_running),
            name=f"{DOMAIN} evaluate {entity_id}",
        )

    @callback
    def _registry_changed(self, _event: Event) -> None:
        """Labels, disabled state, areas and devices can change eligibility."""
        if not self.monitoring_enabled:
            return
        self.entry.async_create_task(
            self.hass,
            self.async_evaluate_all(),
            name=f"{DOMAIN} registry evaluation",
        )

    @callback
    def _config_entry_changed(
        self, _change: ConfigEntryChange, changed_entry: ConfigEntry
    ) -> None:
        """Track added, removed and updated prerequisite integration entries."""
        if changed_entry.domain not in self._pack_prerequisite_domains():
            return
        self._refresh_pack_entry_listeners()
        self._schedule_pack_availability_refresh()

    @callback
    def _pack_entry_state_changed(self) -> None:
        """Re-evaluate packs when a prerequisite entry loads or unloads."""
        self._schedule_pack_availability_refresh()

    @callback
    def _schedule_pack_availability_refresh(self) -> None:
        """Schedule availability handling on Home Assistant's event loop."""
        if self._unloading:
            return
        self.entry.async_create_task(
            self.hass,
            self.async_refresh_pack_availability(),
            name=f"{DOMAIN} pack availability",
        )

    async def async_refresh_pack_availability(self) -> bool:
        """Apply a changed availability snapshot and clean affected records."""
        if self._unloading:
            return False
        self._refresh_pack_entry_listeners()
        availability = self._current_pack_availability()
        if availability == self._pack_availability:
            return False
        self._pack_availability = availability
        if self.monitoring_enabled:
            await self.async_evaluate_all()
        return True

    def _pack_prerequisite_domains(self) -> set[str]:
        """Return every integration domain used as a pack prerequisite."""
        return {domain for pack in PACKS for domain in pack.prerequisites}

    def _refresh_pack_entry_listeners(self) -> None:
        """Subscribe to state changes of current prerequisite config entries."""
        current_entries = {
            entry.entry_id: entry
            for domain in self._pack_prerequisite_domains()
            for entry in self.hass.config_entries.async_entries(domain)
        }
        for entry_id in self._pack_entry_unsubscribers.keys() - current_entries.keys():
            self._pack_entry_unsubscribers.pop(entry_id)()
        for entry_id, config_entry in current_entries.items():
            if entry_id not in self._pack_entry_unsubscribers:
                self._pack_entry_unsubscribers[entry_id] = (
                    config_entry.async_on_state_change(self._pack_entry_state_changed)
                )

    def _current_pack_availability(self) -> dict[str, bool]:
        """Return current availability keyed by stable pack id."""
        return {pack.id: pack.available(self.hass) for pack in PACKS}

    def _pack_is_available(self, pack_id: str) -> bool:
        """Read the cached availability used by the state-change hot path."""
        return self._pack_availability.get(pack_id, False)

    async def async_evaluate_all(
        self,
        *,
        restoring: bool = False,
        save: bool = True,
        publish: bool = True,
        emit_events: bool = True,
    ) -> bool:
        """Evaluate all current and persisted relevant entities."""
        if self._unloading or not self.monitoring_enabled:
            return False
        self._refresh_tracking()
        entity_ids = {
            state.entity_id
            for state in self.hass.states.async_all()
            if self._is_relevant_entity_id(state.entity_id)
        }
        entity_ids.update(record.details.entity_id for record in self.records.values())
        entity_ids.update(
            entity_id for rule in self.rules for entity_id in rule.entity_ids
        )
        persisted_changed = False
        for entity_id in entity_ids:
            persisted_changed |= await self.async_evaluate_entity(
                entity_id,
                restoring=restoring,
                save=False,
                publish=False,
                emit_events=emit_events,
            )
        if save and persisted_changed:
            await self._async_save_state()
        if publish:
            self._publish_if_changed(
                force=restoring and self._last_public_snapshot is None
            )
        return persisted_changed

    async def async_evaluate_entity(
        self,
        entity_id: str,
        *,
        restoring: bool = False,
        save: bool = True,
        publish: bool = True,
        emit_events: bool = True,
    ) -> bool:
        """Evaluate every automatic category and rule for one entity."""
        if self._unloading or not self.monitoring_enabled:
            return False
        now = dt_util.now()
        state = self.hass.states.get(entity_id)
        self._update_automatic_tracking_for_entity(entity_id, state)
        existing_ids = {
            alert_id
            for alert_id, record in self.records.items()
            if record.details.entity_id == entity_id
        }
        # Missing and unknown states are common while integrations are still
        # starting. They are not proof that a persisted condition recovered.
        # Keep those records until a definitive state change can re-evaluate them.
        if restoring and (state is None or state.state == STATE_UNKNOWN):
            for alert_id in existing_ids:
                record = self.records[alert_id]
                if record.status is AlertStatus.PENDING or not self._active_is_visible(
                    record, now
                ):
                    self._schedule_timer(record)
            if publish:
                self._publish_if_changed()
            return False

        candidates = self._build_candidates(state) if state is not None else {}
        persisted_changed = False

        for alert_id, (details, delay) in candidates.items():
            record = self.records.get(alert_id)
            if record is None:
                record = AlertRecord.pending(details, delay, now)
                self.records[alert_id] = record
                persisted_changed = True
            else:
                # Keep the value that originally opened the alert. Registry and
                # rule metadata may be refreshed, but a later matching state must
                # not hide the actual trigger value shown in the panel/history.
                details.value = record.details.value
                record.details = details
                if record.delay != delay:
                    record.delay = delay
                    record.due_at = calculate_due_at(
                        record.detected_at, delay
                    ) + timedelta(seconds=record.paused_seconds)
                    self._cancel_timer(alert_id)
                    if record.status is AlertStatus.ACTIVE and now.astimezone(
                        UTC
                    ) < record.due_at.astimezone(UTC):
                        record.status = AlertStatus.PENDING
                        record.active_since = None
                        record.visible_at = None
                        record.clear_acknowledgement()
                    elif record.status is AlertStatus.ACTIVE:
                        self._recalculate_hidden_visibility(record, now)
                    persisted_changed = True

            became_active = advance_record(record, now)
            if became_active:
                persisted_changed = True
                self._cancel_timer(alert_id)
                record.visible_at = calculate_due_at(
                    record.active_since,
                    min(self.config["active_display_delay"], record.delay),
                )
                if not self._active_is_visible(record, now):
                    self._schedule_timer(record)
                if emit_events:
                    self._fire_started(record)
            elif (
                record.status is AlertStatus.PENDING
                or not self._active_is_visible(record, now)
            ) and alert_id not in self._timers:
                self._schedule_timer(record)

        for alert_id in existing_ids - candidates.keys():
            record = self.records.pop(alert_id)
            self._cancel_timer(alert_id)
            persisted_changed = True
            if record.status is AlertStatus.ACTIVE:
                self._pending_history.append(AlertHistoryEntry.resolved(record, now))
                if emit_events:
                    self._fire_resolved(record, now)
        if save and persisted_changed:
            await self._async_save_state()
        if publish:
            self._publish_if_changed()
        return persisted_changed

    def _build_candidates(self, state: State) -> dict[str, tuple[AlertDetails, int]]:
        """Build the deduplicated current alert candidates for one state."""
        if not self._is_base_eligible(state.entity_id):
            return {}

        result: dict[str, tuple[AlertDetails, int]] = {}
        entity_id = state.entity_id
        automatic_eligible = self._is_automatic_eligible(entity_id)

        if state.state == STATE_UNAVAILABLE:
            if automatic_eligible:
                self._add_pack_candidate(result, state, CATEGORY_UNAVAILABLE)
            return result

        if state.state == STATE_UNKNOWN:
            return result

        if automatic_eligible:
            for pack in PACKS:
                if pack.id != CATEGORY_UNAVAILABLE:
                    self._add_pack_candidate(result, state, pack.id)

        if self._is_explicitly_excluded(entity_id):
            return result
        for rule in self._rules_by_entity.get(entity_id, ()):
            if not rule.enabled:
                continue
            if rule.source == "attribute" and rule.attribute not in state.attributes:
                continue
            current = (
                state.state
                if rule.source == "state"
                else state.attributes.get(rule.attribute or "")
            )
            if not rule.matches(current):
                continue
            alert_id = f"rule:{rule.id}:{entity_id}"
            condition = rule.message or self._rule_condition(rule, state)
            condition_key = None
            condition_params = None
            if rule.message is None:
                condition_key = "rule.generated"
                condition_params = self._rule_condition_params(rule, state)
            result[alert_id] = (
                self._details(
                    state,
                    alert_id,
                    "rule",
                    condition,
                    value=current,
                    condition_key=condition_key,
                    condition_params=condition_params,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    message=rule.message,
                    source=rule.source,
                    operator=rule.operator,
                    comparison_value=rule.value,
                    attribute=rule.attribute,
                ),
                rule.duration,
            )
        return result

    def _add_pack_candidate(
        self,
        result: dict[str, tuple[AlertDetails, int]],
        state: State,
        pack_id: str,
    ) -> None:
        """Evaluate one enabled pack and append its candidate when matching."""
        config = self.config["automatic"][pack_id]
        pack = PACKS_BY_ID[pack_id]
        if not config["enabled"] or not self._pack_is_available(pack_id):
            return
        match = pack.evaluate(self.hass, state, config)
        if match is None:
            return
        alert_id = f"{pack_id}:{state.entity_id}"
        result[alert_id] = (
            self._details(
                state,
                alert_id,
                pack_id,
                match.condition,
                value=match.value,
                condition_key=match.condition_key,
                condition_params=match.condition_params,
            ),
            self._delay_for(state, pack_id),
        )

    def _is_base_eligible(self, entity_id: str) -> bool:
        """Reject Alert Manager's own and registry-disabled entities."""
        entity_entry = self._entity_registry.async_get(entity_id)
        if entity_id in ALERT_MANAGER_ENTITY_IDS or (
            entity_entry is not None and entity_entry.platform == DOMAIN
        ):
            return False
        if entity_entry is not None and entity_entry.disabled_by is not None:
            return False

        device = None
        if entity_entry is not None and entity_entry.device_id:
            device = self._device_registry.async_get(entity_entry.device_id)
            if device is not None and device.disabled_by is not None:
                return False
        return True

    def _is_explicitly_excluded(self, entity_id: str) -> bool:
        """Apply the existing explicit entity and device exclusions."""
        if entity_id in self._excluded_entities:
            return True
        entity_entry = self._entity_registry.async_get(entity_id)
        return bool(
            entity_entry is not None
            and entity_entry.device_id in self._excluded_devices
        )

    def _is_automatic_eligible(self, entity_id: str) -> bool:
        """Apply explicit and selected-label exclusions to automatic packs only."""
        if self._is_explicitly_excluded(entity_id):
            return False
        if not self._excluded_labels:
            return True
        entity_entry = self._entity_registry.async_get(entity_id)
        if entity_entry is None:
            return True
        if self._excluded_labels.intersection(entity_entry.labels):
            return False

        device = None
        if entity_entry.device_id:
            device = self._device_registry.async_get(entity_entry.device_id)
        return not (
            device is not None and self._excluded_labels.intersection(device.labels)
        )

    def _delay_for(self, state: State, category: str) -> int:
        """Resolve delay priority for automatic detections."""
        entity_id = state.entity_id
        if entity_id in self.config["entity_delays"]:
            return self.config["entity_delays"][entity_id]
        category_delay = self.config["automatic"][category].get("delay")
        if isinstance(category_delay, int):
            return category_delay
        return self.config["global_delay"]

    def _details(
        self,
        state: State,
        alert_id: str,
        alert_type: str,
        condition: str,
        *,
        value: Any | None = None,
        condition_key: str | None = None,
        condition_params: dict[str, Any] | None = None,
        rule_id: str | None = None,
        rule_name: str | None = None,
        message: str | None = None,
        source: str | None = None,
        operator: str | None = None,
        comparison_value: Any = None,
        attribute: str | None = None,
    ) -> AlertDetails:
        """Resolve names, device, area and integration once per evaluation."""
        entity_entry = self._entity_registry.async_get(state.entity_id)
        device = None
        if entity_entry is not None and entity_entry.device_id:
            device = self._device_registry.async_get(entity_entry.device_id)

        area_id = None
        if entity_entry is not None:
            area_id = entity_entry.area_id
        if area_id is None and device is not None:
            area_id = device.area_id
        area_entry = self._area_registry.async_get_area(area_id) if area_id else None

        return AlertDetails(
            id=alert_id,
            type=alert_type,
            entity_id=state.entity_id,
            name=state.attributes.get(ATTR_FRIENDLY_NAME, state.entity_id),
            device_id=(device.id if device is not None else None),
            device_name=(
                (device.name_by_user or device.name) if device is not None else None
            ),
            area=area_entry.name if area_entry is not None else None,
            integration=entity_entry.platform if entity_entry is not None else None,
            value=state.state if value is None else value,
            unit=state.attributes.get(ATTR_UNIT_OF_MEASUREMENT),
            condition=condition,
            condition_key=condition_key,
            condition_params=condition_params,
            rule_id=rule_id,
            rule_name=rule_name,
            message=message,
            source=source,
            operator=operator,
            comparison_value=comparison_value,
            attribute=attribute,
        )

    def _rule_condition_params(self, rule: Rule, state: State) -> dict[str, Any]:
        """Return stable structured parameters for a generated rule condition."""
        return {
            "source": rule.source,
            "attribute": rule.attribute,
            "operator": rule.operator,
            "expected": (
                " / ".join(str(value) for value in rule.value)
                if isinstance(rule.value, list)
                else str(rule.value)
            ),
            "unit": state.attributes.get(ATTR_UNIT_OF_MEASUREMENT),
            "duration": rule.duration,
        }

    def _rule_condition(self, rule: Rule, state: State) -> str:
        """Build a compact human-readable rule condition."""
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        source = f"Attribut {rule.attribute}" if rule.source == "attribute" else "État"
        suffix = f" {unit}" if unit else ""
        duration = f" pendant {rule.duration} s" if rule.duration else ""
        expected = (
            " / ".join(str(value) for value in rule.value)
            if isinstance(rule.value, list)
            else str(rule.value)
        )
        return (
            f"{source} {_LEGACY_OPERATOR_LABELS[rule.operator].lower()} "
            f"{expected}{suffix}{duration}"
        )

    @property
    def rules(self) -> list[Rule]:
        """Return validated rule objects."""
        return list(self._rules)

    def _rebuild_rule_index(self) -> None:
        """Cache validated rule objects by entity for hot-path evaluations."""
        self._refresh_config_caches()
        self._rules = [Rule.from_dict(rule) for rule in self.config.get("rules", [])]
        self._rules_by_entity = {}
        for rule in self._rules:
            for entity_id in rule.entity_ids:
                self._rules_by_entity.setdefault(entity_id, []).append(rule)
        self._refresh_custom_tracking()

    def _refresh_config_caches(self) -> None:
        """Cache exclusion membership used for every state change."""
        self._excluded_entities = frozenset(self.config.get("excluded_entities", ()))
        self._excluded_devices = frozenset(self.config.get("excluded_devices", ()))
        self._excluded_labels = frozenset(self.config.get("excluded_labels", ()))

    def _enrich_rule_metadata(self) -> bool:
        """Add V1.5.5 rule identity fields to persisted runtime records."""
        changed = False
        for record in self.records.values():
            if record.details.type != "rule":
                continue
            prefix = "rule:"
            suffix = f":{record.details.entity_id}"
            if not record.details.id.startswith(
                prefix
            ) or not record.details.id.endswith(suffix):
                continue
            rule_id = record.details.id[len(prefix) : -len(suffix)]
            rule = next(
                (candidate for candidate in self._rules if candidate.id == rule_id),
                None,
            )
            if rule is None:
                continue
            if record.details.rule_id != rule.id:
                record.details.rule_id = rule.id
                changed = True
            if record.details.rule_name != rule.name:
                record.details.rule_name = rule.name
                changed = True
            for field, value in (
                ("message", rule.message),
                ("source", rule.source),
                ("operator", rule.operator),
                ("comparison_value", rule.value),
                ("attribute", rule.attribute),
            ):
                if getattr(record.details, field) != value:
                    setattr(record.details, field, deepcopy(value))
                    changed = True
        return changed

    def _is_own_entity(self, entity_id: str) -> bool:
        """Identify every current or registry-renamed Alert Manager entity."""
        if entity_id in ALERT_MANAGER_ENTITY_IDS:
            return True
        entity_entry = self._entity_registry.async_get(entity_id)
        return entity_entry is not None and entity_entry.platform == DOMAIN

    def _validate_rule_sources(self, rule: Rule) -> None:
        """Reject custom rules targeting Alert Manager itself."""
        if any(self._is_own_entity(entity_id) for entity_id in rule.entity_ids):
            raise ValueError("Alert Manager entities cannot be monitored")

    def _validate_config_rule_sources(self, config: dict[str, Any]) -> None:
        """Apply self-monitoring rejection to a complete imported config."""
        for raw_rule in config["rules"]:
            self._validate_rule_sources(Rule.from_dict(raw_rule))

    def _remove_own_rule_sources(self) -> bool:
        """Clean inert self-references created by earlier versions."""
        changed = False
        cleaned_rules: list[dict[str, Any]] = []
        for raw_rule in self.config.get("rules", []):
            rule = Rule.from_dict(raw_rule)
            allowed = [
                entity_id
                for entity_id in rule.entity_ids
                if not self._is_own_entity(entity_id)
            ]
            if allowed != rule.entity_ids:
                changed = True
            if not allowed:
                continue
            rule.entity_ids = allowed
            cleaned_rules.append(rule.as_dict())
        if changed:
            self.config["rules"] = cleaned_rules
        return changed

    def _remove_own_records(self) -> bool:
        """Remove impossible self-alerts left by earlier runtime snapshots."""
        own_ids = [
            alert_id
            for alert_id, record in self.records.items()
            if self._is_own_entity(record.details.entity_id)
        ]
        for alert_id in own_ids:
            self.records.pop(alert_id)
        return bool(own_ids)

    def _is_relevant_entity_id(self, entity_id: str) -> bool:
        """Return whether a state change can affect an alert or existing record."""
        if not self._is_base_eligible(entity_id):
            return False
        if entity_id in self._rules_by_entity:
            return True
        if any(
            record.details.entity_id == entity_id for record in self.records.values()
        ):
            return True
        domain = entity_id.partition(".")[0]
        automatic = self.config.get("automatic", {})
        unavailable = automatic.get(CATEGORY_UNAVAILABLE, {})
        if unavailable.get("enabled"):
            return True
        pack_ids = {
            pack.id
            for pack in PACKS
            if automatic.get(pack.id, {}).get("enabled", False)
            and self._pack_is_available(pack.id)
        }
        return (
            (domain == "binary_sensor" and "connectivity" in pack_ids)
            or (domain == "device_tracker" and "unifi" in pack_ids)
            or (domain == "sensor" and "battery" in pack_ids)
        )

    def public_snapshot(self) -> dict[str, Any]:
        """Return active and pending lists without resolved history."""
        now = dt_util.now()
        active_records = sorted(
            (
                record
                for record in self.records.values()
                if record.status is AlertStatus.ACTIVE
                and self._active_is_visible(record, now)
            ),
            key=lambda record: (record.active_since or record.due_at).astimezone(UTC),
        )
        pending_records = sorted(
            (
                record
                for record in self.records.values()
                if record.status is AlertStatus.PENDING
            ),
            key=lambda record: record.due_at.astimezone(UTC),
        )
        active = [record.as_public_dict() for record in active_records]
        unacknowledged = [
            alert for alert in active if alert.get("acknowledged") is not True
        ]
        acknowledged = [alert for alert in active if alert.get("acknowledged") is True]
        pending = [record.as_public_dict() for record in pending_records]
        active_devices = self._active_devices(active_records)
        return {
            "active_count": len(unacknowledged),
            "acknowledge_count": len(acknowledged),
            "pending_count": len(pending),
            "tracked_count": self._tracked_count(),
            "alerts": unacknowledged,
            "acknowledge": acknowledged,
            "pending": pending,
            "device_active_count": len(active_devices),
            "active_devices": active_devices,
        }

    def _active_is_visible(
        self, record: AlertRecord, now: datetime | None = None
    ) -> bool:
        """Return whether an active occurrence reached its presentation time."""
        if record.status is not AlertStatus.ACTIVE:
            return False
        if record.visible_at is None:
            return True
        current = now or dt_util.now()
        return current.astimezone(UTC) >= record.visible_at.astimezone(UTC)

    def _recalculate_hidden_visibility(
        self, record: AlertRecord, now: datetime
    ) -> None:
        """Apply current delay settings only while an alert is still hidden."""
        if record.active_since is None or self._active_is_visible(record, now):
            return
        record.visible_at = calculate_due_at(
            record.active_since,
            min(self.config["active_display_delay"], record.delay),
        )

    def _active_devices(
        self, active_records: list[AlertRecord] | None = None
    ) -> list[dict[str, Any]]:
        """Group visible active occurrences by Home Assistant device."""
        records = active_records
        if records is None:
            now = dt_util.now()
            records = [
                record
                for record in self.records.values()
                if record.status is AlertStatus.ACTIVE
                and self._active_is_visible(record, now)
            ]
        grouped: dict[str, list[AlertRecord]] = {}
        for record in records:
            if record.details.device_id:
                grouped.setdefault(record.details.device_id, []).append(record)

        devices = []
        for device_id, device_records in grouped.items():
            ordered = sorted(
                device_records,
                key=lambda record: (record.active_since or record.due_at).astimezone(
                    UTC
                ),
            )
            first = ordered[0]
            alert_ids = [record.details.id for record in ordered]
            acknowledged = sum(record.acknowledged for record in ordered)
            devices.append(
                {
                    "device_id": device_id,
                    "device_name": first.details.device_name or device_id,
                    "area": first.details.area,
                    "started_at": (first.active_since or first.due_at).isoformat(),
                    "alert_count": len(ordered),
                    "unacknowledged_alert_count": len(ordered) - acknowledged,
                    "acknowledged_alert_count": acknowledged,
                    "alert_ids": alert_ids,
                }
            )
        return sorted(
            devices,
            key=lambda device: (
                str(device["device_name"]).casefold(),
                device["device_id"],
            ),
        )

    def _tracked_count(self) -> int:
        """Count enabled custom instances and unique automatic sources."""
        return self._custom_tracked_count + len(self._automatic_tracked_entities)

    def _refresh_tracking(self) -> None:
        """Refresh tracked-source caches during infrequent full evaluations."""
        self._refresh_custom_tracking()
        self._automatic_tracked_entities = {
            state.entity_id
            for state in self.hass.states.async_all()
            if self._is_automatically_tracked(state)
        }

    def _refresh_custom_tracking(self) -> None:
        """Refresh enabled custom rule/entity pairs after config changes."""
        self._custom_tracked_count = sum(
            1
            for rule in self._rules
            if rule.enabled
            for entity_id in rule.entity_ids
            if self._is_base_eligible(entity_id)
            and not self._is_explicitly_excluded(entity_id)
        )

    def _update_automatic_tracking_for_entity(
        self, entity_id: str, state: State | None
    ) -> None:
        """Update one automatic tracked-source membership in constant time."""
        if state is not None and self._is_automatically_tracked(state):
            self._automatic_tracked_entities.add(entity_id)
        else:
            self._automatic_tracked_entities.discard(entity_id)

    def _is_automatically_tracked(self, state: State) -> bool:
        """Return whether at least one enabled automatic pack monitors a state."""
        return (
            self._is_base_eligible(state.entity_id)
            and self._is_automatic_eligible(state.entity_id)
            and any(
                self.config["automatic"][pack.id]["enabled"]
                and self._pack_is_available(pack.id)
                and pack.applies(self.hass, state)
                for pack in PACKS
            )
        )

    def get_config(self) -> dict[str, Any]:
        """Return a defensive copy for WebSocket clients."""
        return deepcopy(self.config)

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
            await self._async_save_state()
        except Exception:
            self.config = previous_config
            self.records = previous_records
            self._pending_history = previous_pending_history
            self._cancel_all_timers()
            self._reschedule_record_timers()
            raise

        if enabled:
            async_dismiss_persistent_notification(self.hass, MONITORING_NOTIFICATION_ID)
            self._emit_resume_events(previous_records)
        else:
            self._cancel_all_timers()
        self._refresh_tracking()
        self._publish_if_changed(force=True)
        async_dispatcher_send(self.hass, SIGNAL_MONITORING_UPDATED)
        return True

    async def _async_sync_monitoring_notification(self) -> None:
        """Keep one localized persistent startup warning in sync."""
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
        return rule_to_yaml_data(rule)

    def export_config_yaml(self) -> str:
        """Return a deterministic, runtime-free YAML configuration export."""
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

    async def async_update_config(self, changes: dict[str, Any]) -> dict[str, Any]:
        """Validate, atomically persist and immediately apply config changes."""
        validate_config_update(changes)
        if "rules" in changes:
            raise ValueError("Rules must be changed through the rules API")
        candidate = _deep_merge(self.get_config(), changes)
        # Entity delays are a complete mapping from the settings form, not a
        # partial nested update. Replacing it allows removed rows to disappear.
        if "entity_delays" in changes:
            candidate["entity_delays"] = deepcopy(changes["entity_delays"])
        candidate["rules"] = self.config["rules"]
        candidate = validate_config(candidate)
        previous = self._configuration_snapshot()
        try:
            self.config = candidate
            self._rebuild_rule_index()
            await self.async_evaluate_all(save=False, publish=False)
            if "active_display_delay" in changes:
                self._reschedule_hidden_active_visibility(dt_util.now())
            await self._async_save_state()
        except Exception:
            self._restore_configuration_snapshot(previous)
            raise
        self._publish_if_changed()
        return self.get_config()

    async def async_import_config(self, raw_yaml: str) -> dict[str, Any]:
        """Atomically replace configuration after fully parsing its YAML document.

        Runtime records are never read from the import.  They are reconciled
        against the newly valid configuration and persisted together with it in
        one Store write.  A failed write restores the in-memory configuration,
        records and pending timers.
        """
        candidate = parse_config_yaml(raw_yaml)
        # Retention is panel configuration, deliberately absent from YAML.
        candidate["history_limit"] = self.config["history_limit"]
        self._validate_config_rule_sources(candidate)
        summary = import_summary(candidate)
        previous = self._configuration_snapshot()

        self._cancel_all_timers()
        try:
            self.config = candidate
            self._rebuild_rule_index()
            if self.monitoring_enabled:
                self._resume_pending_alerts(dt_util.now())
            else:
                self._freeze_pending_alerts(dt_util.now())
            await self.async_evaluate_all(
                save=False,
                publish=False,
                emit_events=False,
            )
            self._reschedule_hidden_active_visibility(dt_util.now())
            await self._async_save_state()
        except Exception:
            self._restore_configuration_snapshot(previous)
            raise

        monitoring_changed = (
            previous[0].get("monitoring_enabled", True) != self.monitoring_enabled
        )
        if monitoring_changed:
            if self.monitoring_enabled:
                async_dismiss_persistent_notification(
                    self.hass, MONITORING_NOTIFICATION_ID
                )
                self._emit_resume_events(previous[1])
            else:
                self._cancel_all_timers()
            async_dispatcher_send(self.hass, SIGNAL_MONITORING_UPDATED)
        self._publish_if_changed(force=True)
        return {"config": self.get_config(), "summary": summary}

    async def async_create_rule(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create and immediately evaluate a custom rule."""
        rule = validate_rule_payload(data)
        self._validate_rule_sources(rule)
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
        previous = self._configuration_snapshot()
        try:
            self.config["rules"][index] = rule.as_dict()
            self._rebuild_rule_index()

            removed_entities = set(old_rule.entity_ids) - set(rule.entity_ids)
            if not rule.enabled:
                removed_entities.update(old_rule.entity_ids)
            if self.monitoring_enabled:
                self._remove_rule_instances(rule_id, removed_entities)

            affected_entities = set(old_rule.entity_ids) | set(rule.entity_ids)
            for entity_id in affected_entities:
                await self.async_evaluate_entity(entity_id, save=False, publish=False)
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
    ) -> tuple[dict[str, Any], dict[str, AlertRecord], list[AlertHistoryEntry]]:
        """Copy the state needed to roll back a failed configuration write."""
        return (
            deepcopy(self.config),
            deepcopy(self.records),
            list(self._pending_history),
        )

    def _restore_configuration_snapshot(
        self,
        snapshot: tuple[
            dict[str, Any], dict[str, AlertRecord], list[AlertHistoryEntry]
        ],
    ) -> None:
        """Restore configuration, records, indexes and pending timers."""
        self._cancel_all_timers()
        self.config, self.records, self._pending_history = snapshot
        self._rebuild_rule_index()
        self._refresh_tracking()
        self._reschedule_record_timers()

    def _remove_rule_instances(self, rule_id: str, entity_ids: set[str]) -> None:
        """Remove configuration-owned instances without user resolution events."""
        for entity_id in entity_ids:
            alert_id = f"rule:{rule_id}:{entity_id}"
            if self.records.pop(alert_id, None) is not None:
                self._cancel_timer(alert_id)

    def _cancel_all_timers(self) -> None:
        """Cancel each scheduled due transition before a full rebuild."""
        for cancel in self._timers.values():
            cancel()
        self._timers.clear()

    async def _async_save_state(self) -> None:
        """Persist runtime first, then archive without coupling business success."""
        await self.storage.async_save(self.config, self.records)
        await self._async_flush_history()

    async def _async_flush_history(self) -> None:
        """Best-effort archive queued resolutions after runtime is durable."""
        if not self._pending_history:
            return
        if self.config["history_limit"] == 0:
            self._pending_history.clear()
            return
        candidate = sort_history([*self.history, *self._pending_history])[
            : self.config["history_limit"]
        ]
        try:
            await self.history_storage.async_save(candidate)
        except Exception:
            _LOGGER.exception(
                "Unable to persist completed alert history; runtime transition "
                "remains valid"
            )
            return
        self.history = candidate
        self._pending_history.clear()
        async_dispatcher_send(self.hass, SIGNAL_HISTORY_UPDATED)

    def _trim_history(self) -> bool:
        """Apply the configured retention limit deterministically in memory."""
        trimmed = sort_history(self.history)[: self.config["history_limit"]]
        if trimmed == self.history:
            return False
        self.history = trimmed
        return True

    def _freeze_pending_alerts(self, now: datetime) -> bool:
        """Remember when each pending delay stopped consuming monitored time."""
        changed = False
        for record in self.records.values():
            if record.status is AlertStatus.PENDING and record.paused_at is None:
                record.paused_at = now
                changed = True
        return changed

    def _resume_pending_alerts(self, now: datetime) -> bool:
        """Move due dates by the suspension duration, preserving remaining time."""
        changed = False
        now_utc = now.astimezone(UTC)
        for record in self.records.values():
            if record.status is not AlertStatus.PENDING or record.paused_at is None:
                continue
            paused_for = now_utc - record.paused_at.astimezone(UTC)
            if paused_for.total_seconds() > 0:
                record.due_at += paused_for
                record.paused_seconds += paused_for.total_seconds()
            record.paused_at = None
            changed = True
        return changed

    def _reschedule_record_timers(self) -> None:
        """Restore transition and visibility timers after a configuration swap."""
        if not self.monitoring_enabled:
            return
        for record in self.records.values():
            if record.status is AlertStatus.PENDING or not self._active_is_visible(
                record
            ):
                self._schedule_timer(record)

    def _reschedule_hidden_active_visibility(self, now: datetime) -> None:
        """Recalculate only not-yet-exposed active alerts and their timers."""
        for record in self.records.values():
            if record.status is not AlertStatus.ACTIVE:
                continue
            self._recalculate_hidden_visibility(record, now)
            self._cancel_timer(record.details.id)
            if not self._active_is_visible(record, now):
                self._schedule_timer(record)

    def _rule_index(self, rule_id: str) -> int:
        """Find a rule or raise a stable API error."""
        for index, rule in enumerate(self.config["rules"]):
            if rule["id"] == rule_id:
                return index
        raise ValueError(f"Unknown rule id: {rule_id}")

    def _schedule_timer(self, record: AlertRecord) -> None:
        """Schedule exactly one lifecycle or presentation timer for an alert."""
        if not self.monitoring_enabled:
            return
        alert_id = record.details.id
        self._cancel_timer(alert_id)
        if record.status is AlertStatus.PENDING:
            when = record.due_at.astimezone(UTC)
        elif record.visible_at is not None and not self._active_is_visible(record):
            when = record.visible_at.astimezone(UTC)
        else:
            return

        @callback
        def timer_due(_now: datetime) -> None:
            """Run the timer handler on Home Assistant's event loop."""
            self._timer_due(alert_id)

        self._timers[alert_id] = async_track_point_in_utc_time(
            self.hass,
            timer_due,
            when,
        )

    @callback
    def _timer_due(self, alert_id: str) -> None:
        """Re-evaluate the source at due time instead of blindly activating."""
        self._timers.pop(alert_id, None)
        if not self.monitoring_enabled:
            return
        record = self.records.get(alert_id)
        if record is None:
            return
        self.entry.async_create_task(
            self.hass,
            self.async_evaluate_entity(record.details.entity_id),
            name=f"{DOMAIN} timer {alert_id}",
        )

    def _cancel_timer(self, alert_id: str) -> None:
        """Cancel a pending timer if present."""
        if cancel := self._timers.pop(alert_id, None):
            cancel()

    def _fire_started(self, record: AlertRecord) -> None:
        """Emit the documented start event exactly on activation."""
        self.hass.bus.async_fire(EVENT_ALERT_STARTED, record.as_public_dict())

    def _fire_resolved(self, record: AlertRecord, now: datetime) -> None:
        """Emit resolution information without retaining history."""
        data = record.as_public_dict()
        data["resolved_at"] = now.isoformat()
        self.hass.bus.async_fire(EVENT_ALERT_RESOLVED, data)

    def _fire_acknowledged(self, record: AlertRecord) -> None:
        """Emit an acknowledgement event only after durable state changed."""
        self.hass.bus.async_fire(EVENT_ALERT_ACKNOWLEDGED, record.as_public_dict())

    def _fire_unacknowledged(
        self,
        record: AlertRecord,
        now: datetime,
        actor: str | None,
        previous_at: datetime | None,
        previous_by: str | None,
    ) -> None:
        """Emit removal metadata without retaining it on the active alert."""
        data = record.as_public_dict()
        data["unacknowledged_at"] = now.isoformat()
        if actor is not None:
            data["unacknowledged_by"] = actor
        if previous_at is not None:
            data["previous_acknowledged_at"] = previous_at.isoformat()
        if previous_by is not None:
            data["previous_acknowledged_by"] = previous_by
        self.hass.bus.async_fire(EVENT_ALERT_UNACKNOWLEDGED, data)

    def _fire_new_device_alerts(self, snapshot: dict[str, Any]) -> None:
        """Emit one event when a device enters the visible active set."""
        devices = {
            device["device_id"]: device for device in snapshot.get("active_devices", [])
        }
        for device_id in sorted(devices.keys() - self._active_device_ids):
            self.hass.bus.async_fire(EVENT_DEVICE_ALERT_STARTED, devices[device_id])
        self._active_device_ids = set(devices)

    def _publish_if_changed(self, *, force: bool = False) -> None:
        """Avoid redundant sensor writes and Recorder churn."""
        snapshot = self.public_snapshot()
        if not force and snapshot == self._last_public_snapshot:
            return
        self._fire_new_device_alerts(snapshot)
        self._last_public_snapshot = deepcopy(snapshot)
        async_dispatcher_send(self.hass, SIGNAL_ALERTS_UPDATED)


def _deep_merge(base: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    """Merge a partial WebSocket configuration update."""
    for key, value in changes.items():
        if isinstance(base.get(key), dict) and isinstance(value, dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
