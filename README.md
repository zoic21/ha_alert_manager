<p align="center">
  <img src="docs/assets/alert-manager-logo.svg" width="520" alt="Alert Manager">
</p>

<p align="center">
  🇬🇧 <strong>English</strong> · 🇫🇷 <a href="README.fr.md">Français</a>
</p>

# Alert Manager for Home Assistant

**Know when something is wrong — and keep it visible until it is fixed.**

Alert Manager brings Home Assistant problems into one place: unavailable devices, low batteries, failed automations, unexpected values or broken configuration references. It follows each alert from detection to resolution, instead of leaving you with a notification that is easy to miss.

Use automatic monitoring for common failures and custom rules for your own equipment. A problem stays visible while it needs attention; acknowledging it records that you know about it without pretending it is fixed. Resolved occurrences can be kept in history to make recurring problems easier to spot.

[Installation](#installation) · [Documentation](docs/user-guide.md) · [Report an issue](https://github.com/zoic21/ha_alert_manager/issues)

<p align="center">
  <img src="docs/assets/screenshots/dashboard.png" alt="Alert Manager overview with current alerts">
</p>

## What you can do

### Monitor everyday problems automatically

Enable packs for unavailable entities, connectivity failures, low batteries, UniFi devices away from home, available updates, automation/script execution errors and repeated instability. Each pack has its own settings and labels. Adjust delays, thresholds and device/entity exceptions where supported, using a compact visual editor or YAML. Exceptions can disable monitoring for a target; global label exclusions remain available. The available-updates pack follows Home Assistant `update` entities and lets you exclude individual entities.

Open the relevant monitoring configuration directly from an automatic alert. Exceptions collapse into summaries to keep longer configurations readable.

Everything is configured from the panel. Labels help organize alerts and route notifications, while monitoring entities and lifecycle events remain available for your own automations.

### Define rules for your installation

Monitor a fridge consuming more than 200 W for two hours, a temperature outside an expected range, heating without a sufficient temperature rise, a sensor that stops changing or a completed appliance cycle.

Rules support states, nested attributes, numeric and text comparisons, inactivity, variations, transitions, ordered sequences and Jinja conditions. One rule can monitor several entities independently. Edit visually or in YAML, duplicate a rule and test an unsaved draft against current values, including the notification profiles that would match. Custom Jinja messages can explain the problem and optionally stay updated while it is active.

Filter the rules list by enabled/disabled status, rule labels, integration, device, domain and area. The label filter uses only labels attached to the rule, without inheriting entity or device labels. Entity filters use only the entities selected at the top of the rule, without inspecting Jinja conditions or messages. An entity’s area overrides its device’s area. Multiple selections within a filter match any selected value; different filters combine.

Sequences recognize 2–20 steps on the same value, with a minimum hold, an exit before a limit or a hold between two bounds, plus an optional overall timeout. Steps collapse into summaries and can be individually disabled or reordered by dragging or using the keyboard. From the first step’s hold, the sequence appears in pending alerts with its progress and remaining time. Abandoned or expired progress disappears without history or a recovery notification. Unfinished sequences start from a fresh observation after a restart, without counting downtime.

Transitions and sequences offer three resolution modes: after a duration, when the arrival value or last enabled step no longer matches, or using a separate value comparison. State/condition resolution can send recovery notifications; automatic expiration remains silent. The [custom rules guide](docs/custom-rules.md) explains durations, progression and YAML examples.

### Follow alerts from the dashboard to history

Overview separates active, upcoming and acknowledged alerts, with search, filters, sorting, device grouping, customizable columns and multiple selection. Open an alert to inspect its triggering/current values, notification deliveries and previous occurrences. Acknowledgement can be indefinite or temporary. The ten latest acknowledgement and unacknowledgement actions (including automatic expiry) are timestamped in the timeline and survive resolution and restarts; the oldest event is removed when this limit is exceeded.

An always-visible timeline brings together detection, activation, acknowledgement, resolution, sequence step values and timestamps, instability occurrences and notification deliveries. Start and recovery notifications show their send time and profile; reminders are summarized by count and profiles. Users and automations are identified when known. Today’s events show only the time; other events retain their date.

The included dashboard card presents a compact view grouped by device. Choose desktop/mobile tile limits, sorting, label inclusions/exclusions, optional age and grouping, alignment and icon color. Keep the default Classic style or choose Bubble for rounded capsules with a pastel background derived from the selected color, without installing Bubble Card. The card hides when there are no matching alerts and opens the relevant details on click. In History, review resolved occurrences and use recurrence statistics to identify frequent alerts, affected devices and cumulative active duration.

### Choose when to notify and check configuration health

Optional built-in notification profiles support multiple `notify` recipients, new alerts, recoveries, reminders and batched delivery. Select alerts by label and define ordered exceptions; labels from the entity, device and custom rule or pack participate in matching. The profile’s label filter must match first; then the first exception whose labels all match applies. Label exceptions can enable “Informational notification”: blue information icon, “Notification” title and preserved custom messages, delivered separately from standard alerts.

This changes notification presentation only, without introducing alert severity or changing the alert lifecycle. Standard Companion notifications use red for activation, green for recovery, orange for reminders and blue with a check icon for combined activation/recovery, where supported by the client. See the [notification guide](docs/configuration.md#informational-neutral-notifications) for setup and YAML. Profiles can be tested, duplicated and edited in YAML. Supported Companion notifications open the relevant alert or view when tapped. Your own event-based notification automations remain available.

If an alert resolves before its batch is sent, activation-only profiles still receive it; profiles requesting both activation and recovery receive one combined message, identified as such in the timeline. Automatic transition/sequence expiry does not imply recovery.

Coherence scans find static references to missing entities and ZHA devices in supported configuration sources. Run them on demand or on a schedule, open the affected configuration where possible, and optionally keep an alert while findings remain. YAML import/export and automatic configuration backups provide a separate path for configuration recovery.

### Inspect runtime diagnostics

Configuration shows rule evaluation counts and processing times, alert transitions and notification sends over 24 hourly buckets, kept only in memory and reset on restart.

Detection is driven by Home Assistant events. A safety check every 10 minutes also checks the current states of already tracked entities, without requesting entity updates or reconstructing missed transitions. Newly detected conditions start at the check time. A recovery counter in diagnostics shows whether this check corrected discrepancies.

The interface is available in **English and French**, on desktop and mobile. All authenticated users can read the card, Overview and History; configuration and all actions, including acknowledgement, require an administrator.

<details>
<summary><strong>More screenshots</strong></summary>

### Dashboard card

<img src="docs/assets/screenshots/card.png" alt="Compact Alert Manager dashboard card">

### Card configuration

<img src="docs/assets/screenshots/card%20configuration.png" alt="Visual card editor with tile limits, sorting and labels">

### Upcoming alerts

<img src="docs/assets/screenshots/incomming.png" alt="Alerts waiting for their trigger delay">

### Alert details and timeline

<img src="docs/assets/screenshots/alert.png" width="596" alt="Resolved sequence with its steps and notification in the timeline">

### Custom rules

<img src="docs/assets/screenshots/regle%20personalis%C3%A9e.png" alt="Custom rules in Alert Manager">

### Sequences

<img src="docs/assets/screenshots/sequence.png" width="574" alt="Sequence editor with collapsible steps and resolution mode">

### Notification profiles

<img src="docs/assets/screenshots/notification.png" width="572" alt="Notification profile with standard and informational exceptions">

### Configuration coherence

<img src="docs/assets/screenshots/coherence.png" alt="Coherence page and deleted-entity list">

### Configuration

<img src="docs/assets/screenshots/configuration.png" alt="Alert Manager configuration">

</details>

## Installation

Requires **Home Assistant 2026.8 or newer**. One Alert Manager instance is supported per Home Assistant installation.

### HACS

1. In **HACS → Custom repositories**, add `https://github.com/zoic21/ha_alert_manager` with category **Integration**.
2. Install **Alert Manager** and restart Home Assistant.
3. Open **Settings → Devices & services → Add integration** and search for **Alert Manager**.

The panel appears in the Home Assistant sidebar. No YAML configuration is required.

<details>
<summary>Manual installation</summary>

Copy `custom_components/alert_manager` to `/config/custom_components/alert_manager`, restart Home Assistant, then add **Alert Manager** from **Settings → Devices & services**.

</details>

### Add the dashboard card

Choose **Alert Manager** in the dashboard card picker. No separate frontend installation or manual Lovelace resource is needed; refresh your browser after installing or updating the integration.

```yaml
type: custom:alert-manager-card
max_tiles: 5
alignment: left
```

## Documentation

Start in **Configuration → Automatic monitoring**, review the enabled packs and their delays, then add custom rules for situations specific to your installation. Notification profiles are optional.

The detailed documentation is maintained **in English**:

| Guide | What it covers |
| --- | --- |
| [Custom rules](docs/custom-rules.md) | Operations, attributes, Jinja, variations, transitions, sequences, rule testing and practical YAML examples. |
| [Configuration](docs/configuration.md) | Monitoring packs, delays, exclusions, notification profiles, YAML, backups and diagnostics. |
| [Configuration coherence](docs/coherence.md) | Reference scans, ZHA checks, exclusions, schedules and coherence alerts. |
| [Dashboard and history](docs/dashboard-and-history.md) | Overview, card options, acknowledgement, startup, history and recurrence statistics. |

The [documentation index](docs/user-guide.md) provides an entry point to all four guides. Documentation follows the branch being read; use the matching release branch or tag for an installed version.

Questions, bugs and monitoring ideas are welcome through **[GitHub Issues](https://github.com/zoic21/ha_alert_manager/issues)**.

Alert Manager is an unofficial community integration, not affiliated with Home Assistant. This code was written partly with the help of AI.
