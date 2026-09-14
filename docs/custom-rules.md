# Custom rules

[Documentation](user-guide.md) · [Configuration](configuration.md) · [Coherence](coherence.md) · [Dashboard and history](dashboard-and-history.md)

Custom rules monitor situations specific to your installation: a fridge drawing too much power, heating that does not warm a room, a stale sensor, an error message or a completed appliance cycle. Create them from **Custom rules** using the visual editor or YAML.

## Alert or Information

The **Level** field is presentation metadata for custom rules: `alert` (default)
keeps the usual appearance; `info` uses an information icon and a theme blue accent.
Set it in the visual editor or YAML:

```yaml
level: info
```

Information follows the same pending, active, acknowledged and resolved lifecycle.
It contributes to the same counters and statistics. Conditions, delays, flapping,
automatic resolution and notification policies are unchanged. Changing only the
level preserves the current occurrence, timers and acknowledgement. Resolved
history keeps the level captured at resolution, even if the rule later changes or
is deleted. Older data without a level is treated as Alert.

To notify only when an information starts, assign a Home Assistant label such as
`information` to the rule and add a notification profile exception for that label:
enable starts, disable resolutions and set reminders to never. The label and level
are independent; no label is created or interpreted automatically.

Mixed notification batches retain their alert presentation and remain a single
batch. Information-only notifications use informative titles and the existing
native icon path where supported, or an information symbol in the title otherwise.
Reminder and resolution titles retain their meaning. Dashboard groups use the
Information appearance only when all their active members are informative;
explicit card icon color settings still take precedence.

## Create and test a rule

Choose a name, select the entities, choose an operation and configure its comparison or condition. Set a trigger delay when brief anomalies should be ignored. An optional Jinja message explains the problem when the alert activates.

Each selected entity is evaluated independently and has its own alert. A configuration supports up to **500 rules**, with **50 entities per rule**. Rules can be enabled, disabled, duplicated and edited without writing an automation.

The **Test** button evaluates the unsaved draft against current values. For each entity it shows the value read, comparison and Jinja results, rendered message, errors and the profiles that would notify a new alert. This preview does not save the rule, change alerts or timers, or send notifications. A compatible baseline is needed to test a variation; a current value cannot prove that a transition happened.

Home Assistant labels can be attached to a rule. They help organize rules and participate in [notification selection](configuration.md#labels-and-exceptions), alongside entity and device labels. They do **not** dynamically select the entities monitored by the rule.

## Operations and comparisons

| Operation | YAML source | Use it to |
| --- | --- | --- |
| Value | `value` | Compare the state or an attribute with an expected value, threshold or range, or check that this specific value has stopped changing. |
| Variation | `value_variation` | Measure a numeric change from a baseline recorded when a Jinja condition becomes true. |
| Transition | `value_transition` | Observe a specific `from_value` → `to_value` change and keep the resulting alert visible for a configured time. |
| No change | `unchanged` | Detect an entity with no state or attribute change for the configured duration. |
| Jinja | `jinja` | Use a template as the complete rule condition. |

Value comparisons include equality, inequality, contains/not contains, above/below and between/outside a range. Text comparisons can use several values. Inactivity can concern the whole entity or only the selected state/attribute: choose the operation that matches the behavior you need to observe.

For Value, Variation and Transition, an omitted or empty `attribute` targets the state; a populated `attribute` targets that attribute. Missing attributes never fall back to the state. Nested paths are supported; wildcard paths such as `data.*.key` are limited to regular comparisons.

### Delays, conditions and messages

Use `duration` to require a condition to persist before activation. Duration fields use Home Assistant's hours/minutes/seconds selector; YAML stores seconds. If an ordinary pending condition disappears before the deadline, it creates no resolved-history entry.

A Jinja condition can complement a comparison or supply the complete rule logic. A message can include the entity and measured value. Messages are frozen at activation by default; enable `update_message_when_active` to keep the message current while the alert is active.

A Jinja rendering error is indeterminate, **not a recovery**: it preserves existing alerts, pending deadlines and the last valid message. Relevant dependency changes retry evaluation. For variations, an error neither creates nor resets the baseline; only an explicitly false condition ends the baseline window. Errors appear in the tester and logs.

### Variations

A variation measures the current numeric value minus the baseline, rather than comparing the absolute value. The baseline starts when the Jinja condition becomes true and belongs to that condition window. This can detect heating without a sufficient temperature rise or insufficient progress during a running cycle.

### Transitions and automatic resolution

A transition requires an observed edge. Initial discovery, reloads and startup do not infer one; unknown/unavailable states and missing attributes cannot start a hold.

With `duration` greater than zero, the arrival value must remain unchanged for the entire delay. Leaving it cancels the hold and requires a new matching edge; unrelated attribute changes do not restart it.

After activation, the alert expires after `auto_resolve` seconds (**600 by default**, minimum 1). Leaving the arrival value after activation does not resolve it. Another confirmed transition extends the same alert's deadline and preserves its acknowledgement.

Automatic expiration is recorded in history but sends **no recovery notification**. New-alert notifications and reminders still apply. Unconfirmed holds do not survive a restart or monitoring pause; active/acknowledged expiration deadlines survive restarts. After a pause, a new activation requires a fresh edge.

## YAML editing and compatibility

Switch between the visual editor and YAML from the rule editor's menu. Unsaved changes are preserved when switching; invalid content must be corrected before saving. Closing a modified editor asks for confirmation. Desktop editors can be resized and adapt to mobile screens.

Use the canonical sources in the table above for new YAML. Imports migrate earlier source names: `state`/`attribute` to `value`, variation names to `value_variation`, transition names to `value_transition`, and `none` to `jinja`.

Rules can also opt into [flapping detection](configuration.md#flapping-and-instability) when repeated short anomalies matter even though they do not last long enough to become ordinary alerts.

## Generate rules from blueprints

In **Custom rules → Generate rules**, select built-in blueprints and choose **Create selected rules**. The generator shows matching entity counts and explains unavailable choices. CPU/memory usage and CPU temperature cover System Monitor and compatible device sensors, including UniFi, with matching units and names; Supervisor apps/add-ons are excluded. Disk usage remains System Monitor only. Enable the relevant sensors first.

Each selection creates one editable rule containing up to 50 compatible entities. The selected rules are created together or not at all. New rules remain managed by their blueprint. The editor allows changing the name, enabled state (in YAML or the rules table), presentation level, labels, comparison value (when applicable) and duration. The menu offers YAML editing of those settings only. The YAML always keeps `enabled` at the top level. Only explicit customizations appear under `override:`: `name`, `level`, `label_ids`, `duration` and, when applicable, `value`. Unmodified rules have no `override` block. Removing a field from that block restores its inherited blueprint value; removing the whole block restores all inherited settings while preserving `enabled`. Returning to a default in the visual editor also clears its override. Legacy YAML with top-level fields remains accepted as a partial edit. Blueprint-owned conditions and templates stay hidden, and managed rules cannot be duplicated. **Test** evaluates the effective rule, including its blueprint condition. **Take control** detaches it for full manual editing.

Opening the rules tab checks for proposed blueprint updates without automatic synchronization or periodic scanning. **Review / Update** shows the proposed entity selection: checked means monitor, unchecked means exclude from this rule and future proposals. Keep at least one entity selected, or disable the rule to stop monitoring. Click **Apply selected changes** to save the reviewed selection directly. A success message in the rule drawer confirms that the changes were saved. Renaming keeps the blueprint origin. Regenerating an existing rule requires confirmation, overwrites customizations with defaults and currently discovered entities, and preserves its identifier.

See the [blueprint documentation index](blueprints/README.md) for requirements, discovery, defaults and limitations, including Home Assistant backup/update checks. The [contributor guide](rule-blueprints.md) describes the blueprint YAML format.

## Examples

Replace the entity IDs with your own and paste an example into a rule's YAML editor. Use **Test** before saving to check the selected entities and template output.

### High power consumption for two hours

This rule alerts when a fridge's power consumption stays above 200 W for two hours. Select a sensor whose unit is watts.

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

### Heating without warming the room

The baseline starts when the thermostat reports `hvac_action: heating`. The rule alerts after two hours if the temperature has risen by less than 0.2 °C. In the message, `value` is the measured variation. The selected climate entity must expose these attributes.

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

### Bayrol messages with expected states filtered out

The comparison examines the keys in the `data` array; the Jinja condition also requires flow to be present. Adapt the allowed keys to your equipment.

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

### A completed cycle visible for ten minutes

A real change from `running` to `finished` activates this alert immediately and keeps it visible for ten minutes. Adapt both values to the actual states reported by the appliance.

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
