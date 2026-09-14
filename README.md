<p align="center">
  <img src="docs/assets/alert-manager-logo.svg" width="520" alt="Alert Manager">
</p>

<p align="center">
  🇬🇧 <strong>English</strong> · 🇫🇷 <a href="README.fr.md">Français</a>
</p>

# Alert Manager for Home Assistant

**Know when something is wrong — and keep it visible until it is fixed.**

Alert Manager brings Home Assistant problems into one place: unavailable devices, low batteries, failed automations, unexpected values or broken configuration references. It follows each alert from detection to resolution, instead of leaving you with a notification that is easy to miss.

[Installation](#installation) · [User guide](docs/user-guide.md) · [Report an issue](https://github.com/zoic21/ha_alert_manager/issues)

<p align="center">
  <img src="docs/assets/screenshots/dashboard.png" alt="Alert Manager overview with current alerts">
</p>

## Features

| Area | What you can do |
| --- | --- |
| Automatic monitoring | Detect unavailable entities, connectivity failures, low batteries, UniFi devices away from home, automation/script errors and repeated instability. Adjust delays and exclusions to avoid noise. |
| Custom rules | Monitor states, attributes, thresholds, ranges, inactivity, variations, transitions and Jinja conditions. Edit visually or in YAML, duplicate rules and test them against current values, including matching notification profiles. |
| Alert management | Search, filter and group alerts; acknowledge them indefinitely or temporarily; inspect their details, notification deliveries and previous occurrences. Explore history and recurrence statistics. |
| Dashboard card | Display a compact, responsive view grouped by device, with label filtering, a tile limit, alignment and icon color. The card hides when there are no matching alerts and opens the relevant details on click. |
| Notifications | Configure optional profiles with several recipients, new alerts, recoveries, reminders, batching and ordered label exceptions. Edit profiles in YAML, duplicate them or send a test. |
| Configuration coherence | Find missing static entity references and invalid ZHA device references, scan on demand or on a schedule, and optionally raise an alert for unresolved findings. |
| Configuration and automation | Use Home Assistant labels, YAML import/export, automatic configuration backups, monitoring entities and lifecycle events for your own automations. |

The interface is available in **English and French**, on desktop and mobile. All authenticated users can read the card, Overview and History; configuration and all actions, including acknowledgement, require an administrator.

<details>
<summary><strong>More screenshots</strong></summary>

### Dashboard card

<img src="docs/assets/screenshots/card.png" alt="Compact Alert Manager dashboard card">

### Upcoming alerts

<img src="docs/assets/screenshots/incomming.png" alt="Alerts waiting for their trigger delay">

### History

<img src="docs/assets/screenshots/history.png" alt="Alert history and filtering">

### Custom rules

<img src="docs/assets/screenshots/regle%20personalis%C3%A9e.png" alt="Custom rules in Alert Manager">

### Configuration coherence

<img src="docs/assets/screenshots/coherence.png" alt="Configuration coherence results">

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

## Using Alert Manager

Start in **Configuration → Automatic monitoring**, adjust the enabled packs and their delays, then add custom rules for situations specific to your installation. Notification profiles are optional; your own event-based automations can be used instead.

The **[user guide](docs/user-guide.md)** covers rule examples, transitions, card options and startup behavior, notification routing, temporary acknowledgement, history statistics, coherence scans, YAML and recovery. A **[French guide](docs/user-guide.fr.md)** is also available.

Questions, bugs and monitoring ideas are welcome through **[GitHub Issues](https://github.com/zoic21/ha_alert_manager/issues)**.

Alert Manager is an unofficial community integration, not affiliated with Home Assistant. This code was written partly with the help of AI.
