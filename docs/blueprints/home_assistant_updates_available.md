# Updates available

[Back to blueprint index](README.md)

Creates an aggregate alert listing available updates across Home Assistant.
The Home Assistant Core update entity anchors the rule, but the condition checks
all update entities, not just Core.

## Default behavior

| Setting | Value |
| --- | --- |
| Blueprint ID | `home_assistant_updates_available` |
| Blueprint version | 1 |
| Source | Jinja (`jinja`) |
| Condition | At least one entity in `states.update` has state `on` |
| Duration | 0 seconds (no additional pending delay) |
| Update message while active | Enabled |
| Flapping detection | Disabled |

The generated condition is:

```jinja
{{ states.update | selectattr('state', 'eq', 'on') | list | count > 0 }}
```

The alert remains active while any update entity is `on`, even when Core itself
has no update available. It resolves when none are `on`.

## Compatible entities and scope

Generation requires an enabled `update` entity belonging to the **Supervisor**
integration (`hassio`) with unique ID exactly
`home_assistant_core_version_latest`. Renaming this entity does not prevent
discovery. An installation without that entity cannot generate this blueprint,
even if it exposes other update entities.

Only the Core update entity is placed in the generated entity list. The Jinja
condition reads all update states, so device firmware, apps/add-ons and other
integrations' updates can also keep the aggregate alert active. Newly exposed
update states are within that template's scope without regenerating the rule.

## Alert message

The message starts with a prefix translated into the Home Assistant language
when the rule is generated (`Updates available:` in English). It lists the names
of update entities currently `on`, removing ` Update` and ` Mise à jour` text and
deduplicating the resulting names.

For example:

```text
Updates available: Home Assistant Core, Living room light
```

The message is refreshed while the alert is active as its tracked dependencies
change. This does not create a separate alert for each update or imply a new
notification for each message change; notification profiles control delivery
and reminders.

## Adjustments and limitations

To restrict monitoring to selected updates, edit both the condition and the message
template so that they use the same scope. Changing only the rule's entity list
does not narrow the global `states.update` expression.

Only state `on` counts. `off`, `unknown` and `unavailable` do not count as available
updates. This rule neither checks version numbers independently nor installs any
update. Identical cleaned names appear once in the message, even if multiple
update entities share them.

[Blueprint source](../../custom_components/alert_manager/blueprint/home_assistant/home_assistant_updates_available.yaml)
