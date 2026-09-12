# Built-in rule blueprints

A blueprint creates one ordinary custom rule containing all matching entities.
It does not run a detector or synchronize that rule afterward. Automatic packs
remain responsible for broad monitoring and specialized lifecycle behavior.

## Adding a recipe

1. Add an independent YAML file under
   `custom_components/alert_manager/blueprint/<category>/`.
2. Choose a permanent `blueprint_id`, `schema_version: 1`, and an independent
   positive `blueprint_version`. Increase the latter when changing the recipe.
3. Add its `name_key`, `description_key`, and category name to the `config_panel`
   sections of **both** `translations/en.json` and `translations/fr.json`.
4. Supply a normal `rule` payload without an ID or entity list. Its name is an
   English fallback; creation uses the HA language translation of `name_key`.
5. Add discovery tests against representative registry/state metadata.

See `blueprint/system/system_cpu_usage.yaml` for a complete example.
There are no per-blueprint Python branches or frontend definitions.

## Requirements and discovery

Optional `requirements.integrations` and `requirements.entity_domains` are lists
of prerequisites that must all exist. They distinguish a missing integration or
entity domain from an installation with no compatible enabled entities.

Discovery uses a small predicate tree:

```yaml
discovery:
  all:
    - field: integration
      equals: systemmonitor
    - field: domain
      equals: sensor
    - any:
        - field: translation_key
          equals: processor_use
        - field: unique_id
          equals: processor_use
    - field: unit_of_measurement
      equals: '%'
    - not:
        field: entity_id
        glob: sensor.excluded_*
```

`all`, `any` and `not` compose predicates. A leaf has one `field` and exactly one
operator: `equals`, `in` (list), `glob` (case-sensitive shell pattern), or `exists`
(boolean). Unsupported fields/operators and malformed trees fail closed. Trees
are limited to eight nesting levels and 32 children per composition.

Fields: `integration` (config-entry domain, falling back to registry platform),
`domain`, `entity_id`, `unique_id`, `original_name`, `translation_key`,
`device_class`, `unit_of_measurement`, and `attributes.<attribute_name>` (a direct
state attribute, not a dotted-path expression).

Prefer registry identity over entity names. Registry metadata takes precedence
for device class and units. State **values** never participate in discovery, so
`unknown` or `unavailable` alone does not remove an entity. Disabled registry
entities/config entries are excluded. Criteria that require state attributes can
only match when those attributes are present; do not use volatile attributes for
stable membership. The initial Celsius temperature recipe deliberately excludes
Fahrenheit sensors, avoiding an incorrect numeric threshold.

`snapshot_installation` copies metadata on the HA event loop, including only
state attributes referenced by valid catalog predicates. File loading and
`prepare_blueprints` run in the executor. `discover_blueprint` and `explain_match`
are pure and reusable without a panel or manager. The latter returns the outcome
of each predicate for diagnostics/tests; the UI only consumes summary statuses.
Discovery returns unique sorted entity IDs and only runs on opening/refreshing
the generator or explicitly creating rules. There are no listeners or timers.

The CPU usage, memory usage and CPU temperature recipes also accept explicit
entity-ID suffixes such as `_cpu_utilization`, `_cpu_usage`,
`_memory_utilization`, `_memory_usage`, `_cpu_temperature` and
`_temperature_du_processeur`, without requiring System Monitor. The original
System Monitor registry matching remains available for renamed sensors. Units
are still required, and `hassio` entities are excluded before name matching so
Supervisor apps/add-ons cannot be selected. Other renamed device sensors must
retain a supported suffix. Disk discovery remains System Monitor only.

## Creation and provenance

The server rechecks the selected IDs under the existing configuration mutation
lock. All candidates pass normal custom-rule, source and template validation
before any live change. Manual and batch creation share the same evaluation,
notification deferral, persistence and rollback path. A failure rejects the whole
batch, including stale selections or equivalent rules within the same batch.
Existing limits remain 50 entities per rule and 500 custom rules in total; entities
are never silently truncated or split.

Generated rules store:

```yaml
blueprint:
  id: system_cpu_usage
  version: 1
  managed: false
```

This is content-version provenance only, not a runtime dependency. It survives
renaming, editing, restarts and YAML export/import. The generator checks it before
creating duplicates. It also recognizes equivalent manually created rules,
ignoring presentation, labels, enablement and entity ordering. Duplicating a rule
in the editor creates an independent copy without blueprint provenance.

Existing generated rules do not need their source YAML file. `deprecated: true`
disables a recipe for new creation; optional `replaced_by` explains its successor.
Neither deprecation nor removal updates existing rules. Never reuse an ID for a
semantically different recipe. Managed rules and automatic reconciliation belong
to issue #112; adding them later can extend the structured provenance and reuse
this discovery implementation.

The generator WebSocket list/create commands require an administrator. The
frontend only submits blueprint IDs and never interprets discovery definitions.
