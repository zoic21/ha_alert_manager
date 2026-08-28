<p align="center">
  <img src="docs/assets/alert-manager-logo.svg" width="520" alt="Alert Manager">
</p>

<p align="center">
  🇬🇧 <strong>English</strong> · 🇫🇷 <a href="README.fr.md">Français</a>
</p>

# Alert Manager for Home Assistant

**Know when something is wrong in Home Assistant — and keep it visible until it is fixed.**

Alert Manager gives you one place to monitor abnormal situations in your Home Assistant installation. Instead of maintaining many templates, automations, notifications and dashboard cards, you define what should be considered abnormal and Alert Manager keeps track of it for you.

Typical examples:

- an entity has been `unavailable` for more than 15 minutes;
- a battery drops below 15%;
- a connectivity sensor stays `off`;
- a UniFi device stays `not_home`;
- a fridge consumes more than 200 W for 2 hours;
- a fridge temperature stays above 8 °C for 30 minutes;
- any custom state, attribute or Jinja-based condition you want to monitor.

The important difference from a simple notification is that the problem **remains visible until it is resolved**.

## What you get

- **Central alert dashboard** with active, upcoming and acknowledged alerts.
- **Automatic monitoring** for unavailable entities, connectivity, low batteries and UniFi devices.
- **Custom rules** on entity states or attributes with delays.
- **Jinja conditions and messages** using Home Assistant templates.
- **Acknowledgement** without losing track of the underlying problem.
- **History** of resolved alerts.
- **Search, filters, sorting and grouping** in the dashboard.
- **Exclusions** by entity, device or label.
- **Per-rule, per-entity and global delays** so short glitches do not become noise.
- **Home Assistant events and sensors** for your own dashboards and automations.
- **Event-driven monitoring** without frequent global polling.
- **French and English UI**.

Alert Manager does **not** force a notification system on you. Notifications remain regular Home Assistant automations, so you decide who gets notified, how, and when.

## Screenshots

The current UI screenshots and the original beta-test discussion are available here:

**[Reddit — Integration alarm manager: need beta test](https://www.reddit.com/r/homeassistant/comments/1vzyqg1/integration_alarm_manager_need_beta_test/)**

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

## Automatic monitoring

Alert Manager can automatically watch common Home Assistant problems:

| Monitor | Alert condition |
| --- | --- |
| Unavailable entities | entity stays `unavailable` |
| Connectivity | `binary_sensor` with `device_class: connectivity` stays `off` |
| Low battery | battery sensor reaches the configured threshold |
| UniFi | UniFi network `device_tracker` stays away from `home` |

Automatic checks can be enabled independently and adjusted from the UI.

## Custom rules

For everything else, create your own rules directly from the Alert Manager panel.

Rules can:

- monitor one or several entities independently;
- use the entity state or an attribute;
- compare with `equals`, `not equals`, `contains`, `not contains`, `above` or `below`;
- require the condition to remain true for a configurable duration;
- add an optional Home Assistant Jinja condition;
- generate a custom Jinja message with live entity data.

Example use cases include temperature limits, abnormal power consumption, backup age, device error codes or almost any state Home Assistant exposes.

Rules can be edited visually or in YAML. The full Alert Manager configuration can also be exported and imported as YAML.

## Active, upcoming and acknowledged alerts

Alert Manager exposes dedicated entities so you can also use its state outside the built-in panel:

- `switch.alert_manager_main_monitoring`
- `sensor.alert_manager_main_active`
- `sensor.alert_manager_main_pending`
- `sensor.alert_manager_main_acknowledge`
- `sensor.alert_manager_device_main_active`

This makes it easy to create a conditional card on your normal dashboard, drive a notification automation, or expose a simple health indicator for your Home Assistant installation.

## Events and actions

Useful events include:

- `alert_manager_alert_started`
- `alert_manager_alert_resolved`
- `alert_manager_device_alert_started`
- `alert_manager_alert_acknowledged`
- `alert_manager_alert_unacknowledged`

Alert acknowledgement is also available through:

- `alert_manager.acknowledge`
- `alert_manager.unacknowledge`

## Requirements

- Home Assistant **2026.8 or newer**.
- One Alert Manager instance per Home Assistant installation.
- Administrator access is required for the Alert Manager panel.

Alert Manager is an unofficial community integration and is not affiliated with the Home Assistant project.

## Feedback and beta testing

Alert Manager is actively evolving and real-world installations are the best way to find edge cases.

If you test it, bug reports and use cases are very welcome through **[GitHub Issues](https://github.com/zoic21/ha_alert_manager/issues)**.

If you have an unusual thing you monitor today with a template or automation, feel free to describe it too — it may be a good candidate for a future built-in rule.
