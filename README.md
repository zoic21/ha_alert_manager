<p align="center">
  <img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/alert-manager-logo.svg" width="520" alt="Alert Manager">
</p>

🇬🇧 **English** · 🇫🇷 [Français](README.fr.md)

# Alert Manager for Home Assistant

**Know what needs attention in your home — and follow it until it is fixed.**

Unavailable devices, low batteries, failed automations or unexpected sensor values:
Alert Manager brings the problems into one place, with a dashboard, notifications
and a history of resolved alerts.

[Documentation](docs/user-guide.md) ·
[Report an issue](https://github.com/zoic21/ha_alert_manager/issues)

<p align="center">
  <img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/screenshots/dashboard.png" alt="Alert Manager overview with current alerts">
</p>

## What you can do

- **Monitor common problems automatically.** Detect unavailable entities, connection
  failures, low batteries, missing UniFi devices, available updates, automation/script
  errors and repeated instability.
- **Create your own rules.** Watch a temperature, unusual power consumption, a sensor
  that stops changing or the end of an appliance cycle. Use the visual editor or YAML.
- **Follow each alert.** See active, upcoming and acknowledged alerts, inspect their
  timeline and review past occurrences. Acknowledging an alert records that you have
  seen it; it does not resolve the problem.
- **Choose your notifications.** Use labels to select what matters, with reminders,
  grouped messages and optional informational notifications.
- **Keep alerts on your dashboard.** The included card groups alerts by device and
  supports custom CSS.
- **Find broken configuration references.** Check missing entity references and
  export your Home Assistant entities.

The interface is available in **English and French**, on desktop and mobile.

## Installation

Requires **Home Assistant 2026.8 or newer**.

1. In **HACS**, find and install **Alert Manager**.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration** and search for
   **Alert Manager**.

The panel appears in the sidebar. Open **Configuration → Automatic monitoring**
to review the enabled packs and their delays, then add custom rules or notification
profiles as needed.

**To update:** update through HACS, restart Home Assistant and refresh your browser.

<details>
<summary>Manual installation</summary>

Copy `custom_components/alert_manager` to `/config/custom_components/alert_manager`,
restart Home Assistant, then add **Alert Manager** from **Settings → Devices & services**.

</details>

### Add the dashboard card

Choose **Alert Manager** in the dashboard card picker. The card is included with the
integration; refresh your browser after installing or updating it.

## Documentation

The detailed guides are maintained **in English**:

| Guide | Find out how to… |
| --- | --- |
| [Custom rules](docs/custom-rules.md) | Create rules, sequences and Jinja conditions, with examples. |
| [Configuration](docs/configuration.md) | Set up monitoring, notifications, backups and diagnostics. |
| [Configuration coherence](docs/coherence.md) | Check configuration references and export entities. |
| [Dashboard and history](docs/dashboard-and-history.md) | Configure the card, acknowledge alerts and explore history. |

See the [documentation index](docs/user-guide.md) for common tasks.
For an installed version, select its release tag on GitHub.

<details>
<summary><strong>More screenshots</strong></summary>

### Dashboard card

<img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/screenshots/card.png" alt="Compact Alert Manager dashboard card">

### Card configuration

<img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/screenshots/card%20configuration.png" alt="Visual editor for the dashboard card">

### Upcoming alerts

<img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/screenshots/incomming.png" alt="Alerts waiting for their trigger delay">

### Alert details and timeline

<img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/screenshots/alert.png" width="596" alt="Alert details with the sequence steps and notification timeline">

### Custom rules

<img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/screenshots/regle%20personalis%C3%A9e.png" alt="Custom rules in Alert Manager">

### Sequences

<img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/screenshots/sequence.png" width="574" alt="Sequence editor with collapsible steps">

### Notification profiles

<img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/screenshots/notification.png" width="572" alt="Notification profile with standard and informational exceptions">

### Configuration coherence

<img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/screenshots/coherence.png" alt="Configuration coherence checks">

### Configuration

<img src="https://raw.githubusercontent.com/zoic21/ha_alert_manager/main/docs/assets/screenshots/configuration.png" alt="Alert Manager configuration">

</details>

All signed-in users can view the dashboard card, Overview and History.
Configuration and actions, including acknowledgement, require an administrator.
One Alert Manager instance is supported per Home Assistant installation.

Questions or ideas? [Open a GitHub issue](https://github.com/zoic21/ha_alert_manager/issues).

Alert Manager is an unofficial community integration, not affiliated with Home Assistant.
This code was written partly with the help of AI.
