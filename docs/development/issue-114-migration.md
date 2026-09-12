# Issue 114: migration inventory and implementation status

This draft does **not implement issue 114**. It captures the old effective
precedence and provides a pure prospective resolver. The resolver is deliberately
not connected to monitoring until the canonical validator, migration and lifecycle
changes can be delivered together. Do not merge or close #114 on this basis.

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

`tests/test_pack_configuration_legacy.py` captures the old delay and flapping
precedence so conversion tests can retain those examples. Existing battery,
execution-cycle, monitoring and flapping tests also remain unchanged.

## Existing boundaries that must be updated together

- `storage.AlertManagerStore._async_migrate_func` and
  `AlertManagerStorage._migrate_config`: load/migrate before startup reconciliation;
  preserve the original store and enter configuration recovery on failure.
- `validation.validate_config` and `validate_config_update`: one canonical sparse
  schema, duplicate/unknown-field rejection, strict durations and scope validation.
- `yaml_io`: versioned complete import/export and per-drawer validation must use
  the same validator. YAML parsing runs in the executor; HA registry calls must
  remain on the event loop.
- `manager_api.async_import_config`: the current import transaction **clears live
  records and history**. Do not reuse that behavior for the automatic 2.4 storage
  migration. Its interaction with legacy backup restoration must be addressed
  explicitly before preserving migration-related IDs/history can be claimed.
- Registry label creation/assignment is not atomic with Alert Manager storage.
  Test interrupted retries and durability ordering; adding a label to a registry
  entry must not be assumed durable merely because the callback returned.
- Entity rename handling currently updates separate delay/flapping/exclusion
  structures. It must rename canonical overrides in every source scope and reject
  identity conflicts, while preserving orphaned exceptions for user recovery.
- `manager_runtime` currently can demote an active alert to pending and clear its
  acknowledgement when a longer delay is saved. The new configuration contract
  requires preserving active/acknowledged instances.
- Missing candidates currently follow normal resolution handling. Administrative
  disable/exclusion needs explicit history attribution, timer/detector cleanup,
  queued notification invalidation, and no recovery event. Reuse
  `NotificationRuntime.async_discard_alerts` after a successful transaction.
- Execution trace observers and evaluations both need the same effective settings;
  changing only candidate creation would leave failed-cycle counting inconsistent.
- Flapping source disable/exclusion must clear only affected automatic source
  memory and timers, without turning a configuration reevaluation into an occurrence.

## Prospective resolver

`pack_settings.resolve_settings` expects already validated canonical settings.
It performs dictionary lookups only, returns values and their origin, preserves
explicit zero/false and parent-equal overrides, and never mutates configuration.
The caller supplies current registry membership and enforces global switches,
labels and eligibility. A disabled pack cannot be enabled by a target exception.

Common target scopes are `device_overrides` and `entity_overrides`. For automatic
flapping, a selected `source_packs` entry can also contain those sparse maps.
Source-specific target fields beat corresponding common target fields; entity
fields beat device fields; device fields beat source defaults. Validation must
prevent nested maps or unsupported fields inside an individual target exception.
Custom rules must keep a separate source-policy boundary.

## Still required before this PR is ready

- Canonical descriptors, authoritative validation and all detector consumers.
- Idempotent load/import/restore conversion, including label failure/interruption
  tests and preservation of alerts, acknowledgements, evidence and history.
- Live reconciliation, execution-cycle state, flapping resources, notification
  queues/reminders and registry-change regression coverage.
- One compact pack row and one visual/YAML drawer, native selectors, effective
  inherited values/origins, restoring inheritance, source-specific editing,
  orphan visibility and relevant target filtering.
- Administrator-only contextual editing from applicable automatic alerts.
- French/English translations, user documentation and migration/changelog notes.
- Full final backend/frontend validation and desktop/mobile UI verification.
