# Changelog

This changelog intentionally tracks only significant release-level changes in Alert Manager.
Development, beta and release-candidate iterations are not listed separately. Intermediate
implementation details, cosmetic adjustments, temporary experiments and changes reverted
before a stable release are intentionally omitted.

## 2.4 — Release candidate

Current release candidate: **2.4.0-rc.4**, dated **2026-09-19**.
This is a prerelease for testing, not a stable release.

### Reliability fixes

- Finish shared coherence scans against the current integration instance after
  a reload, including shutdown while reconciliation waits for its mutation lock.
- Publish Home Assistant lifecycle events only after configuration commits;
  failed transactions no longer trigger automations for rolled-back alerts.
- Track the allowed coherence sensor as a Jinja dependency so conditions and
  live messages react without waiting for their own source entity to change.
- Compare elapsed instants across daylight-saving changes for Jinja throttling,
  notification accounting, acknowledgement expiry and rename collision selection.
- Serialize history clearing and retention changes with late notification writes
  so removed occurrences cannot reappear after reload.
- Apply explicit message edits consistently through individual rule updates and
  full YAML imports, including messages normally frozen at activation.
- Persist long-lived pending alerts after five elapsed minutes across daylight-saving
  changes, avoiding premature writes in spring and repeated overdue callbacks in autumn.
- Recognize the coherence sensor by its immutable registry identity so custom rules
  and Jinja references remain valid after a rename and survive integration reloads.
- Reconcile incompatible rule runtime state consistently after edits and full YAML
  imports: discard obsolete transition deadlines, removed or disabled instances,
  and variation references whose attribute or template changed.
- Measure temporary acknowledgements and resumed pending deadlines in elapsed time
  across daylight-saving changes, including subsequent delay edits.
- Resolve Alert Manager's entity IDs through the Home Assistant registry so renamed
  sensors and switches keep the dashboard, panel and monitoring action working.
- Count execution errors confirmed by delayed trace rechecks toward flapping.
- Allow testing sequences with every step disabled and reevaluating a pending
  sequence during its first hold.
- Enrich restored rule metadata with one indexed lookup per record.
- Gate release publication on CI for the exact tagged commit and require committed
  frontend bundles to be reproducible; CI no longer pushes a separate build commit.

- Deliver recovery notifications for transitions and sequences resolved by state
  or condition; automatic expiration remains silent.
- Preserve pending countdowns when YAML imports pause or resume monitoring,
  using the same runtime cleanup and rollback behavior as the monitoring switch.
- Measure transition and sequence durations in elapsed time across daylight-saving
  changes, including an outgoing state event arriving before a hold timer.
- Preserve variation baselines and alert continuity when an entity is renamed.
- Index restored alerts by entity during startup reconciliation to avoid repeated
  full scans that block the Home Assistant event loop on large installations.
- Apply label edits immediately to in-progress sequences without resetting their
  completed steps or hold timers.

- Reuse the observation completing a sequence to start the next cycle when it
  also matches the first step, keeping the previous occurrence evidence separate
  and starting new hold timers from that observation.

- Discard a pending sequence as soon as a bounded step exceeds its allowed hold,
  using a deadline timer even when its value never changes. Clear all completed
  steps silently and preserve the inclusive upper bound for between durations.

- Initialize sequence observations from the current value after startup reconciliation,
  including entities first discovered later, without counting downtime or replaying
  restored active alerts. Show step countdowns inline after the observed value.

- Always show the complete timeline in pending, active and historical alert details,
  without expanding a panel or limiting the displayed events; use the dialog scroll.

- Use Home Assistant’s native user badge beside timeline timestamps: person photo
  when linked, initials otherwise, with the name accessible as a tooltip. Retain
  authenticated user ids for future events; never guess identities in older history.

- Replace timeline actor names with accessible icons beside timestamps; identify
  automation/script service origins when Home Assistant provides them and retain
  them through restarts and resolution. Unknown origins remain unlabelled.
- Show only the time for today throughout the interface, including timeline
  occurrences, tables, backups and coherence; retain full dates on other days.

- Show in-progress sequence holds from the first step, with mode-aware countdowns
  for minimum, maximum and bounded durations and an indication when a limit is exceeded.

- Round displayed durations to whole seconds, including sequence evidence,
  avoiding fractional-second artifacts and handling minute/hour boundaries.

- Clarify alert details: move the history link into the entity information card,
  show trigger values below detection and sequence values below step headings,
  show transition departure/arrival values, resolution reasons and the total
  duration in the timeline heading; hide redundant transition markers and order
  simultaneous events. Keep recorded units beside timeline values and use only
  the dialog scroll, with a neutral timeline heading.
  Place pending countdowns in the heading and future expiration/acknowledgement
  deadlines beneath their lifecycle events, without a separate footer or redundant
  sequence detection/progress entries.

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

- Retain the ten latest acknowledgement and unacknowledgement actions in each
  alert timeline, including automatic expiry. Preserve timestamps and actors across
  restarts and resolution, discard the oldest event at the limit, and roll back
  the timeline when persistence fails.

- All alert details share one always-visible chronological timeline with colored event
  markers, lifecycle dates, sequence steps and instability occurrences. Start and
  resolution notifications retain send times and profile names; reminders display
  a total and profiles without timestamps. The timeline remains visible during refreshes.

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
