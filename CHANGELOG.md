# Changelog

This changelog intentionally tracks only significant release-level changes in Alert Manager.
Development, beta and release-candidate iterations are not listed separately. Intermediate
implementation details, cosmetic adjustments, temporary experiments and changes reverted
before a stable release are intentionally omitted.

## 2.4 — Unreleased

- Consolidated automatic monitoring into autonomous packs with one visual/YAML drawer,
  explicit defaults, and sparse device/entity exceptions with visible inheritance.
- Kept global automatic exclusions by label; migrate old direct exclusions to a dedicated
  Home Assistant label and preserve effective delays, thresholds and flapping precedence.
  Missing registry targets or failed writes stop conversion with recoverable source data.
- Added administrator-only contextual configuration from automatic alert details.
- Preserve compatible alert identities, acknowledgements, history and occurrence evidence
  during edits/imports. Disabled monitoring cancels affected notifications and timers
  without announcing recovery. Configuration exports now use version 2 and retain rule IDs.

## 2.3.0 — Release candidate

### Major changes

- Added a native Alert Manager dashboard card with compact device grouping, label filtering
  and direct navigation to alert details or the filtered Overview.
- Added transition alerts for short-lived state or attribute changes, with optional automatic
  resolution and no pending phase.
- Added History insights for 7- and 30-day periods, including recurrence, affected entities and
  devices, cumulative alert duration, packs, custom rules and associated notification profiles.
- Added lightweight in-memory 24-hour runtime statistics for Alert Manager activity and
  performance diagnostics.
- Added YAML editing for notification profiles and configuration sections while preserving the
  visual editors.
- Extended coherence analysis to Alert Manager custom rules and static ZHA device references,
  with an optional persistent alert while coherence issues remain.
- Added read-only access for non-administrators to the dashboard card, Overview, History and
  alert details. Configuration and all actions remain administrator-only.
- Redesigned alert details for a more compact desktop/mobile presentation, clearer timeline and
  separate activation, reminder and resolution notification information.
- Added the retained occurrence timestamps behind flapping alerts and direct access from an
  alert to its matching History entries.
- Simplified custom-rule operations by using the optional Attribute field to determine whether
  an operation targets the entity state or an attribute. Existing rules and active alerts are
  migrated automatically.

### Compatibility

- Removed the obsolete `sensor.alert_manager_device_main_active` sensor and
  `alert_manager_device_alert_started` event. Automations using them must migrate to built-in
  notification profiles or per-alert events.

## 2.2.0 — September 8, 2026

### Major changes

- Added notification profiles with multiple notify targets, batching, reminders and separate
  handling for new alerts and resolutions.
- Added configurable notification routing and exceptions using packs, custom rules and Home
  Assistant labels, with notification delivery information available in alert details.
- Added flapping / instability detection with configurable occurrence windows and recovery
  delay.
- Added a dry-run tester for custom rules and Home Assistant labels on custom rules.
- Added temporary alert acknowledgement, manual alert re-evaluation and bulk deletion from
  History.
- Consolidated automatic monitoring into Configuration and aligned duration controls and major
  configuration interactions with native Home Assistant components.
- Improved startup reconciliation, concurrent history archival and Jinja evaluation recovery.
- Reduced storage writes, unnecessary full evaluations and frontend refreshes, and moved YAML
  backup work off the Home Assistant event loop.

## 2.1.x — September 2026

### Major changes

- Added monitoring of automation and script execution failures using Home Assistant execution
  information rather than polling.
- Expanded custom-rule capabilities with additional value, variation, transition and time-based
  conditions while preserving existing rules and alert identifiers.
- Added configuration safety with automatic valid backups, manual restore support and user
  notification when configuration cannot be loaded safely.
- Added stronger startup stabilization and restoration handling so pending and restored alerts
  are reconciled after Home Assistant startup without creating unnecessary false alerts.
- Added runtime guardrails and indexing to keep rule evaluation bounded as configurations grow.
- Improved coherence analysis and configuration validation while keeping scans explicit and
  avoiding continuous global polling.

## 1.8.0 — August 28, 2026

### Major changes

- Hardened permissions and input validation following a security review.
- Optimized the state-change and snapshot hot paths to reduce work performed for each Home
  Assistant event.
- Serialized concurrent configuration mutations and strengthened runtime consistency.
- Simplified the internal runtime architecture without changing the alert lifecycle or existing
  configuration behavior.

## 1.7.x — August 26–27, 2026

### Major changes

- Reworked Overview and History around native Home Assistant data tables with search, filters,
  sorting, grouping, configurable columns and bulk selection.
- Added a responsive compact mobile presentation while keeping the desktop interface close to
  Home Assistant's native design.
- Expanded custom rules with optional Jinja conditions and Jinja messages using Home Assistant's
  template environment.
- Added per-device battery thresholds and richer automatic-pack configuration.
- Improved rule editing with native Home Assistant selectors and preserved user table
  preferences.
- Reduced unnecessary frontend rerenders and kept pending countdown updates targeted instead of
  refreshing complete tables.

## 1.6.x — August 26, 2026

### Major changes

- Added persistent alert History with resolved-alert metadata and configurable retention.
- Added the History page with filtering, alert details and maintenance actions.
- Preserved resolved alert information across Home Assistant restarts.

## 1.5.x — August 25–26, 2026

### Major changes

- Added the custom-rule foundation with persistent rules, runtime evaluation and WebSocket
  management.
- Added visual and YAML editing for custom rules.
- Added the dedicated Alert Manager service device and separated monitoring control from
  read-only alert diagnostics.
- Improved pause/resume behavior so pending alert timers remain consistent when monitoring is
  disabled or Home Assistant restarts.
- Added stricter validation preventing Alert Manager's own entities from being used as custom
  rule sources.
