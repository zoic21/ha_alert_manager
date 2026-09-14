# Built-in blueprint documentation

Alert Manager blueprints generate editable custom rules from compatible entities
in your Home Assistant installation. They are bundled with Alert Manager and are
used from its rule generator, not imported as Home Assistant automation blueprints.

## Blueprint index

| Category | Blueprint | Default alert condition |
| --- | --- | --- |
| System | [High CPU usage](system_cpu_usage.md) | Above 90% for 5 minutes |
| System | [High memory usage](system_memory_usage.md) | Above 90% for 5 minutes |
| System | [High CPU temperature](system_cpu_temperature.md) | Above 80 °C for 5 minutes |
| Storage | [High disk usage](storage_disk_usage.md) | Above 90% for 5 minutes |
| Home Assistant | [Backup alert](home_assistant_backup_age.md) | Last successful automatic backup older than 25 hours |
| Home Assistant | [Updates available](home_assistant_updates_available.md) | At least one update entity is on |

## Generate a rule

1. Sign in to Home Assistant as an administrator and open **Alert Manager**.
2. Open **Custom rules → Generate rules**.
3. Check the matching entity counts and availability messages. Enable any required
   sensors in Home Assistant, then use **Refresh** if needed.
4. Select the blueprints and click **Create selected rules**.
5. Open each generated rule to review its entities, threshold or template, delay,
   labels and message. Use the rule tester to check the current evaluation.

Each blueprint creates one rule containing all its matching entities. Ordinary
custom rules evaluate each entity independently and can produce multiple alerts.
The updates blueprint instead uses the Core update entity as the anchor for an
installation-wide condition; see its page for details.

Generated rules use the normal alert lifecycle and notification profiles. Configure
notification delivery separately; generating a rule does not create a profile.
Thresholds are starting points and can be changed in the rule editor.

## Discovery and regeneration

Discovery runs when opening or refreshing the generator and is checked again when
creating rules. Disabled entities and entities from disabled configuration entries
are excluded. An `unknown` or `unavailable` state does not by itself prevent
discovery, provided the required metadata is present. Matching is case-sensitive;
friendly names alone do not satisfy an entity-ID or registry criterion.

Generated rules do not synchronize automatically with newly added entities or later
blueprint changes. New rules remain managed by their blueprint. Use **Review /
Update** to choose which proposed entities to monitor (checked) or exclude
(unchecked), then apply the selection. Keep at least one entity selected; disable
the rule to stop monitoring. The editor and its YAML mode expose only customizable
settings. YAML keeps `enabled` separate and shows only explicit customizations under
`override:`. Removing a field from that block restores the inherited blueprint value.
**Test** evaluates the effective blueprint rule. **Take control** detaches
it for full manual editing. You can also select the blueprint again to regenerate it. After confirmation, regeneration **overwrites the existing rule's
customizations** with the current blueprint defaults and discovered entities,
while preserving the rule identifier.

The generator recognizes existing generated rules even after renaming them. An
equivalent manually created rule prevents duplicate creation. Managed rules cannot be duplicated. After taking control, duplication creates an
independent copy without blueprint provenance.

## When a blueprint is unavailable

| Message or situation | What to check |
| --- | --- |
| Required integration not configured | Set up the integration required by the blueprint. |
| No compatible enabled entity found | Check the integration, enabled state, registry identity, entity-ID patterns and units documented on the blueprint page. |
| More than 50 matching entities | The generator cannot split or truncate the selection. Create custom rules with smaller entity lists instead. |
| A matching rule already exists | Review the existing equivalent custom rule. |
| Multiple rules use this blueprint | Resolve duplicate provenance before regenerating. |
| Invalid or deprecated blueprint | It cannot be used for new generation; existing generated rules remain independent of its source file. |

The integration supports at most 500 custom rules. A batch is created together or
not at all; if discovery changes before creation, refresh the generator and retry.

For the YAML format and instructions for adding recipes, see the
[blueprint contributor guide](../rule-blueprints.md).
