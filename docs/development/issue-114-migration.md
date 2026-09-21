# Issue 114: migration boundaries and invariants

This note describes the implemented 2.4 migration. For upgrade instructions, see
[Configuration](../configuration.md#migration-from-earlier-configurations).

## Legacy fields and consumers

| Legacy configuration | Pre-2.4 behavior | 2.4 conversion |
| --- | --- | --- |
| `global_delay` | `_delay_for` falls back to it when a state pack's delay is `None`. | Explicit delay for each inheriting pack, including disabled packs. |
| `entity_delays` | `_delay_for` checks it **before** pack delay, including execution errors. An explicit zero wins. | Sparse entity delay overrides on each affected state pack. |
| `automatic.execution_errors.delay` | Defaults to zero independently of `global_delay`. | Preserve zero; distinguish timer duration from failed execution count. |
| `automatic.battery.device_thresholds` | Battery detector resolves registry device membership and then the threshold. | Device override of `threshold`, without materializing a list of entities. |
| `automatic.execution_errors.failure_thresholds` | Per automation/script consecutive-cycle count used in both transition observation and trace evaluation. | Sparse entity failure-count overrides and an explicit pack count default. |
| `automatic.flapping.entity_overrides` | Complete entity settings; an entity disable blocks the source. | Sparse common overrides preserving explicitly stored fields. |
| `automatic.flapping.source_packs` | Selected sources; nonempty source numeric values beat entity numeric values. | Source-scoped entity values where needed to preserve the old effective result under the new priority. |
| Custom-rule `flapping_*` | Explicit opt-in; rule values win over entity values. | Preserve custom-rule independence and opt-in; do not apply automatic exclusion labels. |
| `excluded_entities`, `excluded_devices` | Cached automatic-only gates in `manager_templates`/`manager_runtime`. | Disabled exceptions in compatible packs; preserve eligible missing targets and existing per-target settings. |
| `excluded_labels` | Entity labels and device labels gate automatic monitoring. | Preserve selected labels and all existing registry label assignments. |
| `pending_display_delay` | Controls pending visibility, independently of anomaly duration. | Unchanged; do not remove with `global_delay`. |


## Canonical implementation

`pack_settings.resolve_settings` resolves validated sparse fields with dictionary
lookups and current registry membership. Entity beats device beats pack for each
field; flapping additionally uses selected source defaults and scoped exceptions.
Pack/global/label/eligibility gates remain hard gates. Runtime never converts old
fields. Registry bursts reconcile flapping memory and timers in the existing worker.

Storage shape migration and version-1 YAML parsing use the pure conversions in
`pack_migration.py`. `migrate_pack_config` materializes inherited delays and moves
legacy target settings; `migrate_flapping_precedence` preserves the old effective
source values. `migrate_exclusions` validates copied input, then adds
`enabled: false` to compatible pack exception maps and validates the result.
Existing target parameters are retained. The migration creates no labels, writes
no Home Assistant registries and needs no private registry Store access. Invalid
input leaves the original persisted/exported source recoverable.

Pack `exception_targets` and `supports_exception_target` define supported target
kinds and entity domains. Normalization also removes incompatible exceptions from
already migrated configurations and flapping source contexts. Execution errors
accept only automation/script entities; available updates accept only update
entities, and neither accepts device exceptions. Battery, connectivity and UniFi
restrict entity domains to sensor, binary_sensor and device_tracker respectively.
Missing targets remain if their kind/domain is compatible. Device classes and
integration ownership are runtime eligibility checks, not reasons for destructive
migration cleanup when registry metadata may be absent.

Storage records `pack_config_version: 2` after shape conversion, preventing legacy
flapping precedence from being reapplied. Unknown stored keys are pruned after
supported migrations; new API/YAML input still rejects unknown keys. Invalid known
values use the existing configuration-recovery path.

Imports retain compatible records, history, acknowledgements and flapping evidence.
Administrative removals use existing history with `monitoring_disabled` attribution,
cancel detector/timer work, and discard queued sends/reminders after durable commit.
Pending delay edits derive deadlines from the existing observation start.

The legacy characterization cases, exclusion/domain migration tests, live configuration
regressions, existing execution/flapping/runtime tests and visual/YAML UI tests cover
the boundary behavior. The UI uses shared pack metadata for one drawer per pack,
with source contexts, sparse exceptions, native pickers and administrator-only actions.

## Pack ownership after review

A module in `packs/` exports its own `PACK: AutomaticPack`. Discovery happens once
at import, with explicit `order` preserving the existing detector order. The
registry neither changes descriptors nor maintains a list of pack-specific fields.
`config_defaults.py` assembles defaults directly from each declaration, and the
configuration API exports its `target_filter`, supported exception targets and field
metadata. Pack-specific behavior remains declared by the pack.

For example, a state pack can declare:

```python
PACK = AutomaticPack(
    id="example",
    translation_key="example",
    prerequisites=(),
    applies=_applies,
    evaluate=_evaluate,
    default_delay=60,
    target_filter={"domain": "sensor"},
    config_fields=configuration_fields(
        PackConfigField("threshold", "number", "threshold", 15, minimum=0),
        PackConfigField("strict", "boolean", "strict", True),
        PackConfigField("message", "text", "message", "check"),
        PackConfigField("mode", "select", "mode", "fast", options=("fast", "slow")),
    ),
)
```

The shared helper is optional: it creates device/entity exception maps for exactly
those fields, plus the common enabled/delay controls. Packs may declare those
maps themselves when their schema differs, as flapping does for source contexts.
`uses_delay=False` omits the common timer setting. `default_enabled` and
`default_delay` belong to the pack; enabling or disabling monitoring does not
change the evaluator contract. New field labels use the usual FR/EN translations.

Boolean, numeric, text and choice fields use the same schema for backend
validation, visual drafts, YAML and field-by-field inheritance. Empty exception
inputs inherit; explicit false and zero remain overrides. Optional transactional
snapshot/restore callbacks also belong to the pack, without naming a detector in
the configuration API.

Review regressions load a fresh integration with only one additional pack file,
then exercise discovery, defaults, strict validation, inheritance and YAML round
trips. Existing exports may omit subsequently added packs. V1 migration remains
limited to the packs that actually existed in V1. A rename collision retains both
explicit exception entries, logs the conflict, and continues reconciling live
identities; it must not partially abort the registry worker.
