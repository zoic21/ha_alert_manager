# Alert Manager user guide

[Project and installation](../README.md) · [Français](user-guide.fr.md)

## Automatic monitoring

Open **Configuration → Automatic monitoring** to configure the automatic packs. Each pack can be enabled independently and can carry Home Assistant labels for filtering and notification routing.

| Pack | Condition |
| --- | --- |
| Unavailable entities | An entity remains `unavailable`. |
| Connectivity | A `binary_sensor` with `device_class: connectivity` remains `off`. |
| Low battery | A battery sensor reaches the configured threshold, 15% by default. |
| UniFi | A UniFi network `device_tracker` remains away from `home`. |
| Automation and script errors | An execution finishes with an error; a successful completed execution resolves the alert. |
| Flapping / instability | The same anomaly recurs within a detection window. |

Each pack has a **Configure** drawer for defaults, labels and device/entity exceptions. Delay and pack parameters inherit independently: **entity → device → pack**. Clearing a numeric override restores inheritance; an explicit zero delay is immediate. The **Monitor** switch is on by default. Disabling a pack or device blocks its entity exceptions, and no exception bypasses global monitoring, an exclusion label or eligibility checks. Battery thresholds and consecutive failed-cycle counts use the same exception hierarchy; automation/script errors have no delay by default.

In **Configuration → General**, global exclusions use Home Assistant labels attached to entities or devices and affect automatic monitoring only. Custom rules remain independent. Trigger delays belong to individual packs; the separate pending-alert display delay only controls visibility. Device exceptions also cover newly added eligible entities.

Exceptions collapse to summaries with monitoring and delete controls. Disabling an exception hides its parameters without clearing their values. The main Save button saves page settings and pack activation; each drawer has its own Save button. An unfinished drawer does not block saving the page, and editing it does not reveal the general Save button.

**Configure this monitoring**, in an automatic alert's details, opens its target and flapping source as an unsaved draft. Missing targets remain available for correction or removal. Disabling a target cancels its timers, queued notifications and reminders without a recovery notification. A changed pending delay retains the original observation time; compatible active and acknowledged alerts keep their identity.

Flapping is disabled by default. Its defaults are **5 occurrences within 1 hour**, followed by recovery after **30 minutes without another occurrence**. It can detect short anomalies that disappear before the normal alert delay. Unavailable and connectivity are the preselected sources; their packs must be enabled. Settings can be adjusted at pack level, per source pack, per device, per entity or per custom rule. The alert details retain occurrence times in a collapsible section, including in resolved history.

Pack labels update current alerts when changed; history keeps the labels recorded at resolution. Custom-rule labels complement entity and device labels for notifications; they do not dynamically select which entities a rule monitors.

## Custom rules

Create rules in **Custom rules**, using the visual editor or YAML. A configuration supports up to **500 rules**, with **50 entities per rule**. Each selected entity is monitored independently. Rules can be duplicated and can have Home Assistant labels and a custom Jinja message.

| Operation | YAML source | Purpose |
| --- | --- | --- |
| Value | `value` | Compare a state or attribute: equality, text, numeric thresholds, between/outside, or an unchanged value. |
| Variation | `value_variation` | Measure a numeric change from the baseline recorded when a Jinja condition becomes true. |
| Transition | `value_transition` | Observe a specific `from_value` → `to_value` change. |
| No change | `unchanged` | Detect an entity that has stopped updating. |
| Jinja | `jinja` | Use a template as the complete rule condition. |

For Value, Variation and Transition, an omitted or empty `attribute` targets the state; a populated `attribute` targets that attribute. Missing attributes never fall back to the state. Nested paths are supported; wildcard paths such as `data.*.key` are limited to regular comparisons.

Use `duration` to require a condition to persist. Duration fields use Home Assistant's hours/minutes/seconds selector; YAML values remain in seconds. Messages are frozen at activation by default; `update_message_when_active` keeps them updated while the alert remains active.

The **Test** button evaluates the unsaved draft against current values and reports the comparison, Jinja condition, rendered message, errors and matching new-alert notification profiles for each entity. It does not save the rule, change alerts or timers, or send notifications. A variation without a compatible baseline is indeterminate, and a current value alone cannot prove a transition.

A Jinja rendering error is indeterminate, not a recovery: it preserves existing alerts, pending deadlines and the last valid message. Relevant dependency changes retry evaluation. For variation rules, only an explicitly false condition ends the baseline window. Errors are shown in the tester and logs.

Older YAML source names are migrated on import: `state`/`attribute` to `value`, variation names to `value_variation`, transition names to `value_transition`, and `none` to `jinja`. Use the canonical names below for new rules.

### Transition behavior

A transition rule requires an observed edge; initial discovery, reloads and startup do not infer one. Unknown/unavailable states or a missing attribute cannot start a hold.

With `duration` greater than zero, the arrival value must remain unchanged for that delay. Leaving it cancels the hold; unrelated attribute changes do not restart it. Once active, the alert expires after `auto_resolve` seconds (**600 by default**, minimum 1), even if the state changes again. A new confirmed transition extends the same alert's expiry and preserves its acknowledgement.

Automatic expiration is recorded in history but sends **no recovery notification**. New-alert notifications and reminders still apply. Unconfirmed holds do not survive a restart or monitoring pause; active/acknowledged expiry deadlines survive restarts. A monitoring pause requires a fresh edge for a new activation.

### Generate rules from blueprints

In **Custom rules → Generate rules**, select built-in blueprints and choose **Create selected rules**. The generator shows matching entity counts and explains unavailable choices. CPU/memory usage and CPU temperature cover System Monitor and compatible device sensors, including UniFi, with matching units and names; Supervisor apps/add-ons are excluded. Disk usage remains System Monitor only. Enable the relevant sensors first.

Each selection creates one editable rule containing up to 50 compatible entities. The selected rules are created together or not at all. They remain independent afterward: there is no automatic synchronization or periodic scan. Renaming keeps the blueprint origin. Regenerating an existing rule requires confirmation, overwrites customizations with defaults and currently discovered entities, and preserves its identifier.

See the [blueprint documentation index](blueprints/README.md) for requirements, discovery, defaults and limitations, including Home Assistant backup/update checks. The [contributor guide](rule-blueprints.md) describes the blueprint YAML format.

### Examples

Replace the entity IDs with your own. These examples can be pasted into a rule's YAML editor.

#### High power consumption for two hours

```yaml
name: "Fridge power consumption"
enabled: true
entity_ids:
  - sensor.fridge_power
source: value
operator: above
value: "200"
duration: 7200
```

#### A thermostat that heats without warming the room

The baseline starts when the thermostat reports `hvac_action: heating`. The rule alerts after two hours if the temperature has risen by less than 0.2 °C. In the message, `value` is the measured variation.

```yaml
name: "Heating performance"
enabled: true
entity_ids:
  - climate.living_room
source: value_variation
attribute: current_temperature
operator: below
value: "0.2"
duration: 7200
condition_template: "{{ state_attr(entity_id, 'hvac_action') == 'heating' }}"
message: "Heating has been active for 2 h, but the temperature has risen by only {{ value | float(0) | round(1) }} °C."
update_message_when_active: false
```

#### Bayrol messages with expected states filtered out

The comparison checks the message keys in the `data` array, while the Jinja condition requires flow to be present.

```yaml
name: "Bayrol alert"
enabled: true
entity_ids:
  - sensor.bayrol_messages
source: value
attribute: data.*.key
operator: not_contains
value:
  - al_no_flow_bnc
  - al_start_delay
  - enjoy
duration: 5400
condition_template: "{{ is_state('binary_sensor.bayrol_flow_contact', 'on') }}"
message: >-
  {% for item in state_attr(entity_id, 'data') or [] %}
    {% if item.key not in ['al_no_flow_bnc', 'enjoy', 'al_start_delay'] %}
      {{ item.message | replace('\n', ' ') }}
    {% endif %}
  {% endfor %}
update_message_when_active: false
```

#### A completed cycle visible for ten minutes

```yaml
name: "Washing cycle completed"
enabled: true
entity_ids:
  - sensor.washing_machine_state
source: value_transition
from_value: running
to_value: finished
duration: 0
auto_resolve: 600
```

## Dashboard card

The integration registers **Alert Manager** in the dashboard card picker. No additional HACS frontend installation or manual Lovelace resource is required. Refresh the browser after installation or an update.

```yaml
type: custom:alert-manager-card
max_tiles: 5
alignment: left
# icon_color: red
# label: maintenance
```

`max_tiles` accepts 1–100 (default 5). `alignment` accepts `left`, `center` or `right`. The optional `icon_color` uses Home Assistant's native palette; otherwise the theme applies. `label` is a Home Assistant label ID. These options are also available in the visual editor.

Matching active, unacknowledged alerts are grouped by device before the limit is applied. A single-alert tile opens its details; a grouped tile opens the device-filtered list. The **+N** bubble opens matching alerts and counts the remaining alerts, not devices. Tiles wrap on narrow screens and are capped at 300 px.

With no matching alerts, the card and its wrapper hide in standard Sections and Masonry views; custom layouts may behave differently. During startup, known active alerts remain visible with an **hourglass** while they are reevaluated. The hourglass shares the overflow bubble and opens the filtered Overview. On mobile the bubble stays beside the last visible alert, which narrows to make room. Startup with no matching alerts displays nothing.

Loading, disabled monitoring and unavailability remain visible. Example alerts are displayed only in the editor, outside startup. All authenticated users can read the card, Overview, History, alert details and history statistics. Other tabs and every mutation, including acknowledgement, require an administrator; non-administrators do not load integration configuration.

## Alert lifecycle and history

An alert is **Upcoming** while its trigger delay runs, **Active** after confirmation, **Acknowledged** when the issue is known but not fixed, and **Resolved** when its condition clears. Acknowledged alerts remain visible but are excluded from the active count. A pending condition that disappears does not enter history.

Disabling monitoring pauses detection and pending timers, exposes zero alert counts and delays temporary-acknowledgement expiry handling until monitoring resumes. Resuming evaluates current conditions without creating duplicate alerts.

Alert tables support search, filters, sorting, device grouping, customizable columns and multiple selection. Details show the triggering and current values, contextual access to the entity, notification deliveries and a clickable previous-occurrence count. That count opens History filtered to the same stable alert ID.

**Reevaluate**, in an ongoing alert's details menu, checks the entity's current state again, including its other alerts. It preserves normal delays and protections and requires monitoring to be enabled and startup to be complete. Select history entries, or use **Delete** in their details, to remove occurrences after confirmation without affecting current alerts.

### Temporary acknowledgement

The details menu offers **Acknowledge temporarily…** for 15 min, 30 min, 1 h, 24 h or a custom duration up to one year. Details show the remaining time; clicking it reveals the exact deadline. Regular acknowledgement has no time limit.

At expiry, an ongoing alert becomes active again with the same identity and start time. Profiles allowing new-alert notifications can notify again even without reminders configured. Resolution or manual unacknowledgement cancels the deadline. Deadlines survive restarts and are handled after startup reconciliation; pausing monitoring does not shift them.

### History statistics

Use **Statistics** in History to rank alerts, entities, devices, integrations or rules over **7 or 30 days**. Results include occurrences and cumulative/average active duration, with affected-entity/device counts and the most frequent items. Click a ranking or highlighted item to open matching history.

Calculations run on demand from **retained resolved history**, independently of the table's filters. Ongoing and deleted/expired occurrences are excluded. Durations are clipped to the selected period and include acknowledged time. Concurrent alerts contribute separately: these totals are **not device downtime**.

## Notifications

In **Configuration → Notifications**, create profiles with one or more **`notify` entities**. Choose new-alert and recovery notifications and optional reminders (minimum interval: one minute). Each profile has an enable switch. Channels exposed only as actions or scripts can still be used through your own event-based automations.

The profile's three-dot menu offers **YAML mode**, **Duplicate** and **Test**. Duplication preserves settings, recipients and exception order, but creates the copy only on save and does not copy usage counters or runtime state. Test sends a real notification through the saved profile without creating an alert.

### Labels and ordered exceptions

A profile can cover all alerts or match **any selected label (OR)**. Matching combines entity, device, custom-rule and automatic-pack labels. An exception requires **all its selected labels (AND)**. The **first matching exception in list order** wins; inherited settings keep the profile defaults. Exceptions can independently override new-alert, recovery and reminder behavior. The visual editor uses explicit switches and a reminder interval; clearing the interval disables reminders. Sparse exceptions display effective profile values, and YAML can omit fields to inherit defaults. In YAML exceptions use `selector_ids`; legacy `selector_id` remains accepted.

### Batching and reminders

New alerts and recoveries are grouped separately per profile. The batching delay is **30 seconds by default**, adjustable from **10 to 300 seconds**. Changing it affects new batches, not batches already waiting. When an alert clears before its queued activation is sent, the unsent activation/recovery pair is discarded.

Reminders are grouped per profile and stop on acknowledgement or resolution. After restart they wait for alert reconciliation; overdue deadlines restart from the configured interval without replaying missed reminders.

Recognized Companion targets receive native `notification_icon` metadata and an emoji-free title; actual icon rendering depends on the client. Generic targets keep 🚨 new-alert, 🔔 reminder and ✅ recovery title prefixes. Tapping a supported Companion notification opens the single ongoing alert, Overview for several ongoing alerts, or History for recoveries. Generic targets receive no appended raw navigation URL.

### Delivery details

Alert details separate activation and reminder deliveries; history also records recovery deliveries, matching profiles and last delivery times. A batch counts once per profile and alert when at least one target succeeds. Tests and complete failures are excluded. These details survive restarts, are hidden for pending alerts and do not count notifications sent by external automations.

Profile usage counters cover the current hour and previous 23 hours since startup. They are kept only in memory and reset on restart/reload; a grouped send counts once even with multiple targets.

## Configuration coherence

**Coherence** checks static references in automations, scripts, dashboards, templates, ESPHome and custom rules, including disabled rules and static Jinja references. Dynamic references and plain message text are skipped. Findings identify the source and offer contextual navigation where possible, including directly to a custom rule's editor.

When ZHA is fully loaded, the scan also checks static `device_ieee` references in `zha_event` triggers and `wait_for_trigger` steps against Home Assistant's ZHA device registry. This checks registered devices, **not availability or radio-network membership**. Disabled devices and remotes without entities still count as present. Templates, blueprint inputs and malformed IEEE values are skipped; blueprints are not expanded. Incomplete ZHA metadata produces a skipped check, not missing-device findings.

Run a scan manually or schedule it daily, weekly or monthly. ESPHome scanning can be disabled, and reference exclusions can include exact ZHA IEEE addresses. Reports survive restarts. The page also shows the latest 50 deleted entities still retained by Home Assistant's registry, without maintaining a separate deletion history.

Enable **Create an alert for coherence issues** in **Configuration → Coherence analysis** to keep one immediate alert while findings remain. It uses normal acknowledgement, history and notification profiles. Only a complete check confirming recovery resolves it; failed or incomplete scans cannot clear it. Enabling uses the latest report without starting a scan. Disabling removes the alert and its reminders without reporting a recovery. Findings are also exposed through `sensor.alert_manager_coherence_issue`.

## Configuration, YAML and recovery

Each pack drawer offers **YAML mode** in its three-dot menu. Its `pack` mapping contains the complete configuration, including sparse `device_overrides`, `entity_overrides` and source-specific flapping exceptions. Durations are in seconds; both editors use backend validation. Duplicate targets, unknown keys and invalid settings block saving. Notification profiles have their own YAML editor. Switching preserves unsaved values and list order; closing a modified editor asks for confirmation. Desktop drawers can be resized; details and diagnostics remain read-only.

The full configuration can be exported/imported as YAML. Alert Manager retains the **three latest valid daily configuration backups**, downloadable and restorable from Configuration.

An invalid saved configuration starts safe defaults, displays a persistent warning and lets an administrator choose a backup; it is never restored silently. **Restoring a complete backup replaces the configuration and reevaluates current states while retaining compatible alert/rule IDs, acknowledgements, occurrence evidence and history.** Version-2 exports retain rule IDs.

### Configuration migration

Older configurations, version-1 YAML and backups convert shared trigger delays into explicit pack defaults and per-entity delays into pack exceptions, including disabled packs. Battery thresholds, consecutive failed-cycle counts and source-priority flapping values retain their behavior.

Direct entity/device exclusions become disabled exceptions in every pack while preserving thresholds and delays. Global label exclusions remain unchanged; no Home Assistant labels or registry entries are created or modified. Missing targets remain in exception maps so they stay excluded if they return. Invalid source data leaves the original configuration recoverable.

### Runtime diagnostics

Configuration shows custom-rule evaluation counts and average/maximum/total processing time, alert transitions and successful profile sends. Exactly 24 hourly aggregate buckets are kept in memory, with no persistence. The observation period begins at startup or the oldest retained hour. Tests, automatic packs and coherence scans are excluded from rule timing; this does **not** measure Home Assistant event-loop load. Activity counts transitions, not the current number of alerts.

## Home Assistant entities and events

| Entity | Purpose |
| --- | --- |
| `switch.alert_manager_main_monitoring` | Enable or pause monitoring. |
| `sensor.alert_manager_main_active` | Active, unacknowledged alert count. |
| `sensor.alert_manager_main_pending` | Pending alert count. |
| `sensor.alert_manager_main_acknowledge` | Acknowledged alert count. |
| `sensor.alert_manager_coherence_issue` | Coherence findings. |

Lifecycle events are `alert_manager_alert_started`, `alert_manager_alert_resolved`, `alert_manager_alert_acknowledged` and `alert_manager_alert_unacknowledged`. Acknowledgement actions are `alert_manager.acknowledge` and `alert_manager.unacknowledge`.

Built-in notification profiles are optional; these entities, events and actions remain available for your own dashboards and automations.
