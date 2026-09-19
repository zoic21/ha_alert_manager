# Custom rules

[Documentation](user-guide.md) · [Configuration](configuration.md) · [Coherence](coherence.md) · [Dashboard and history](dashboard-and-history.md)

Custom rules monitor situations specific to your installation: a fridge drawing too much power, heating that does not warm a room, a stale sensor, an error message or a completed appliance cycle. Create them from **Custom rules** using the visual editor or YAML.

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
| Sequence | `value_sequence` | Recognize 2–20 ordered conditions on the same state or attribute before creating an alert. |
| Transition | `value_transition` | Observe a specific `from_value` → `to_value` change and resolve the resulting alert after a duration, when the arrival value is left, or when a value condition matches. |
| No change | `unchanged` | Detect an entity with no state or attribute change for the configured duration. |
| Jinja | `jinja` | Use a template as the complete rule condition. |

Value comparisons include equality, inequality, contains/not contains, above/below and between/outside a range. Text comparisons can use several values. Inactivity can concern the whole entity or only the selected state/attribute: choose the operation that matches the behavior you need to observe.

For Value, Variation, Transition and Sequence, an omitted or empty `attribute` targets the state; a populated `attribute` targets that attribute. Missing attributes never fall back to the state. Nested paths are supported; wildcard paths such as `data.*.key` are limited to regular comparisons.

### Delays, conditions and messages

Use `duration` to require a condition to persist before activation. Duration fields use Home Assistant's hours/minutes/seconds selector; YAML stores seconds. If an ordinary pending condition disappears before the deadline, it creates no resolved-history entry.

A Jinja condition can complement a comparison or supply the complete rule logic. A message can include the entity and measured value. Messages are frozen at activation by default; enable `update_message_when_active` to keep the message current while the alert is active.

A Jinja rendering error is indeterminate, **not a recovery**: it preserves existing alerts, pending deadlines and the last valid message. Relevant dependency changes retry evaluation. For variations, an error neither creates nor resets the baseline; only an explicitly false condition ends the baseline window. Errors appear in the tester and logs.

### Variations

A variation measures the current numeric value minus the baseline, rather than comparing the absolute value. The baseline starts when the Jinja condition becomes true and belongs to that condition window. This can detect heating without a sufficient temperature rise or insufficient progress during a running cycle.

### Transitions and automatic resolution

A transition requires an observed edge. Initial discovery, reloads and startup do not infer one; unknown/unavailable states and missing attributes cannot start a hold.

With `duration` greater than zero, the arrival value must remain unchanged for the entire delay. Leaving it cancels the hold and requires a new matching edge; unrelated attribute changes do not restart it.

Choose a resolution mode after activation:

- **After a duration** (`resolve_mode: duration`, the default): the alert expires after `auto_resolve` seconds (**600 by default**, minimum 1). Leaving the arrival value does not resolve it. Another confirmed transition extends the same alert's deadline and preserves its acknowledgement.
- **While the arrival value is maintained** (`resolve_mode: state`): the alert has no expiration deadline. A known value different from `to_value` resolves it through the normal lifecycle, including recovery notifications when enabled. Unknown/unavailable states and missing attributes preserve the active alert until a known value is observed. Unrelated attribute updates do not resolve it. This applies to both entity states and selected attributes.
- **When a value condition is true** (`resolve_mode: condition`): `resolve_condition` uses the same comparison operators as sequence steps (`above`, `below`, `between`, `outside`, `equals`, `not_equals`, `contains`, `not_contains`) on the same entity and attribute. For example, `resolve_condition: {operator: below, value: 10}` resolves below 10. There is no hold delay or expiration timer. Unknown/unavailable or invalid numeric values cannot resolve the alert. This test is independent of the trigger's Jinja condition.


Existing rules keep the duration mode. Active alerts retain their acknowledgement across restarts; the state mode rechecks the current value on restart or monitoring resume. Changing the resolution mode keeps the current episode and removes its deadline or starts the configured expiration duration from the change.

Automatic expiration is recorded in history but sends **no recovery notification**. New-alert notifications and reminders still apply. Unconfirmed holds do not survive a restart or monitoring pause; active/acknowledged expiration deadlines survive restarts. After a pause, a new activation requires a fresh edge.

### Ordered sequences

Choose **Sequence** to detect an ordered scenario, such as the end of an appliance cycle. Add or remove steps, enable or disable them individually, and reorder them by dragging their handle or using the keyboard (arrow keys, Home and End). Disabled steps are skipped; if every step is disabled, the sequence cannot trigger. Final-step resolution follows the last enabled step. The editor uses native HA selectors and stacks fields when the drawer is narrow.

Each of the **2–20 steps** compares the same selected scalar state or nested attribute, using the ordinary numeric/text operators. Wildcards and per-step entities or attributes are not supported. Each entity has independent progress; only one sequence per rule/entity can be in progress.

| Duration mode | When the step completes |
| --- | --- |
| `at_least` (default) | When the condition has remained continuously true for `duration` seconds. `0` completes immediately. Matching value changes do not restart the hold. |
| `less_than` | Only when a known value stops matching, and the completed hold is strictly shorter than `duration`. |
| `between` | Only when a known value stops matching, and the completed hold is between `duration` and `duration_max`, including both bounds. |

From the first step’s hold, the sequence appears in pending alerts with its progress and a countdown for the current hold or exit limit.

Completed steps remain completed while the engine waits for the next condition. Interrupting a minimum hold resets only that hold. Time before an earlier step completed is never reused. Unknown/unavailable states, missing attributes and invalid numeric values cancel the current hold without validating an exit.

`sequence_timeout` is optional (`0` = no limit). It starts when the first step begins progressing, even if that first hold is interrupted. Reaching this total deadline discards the progression; a later event can start a new sequence. The sequence must finish **before** the deadline. Minimum holds, bounded-hold limits and the total deadline use timers; there is no polling. Reaching a `less_than` limit or exceeding an inclusive `between` upper bound discards the entire progression and removes the pending alert immediately, without history or a recovery notification. A later attempt must complete the full sequence again.

A complete sequence creates a normal alert immediately (`duration: 0`) with normal labels, notifications, acknowledgement and history. Resolution has three modes: `duration` uses `auto_resolve` and the existing transition expiration behavior (no recovery notification for automatic expiration); `state` resolves when the last step comparison is false; `condition` uses the independent `resolve_condition` comparison described above. State/condition resolution uses the normal recovery lifecycle. A last-step exit resolves immediately if that exit also completed the sequence; the hold duration is not applied again. Unknown/unavailable or invalid numeric values preserve the alert. Remaining in the final condition cannot generate repeated occurrences: it must be left before a new complete sequence can rearm. The observation completing a sequence by leaving its final condition can also start the next cycle if it matches the first enabled step. New holds start at that observation, without reusing time from the previous cycle. A second completion during the same active episode refreshes its expiration and preserves acknowledgement.

Progress is transient: restart, reload, monitoring pause, rule disable/removal or incompatible edits discard unfinished steps. After startup reconciliation, the current value starts a fresh observation of the first enabled step, without reconstructing earlier steps or counting time while Home Assistant was stopped. Entities becoming available later can also start the first step. Restored active alerts are not retriggered by this initial observation. Active and acknowledged alerts continue to use normal persistence.

The **Test** result distinguishes the current comparison from observed progression. It shows the current step, completed holds, interrupted/invalid holds and the next deadline. It is a read-only snapshot; click **Test** again to refresh. Alert details and history retain a bounded summary of the steps and observed durations of the completed occurrence. Message templates are supported; sequence condition templates, branches, loops, exact-duration timing and actions between steps are deliberately excluded.

```yaml
name: Washing machine finished
entity_ids:
  - sensor.washing_machine_power
source: value_sequence
steps:
  - operator: above
    value: 100
    duration_mode: at_least
    duration: 300
  - operator: below
    value: 10
    duration_mode: at_least
    duration: 120
sequence_timeout: 21600
duration: 0
auto_resolve: 600
resolve_mode: duration
```

Steps use native collapsible panels: a collapsed step shows its comparison and hold duration. Expanding, reordering or collapsing a step preserves its fields; newly added steps open for editing.

Existing rules keep their resolution mode and require no migration.

## YAML editing and compatibility

Switch between the visual editor and YAML from the rule editor's menu. Unsaved changes are preserved when switching; invalid content must be corrected before saving. Closing a modified editor asks for confirmation. Desktop editors can be resized and adapt to mobile screens.

Use the canonical sources in the table above for new YAML. Imports migrate earlier source names: `state`/`attribute` to `value`, variation names to `value_variation`, transition names to `value_transition`, and `none` to `jinja`.

Rules can also opt into [flapping detection](configuration.md#flapping-and-instability) when repeated short anomalies matter even though they do not last long enough to become ordinary alerts.

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
