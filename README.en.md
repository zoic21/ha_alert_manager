<p align="center">
  <img src="docs/assets/alert-manager-logo.svg" width="520" alt="Alert Manager">
</p>

<p align="center">
  🇫🇷 <a href="README.md">Français</a> | 🇬🇧 <strong>English</strong>
</p>

# Alert Manager for Home Assistant

Alert Manager centralizes Home Assistant anomalies in an event-driven engine, a
dedicated panel and one entity: `sensor.alert_manager`.

Minimum supported version: **Home Assistant 2026.8**. Alert Manager is an
unofficial community integration and is not affiliated with the Home Assistant
project.

## Features and scope

- persistent `normal`, `pending` and `active` internal states;
- automatic detection of unavailable entities, lost connectivity, away UniFi
  devices and low batteries;
- custom multi-entity rules on a state or attribute;
- explicit exclusions by labels, entities and devices;
- per-rule, per-entity, per-pack and global delays;
- responsive administrator panel in French and English;
- visual grouping, without merging records, when several alerts belong to one
  device;
- persistent per-alert acknowledgement from the panel and Home Assistant
  automations;
- visual or YAML editing of custom rules, plus complete YAML configuration
  export and replacement import;
- start, resolution, acknowledgement and unacknowledgement events;
- no imposed notifications and no frequent global polling.

Alert Manager handles simple independent anomalies. It is not an external
monitoring system, an alert history database or a notification service.

## Installation

### HACS

Until the repository is listed in the default HACS catalog, add it as a custom
repository:

1. Open **HACS → Custom repositories**.
2. Add `https://github.com/zoic21/ha_alert_manager` as an **Integration**.
3. Install Alert Manager and restart Home Assistant.
4. Add the integration from **Settings → Devices & services**.

Published versions use a `vX.Y.Z` Git tag and a matching GitHub release so HACS
shows the functional version and its release notes.

### Manual installation

1. Copy `custom_components/alert_manager` to
   `/config/custom_components/alert_manager`.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration**.
4. Search for **Alert Manager** and confirm.

No YAML configuration or Lovelace resource is required.

## Adding the integration and opening the panel

Only one config entry is allowed. After setup, the **Alert Manager** panel appears
in the sidebar and is available to administrators. Its language follows the
current user's Home Assistant language. Entity, device, area and rule names, user
messages and comparison values are user data and are never translated.

## Overview and device grouping

The overview separates active alerts (red), upcoming alerts (orange) and
acknowledged alerts (blue). Each card shows the source, current value,
translated condition, device, area and timestamps. Selecting an existing source
opens Home Assistant's native more-info dialog.

Several alerts with the same `device_id` are grouped inside the same status
section. This is display-only: alert IDs, lifecycle, sensor attributes and events
remain independent. A lone device alert and an entity without a device use a
compact individual card.

Hovering the red status icon on the left turns it into a dark-blue check on a
light-blue background; selecting it acknowledges that alert. For an acknowledged
alert, hovering the icon reveals a dark-red cross on a light-red background to
remove acknowledgement. Every grouped row keeps its own action, and there is no
device-wide acknowledgement action.

The remaining time is calculated in the browser from `due_at`; Alert Manager does
not write a countdown to Recorder every second.

## Automatic packs

### Unavailable entities

Every eligible domain is monitored for the exact `unavailable` state. `unknown`
is not included. Alert Manager's own entities, registry-disabled entities,
disabled devices and exclusions are ignored. `restored: true` alone is not a
reason to ignore an entity.

### Connectivity

A `binary_sensor` with `device_class: connectivity` is in alert when it is `off`.
An `unavailable` state is handled only by the unavailable pack, avoiding a
duplicate alert.

### UniFi prerequisite

A `device_tracker` provided by the `unifi` integration with
`source_type: router` is in alert when it is not `home`. The pack is displayed and
evaluated only while Home Assistant has at least one loaded, enabled and usable
UniFi config entry. Its configured state is retained while the prerequisite is
temporarily unavailable.

### Low batteries

A `sensor` with `device_class: battery` is in alert when its numeric value is less
than or equal to the configured threshold (15% by default). A numeric
`low_battery_level` attribute overrides the global threshold for that entity.
Invalid numbers, booleans, `NaN`, infinity, `unknown` and `unavailable` are ignored
by this pack.

## Exclusions

Automatic packs can be excluded by one or more Home Assistant labels. A selected
label on either the entity or its device excludes that source. During migration,
the existing `pas_d_alerte` label is selected automatically when found, but Alert
Manager never creates it.

Explicit entity and device exclusions apply in addition. Custom rules ignore
label exclusions but respect explicit entity and device exclusions.

## Delay priority

The effective delay is selected in this order:

1. custom rule duration;
2. entity-specific delay;
3. automatic pack delay;
4. global delay.

All delays are stored in seconds. An empty pack delay uses the global delay.
Changing a delay recalculates `due_at` from the original `detected_at`: an overdue
pending alert can activate immediately, while an active alert can return to
pending when its new due time is in the future. Its ID and lifecycle are kept.

## Custom rules

A rule monitors one or more entities. Every rule/entity pair has its own alert
cycle and stable ID: `rule:<rule_uuid>:<entity_id>`. A rule compares the main state
or one attribute with these operators:

| Operator | Behavior | Values |
| --- | --- | --- |
| `equals` | Exact trimmed textual equality with any configured value | One or more |
| `not_equals` | Current value equals none of the configured values | One or more |
| `contains` | Current value contains any configured value | One or more |
| `not_contains` | Current value contains none of the configured values | One or more |
| `above` | Strict numeric greater-than comparison | Exactly one |
| `below` | Strict numeric less-than comparison | Exactly one |

Duplicate or empty text values are rejected. Numeric comparisons reject booleans,
invalid values, `NaN` and infinity. A missing attribute does not match. Main
states `unknown` and `unavailable` are left to automatic detection.

Examples include `binary_sensor.service equals off`, `sensor.ups_status contains
CHRG or ERROR`, `sensor.mode not_equals off or idle`, and
`sensor.fridge_temperature above 9` for 1,800 seconds.

### Visual and YAML editing

The visual editor remains the default. In a create or edit drawer, open the
three-dot menu in the upper-right corner and select **Edit in YAML**. The same
drawer then displays Home Assistant's YAML code editor; **Edit visually** parses
and validates the YAML before filling the visual fields. Invalid YAML stays in
the YAML editor and is never saved. Existing rule IDs remain server-owned and
immutable; they are deliberately omitted from the editable rule YAML.

```yaml
name: Server rack temperature high
enabled: true
entity_ids:
  - sensor.server_rack_temperature
source: state
operator: above
value: 33
duration: 900
message: null
```

`entity_ids` is a required list and each source is evaluated independently.
`source` is `state` or `attribute`; `attribute` is required only for the latter.
`duration` is seconds. `equals`, `not_equals`, `contains` and `not_contains`
accept either one scalar value or a YAML list; `above` and `below` require one
finite numeric value. This syntax intentionally is **not** Home Assistant
automation-condition YAML: it has no templates, `and`/`or`/`not` groups,
arbitrary conditions or the automation condition engine.

### Full configuration export and import

**Exclusions and settings** contains **Export YAML** and **Import YAML**. An
export is a UTF-8 `alert-manager-config.yaml` file with format `version: 1`,
general configuration, exclusion tags, default and entity-specific delays,
automatic-pack configuration and all custom rules including their stable IDs.
It contains no active or pending alerts, acknowledgements, timers, detection or
activation timestamps, or execution history.

Import accepts only supported complete format versions and rejects unknown,
duplicate or runtime fields. It is validated before any write, displays its rule,
enabled-pack and entity-delay totals, then requires explicit confirmation.
**Import replaces the whole current configuration; it is not a merge.** Existing
runtime alerts are reconciled only after a valid import, and the configuration is
persisted atomically.

## `sensor.alert_manager`

The integration creates exactly `sensor.alert_manager`. Its state is the
unacknowledged active alert count. Its attributes separate unacknowledged active, acknowledged active
and pending individual alerts:

```yaml
state: 0
attributes:
  active_count: 0
  acknowledge_count: 1
  pending_count: 1
  tracked_count: 47
  alerts: []
  acknowledge:
    - id: unavailable:sensor.nas_cpu
      type: unavailable
      entity_id: sensor.nas_cpu
      name: NAS CPU
      value: unavailable
      condition: État indisponible
      condition_key: automatic.unavailable
      condition_params: {}
      detected_at: "2026-08-25T14:10:00+02:00"
      due_at: "2026-08-25T14:25:00+02:00"
      active_since: "2026-08-25T14:25:00+02:00"
      delay: 900
      acknowledged: true
      acknowledged_at: "2026-08-25T16:30:00+02:00"
      acknowledged_by: "Loïc"
  pending:
    - id: battery:sensor.entry_battery
      type: battery
      entity_id: sensor.entry_battery
      value: 12
      unit: "%"
      condition: Batterie inférieure ou égale à 15 %
      condition_key: automatic.battery
      condition_params:
        threshold: "15"
      detected_at: "2026-08-25T14:20:00+02:00"
      due_at: "2026-08-25T14:35:00+02:00"
      delay: 900
```

`alerts` contains unacknowledged active alerts, while `acknowledge` contains
acknowledged active alerts; `acknowledge_count` is the size of the latter list.
All three public lists (`alerts`, `pending` and `acknowledge`) contain individual
alerts only, never visual device groups.

Optional metadata includes `device_id`, `device_name`, `area`, `integration` and
`unit`. `condition` is retained for existing automations. Generated conditions
also provide `condition_key` and `condition_params` so the panel can render the
user's language. A custom rule message remains unchanged and has no translation
key. Resolved history and periodic countdown values are not recorded.

For an unacknowledged active alert, `acknowledged` is `false`.
`acknowledged_at` and `acknowledged_by` are present only after acknowledgement;
the author is absent for an automation or system call. Acknowledgement does not
resolve the alert: it moves from `alerts` to `acknowledge` and remains active while
its condition is true, but it is excluded from `active_count` and the state of
`sensor.alert_manager`. It remains included in `acknowledge_count`.

## Acknowledgement services

Acknowledgement always targets one exact active alert by its stable ID. Pending,
unknown and resolved IDs are rejected clearly. Repeating an action that has
already taken effect is idempotent and emits no additional event.

Both services are available in Home Assistant Actions and automations:

```yaml
action: alert_manager.acknowledge
data:
  alert_id: unavailable:sensor.nas_cpu
```

```yaml
action: alert_manager.unacknowledge
data:
  alert_id: unavailable:sensor.nas_cpu
```

Home Assistant's call context determines the displayed user. Without a user, the
panel shows the translated “Automation or system” label. Resolution discards the
acknowledgement with that occurrence; a later occurrence starts unacknowledged.

## Events and notifications

`alert_manager_alert_started` fires exactly when an alert becomes active.
`alert_manager_alert_resolved` fires when an active alert recovers and adds
`resolved_at`. An alert restored as active after a restart does not fire a second
start event. Event data keeps the existing `condition` field and adds structured
condition fields when available.

`alert_manager_alert_acknowledged` fires only when an active alert becomes
acknowledged. `alert_manager_alert_unacknowledged` fires only when that state is
actually removed. They contain the complete public alert data, the stable `id`,
the action timestamp and relevant acknowledgement metadata. Neither is replayed
after a restart.

Example handling both events:

```yaml
alias: Alert Manager acknowledgement log
triggers:
  - trigger: event
    event_type: alert_manager_alert_acknowledged
  - trigger: event
    event_type: alert_manager_alert_unacknowledged
actions:
  - action: logbook.log
    data:
      name: Alert Manager
      message: >-
        {{ trigger.event.event_type }}: {{ trigger.event.data.id }}
mode: queued
```

Short mobile notification example:

```yaml
alias: Alert Manager notification
triggers:
  - trigger: event
    event_type: alert_manager_alert_started
actions:
  - action: notify.mobile_app_my_phone
    data:
      title: "{{ trigger.event.data.name }}"
      message: >-
        {{ trigger.event.data.condition }}
        ({{ trigger.event.data.entity_id }})
      data:
        tag: "{{ trigger.event.data.id }}"
mode: queued
```

Alert Manager does not send notifications itself.

## Troubleshooting

- **The panel is missing:** confirm the integration is configured, use an
  administrator account and clear the browser cache after a frontend update.
- **The UniFi pack is missing:** load and enable at least one UniFi config entry.
- **A disabled entity is reported:** inspect both the entity registry entry and
  its parent device. `restored: true` does not mean disabled.
- **An alert is delayed:** check the rule duration, entity delay, pack delay and
  global delay in that order.
- **The language did not change:** reload the panel after changing the Home
  Assistant profile language. User-provided names and messages remain unchanged.

## Persistence and performance

Configuration, pending and active records, and acknowledgement state use a
versioned Home Assistant `Store` with atomic writes. V1.3 records without
acknowledgement fields migrate idempotently as unacknowledged alerts. Conditions
are reevaluated at startup. A temporarily
missing or `unknown` startup state does not incorrectly resolve a stored alert.

The engine listens for state and registry changes and normally reevaluates only
the affected entity. A full evaluation occurs at startup, after configuration or
registry changes, and when pack availability changes. One timer is scheduled per
pending alert, and the sensor is written only when its structured content changes.

## Known limitations and deferred features

- no snooze;
- no resolved-alert history, CSV storage, repeat or escalation;
- no combined conditions, Jinja templates or hysteresis (including in rule YAML);
- no built-in notification service;
- device grouping is visual only;
- configuration is administrator-only;
- the interface is available only in French and English in this release.

## Development and validation

```bash
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest -q

npm run build
npm run lint:frontend
npm run test:frontend
```

The workflows also run Hassfest and HACS validation.
