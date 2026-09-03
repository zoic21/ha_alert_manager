<p align="center">
  <img src="docs/assets/alert-manager-logo.svg" width="520" alt="Alert Manager">
</p>

<p align="center">
  🇬🇧 <strong>English</strong> · 🇫🇷 <a href="README.fr.md">Français</a>
</p>

# Alert Manager for Home Assistant

**Know when something is wrong in Home Assistant — and keep it visible until it is fixed.**

Alert Manager turns abnormal situations in Home Assistant into issues you can actually follow. Instead of spreading the logic across templates, automations, notifications and dashboard cards, you define what “not normal” means and Alert Manager keeps track of it from detection to resolution.

It can also look for **broken entity references in your Home Assistant configuration**, helping you find leftovers after an entity is renamed or removed.

Typical examples:

- an entity has been `unavailable` for more than 15 minutes;
- a battery drops below 15%;
- a connectivity sensor stays `off`;
- a UniFi device stays `not_home`;
- an automation or script finishes with an error;
- a fridge consumes more than 200 W for 2 hours;
- a temperature remains outside an expected range;
- a value or attribute stops changing for too long;
- an automation or dashboard still references an entity that no longer exists;
- any custom state, attribute or Jinja-based condition you want to monitor.

The important difference from a simple notification is that a problem **remains visible until it is resolved**.

## What Alert Manager gives you

- **A central alert dashboard** for active, upcoming and acknowledged problems.
- **Automatic monitoring** for common Home Assistant failures such as unavailable entities, connectivity, low batteries, UniFi devices, and failed automations or scripts.
- **Powerful custom rules** for states, attributes, ranges, inactivity and Jinja conditions.
- **Configuration coherence checks** to find references to missing entities and jump back to the affected configuration when possible.
- **Alert acknowledgement and history** so temporary handling does not hide the real state of your installation.
- **Search, filters, sorting, grouping and customizable columns**, with a responsive mobile view.
- **Exclusions and delays** to keep expected situations and short glitches from becoming noise.
- **YAML export and automatic configuration backups** with guided recovery if the saved configuration becomes invalid.
- **Home Assistant entities and events** so Alert Manager can feed your own dashboards and notification automations.
- **French and English UI**.

Alert Manager does **not** impose its own notification system. Notifications stay regular Home Assistant automations, so you decide who gets notified, how and when.

## Screenshots

### Overview

<p align="center">
  <img src="docs/assets/screenshots/overview.webp" alt="Alert Manager overview">
</p>

<details>
<summary><strong>More screenshots</strong></summary>

### History

<p align="center">
  <img src="docs/assets/screenshots/history.webp" alt="Alert Manager history">
</p>

### Automatic monitoring

<p align="center">
  <img src="docs/assets/screenshots/automatic-monitoring.webp" alt="Alert Manager automatic monitoring">
</p>

### Custom rules

<p align="center">
  <img src="docs/assets/screenshots/custom-rules.webp" alt="Alert Manager custom rules">
</p>

### Configuration coherence

<p align="center">
  <img src="docs/assets/screenshots/coherence.png" alt="Alert Manager configuration coherence">
</p>

### Rule editor

<p align="center">
  <img src="docs/assets/screenshots/rule-editor.webp" width="520" alt="Alert Manager rule editor">
</p>

### Configuration

<p align="center">
  <img src="docs/assets/screenshots/configuration.webp" alt="Alert Manager configuration">
</p>

</details>

## Installation

### HACS

Until Alert Manager is available in the default HACS catalog:

1. Open **HACS → Custom repositories**.
2. Add `https://github.com/zoic21/ha_alert_manager` as an **Integration**.
3. Install **Alert Manager**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration** and search for **Alert Manager**.

The **Alert Manager** panel then appears in the Home Assistant sidebar.

### Manual installation

1. Copy `custom_components/alert_manager` to `/config/custom_components/alert_manager`.
2. Restart Home Assistant.
3. Add **Alert Manager** from **Settings → Devices & services**.

No Lovelace resource and no YAML configuration are required to get started.

## Automatic monitoring

Alert Manager can automatically watch common Home Assistant problems:

| Monitor | Alert condition |
| --- | --- |
| Unavailable entities | entity stays `unavailable` |
| Connectivity | `binary_sensor` with `device_class: connectivity` stays `off` |
| Low battery | battery sensor reaches the configured threshold |
| UniFi | UniFi network `device_tracker` stays away from `home` |
| Automation and script errors | an `automation` or `script` execution finishes with an error |

Each monitor can be enabled independently. Delays and exclusions can be adjusted from the UI, and battery thresholds can be adapted when some devices need different limits.

Automation and script errors have no delay by default. A successful completed execution resolves the alert. For selected automations or scripts, you can require several consecutive failed execution cycles before raising it.

## Custom rules

For everything else, create your own rules directly from the Alert Manager panel.

A rule can monitor one or several entities independently and use:

- the entity state or a nested attribute, including array paths such as `data.*.key`;
- equality, text, numeric threshold, **between** and **outside** comparisons;
- the variation of the state or a numeric attribute from the moment a Jinja condition becomes true;
- the absence of any change, or only a specific state or attribute that stops changing;
- a Jinja condition in addition to a comparison, or Jinja as the complete rule logic.

Delays let you require the situation to persist before it becomes an alert, which prevents short glitches from filling the dashboard. Custom Jinja messages are frozen when the alert activates by default, or can be kept up to date while it remains active.

Example use cases include abnormal temperatures, unexpected power consumption, backup age, error codes, stale sensors, equipment that stopped updating or almost any state Home Assistant exposes.

Rules can be edited visually or in YAML and duplicated from the panel. One rule can monitor up to 50 entities, and one configuration can contain up to 500 rules. Jinja-only YAML rules use `source: jinja`; existing `source: none` rules are migrated automatically.

### Examples

#### A thermostat that heats without warming the room

When the thermostat starts heating, the Jinja condition becomes true and Alert Manager stores the initial current_temperature. After two hours, this rule raises an alert if the room has gained less than 0.2 °C. In the message, value is the measured temperature variation.

```yaml
name: "Thermostat : surveillance"
enabled: true
entity_ids:
  - "climate.tado_smart_thermostat_su0582429440"
source: "attribute_variation"
attribute: "current_temperature"
operator: "below"
value: "0.2"
duration: 7200
message: "Le chauffage {{ state_attr(entity_id, 'friendly_name') }} est en marche depuis 2 h, mais la température n'a augmenté que de {{ value | float(0) | round(1) }} °C."
update_message_when_active: false
condition_template: "{{ state.state == 'heating' }}"
```

#### Bayrol messages, with expected states filtered out

This rule evaluates every message key in the Bayrol data array. It can activate only when none of the expected flow, start-delay and enjoyment states is present; its Jinja condition also requires flow to be present.

```yaml
name: "Alerte Bayrol"
enabled: true
entity_ids:
  - "sensor.bayrol_messages"
source: "attribute"
attribute: "data.*.key"
operator: "not_contains"
value:
  - "al_no_flow_bnc"
  - "al_start_delay"
  - "enjoy"
duration: 5400
message: "{% if state_attr('sensor.bayrol_messages','data') %}\n{% for item in state_attr('sensor.bayrol_messages','data') %}     \n    {% if item.key not in ['al_no_flow_bnc','enjoy','al_start_delay'] %}       \n      {{ item.message | replace(\"\\n\",\" \") }}  \n    {% endif %}      \n{% endfor %}     \n{% endif %}"
update_message_when_active: false
condition_template: "{% set flow = states('binary_sensor.bayrol_flow_contact') %}\n{{ (flow == 'on') }}"

```

## Configuration coherence

The **Coherence** page checks static entity references found in your Home Assistant configuration against the entities that currently exist.

When an issue is found, Alert Manager shows where it comes from and, when possible, lets you open the affected automation, script, dashboard, template or other Home Assistant object directly. Results are stored between restarts and can also be exposed through `sensor.alert_manager_coherence_issue` so a failed coherence check can itself become something you monitor.

Scans can run on demand or automatically on a daily, weekly or monthly schedule. ESPHome scanning can be disabled, and known references can be ignored from the configuration page.

The same page also provides the 50 latest deleted entities still retained by Home Assistant, with their deletion date and integration. This is read directly from Home Assistant's entity registry and does not require Alert Manager to maintain its own deletion history.

## Configuration export and recovery

The complete configuration can be exported and imported as YAML. Alert Manager also keeps the three latest valid daily configuration exports. They can be downloaded or restored from the settings page.

If the stored configuration cannot be loaded at startup, Alert Manager starts safely with defaults, displays a persistent warning and lets an administrator choose a backup. It never restores one silently. Restoring a complete backup replaces the current configuration, runtime alerts and history.

## Alert lifecycle

An alert can be:

- **Upcoming** while its delay is still running;
- **Active** once the condition has lasted long enough;
- **Acknowledged** when you know about the issue but it is not resolved yet;
- **Resolved** when the abnormal condition disappears.

Resolved alerts can be kept in history, making it easier to spot recurring problems instead of only seeing what is wrong right now.

Selecting an alert opens its details, including the value that triggered it and the current value, with contextual access to the related Home Assistant entity when available.

## Notifications without getting spammed

Alert Manager emits `alert_manager_device_alert_started` when a device enters an alert state. Alerts that arrive close together for the same device are grouped before the event is emitted, which makes it useful for sending **one useful notification for the device instead of one notification per rule**.

Example:

```yaml
alias: Notification Alert Manager
triggers:
  - trigger: event
    event_type: alert_manager_device_alert_started
actions:
  - action: script.notification
    metadata: {}
    data:
      title: '{{ trigger.event.data.device_name }} en alerte'
      message: |-
        {% for message in trigger.event.data.messages | default([], true) %}
        - {{ message }}
        {% endfor %}
      recipients:
        - loic
mode: queued
```

`script.notification` is only an example here: replace it with your own notification script or any Home Assistant notification action.

## Home Assistant entities and events

Alert Manager exposes dedicated entities so its state can also be used outside the built-in panel:

- `switch.alert_manager_main_monitoring`
- `sensor.alert_manager_main_active`
- `sensor.alert_manager_main_pending`
- `sensor.alert_manager_main_acknowledge`
- `sensor.alert_manager_device_main_active`
- `sensor.alert_manager_coherence_issue`

Useful events include:

- `alert_manager_alert_started`
- `alert_manager_alert_resolved`
- `alert_manager_device_alert_started`
- `alert_manager_alert_acknowledged`
- `alert_manager_alert_unacknowledged`

Alert acknowledgement is also available through `alert_manager.acknowledge` and `alert_manager.unacknowledge`.

## Requirements

- Home Assistant **2026.8 or newer**.
- One Alert Manager instance per Home Assistant installation.
- Administrator access is required for the Alert Manager panel.

Alert Manager is an unofficial community integration and is not affiliated with the Home Assistant project.

## Note

This code was written partly with the help of AI.

## Feedback

Alert Manager is actively evolving and real-world installations are the best way to find edge cases.

Bug reports, ideas and unusual monitoring use cases are very welcome through **[GitHub Issues](https://github.com/zoic21/ha_alert_manager/issues)**.
