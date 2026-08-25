"""Event-driven alert detection manager."""

from __future__ import annotations

import logging
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_FRIENDLY_NAME,
    ATTR_UNIT_OF_MEASUREMENT,
    EVENT_HOMEASSISTANT_STARTED,
    EVENT_STATE_CHANGED,
    STATE_HOME,
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
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .const import (
    CATEGORY_BATTERY,
    CATEGORY_CONNECTIVITY,
    CATEGORY_UNAVAILABLE,
    CATEGORY_UNIFI,
    DOMAIN,
    EVENT_ALERT_RESOLVED,
    EVENT_ALERT_STARTED,
    SIGNAL_ALERTS_UPDATED,
)
from .models import (
    AlertDetails,
    AlertRecord,
    AlertStatus,
    Rule,
    advance_record,
    calculate_due_at,
    safe_delay_seconds,
    safe_float,
)
from .storage import AlertManagerStorage
from .validation import (
    validate_config,
    validate_config_update,
    validate_rule_payload,
    validate_rule_update_fields,
)

_LOGGER = logging.getLogger(__name__)

_CATEGORY_LABELS = {
    CATEGORY_UNAVAILABLE: "État indisponible",
    CATEGORY_CONNECTIVITY: "Connectivité désactivée",
    CATEGORY_UNIFI: "Équipement UniFi absent",
}
_OPERATOR_LABELS = {
    "equals": "Égal à",
    "not_equals": "Différent de",
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
        self._timers: dict[str, Callable[[], None]] = {}
        self._unloading = False
        self._last_public_snapshot: dict[str, Any] | None = None

    async def async_setup(self) -> None:
        """Load persisted state and start event-driven evaluation."""
        config, records = await self.storage.async_load()
        try:
            self.config = validate_config(config)
        except ValueError:
            _LOGGER.exception("Stored configuration is invalid; using defaults")
            self.config = validate_config({})
        self.records = records
        self._rebuild_rule_index()

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
            )
        )

        if self.hass.is_running:
            await self.async_evaluate_all(restoring=True)
        else:
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
            self.async_evaluate_entity(entity_id),
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

    async def async_evaluate_all(
        self, *, restoring: bool = False, save: bool = True
    ) -> None:
        """Evaluate all current and persisted relevant entities."""
        if self._unloading:
            return
        entity_ids = {
            state.entity_id
            for state in self.hass.states.async_all()
            if self._is_relevant_entity_id(state.entity_id)
        }
        entity_ids.update(record.details.entity_id for record in self.records.values())
        entity_ids.update(rule.entity_id for rule in self.rules)
        persisted_changed = False
        for entity_id in entity_ids:
            persisted_changed |= await self.async_evaluate_entity(
                entity_id, save=False, publish=False
            )
        if save and persisted_changed:
            await self.storage.async_save(self.config, self.records)
        self._publish_if_changed(force=restoring and self._last_public_snapshot is None)

    async def async_evaluate_entity(
        self,
        entity_id: str,
        *,
        save: bool = True,
        publish: bool = True,
    ) -> bool:
        """Evaluate every automatic category and rule for one entity."""
        if self._unloading:
            return False
        now = dt_util.now()
        state = self.hass.states.get(entity_id)
        candidates = self._build_candidates(state) if state is not None else {}
        existing_ids = {
            alert_id
            for alert_id, record in self.records.items()
            if record.details.entity_id == entity_id
        }
        persisted_changed = False

        for alert_id, (details, delay) in candidates.items():
            record = self.records.get(alert_id)
            if record is None:
                record = AlertRecord.pending(details, delay, now)
                self.records[alert_id] = record
                persisted_changed = True
            else:
                record.details = details
                if record.status is AlertStatus.PENDING and record.delay != delay:
                    record.delay = delay
                    record.due_at = calculate_due_at(record.detected_at, delay)
                    self._cancel_timer(alert_id)
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
        if not self._is_eligible(state.entity_id):
            return {}

        result: dict[str, tuple[AlertDetails, int]] = {}
        entity_id = state.entity_id
        domain = entity_id.partition(".")[0]

        unavailable_config = self.config["automatic"][CATEGORY_UNAVAILABLE]
        if (
            state.state == STATE_UNAVAILABLE
            and unavailable_config["enabled"]
            and domain in unavailable_config["domains"]
        ):
            alert_id = f"{CATEGORY_UNAVAILABLE}:{entity_id}"
            result[alert_id] = (
                self._details(
                    state,
                    alert_id,
                    CATEGORY_UNAVAILABLE,
                    _CATEGORY_LABELS[CATEGORY_UNAVAILABLE],
                ),
                self._delay_for(state, CATEGORY_UNAVAILABLE),
            )
            return result

        if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return result

        connectivity = self.config["automatic"][CATEGORY_CONNECTIVITY]
        if (
            connectivity["enabled"]
            and domain == "binary_sensor"
            and state.attributes.get(ATTR_DEVICE_CLASS) == "connectivity"
            and state.state == "off"
        ):
            alert_id = f"{CATEGORY_CONNECTIVITY}:{entity_id}"
            result[alert_id] = (
                self._details(
                    state,
                    alert_id,
                    CATEGORY_CONNECTIVITY,
                    _CATEGORY_LABELS[CATEGORY_CONNECTIVITY],
                ),
                self._delay_for(state, CATEGORY_CONNECTIVITY),
            )

        unifi = self.config["automatic"][CATEGORY_UNIFI]
        registry_entry = er.async_get(self.hass).async_get(entity_id)
        if (
            unifi["enabled"]
            and domain == "device_tracker"
            and registry_entry is not None
            and registry_entry.platform == "unifi"
            and state.attributes.get("source_type") == "router"
            and state.state != STATE_HOME
        ):
            alert_id = f"{CATEGORY_UNIFI}:{entity_id}"
            result[alert_id] = (
                self._details(
                    state,
                    alert_id,
                    CATEGORY_UNIFI,
                    _CATEGORY_LABELS[CATEGORY_UNIFI],
                ),
                self._delay_for(state, CATEGORY_UNIFI),
            )

        battery = self.config["automatic"][CATEGORY_BATTERY]
        if (
            battery["enabled"]
            and domain == "sensor"
            and state.attributes.get(ATTR_DEVICE_CLASS) == "battery"
        ):
            value = safe_float(state.state)
            override = safe_float(state.attributes.get("low_battery_level"))
            threshold = override if override is not None else battery["threshold"]
            if value is not None and value <= threshold:
                alert_id = f"{CATEGORY_BATTERY}:{entity_id}"
                condition = f"Batterie inférieure ou égale à {threshold:g} %"
                result[alert_id] = (
                    self._details(
                        state,
                        alert_id,
                        CATEGORY_BATTERY,
                        condition,
                        value=value,
                    ),
                    self._delay_for(state, CATEGORY_BATTERY),
                )

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
            alert_id = f"rule:{rule.id}"
            condition = rule.message or self._rule_condition(rule, state)
            result[alert_id] = (
                self._details(
                    state,
                    alert_id,
                    "rule",
                    condition,
                    severity=rule.severity,
                    value=current,
                ),
                rule.duration,
            )
        return result

    def _is_eligible(self, entity_id: str) -> bool:
        """Apply explicit, registry, device and label exclusions."""
        if entity_id in self.config["excluded_entities"]:
            return False
        entity_entry = er.async_get(self.hass).async_get(entity_id)
        if entity_entry is not None and entity_entry.disabled_by is not None:
            return False

        device = None
        if entity_entry is not None and entity_entry.device_id:
            if entity_entry.device_id in self.config["excluded_devices"]:
                return False
            device = dr.async_get(self.hass).async_get(entity_entry.device_id)
            if device is not None and device.disabled_by is not None:
                return False

        label = lr.async_get(self.hass).async_get_label_by_name(
            self.config["exclusion_label"]
        )
        if label is None:
            return True
        if entity_entry is not None and label.label_id in entity_entry.labels:
            return False
        return not (device is not None and label.label_id in device.labels)

    def _delay_for(self, state: State, category: str) -> int:
        """Resolve delay priority for automatic detections."""
        entity_id = state.entity_id
        if entity_id in self.config["entity_delays"]:
            return self.config["entity_delays"][entity_id]
        attribute_delay = safe_delay_seconds(state.attributes.get("alert_delay"))
        if attribute_delay is not None:
            return attribute_delay
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
        severity: str = "warning",
        value: Any | None = None,
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
            device_name=(
                (device.name_by_user or device.name) if device is not None else None
            ),
            area=area_entry.name if area_entry is not None else None,
            integration=entity_entry.platform if entity_entry is not None else None,
            value=state.state if value is None else value,
            unit=state.attributes.get(ATTR_UNIT_OF_MEASUREMENT),
            condition=condition,
            severity=severity,
        )

    def _rule_condition(self, rule: Rule, state: State) -> str:
        """Build a compact human-readable rule condition."""
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        source = f"Attribut {rule.attribute}" if rule.source == "attribute" else "État"
        suffix = f" {unit}" if unit else ""
        duration = f" pendant {rule.duration} s" if rule.duration else ""
        return (
            f"{source} {_OPERATOR_LABELS[rule.operator].lower()} "
            f"{rule.value}{suffix}{duration}"
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
            self._rules_by_entity.setdefault(rule.entity_id, []).append(rule)

    def _is_relevant_entity_id(self, entity_id: str) -> bool:
        """Return whether a state change can affect an alert or existing record."""
        if entity_id == "sensor.alert_manager":
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
        if unavailable.get("enabled") and domain in unavailable.get("domains", ()):
            return True
        return (
            (
                domain == "binary_sensor"
                and automatic.get(CATEGORY_CONNECTIVITY, {}).get("enabled", False)
            )
            or (
                domain == "device_tracker"
                and automatic.get(CATEGORY_UNIFI, {}).get("enabled", False)
            )
            or (
                domain == "sensor"
                and automatic.get(CATEGORY_BATTERY, {}).get("enabled", False)
            )
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
        pending = [record.as_public_dict() for record in pending_records]
        return {
            "active_count": len(active),
            "pending_count": len(pending),
            "alerts": active,
            "pending": pending,
        }

    def get_config(self) -> dict[str, Any]:
        """Return a defensive copy for WebSocket clients."""
        return deepcopy(self.config)

    async def async_update_config(self, changes: dict[str, Any]) -> dict[str, Any]:
        """Validate, atomically persist and immediately apply config changes."""
        validate_config_update(changes)
        if "rules" in changes:
            raise ValueError("Rules must be changed through the rules API")
        candidate = _deep_merge(self.get_config(), changes)
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
        await self.async_evaluate_entity(rule.entity_id, save=False)
        await self.storage.async_save(self.config, self.records)
        return rule.as_dict()

    async def async_update_rule(
        self, rule_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Update a rule without changing its identifier."""
        validate_rule_update_fields(data)
        index = self._rule_index(rule_id)
        existing = self.config["rules"][index]
        rule = validate_rule_payload({**existing, **data}, rule_id=rule_id)
        old_entity_id = existing["entity_id"]
        self.config["rules"][index] = rule.as_dict()
        self._rebuild_rule_index()
        await self.async_evaluate_entity(old_entity_id, save=False, publish=False)
        if rule.entity_id != old_entity_id:
            await self.async_evaluate_entity(rule.entity_id, save=False, publish=False)
        self._publish_if_changed()
        await self.storage.async_save(self.config, self.records)
        return rule.as_dict()

    async def async_delete_rule(self, rule_id: str) -> None:
        """Delete a rule and resolve any active alert it owns."""
        index = self._rule_index(rule_id)
        entity_id = self.config["rules"][index]["entity_id"]
        del self.config["rules"][index]
        self._rebuild_rule_index()
        await self.async_evaluate_entity(entity_id, save=False)
        await self.storage.async_save(self.config, self.records)

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
