# Backup alert

[Back to blueprint index](README.md)

Alerts when Home Assistant's last successful automatic backup is more than
25 hours old. This gives a daily backup schedule a one-hour margin.

## Default behavior

| Setting | Value |
| --- | --- |
| Blueprint ID | `home_assistant_backup_age` |
| Blueprint version | 1 |
| Source | Jinja (`jinja`) |
| Condition | Last successful automatic backup older than 25 hours |
| Duration | 0 seconds (no additional pending delay) |
| Update message while active | Disabled |
| Flapping detection | Disabled |

The condition uses the timestamp stored in each selected entity:

```jinja
{% set last_backup = as_timestamp(states(entity_id), none) %}
{{ last_backup is not none and
   ((as_timestamp(now()) - last_backup) | int) > 25 * 3600 }}
```

The integer age in seconds must be strictly greater than 90,000. The condition
depends on `now()` and is reevaluated through Home Assistant's template tracking;
the zero delay does not promise activation at an exact second. A new successful
automatic backup with a recent timestamp clears the condition.

## Compatible entities

The entity must be a `sensor` from the **Backup** integration (`backup`) with
translation key or unique ID exactly `last_successful_automatic_backup`.
Its visible name and entity ID can be localized or renamed without preventing
discovery, because selection uses registry metadata.

Enable the last successful automatic backup sensor before opening the generator.
A similarly named sensor from another integration is not selected.

## Adjustments and limitations

Change `25 * 3600` in the generated rule's condition template to adjust the maximum
age in seconds. For example, `49 * 3600` allows 49 hours. Keep the timestamp
validity guard when editing the template.

`unknown`, `unavailable` and other values that cannot be parsed as timestamps
make the condition false. Therefore, this rule does **not** alert on a missing
backup date or prove that any backup has ever succeeded. A future timestamp also
does not trigger it. Add separate monitoring if you need to detect these cases.

Only the last successful **automatic** backup timestamp is checked. The rule does
not validate backup contents, restoreability or destination availability, and
does not create or retry backups.

[Blueprint source](../../custom_components/alert_manager/blueprint/home_assistant/home_assistant_backup_age.yaml)
