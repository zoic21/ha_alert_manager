# Changelog

This changelog intentionally tracks only significant release-level changes in Alert Manager.
Development, beta and release-candidate iterations are not listed separately. Intermediate
implementation details, cosmetic adjustments, temporary experiments and changes reverted
before a stable release are intentionally omitted.

## 2.4 — Development prerelease

Current development build: **2.4.0-dev.38**, published on **2026-09-15**.
This is a prerelease for testing, not a stable release.

### Reliability fixes

- Clarify alert details: move the history link into the entity information card,
  show trigger values below detection and sequence values below step headings,
  show transition departure/arrival values, resolution reasons and the total
  duration in the timeline heading; hide redundant transition markers and order
  simultaneous events. Keep recorded units beside timeline values and use only
  the dialog scroll, with a neutral timeline header when expanded or clicked.

- Show sequence evidence immediately when opening active or historical alerts,
  and prevent delayed history responses from restoring stale pending details.

- Keep sequence details visible for active and historical alerts, with an explicit
  message when an older alert has no recorded steps. Present recorded starting
  values and timestamps as a compact timeline; hide expanded editor summaries
  and keep step headers on the normal card background.

- Restore the editable expiration duration when switching transition resolution
  modes, retaining its value across repeated changes.

- Remove unknown stored configuration fields during startup while preserving valid
  notification profiles, rules and pack settings; pack saves remain available.
- Prevent duplicate action icons when opening rule editors from alert details or
  refreshing other configuration surfaces.

### Major changes

- All alert details share one expandable chronological timeline with colored event
  markers, lifecycle dates, sequence steps and instability occurrences. Start and
  resolution notifications retain send times and profile names; reminders display
  a total and profiles without timestamps. The expanded state survives refreshes.

- Custom transition rules support ordered multi-step sequences with continuous hold
  durations, independent progress per entity, an optional overall timeout, and a
  compact step editor with collapsible summaries, per-step activation, drag-and-drop
  ordering, YAML and rule-tester support. Disabled steps are skipped, including for
  final-step resolution. Alert details retain step timestamps and observed values
  in an expandable section, including resolved history. Sequences appear in pending
  alerts after the first completed step, with progress instead of an activation
  countdown; abandoned or expired progress disappears without history or resolution
  notifications.
- Transitions and sequences can resolve after a duration, when the arrival value or
  final step no longer matches, or using a separate numeric/text comparison on the
  same entity and attribute. Unknown/unavailable values preserve active alerts.

- Custom transition rules can resolve after a duration or remain active until a known
  value leaves the arrival state, for both state and attribute transitions.

- Dashboard cards support separate mobile limits, deterministic sorting, multiple label
  inclusions/exclusions, optional alert age and optional device grouping.

- Reworked automatic monitoring around autonomous packs with explicit defaults,
  compact visual/YAML configuration and per-device/per-entity exceptions. Global label
  exclusions remain available, while previous direct exclusions are represented as disabled
  pack exceptions without changing existing monitoring behavior.
- Simplified Configuration with shared General settings, contextual access from automatic
  alerts, inherited pack/device values and independent page/drawer saves so incomplete drafts
  do not interfere with unrelated configuration changes.
- Simplified notification exceptions while preserving routing precedence and existing values,
  and added native Companion notification icons for new alerts, reminders and recoveries.
- Alert details display current Home Assistant labels; resolved history preserves labels,
  names, colors and icons as they were at resolution.
- Deleting a custom rule resolves its active alerts without sending recovery notifications,
  including already queued batches.
- Improved configuration and runtime compatibility: alert identities, acknowledgements,
  history and occurrence evidence are preserved across compatible edits/imports; disabling
  monitoring cancels affected timers and notifications without false recoveries; configuration
  exports now retain rule IDs using format version 2.

## 2.3.0 — September 14, 2026

### Major changes

- Added a native Alert Manager dashboard card with compact device grouping, label filtering
  and direct navigation to alert details or the filtered Overview. The card preserves known
  alerts while refreshing, handles startup with a compact status indicator and uses a
  responsive one-alert-per-row layout on narrow mobile screens.
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
- Redesigned alert details for a more compact desktop/mobile presentation, clearer timeline,
  retained flapping occurrences, direct History access and separate activation, reminder and
  resolution notification information.
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
