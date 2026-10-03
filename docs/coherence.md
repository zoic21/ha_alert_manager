# Configuration coherence

[Documentation](user-guide.md) · [Custom rules](custom-rules.md) · [Configuration](configuration.md) · [Dashboard and history](dashboard-and-history.md)

**Coherence** finds configuration that still points to an entity or ZHA device that no longer exists. It is useful after renaming or removing entities, replacing equipment or reorganizing automations. It checks references, not whether equipment is currently online.

## Run a scan

Open **Coherence** and start an analysis. The results identify the missing reference and its source. When a matching Home Assistant editor or object is available, **Open** takes you there; a finding in a custom rule opens that rule's editor.

Reports are kept between restarts. Changing the configuration does not itself mean that a stored finding has been checked again: run another scan after correcting the reference.

When a missing entity appears in the retained rename history and its source can be
edited, the table shows its current **Target entity** and a **Correct** button.
Successive renames resolve to the current registry identity. Deleted entities,
read-only sources and sources outside the replacement workflow cannot be selected.

Use the table's selection control to check several correctable rows, then choose
**Correct selected rows**. The confirmation lists each old identifier and its target,
with the affected source and location. Only references on the selected lines are
included, through the same native Home Assistant APIs or YAML replacement workflow
described below. After a successful correction, a new scan refreshes the findings.
Follow the reload or ESPHome installation instructions shown in the result.

## What is checked

| Source | Coverage |
| --- | --- |
| Automations and scripts | Static entity references, including supported template references. |
| Dashboards and templates | Static references found by the configuration scanner. |
| ESPHome | References in the scanned configuration when ESPHome scanning is enabled. |
| Custom rules | Selected entities and static references in Jinja conditions/messages, including disabled rules. |
| ZHA event triggers | Static `device_ieee` references in `zha_event` triggers and script/automation `wait_for_trigger` steps. |

Custom rules are checked from an in-memory snapshot and do not increase the scanned-file count. Dynamic references and plain message text are skipped: the scanner does not try to execute a template to guess every entity it might use.

This is a reference check, **not a full configuration validator**. A report without findings does not prove that every automation works or that every dynamically constructed reference is valid.

### ZHA device checks

When ZHA is fully loaded, static IEEE addresses are compared against Home Assistant's **ZHA device registry**. Modern and legacy trigger syntax are supported.

This checks registered devices, **not current availability or radio-network membership**. Disabled devices, remotes without entities and stale registered devices still count as present. Devices registered only with another Zigbee integration do not satisfy a ZHA reference.

Templates, blueprint inputs and malformed IEEE values are skipped; blueprints are not expanded. If ZHA is absent, its check is not applicable. Incomplete setup or unavailable metadata produces a skipped check, not a list of missing devices.

## Scheduling and exclusions

In **Configuration → Coherence analysis**, choose manual-only analysis or a **daily, weekly or monthly** schedule. ESPHome scanning can be disabled independently.

ESPHome's generated `.esphome` directories are excluded from scans and reference replacements. Device YAML files and other hidden configuration directories remain eligible for scanning.

The `bubble_card` directory and its subdirectories are excluded from file scanning to avoid false positives from module code and example entity references. Dashboard configurations outside that directory are still checked.

Use the reference exclusions for known or intentional references. An exact ZHA IEEE address can be excluded through the same mechanism. These exclusions concern coherence findings; they are separate from the labels and exclusions used by automatic alert monitoring.

## Keep an alert while findings remain

Enable **Create an alert for coherence issues** in **Configuration → Coherence analysis** to maintain one immediate alert while findings remain. The option is off by default and is available as `coherence_alert_enabled` in configuration YAML.

The alert uses the ordinary acknowledgement, history and notification profiles. Continuing findings update the same alert instead of creating one alert per missing reference.

Only a **complete check confirming recovery** resolves it. Failed or incomplete scans cannot clear an existing coherence alert. Enabling the option uses the latest report without starting a scan; disabling removes the alert and reminders without sending a recovery notification.

Findings are also exposed through `sensor.alert_manager_coherence_issue` for your own dashboards and automations.

## Deleted entities

The page provides the latest **50 deleted entities** still retained by Home Assistant, including deletion date and integration. This comes directly from Home Assistant's entity registry; Alert Manager does not maintain a separate deletion history. It can help explain a missing reference, but is not an unlimited record of everything ever deleted.

<img src="assets/screenshots/coherence.png" alt="Coherence page with the retained deleted-entity list">

## Entity rename history

**Entity renames**, in the adjacent button column, opens the latest **500 entity ID
changes**, newest first. Each row shows the previous ID, the new ID and the date of
the change in your Home Assistant locale. The information icon at the end of the
row opens Home Assistant's more-info window for the current entity, including when
it has been renamed again. The icon is disabled if the entity has been deleted.

Recording starts when this feature is installed and continues even when alert
monitoring is disabled. Earlier changes cannot be recovered. Changes to display
names alone are not recorded; this history tracks identifiers such as
`sensor.old_name` → `sensor.new_name`.

The history survives restarts in the separate
`.storage/alert_manager.entity_renames` file. Writes are grouped until **5 seconds
after the last rename**, with a final save on unload or shutdown. JSON encoding
and disk writes use Home Assistant's executor. No scan or polling is needed, and
the oldest entry is dropped automatically when the limit is reached. Access is
restricted to administrators, as with the rest of Coherence.

## Export all Home Assistant entities

Below **Deleted entities**, **Export entities (JSON)** downloads a private,
versioned JSON snapshot. It is available to administrators, even before the first
coherence scan. It does not run a scan or change any entity, alert or configuration.

The export combines the entity registry and current HA states, including entities
outside dashboards, disabled/hidden entities and entities without a unique ID.
Registered devices contain their entities; `entities_without_device` contains the
rest. Devices without entities are included. Deleted registry entries are excluded.

The root contains `schema_version`, `exported_at`, Home Assistant and Alert Manager
versions, counts, `devices` and `entities_without_device`. Each entity includes its
ID, name, integration platform, config-entry ID, unique ID, category, labels, explicit
and effective area, state, full attributes, and change/update/report timestamps.
Device metadata includes name, manufacturer, model, software/hardware versions,
area, labels and integrations. Devices, entities and labels are sorted by ID for
repeatable comparisons; attribute arrays retain their original order.

| Field | Meaning |
| --- | --- |
| `disabled` / `disabled_by` | Registry disable flag and reason (`user`, `integration`, `device`, `config_entry`, etc.). Available for both devices and registered entities. |
| `hidden` / `hidden_by` | Registry hiding flag and reason for entities. HA has no device-level hiding flag, so both are `null` for devices. |
| `registered` | Whether the entity exists in the entity registry. For state-only entities, registry flags and integration are `null` when unknown. |
| `state` / `attributes` | Raw HA state string and all published attributes, preserving JSON types. Both are `null` when HA has no state; actual `unknown` and `unavailable` strings are preserved. |
| `area` / `effective_area` | The entity's explicit area and the area after inheriting from its device. |

Disabled, hidden, unavailable and an ordinary `off` state are different concepts.
A device's disable flag is exported separately from each entity's own registry flag;
visibility is never guessed from whether its entities appear on a dashboard.

The snapshot reflects the **last values known to HA**, not a forced refresh of the
equipment. Capture happens before yielding to a worker; grouping and JSON encoding
run off the event loop. Nothing is polled or saved on the server. The filename and
export timestamp use UTC (`Z` or `+00:00`). No historical values, integration
credentials/configuration or import/restore mechanism are included. Published state
attributes themselves can contain locations, URLs or tokens: keep the file private.
If an attribute cannot be encoded as JSON, the export fails visibly rather than
silently dropping data or downloading an incomplete inventory.

## Replace an entity reference

**Entity replacement** is available to administrators before or after a coherence
scan. Select or type the previous and new entity IDs, then choose **Preview
replacement**. The new ID must exist in Home Assistant's states or entity registry;
the previous ID may belong to a deleted entity. This replaces references and does
not rename an entity or change its history.

The preview counts every physical occurrence, including multiple references on one
line. It shows automation, script, scene, template and dashboard/view names, with
the file, line and column underneath. Blueprint instances retain their automation
or script name. Uncheck any occurrence to leave it unchanged, then choose **Replace**.

| Source | Save and activation |
| --- | --- |
| Automations, scripts and scenes in the native editor files without YAML tags | The panel uses Home Assistant's authenticated configuration REST APIs. HA validates the objects and schedules their reload, as when saving in its editors. No restart is needed. |
| Dashboards managed in the UI | The integration reads the live dashboard configuration and uses its native save API, which updates storage and notifies the frontend. No direct `.storage` edit or restart. |
| YAML files containing tags, and other YAML including packages, external automation/script files and YAML dashboards | Selected text is replaced while preserving the remaining formatting, comments and HA tags. Secrets and includes are not resolved or sent to the browser. Reload the affected configuration; restart only for integrations without a reload action. |
| ESPHome | The existing ESPHome scan setting applies. Validate and install the updated configuration on the device through ESPHome. Editing YAML does not flash firmware. |

Home Assistant may stop running automation/script actions when reloading. Its own
editors also control the formatting of the YAML they save.

Replacement uses the coherence scanner's file exclusions and static-reference
traversal. Definition IDs/names, comments, documentation branches, dynamically constructed IDs and
blueprint definitions are skipped. Tagged scalars such as `!secret`, `!input` and
`!include` are not entity references and are left unchanged. Other HA storage files
and Alert Manager custom rules are outside this replacement workflow. Unreadable or invalid files are
reported as skipped in the preview.

Before saving, the backend rechecks that the target entity exists, selected files
still match the preview, and each candidate is valid YAML. A replacement that would
merge two entity mapping keys is rejected. After the native editor API calls, the
backend verifies the YAML they saved before committing other sources. External YAML
is also parsed after writing. If an operation fails, the workflow attempts to restore
every written YAML/dashboard source and attempted native-editor change, even if one
restoration fails. An incomplete restoration is reported separately from a successful
rollback. The backend finishes admitted writes or restorations even if the requesting
connection disconnects.

Keep the panel open until the operation completes: the native REST APIs do not
provide a transaction spanning several objects. If the backend's final reply is lost,
the panel reports an unconfirmed result and does not undo native objects that may
belong to a successfully committed batch. Check the affected sources and generate a
new preview before retrying after an incomplete or unconfirmed operation.

Run a new coherence scan after activation to update the retained findings.

## Working through findings

Open the affected automation, script, dashboard or custom rule and check whether the reference should be replaced or removed. Exclude it only when it is intentional. Run the scan again to validate the correction; an unresolved or incomplete check must not be mistaken for a confirmed recovery.
