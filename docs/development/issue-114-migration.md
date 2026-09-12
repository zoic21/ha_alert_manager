# Issue 114: migration boundaries and invariants

## Legacy fields and consumers

| Existing configuration | Actual behavior | Required conversion |
| --- | --- | --- |
| `global_delay` | `_delay_for` falls back to it when a state pack's delay is `None`. | Explicit delay for each inheriting pack, including disabled packs. |
| `entity_delays` | `_delay_for` checks it **before** pack delay, including execution errors. An explicit zero wins. | Sparse entity delay overrides on each affected state pack. |
| `automatic.execution_errors.delay` | Defaults to zero independently of `global_delay`. | Preserve zero; distinguish timer duration from failed execution count. |
| `automatic.battery.device_thresholds` | Battery detector resolves registry device membership and then the threshold. | Device override of `threshold`, without materializing a list of entities. |
| `automatic.execution_errors.failure_thresholds` | Per automation/script consecutive-cycle count used in both transition observation and trace evaluation. | Sparse entity failure-count overrides and an explicit pack count default. |
| `automatic.flapping.entity_overrides` | Complete entity settings; an entity disable blocks the source. | Sparse common overrides preserving explicitly stored fields. |
| `automatic.flapping.source_packs` | Selected sources; nonempty source numeric values currently beat entity numeric values. | Source-scoped entity values where needed to preserve the old effective result under the new priority. |
| Custom-rule `flapping_*` | Explicit opt-in; rule values currently win over entity values. | Preserve custom-rule independence and opt-in; do not apply automatic exclusion labels. |
| `excluded_entities`, `excluded_devices` | Cached automatic-only gates in `manager_templates`/`manager_runtime`. | Dedicated HA exclusion label; fail closed for missing/non-registry targets and assignment failures. |
| `excluded_labels` | Entity labels and device labels gate automatic monitoring. | Preserve selected labels and all existing registry label assignments. |
| `pending_display_delay` | Controls pending visibility, independently of anomaly duration. | Unchanged; do not remove with `global_delay`. |


## Canonical implementation

`pack_settings.resolve_settings` resolves validated sparse fields with dictionary
lookups and current registry membership. Entity beats device beats pack for each
field; flapping additionally uses selected source defaults and scoped exceptions.
Pack/global/label/eligibility gates remain hard gates. Runtime never converts old
fields. Registry bursts reconcile flapping memory and timers in the existing worker.

Storage shape migration and version-1 YAML parsing use the same pure conversions.
`async_migrate_exclusions` validates all targets and configuration before native HA
label assignments on the event loop. A narrow durability adapter flushes each
registry's native Store before committing removal of source exclusions. HA exposes
no public registry flush method: the adapter uses `_store` and `_data_to_save`,
and fails closed if these internals change. No blocking file I/O runs on the event
loop. Partial assignment is additive and deliberately retained for idempotent retry;
source exclusions are not removed on failure or cancellation.

Imports retain compatible records, history, acknowledgements and flapping evidence.
Administrative removals use existing history with `monitoring_disabled` attribution,
cancel detector/timer work, and discard queued sends/reminders after durable commit.
Pending delay edits derive deadlines from the existing observation start.

The legacy characterization cases, migration failure/retry tests, live configuration
regressions, existing execution/flapping/runtime tests and visual/YAML UI tests cover
the boundary behavior. The UI uses shared pack metadata for one drawer per pack,
with source contexts, sparse exceptions, native pickers and administrator-only actions.
