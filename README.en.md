<p align="center">
  <img src="docs/assets/alert-manager-logo.svg" width="520" alt="Alert Manager">
</p>

<p align="center">
  🇫🇷 <a href="README.md">Français</a> | 🇬🇧 <strong>English</strong>
</p>

# Alert Manager for Home Assistant

Alert Manager centralizes Home Assistant anomalies in an event-driven engine, a
dedicated panel and one service device grouping three alert sensors and one
monitoring switch.

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
- compact table based on Home Assistant's native `ha-data-table` component,
  with search, filters, sorting, collapsible grouping and customizable columns,
  without merging alert records;
- persistent per-alert acknowledgement from the panel and Home Assistant
  automations;
- an `Alert Manager - Général` device, persistent monitoring switch and three
  sensors separating active, upcoming and acknowledged alerts;
- visual or YAML editing of custom rules, plus complete YAML configuration
  export and replacement import;
- persistent history of alerts that actually became active and were then
  resolved, retaining 100 events by default in a dedicated panel tab without
  adding a Home Assistant entity; anomalies that recover while still pending are
  not archived;
- start, resolution, acknowledgement and unacknowledgement events;
- one safety notification when monitoring is still disabled at load time and no
  frequent global polling.

Alert Manager handles simple independent anomalies. It is not an external
monitoring system or a notification service.

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

## Overview table

One compact table combines active alerts (red), upcoming alerts (orange) and
acknowledged alerts (blue). Its default columns are Status, Device, Entity,
Value, Condition, Detected and Active since/Time remaining. Selecting an
existing entity opens Home Assistant's native more-info dialog. The remaining
time is calculated in the browser from `due_at` and becomes an explicit suspended
delay while monitoring is disabled; Alert Manager never writes a per-second
countdown to Recorder.

The toolbar provides immediate search, cumulative filters, collapsible grouping
by device, area, rule or status, and ascending or descending sorting. Optional
columns (entity ID, area, rule and message among them) can be shown, hidden and
reordered. Column order and visibility, grouping and sorting are kept locally for
the user and never alter integration configuration.

Selection mode replaces the normal toolbar with bulk actions. Selecting visible
rows can acknowledge or unacknowledge several alerts at once. A mixed selection
changes only compatible alerts: pending rows and rows already in the requested
state are ignored, while feedback reports the number actually changed.

## History and retention

The administrator-only **History** tab uses the same native table for resolved
alerts and alerts resolved after acknowledgement. Every row freezes rule and
entity names, device, area, message,
triggering condition and value, and detection/resolution timestamps. Search,
filters, grouping, sorting and column customization remain available. History
deliberately exposes neither selection mode nor acknowledgement actions.
An anomaly that recovers before activation is not an effective alert and is not
added to history.

In **Configuration → General settings**, directly below **Global delay**,
**Number of historical events retained** controls retention. **Clear history**
is aligned beside the field; the single common configuration save button at the
bottom right also saves this setting. The default is `100`, the accepted range
is `0` to `1000`, and `0` clears stored events when saved and disables future
history retention. Lowering the limit or
adding an event removes the oldest excess entries immediately and
deterministically. **Clear history** requires an explicit irreversible-action
confirmation and never changes active, upcoming or acknowledged alerts.

## Automatic packs

### Unavailable entities

Every eligible domain is monitored for the exact `unavailable` state. `unknown`
is not included. Alert Manager's own entities, registry-disabled entities,
disabled devices and exclusions are ignored. `restored: true` alone is not a
reason to ignore an entity.
Alert Manager entities are also rejected as custom-rule sources, including when
they have been renamed in Home Assistant.

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

**Configuration** contains **Export YAML** and **Import YAML**. An
export is a UTF-8 `alert-manager-config.yaml` file with format `version: 1`,
general configuration, exclusion tags, default and entity-specific delays,
monitoring-switch state, automatic-pack configuration and all custom rules.
Internal rule IDs are not
exported and are recreated by the backend during import. It contains no active
or pending alerts, acknowledgements, timers, detection or
activation timestamps, or execution history.
The history retention limit and historical events are neither exported nor
imported: importing configuration preserves both local history settings and
stored events.

Import accepts only supported complete format versions and rejects unknown,
duplicate or runtime fields. It is validated before any write, displays its rule,
enabled-pack and entity-delay totals, then requires explicit confirmation.
**Import replaces the whole current configuration; it is not a merge.** Existing
runtime alerts are reconciled only after a valid import, and the configuration is
persisted atomically. A V1.5 export without `monitoring_enabled` remains accepted
and defaults monitoring to on.

## Device and monitoring switch

The `Alert Manager - Général` service device uses the stable `main` category
identifier and groups all four entities introduced by this release:

- `switch.alert_manager_main_monitoring`;
- `sensor.alert_manager_main_active`;
- `sensor.alert_manager_main_pending`;
- `sensor.alert_manager_main_acknowledge`.

The switch defaults to on and is persisted with the configuration. Turning it
off prevents new records, freezes both pending transitions and their remaining
time, cancels their timers and preserves every existing alert. All three sensors
then report `0` with an empty `alerts` list without deleting internal records.
The panel shows a visible warning with a resume button. Turning monitoring back
on resumes each countdown where it stopped, reconciles current Home Assistant
states, recreates each required timer once and emits events only for real
lifecycle transitions.

When the integration loads while monitoring is off, Home Assistant creates the
stable persistent notification `alert_manager_main_monitoring_disabled`. It
explains how to turn on `Alert Manager Monitoring`, is not duplicated across
reloads and is dismissed as soon as monitoring resumes.

## Sensors, attributes and V1.5 migration

The entity registry entry for `sensor.alert_manager` is removed during migration
and no long-term compatibility sensor is created:

| New entity | State | `attributes.alerts` contents |
| --- | ---: | --- |
| `sensor.alert_manager_main_active` | unacknowledged active count | unacknowledged active alerts only |
| `sensor.alert_manager_main_pending` | upcoming count | pending alerts only |
| `sensor.alert_manager_main_acknowledge` | acknowledged active count | acknowledged active alerts only |

An occurrence is never exposed by two sensors. Each sensor has exactly one
`alerts` list attribute. Example custom-rule alert:

```yaml
state: 1
attributes:
  alerts:
    - id: rule:4f9d…:sensor.rack_temperature
      type: rule
      rule_id: 4f9d…
      rule_name: Rack temperature high
      entity_id: sensor.rack_temperature
      name: Rack temperature
      device_id: 0123456789abcdef0123456789abcdef
      device_name: Rack probe
      area: Office
      integration: mqtt
      value: 34.2
      unit: °C
      condition: State greater than 33 °C for 15 min
      condition_key: rule.generated
      condition_params:
        source: state
        attribute: null
        operator: above
        expected: "33"
        unit: °C
        duration: 900
      detected_at: "2026-08-26T10:00:00+02:00"
      due_at: "2026-08-26T10:15:00+02:00"
      delay: 900
      active_since: "2026-08-26T10:15:00+02:00"
      acknowledged: false
```

A pending alert has no `active_since` or acknowledgement fields; remaining time
is derived from `due_at`. An acknowledged alert adds `acknowledged: true`,
`acknowledged_at` and, when a user is known, `acknowledged_by`. `rule_id` and
`rule_name` exist only for custom rules. Device, area, integration and unit
metadata remain optional. Attributes contain no resolved history, visual group or
periodically written countdown.

Cards and automations reading `sensor.alert_manager` must target the appropriate
new sensor and replace the old `alerts`, `pending` or `acknowledge` lists with its
single `attributes.alerts` list. For example:

```jinja
{{ state_attr('sensor.alert_manager_main_pending', 'alerts') | default([], true) }}
```

Example automation using the new active count:

```yaml
triggers:
  - trigger: numeric_state
    entity_id: sensor.alert_manager_main_active
    above: 0
actions:
  - action: persistent_notification.create
    data:
      title: Alert Manager
      message: >-
        {{ states('sensor.alert_manager_main_active') }} active alert(s)
```

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

Alert Manager sends no alert notification itself. Its only direct notification is
the safety warning when monitoring is still disabled at load time.

## Troubleshooting

- **The panel is missing:** confirm the integration is configured, use an
  administrator account and clear the browser cache after a frontend update.
- **The UniFi pack is missing:** load and enable at least one UniFi config entry.
- **A disabled entity is reported:** inspect both the entity registry entry and
  its parent device. `restored: true` does not mean disabled.
- **An alert is delayed:** check the rule duration, entity delay, pack delay and
  global delay in that order.
- **No alert progresses:** verify that
  `switch.alert_manager_main_monitoring` is `on`.
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
pending alert, and sensors are written only when their structured content changes.

## Known limitations and deferred features

- no snooze;
- no CSV history export, repeat or escalation;
- no combined conditions, Jinja templates or hysteresis (including in rule YAML);
- no built-in alert-notification service;
- no business action in History;
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
