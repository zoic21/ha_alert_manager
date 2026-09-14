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
| Automation and script errors | An execution finishes with an error; a successfully completed execution resolves the alert. |
| Flapping / instability | The same anomaly recurs within a detection window. |

### Delays, exclusions and overrides

Use the global delay, pack delays and per-entity delays to tolerate short glitches. Automatic monitoring also supports exclusions by entity, device or Home Assistant label. Battery thresholds can be overridden per device.

Automation/script errors have no delay by default. Selected entities can require several consecutive failed execution cycles before raising an alert; this is different from a time delay.

The trigger delay decides when an anomaly becomes an active alert. The pending-alert display delay only controls when a pending alert is shown, not when it activates. Review both when an expected pending alert is not immediately visible.

Pack labels update current alerts when changed; history keeps the labels recorded at resolution. Rule labels complement entity and device labels for notification selection, not dynamic rule targeting.

### Flapping and instability

Flapping can detect repeated short anomalies that clear before the normal trigger delay. It is disabled by default. The defaults are **5 occurrences within 1 hour**, followed by recovery after **30 minutes without another occurrence**.

Unavailable entities and connectivity are the preselected sources; their source packs must be enabled. Settings can be adjusted globally, per source pack, per entity or per custom rule. Custom rules participate through their flapping option.

An instability alert is separate from its source alert. Its details retain the count/threshold and occurrence times in a collapsible section, including in resolved history. Evidence follows the detector's bounded rolling window rather than providing an unlimited event log.

## Notification profiles

In **Configuration → Notifications**, create a named profile with one or more **`notify` entities**. Choose whether to send new-alert and recovery notifications and whether to repeat reminders. The minimum reminder interval is one minute. Each profile has an enable switch.

Profiles are optional: lifecycle events remain available for your own notification automations. Profiles accept notification entities, not arbitrary actions or scripts; channels exposed only as actions can still be used through an automation.

The profile's three-dot menu offers **YAML mode**, **Duplicate** and **Test**. Duplication preserves settings, recipients and exception order, but creates the copy only on save and does not copy usage counters or runtime state. Test sends a **real notification** through the saved profile without creating an alert.

### Labels and exceptions

A profile can cover all alerts or match **any selected label (OR)**. Matching combines the labels of the entity, its device and the custom rule or automatic pack that produced the alert.

An exception requires **all its selected labels (AND)**. The **first matching exception in list order** wins; inherited settings keep the profile defaults. Exceptions can independently override new-alert, recovery and reminder behavior. In YAML they use `selector_ids`; legacy `selector_id` remains accepted.

For example, a profile may notify every new alert, while its first exception disables reminders for alerts carrying both a maintenance label and a particular rule label. An alert matching only one of those labels does not match that exception.

### Batching and reminders

New alerts and recoveries are grouped separately per profile. The batching delay is **30 seconds by default**, adjustable from **10 to 300 seconds**. Changing it affects new batches, not batches already waiting. When an alert clears before its queued activation is sent, the unsent activation/recovery pair is discarded.

Reminders are grouped per profile and stop on acknowledgement or resolution. After restart they wait for alert reconciliation. Only confirmed alerts resume reminders; overdue deadlines restart from the configured interval without replaying missed reminders.

### Mobile navigation and delivery details

Titles distinguish new alerts, reminders and recoveries with their corresponding emoji prefixes. With supported Companion targets, tapping opens a single ongoing alert's details, Overview for several ongoing alerts, or History for recoveries. Generic targets receive a title and message without an appended raw navigation URL.

Alert details separate activation and reminder deliveries; history also records recovery deliveries, matching profiles and last delivery times. A batch counts once per profile and alert when at least one target succeeds. Tests and complete failures are excluded. These details survive restarts, are hidden for pending alerts and do not count notifications sent by external automations.

Profile usage counters cover the current hour and previous 23 hours since startup. They are kept only in memory and reset on restart/reload; a grouped send counts once even with multiple targets.

## Display, history and coherence settings

Adjust pending-alert visibility separately from trigger delays. The history limit controls how many resolved occurrences are retained; deleted or discarded occurrences are no longer available to history statistics. See [Dashboard and history](dashboard-and-history.md) for acknowledgement, filtering and recurrence reports.

Coherence settings control scheduling, ESPHome scanning, reference exclusions and the optional persistent coherence alert. See the [Coherence guide](coherence.md) for supported references and incomplete-scan behavior.

## YAML editing

Configuration drawers and notification profiles offer **YAML mode** in their three-dot menu. A drawer's YAML contains only its edited field, such as battery thresholds, failed-cycle counts, flapping overrides, entity/device exclusions or per-entity delays.

Visual/YAML switching preserves unsaved values and list order. Invalid YAML, unknown keys and invalid settings block saving or returning to the visual editor. **Save** applies the changes. Closing a modified editor asks for confirmation; desktop drawers can be resized. Details and diagnostic panels remain read-only.

Duration fields use Home Assistant's hours/minutes/seconds selector; YAML stores seconds. Clearing an optional override retains that field's inherited or disabled behavior.

## Configuration backups and recovery

The full configuration can be exported/imported as YAML. Alert Manager retains the **three latest valid daily configuration backups**, downloadable and restorable from Configuration.

If the saved configuration is invalid at startup, the integration uses safe defaults, displays a persistent warning and lets an administrator choose a backup. It never restores one silently.

**Restoring a complete backup replaces the current configuration, runtime alerts and history.** Review what will be replaced before confirming a restoration. Configuration exports should not be confused with a full Home Assistant backup.

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
