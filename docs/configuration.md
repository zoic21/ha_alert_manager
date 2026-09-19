# Configuration

[Documentation](user-guide.md) · [Custom rules](custom-rules.md) · [Coherence](coherence.md) · [Dashboard and history](dashboard-and-history.md)

**Configuration** brings together automatic monitoring, notification profiles, alert display/history settings, coherence scheduling, YAML and backups. Configuration changes require an administrator.

## Automatic monitoring

Open **Configuration → Automatic monitoring** to enable and configure the packs relevant to your installation. Packs identify common problems without creating a custom rule for every entity. Each pack can be enabled independently and can carry Home Assistant labels for filtering and notification routing.

| Pack | Alert condition |
| --- | --- |
| Unavailable entities | An entity remains `unavailable`. |
| Connectivity | A `binary_sensor` with `device_class: connectivity` remains `off`. |
| Low battery | A battery sensor reaches the configured threshold; default 15%. |
| UniFi | A UniFi network `device_tracker` remains away from `home`. |
| Available updates | A Home Assistant `update` entity is `on`. |
| Automation and script errors | An execution finishes with an error; a successfully completed execution resolves the alert. |
| Flapping / instability | The same anomaly recurs within a detection window. |

### Delays, exclusions and overrides

Each pack has a **Configure** drawer for defaults, labels and device/entity exceptions. Delay and pack parameters inherit independently: **entity → device → pack**. Clearing a numeric override restores inheritance; an explicit zero delay is immediate. The **Monitor** switch is on by default.

A disabled pack or device blocks its entity exceptions. No exception bypasses the global monitoring switch, an exclusion label or the pack's eligibility checks. Battery thresholds and consecutive failed-cycle counts use the same exception hierarchy. Automation/script errors have no delay by default; consecutive failed cycles are different from a time delay.

In **Configuration → General**, global exclusions use Home Assistant labels on entities or devices and affect automatic monitoring only. Custom rules remain independent. Device exceptions also cover newly added eligible entities.

Trigger delays belong to individual packs. The pending-alert display delay controls only when a pending alert is shown, not when it becomes active. Pack labels update current alerts when changed; history keeps the labels recorded at resolution.

The available-updates pack supports entity exclusions only. Remove an exclusion to monitor that entity again; it does not offer device exceptions or per-entity delays.

### Configure a pack or target

Exceptions collapse to summaries with monitoring and delete controls. Disabling an exception hides its parameters without clearing their values. The main Save button saves page settings and pack activation; each drawer has its own Save button. An unfinished drawer does not block saving the page, and editing it does not reveal the general Save button.

**Configure this monitoring** in an automatic alert's details opens its target and flapping source as an unsaved draft. Missing or no-longer-applicable targets remain available for correction or removal.

Disabling a target cancels its timers, queued notifications and reminders without a recovery notification; retained history indicates that monitoring was disabled. Changing a pending delay retains the original observation time. Compatible active and acknowledged alerts keep their identity.

### Flapping and instability

Flapping can detect repeated short anomalies that clear before the normal trigger delay. It is disabled by default. The defaults are **5 occurrences within 1 hour**, followed by recovery after **30 minutes without another occurrence**.

Unavailable entities and connectivity are the preselected sources; their source packs must be enabled. Settings can be adjusted at pack level, per source pack, per device, per entity or per custom rule. Custom rules participate through their flapping option.

An instability alert is separate from its source alert. Its details retain the count/threshold and occurrence times in a collapsible section, including in resolved history. Evidence follows the detector's bounded rolling window rather than providing an unlimited event log.

## Notification profiles

In **Configuration → Notifications**, create a named profile with one or more **`notify` entities**. Choose whether to send new-alert and recovery notifications and whether to repeat reminders. The minimum reminder interval is one minute. Each profile has an enable switch.

Profiles are optional: lifecycle events remain available for your own notification automations. Profiles accept notification entities, not arbitrary actions or scripts; channels exposed only as actions can still be used through an automation.

The profile's three-dot menu offers **YAML mode**, **Duplicate** and **Test**. Duplication preserves settings, recipients and exception order, but creates the copy only on save and does not copy usage counters or runtime state. Test sends a **real notification** through the saved profile without creating an alert.

### Labels and exceptions

A profile can cover all alerts or match **any selected label (OR)**. Matching combines the labels of the entity, its device and the custom rule or automatic pack that produced the alert.

An exception requires **all its selected labels (AND)**. The **first matching exception in list order** wins; inherited settings keep the profile defaults. Exceptions can independently override new-alert, recovery and reminder behavior. The visual editor uses explicit switches and a reminder interval; clearing the interval disables reminders. Sparse exceptions display effective profile values, and YAML can omit fields to inherit defaults. In YAML exceptions use `selector_ids`; legacy `selector_id` remains accepted.

For example, a profile may notify every new alert, while its first exception disables reminders for alerts carrying both a maintenance label and a particular rule label. An alert matching only one of those labels does not match that exception.

### Batching and reminders

New alerts and recoveries are grouped separately per profile. The batching delay is **30 seconds by default**, adjustable from **10 to 300 seconds**. Changing it affects new batches, not batches already waiting. When an alert clears before its queued activation is sent, the unsent activation/recovery pair is discarded.

Reminders are grouped per profile and stop on acknowledgement or resolution. After restart they wait for alert reconciliation. Only confirmed alerts resume reminders; overdue deadlines restart from the configured interval without replaying missed reminders.

### Mobile navigation and delivery details

Recognized Companion targets receive native `notification_icon` metadata and an emoji-free title; actual icon rendering depends on the client. Generic targets retain the new-alert, reminder and recovery emoji prefixes. Tapping a supported Companion notification opens a single ongoing alert's details, Overview for several ongoing alerts, or History for recoveries. Generic targets receive no appended raw navigation URL.

Alert details separate activation and reminder deliveries; history also records recovery deliveries, matching profiles and last delivery times. A batch counts once per profile and alert when at least one target succeeds. Tests and complete failures are excluded. These details survive restarts, are hidden for pending alerts and do not count notifications sent by external automations.

Profile usage counters cover the current hour and previous 23 hours since startup. They are kept only in memory and reset on restart/reload; a grouped send counts once even with multiple targets.

## Display, history and coherence settings

Adjust pending-alert visibility separately from trigger delays. The history limit controls how many resolved occurrences are retained; deleted or discarded occurrences are no longer available to history statistics. See [Dashboard and history](dashboard-and-history.md) for acknowledgement, filtering and recurrence reports.

Coherence settings control scheduling, ESPHome scanning, reference exclusions and the optional persistent coherence alert. See the [Coherence guide](coherence.md) for supported references and incomplete-scan behavior.

## YAML editing

Each pack drawer offers **YAML mode** in its three-dot menu. Its `pack` mapping contains the complete configuration, including sparse `device_overrides`, `entity_overrides` and source-specific flapping exceptions. Both editors use backend validation. Duplicate targets, unknown keys and invalid settings block saving. Notification profiles have their own YAML editor.

Switching preserves unsaved values and list order; closing a modified editor asks for confirmation. Desktop drawers can be resized; details and diagnostics remain read-only. Duration fields use Home Assistant's hours/minutes/seconds selector; YAML stores seconds.

## Configuration backups and recovery

The full configuration can be exported/imported as YAML. Alert Manager retains the **three latest valid daily configuration backups**, downloadable and restorable from Configuration.

At startup, unknown stored configuration fields are removed after supported migrations.
Valid notification profiles, rules and pack settings are preserved, and the cleaned
configuration is saved automatically. New API/YAML input still rejects unknown fields.

If a known field in the saved configuration has an invalid value at startup, the integration uses safe defaults, displays a persistent warning and lets an administrator choose a backup. It never restores one silently.

**Restoring a complete backup replaces the configuration and reevaluates current states while retaining compatible alert/rule IDs, acknowledgements, occurrence evidence and history.** Version-2 exports retain rule IDs. Review the replacement configuration before confirming. Configuration exports should not be confused with a full Home Assistant backup.

### Migration from earlier configurations

Older configurations, version-1 YAML and backups convert shared trigger delays into explicit pack defaults and per-entity delays into pack exceptions, including disabled packs. Battery thresholds, consecutive failed-cycle counts and source-priority flapping values retain their behavior.

Direct entity/device exclusions become disabled exceptions in every pack while preserving thresholds and delays. Global label exclusions remain unchanged; no Home Assistant labels or registry entries are created or modified. Missing targets remain in exception maps so they stay excluded if they return. Invalid source data leaves the original configuration recoverable.

## Runtime diagnostics

Configuration shows custom-rule evaluation counts and average/maximum/total processing time, alert transitions and successful profile sends. Exactly **24 hourly aggregate buckets** are kept in memory, with no persistence. The observation period starts at integration startup or the oldest retained hour, whichever is later.

An evaluation is one rule/entity pair, including its condition and excluding asynchronous waiting. Tests, automatic packs and coherence scans are excluded from timing. This does **not** measure Home Assistant event-loop load. Activity counts actual transitions, not the current number of alerts; restored alerts are not counted as new activations.

## Home Assistant entities and events

| Entity | Purpose |
| --- | --- |
| `switch.alert_manager_main_monitoring` | Enable or pause monitoring. |
| `sensor.alert_manager_main_active` | Active, unacknowledged alert count. |
| `sensor.alert_manager_main_pending` | Pending alert count. |
| `sensor.alert_manager_main_acknowledge` | Acknowledged alert count. |
| `sensor.alert_manager_coherence_issue` | Coherence findings. |

Lifecycle events are `alert_manager_alert_started`, `alert_manager_alert_resolved`, `alert_manager_alert_acknowledged` and `alert_manager_alert_unacknowledged`. Acknowledgement actions are `alert_manager.acknowledge` and `alert_manager.unacknowledge`.

These entities, events and actions remain available for your own dashboards and automations, whether or not you use built-in notification profiles.

### Periodic safety check

Every 10 minutes, while monitoring is running, Alert Manager checks the current
Home Assistant states of already tracked entities using its normal evaluator.
It never requests entity updates or reconstructs missed transitions or sequence
steps. Newly discovered conditions start at the check time, including inactivity
windows; existing pending deadlines remain unchanged. Known lifecycle and sequence
timers can be restored. Sequence progress is discarded if its last observed state
no longer matches, because a missed exit cannot prove a completed hold.

**Periodic check recoveries** in Configuration → Runtime diagnostics counts
entities whose alert lifecycle or sequence progress was corrected (once per entity
per pass). Message/metadata refreshes and timer restoration alone do not increment
it. Like the other diagnostics, it uses the current UTC hour and previous 23 hourly
buckets, lives only in memory and resets on reload/restart. An unchanged pass does
not save or publish alert state. Repeated recoveries indicate an event/timer bug to
investigate, not normal polling behavior.
