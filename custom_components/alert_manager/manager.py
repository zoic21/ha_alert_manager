"""Event-driven alert detection manager."""

from __future__ import annotations

import logging
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

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
from homeassistant.util import dt as dt_util

from .const import (
    CATEGORY_UNAVAILABLE,
    DOMAIN,
    EVENT_ALERT_ACKNOWLEDGED,
    EVENT_ALERT_RESOLVED,
    EVENT_ALERT_STARTED,
    EVENT_ALERT_UNACKNOWLEDGED,
    SIGNAL_ALERTS_UPDATED,
)
from .models import (
    AlertDetails,
    AlertRecord,
    AlertStatus,
    Rule,
    advance_record,
    calculate_due_at,
)
from .packs import PACKS, PACKS_BY_ID
from .storage import AlertManagerStorage
from .validation import (
    validate_config,
    validate_config_update,
    validate_rule_payload,
    validate_rule_update_fields,
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
        self.config: dict[str, Any] = {}
        self.records: dict[str, AlertRecord] = {}
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

    async def async_setup(self) -> None:
        """Load persisted state and start event-driven evaluation."""
        config, records, migrated = await self.storage.async_load()
        try:
            self.config = validate_config(config)
        except ValueError:
            _LOGGER.exception("Stored configuration is invalid; using defaults")
            self.config = validate_config({})
        self.records = records
        self._rebuild_rule_index()
        self._refresh_pack_entry_listeners()
        self._pack_availability = self._current_pack_availability()
        self._refresh_tracking()

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
                await self.storage.async_save(self.config, self.records)
        else:
            if migrated:
                await self.storage.async_save(self.config, self.records)
            self._unsubscribers.append(
                self.hass.bus.async_listen_once(
                    EVENT_HOMEASSISTANT_STARTED, self._home_assistant_started
                )
            )
            self._publish_if_changed(force=True)

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
        await self.storage.async_save(self.config, self.records)

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
        self, *, restoring: bool = False, save: bool = True
    ) -> bool:
        """Evaluate all current and persisted relevant entities."""
        if self._unloading:
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
            )
        if save and persisted_changed:
            await self.storage.async_save(self.config, self.records)
        self._publish_if_changed(force=restoring and self._last_public_snapshot is None)
        return persisted_changed

    async def async_evaluate_entity(
        self,
        entity_id: str,
        *,
        restoring: bool = False,
        save: bool = True,
        publish: bool = True,
    ) -> bool:
        """Evaluate every automatic category and rule for one entity."""
        if self._unloading:
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
                if record.status is AlertStatus.PENDING:
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
                record.details = details
                if record.delay != delay:
                    record.delay = delay
                    record.due_at = calculate_due_at(record.detected_at, delay)
                    self._cancel_timer(alert_id)
                    if record.status is AlertStatus.ACTIVE and now.astimezone(
                        UTC
                    ) < record.due_at.astimezone(UTC):
                        record.status = AlertStatus.PENDING
                        record.active_since = None
                        record.clear_acknowledgement()
                    persisted_changed = True

            became_active = advance_record(record, now)
            if became_active:
                persisted_changed = True
                self._cancel_timer(alert_id)
                self._fire_started(record)
            elif record.status is AlertStatus.PENDING and alert_id not in self._timers:
                self._schedule_timer(record)

        for alert_id in existing_ids - candidates.keys():
            record = self.records.pop(alert_id)
            self._cancel_timer(alert_id)
            persisted_changed = True
            if record.status is AlertStatus.ACTIVE:
                self._fire_resolved(record, now)

        if save and persisted_changed:
            await self.storage.async_save(self.config, self.records)
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
        entity_entry = er.async_get(self.hass).async_get(entity_id)
        if entity_id == "sensor.alert_manager" or (
            entity_entry is not None and entity_entry.platform == DOMAIN
        ):
            return False
        if entity_entry is not None and entity_entry.disabled_by is not None:
            return False

        device = None
        if entity_entry is not None and entity_entry.device_id:
            device = dr.async_get(self.hass).async_get(entity_entry.device_id)
            if device is not None and device.disabled_by is not None:
                return False
        return True

    def _is_explicitly_excluded(self, entity_id: str) -> bool:
        """Apply the existing explicit entity and device exclusions."""
        if entity_id in self.config["excluded_entities"]:
            return True
        entity_entry = er.async_get(self.hass).async_get(entity_id)
        return bool(
            entity_entry is not None
            and entity_entry.device_id in self.config["excluded_devices"]
        )

    def _is_automatic_eligible(self, entity_id: str) -> bool:
        """Apply explicit and selected-label exclusions to automatic packs only."""
        if self._is_explicitly_excluded(entity_id):
            return False
        excluded_labels = set(self.config["excluded_labels"])
        if not excluded_labels:
            return True
        entity_entry = er.async_get(self.hass).async_get(entity_id)
        if entity_entry is None:
            return True
        if excluded_labels.intersection(entity_entry.labels):
            return False

        device = None
        if entity_entry.device_id:
            device = dr.async_get(self.hass).async_get(entity_entry.device_id)
        return not (device is not None and excluded_labels.intersection(device.labels))

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
    ) -> AlertDetails:
        """Resolve names, device, area and integration once per evaluation."""
        entity_entry = er.async_get(self.hass).async_get(state.entity_id)
        device = None
        if entity_entry is not None and entity_entry.device_id:
            device = dr.async_get(self.hass).async_get(entity_entry.device_id)

        area_id = None
        if entity_entry is not None:
            area_id = entity_entry.area_id
        if area_id is None and device is not None:
            area_id = device.area_id
        area_entry = (
            ar.async_get(self.hass).async_get_area(area_id) if area_id else None
        )

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
        self._rules = [Rule.from_dict(rule) for rule in self.config.get("rules", [])]
        self._rules_by_entity = {}
        for rule in self._rules:
            for entity_id in rule.entity_ids:
                self._rules_by_entity.setdefault(entity_id, []).append(rule)
        self._refresh_custom_tracking()

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
        active_records = sorted(
            (
                record
                for record in self.records.values()
                if record.status is AlertStatus.ACTIVE
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
        return {
            "active_count": len(active),
            "acknowledge_count": len(acknowledged),
            "pending_count": len(pending),
            "tracked_count": self._tracked_count(),
            "alerts": unacknowledged,
            "acknowledge": acknowledged,
            "pending": pending,
        }

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

    def get_packs(self) -> list[dict[str, Any]]:
        """Return backend-owned pack metadata with current availability."""
        return [pack.as_public_dict(self.hass) for pack in PACKS]

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
            await self.storage.async_save(self.config, self.records)
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
            await self.storage.async_save(self.config, self.records)
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
        self.config = validate_config(candidate)
        self._rebuild_rule_index()
        await self.async_evaluate_all(save=False)
        await self.storage.async_save(self.config, self.records)
        return self.get_config()

    async def async_create_rule(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create and immediately evaluate a custom rule."""
        rule = validate_rule_payload(data)
        self.config["rules"].append(rule.as_dict())
        self._rebuild_rule_index()
        for entity_id in rule.entity_ids:
            await self.async_evaluate_entity(entity_id, save=False, publish=False)
        self._publish_if_changed()
        await self.storage.async_save(self.config, self.records)
        return rule.as_dict()

    async def async_update_rule(
        self, rule_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Update a rule without changing its identifier."""
        validate_rule_update_fields(data)
        index = self._rule_index(rule_id)
        existing = self.config["rules"][index]
        old_rule = Rule.from_dict(existing)
        rule = validate_rule_payload({**existing, **data}, rule_id=rule_id)
        self.config["rules"][index] = rule.as_dict()
        self._rebuild_rule_index()

        removed_entities = set(old_rule.entity_ids) - set(rule.entity_ids)
        if not rule.enabled:
            removed_entities.update(old_rule.entity_ids)
        self._remove_rule_instances(rule_id, removed_entities)

        affected_entities = set(old_rule.entity_ids) | set(rule.entity_ids)
        for entity_id in affected_entities:
            await self.async_evaluate_entity(entity_id, save=False, publish=False)
        self._publish_if_changed()
        await self.storage.async_save(self.config, self.records)
        return rule.as_dict()

    async def async_delete_rule(self, rule_id: str) -> None:
        """Delete a rule and silently clean only the instances it owns."""
        index = self._rule_index(rule_id)
        rule = Rule.from_dict(self.config["rules"][index])
        del self.config["rules"][index]
        self._rebuild_rule_index()
        self._remove_rule_instances(rule_id, set(rule.entity_ids))
        for entity_id in rule.entity_ids:
            await self.async_evaluate_entity(entity_id, save=False, publish=False)
        self._publish_if_changed()
        await self.storage.async_save(self.config, self.records)

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

    def _schedule_timer(self, record: AlertRecord) -> None:
        """Schedule exactly one timer for a pending alert."""
        alert_id = record.details.id
        self._cancel_timer(alert_id)
        when = record.due_at.astimezone(UTC)

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

    def _publish_if_changed(self, *, force: bool = False) -> None:
        """Avoid redundant sensor writes and Recorder churn."""
        snapshot = self.public_snapshot()
        if not force and snapshot == self._last_public_snapshot:
            return
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
