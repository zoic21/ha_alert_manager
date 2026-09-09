# Alert Manager contributor instructions

## Scope

These instructions apply to the whole repository. A closer `AGENTS.md` may add
directory-specific rules; follow both, with the closest file taking precedence.

Keep each change focused on the requested behavior. Do not perform unrelated
cleanup, change versions, edit the changelog, publish releases, or relax tests
unless the task explicitly requires it.

## Product invariants

- Alert Manager is a single-entry Home Assistant integration. Authenticated users
  may read the dashboard card, Overview and History. Configuration, other tabs and
  every mutation (including acknowledgement) require an administrator. Internal HA
  calls without a user context remain supported.
- Detection is event driven. Prefer state, registry, dispatcher, and config-entry
  listeners; use timers only for real deadlines. Do not add broad periodic polling.
- One anomaly has one stable alert instance. Custom rules create an independent
  instance per entity. Do not create one Home Assistant entity per alert.
- Preserve the established pending, active, acknowledged, resolved, and history
  behavior. A pending condition that disappears must not enter history.
- Acknowledged alerts remain visible but do not count as active alerts.
- Disabling monitoring freezes pending timers and exposes zero alert counts; resuming
  monitoring must evaluate current state without manufacturing duplicate events.
- Keep existing entity IDs, event names, action names, WebSocket message types, YAML
  fields, stored data, and public payloads backward compatible unless a migration is
  explicitly part of the task.
- Keep recorder-facing state attributes bounded. Do not restore unbounded alert data
  or duplicate information that is already represented by the state.
- User-visible text must be translated in both French and English. Do not hard-code
  interface strings in Python or JavaScript.
- Treat configuration, YAML imports, templates, and WebSocket payloads as untrusted.
  Validate on the backend and enforce read-only versus administrator access on the server.

## Architecture

### Backend

Paths in this table are relative to `custom_components/alert_manager/`.

| Area | Responsibility |
| --- | --- |
| `__init__.py`, `config_flow.py` | Single-entry integration setup, platform/service/WebSocket registration, panel registration, and unload delegation. |
| `manager.py` | `AlertManager` composition root: owns configuration, records, indexes, locks, listeners, stores, and notification components; coordinates setup and shutdown. |
| `manager_api.py` | Public queries, rule testing, YAML entry points, acknowledgement and reevaluation actions, and serialized configuration/runtime mutations with rollback. |
| `manager_runtime.py` | Startup reconciliation, event and registry routing, coalesced entity evaluation, variation/inactivity tracking, automatic pack selection, candidate construction, and occurrence-batch dispatch. |
| `manager_transitions.py` | Indexed custom state/attribute edges, unpersisted hold observations and confirmed repetitions; reuses alert records and lifecycle timers for automatic expiration. |
| `manager_state.py` | Alert transitions, acknowledgement/expiry timers, pending visibility, persistence scheduling, history archiving, notification delivery facts, lifecycle events, and public snapshots. |
| `manager_templates.py` | Jinja conditions/messages and dependency tracking, rule/configuration indexes and metadata, and source validation preventing self-monitoring. |
| `manager_recovery.py` | Invalid-configuration recovery mode, backup scheduling/listing/downloads, and explicit restoration through the manager's import path. |
| `runtime_phase.py` | Explicit startup, grace, reconciliation, running, and stopping phases that gate runtime evaluation and mutations. |
| `transactions.py` | Cancellation-safe admitted operations, startup reconciliation snapshots, and deterministic identity/collision handling during entity renames. |
| `models.py` | Rule, alert and history models; pure comparison and lifecycle helpers; serialization of model data. |
| `rule_evaluation.py` | Shared rule/entity evaluator and diagnostic result used by live detection and the rule tester; owns no runtime state. |
| `history_statistics.py` | Pure on-demand recurrence aggregation of retained resolved history, run in the executor when requested from History. No runtime counters or additional storage. |
| `statistics.py` | Shared in-memory diagnostics: 24 UTC hourly aggregate buckets for synchronous custom-rule evaluation, committed alert transitions, and profile sends; never persisted. |
| `notifications.py` | Profile validation, label filters and ordered exception policies, plus native notify delivery and profile testing. |
| `notification_runtime.py` | Lifecycle-event routing into profile batches, reminders, label cache, grouped messages/links, delivery accounting, and its own persisted reminder state. Defers configuration-generated notifications until commit. |
| `packs/base.py`, `packs/__init__.py` | Shared pack contracts, configuration metadata, pack registry, and occurrence-consumer registration. |
| `packs/unavailable.py`, `packs/connectivity.py`, `packs/battery.py`, `packs/unifi.py` | Isolated automatic state detectors using the shared pack contract. |
| `packs/execution_errors.py` | Automation/script execution-error detection from execution transitions and trace results. |
| `packs/flapping.py` | Occurrence-driven instability detection and recovery deadlines; consumes source occurrence batches rather than polling entity states. |
| `validation.py`, `yaml_io.py` | Authoritative configuration/rule validation and strict versioned YAML interchange. Manager entry points offload YAML parsing to the executor. |
| `storage.py` | Separate configuration/runtime, history, and valid-configuration backup stores, with migrations and durability helpers. Notification runtime persistence remains in `notification_runtime.py`. |
| `websocket.py`, `services.py`, `permissions.py` | Thin permission-checked transport adapters and shared authorization for non-WebSocket actions; business logic stays in the manager. |
| `coherence_alert.py` | Aggregate coherence alert metadata and conservative report coverage; feeds the ordinary manager candidate lifecycle. |
| `coherence.py` | Explicit or scheduled reference scans, shared YAML traversal, exclusions, counts and reports, with filesystem work off the event loop. |
| `coherence_rules.py` | Immutable custom-rule snapshots and reference-bearing fields for the shared coherence scanner. |
| `coherence_checks/__init__.py`, `coherence_checks/zha.py` | Explicit integration-check registry and isolated ZHA check; snapshot HA metadata on the event loop; each check owns its traversal scopes and node selection in the existing scanner executor. |
| `sensor.py`, `switch.py`, `button.py` | Home Assistant entity adapters for counts/status, monitoring control, and actions. |
| `const.py`, `manifest.json` | Shared constants/defaults, version/cache identity, and Home Assistant integration metadata. |
| `translations/en.json`, `translations/fr.json`, `services.yaml`, `icons.json` | English/French UI and condition text, service descriptions, and native entity icon metadata. |

### Frontend and tooling

See `frontend-src/AGENTS.md` for frontend implementation rules.

| Area | Responsibility |
| --- | --- |
| `frontend-src/alert-manager-panel.js` | Panel lifecycle, subscriptions, navigation/deep links, shared state, and orchestration. |
| `frontend-src/api/alert-manager-api.js` | Panel data loading/refresh coordination using `api/transport.js`, the single WebSocket boundary. |
| `frontend-src/dashboard/`, `frontend-src/api/dashboard.js` | Bundled dashboard card/editor and shared revision-driven alert loading. |
| `frontend-src/views/` | Overview, history, rules, coherence, and configuration rendering/actions. `automatic.js` supplies the automatic-pack section within Configuration. |
| `frontend-src/components/alert-table.js` | Shared live/history table, filtering, selection, grouping, and alert details/actions. |
| `frontend-src/components/rule-editor.js` | Visual/YAML rule editor, drafts, validation, and rule tester presentation. |
| `frontend-src/components/notification-profiles.js` | Notification profile editor, ordered label exceptions, draft handling, and test actions. |
| `frontend-src/components/configuration-drawer.js` | Shared drawer/bottom-sheet presentation, discard helpers, resize markup, added-row scrolling, and notices in the active surface. |
| `frontend-src/components/duration-field.js` | Native Home Assistant duration selectors and conversion to/from stored seconds. |
| `frontend-src/components/config-backups.js` | Backup list, download, and restore confirmation UI. |
| `frontend-src/utils/`, `frontend-src/styles/` | Shared escaping, formatting, translations, table preferences, constants, and responsive styles. |
| `scripts/build-frontend.mjs`, `scripts/lint-frontend.mjs` | Deterministic standalone bundle generation and frontend architecture/syntax checks. |
| `custom_components/alert_manager/frontend/alert-manager-panel.js` | Generated distribution bundle; never edit directly. |
| `tests/` | Python behavior/regression tests and Node frontend tests, including version consistency and bundle verification. |
| `.github/workflows/ci.yml`, `.github/workflows/release.yml` | CI validation and manifest-triggered immutable tag/release publication; see the release procedure below. |

### Runtime boundaries

- Home Assistant events enter the manager's indexed, coalesced evaluation path.
  Candidates pass through the shared state lifecycle; occurrence packs receive one
  batch after source evaluation, with a shared immutable alert-ID snapshot.
- Lifecycle signals feed `NotificationRuntime`, which resolves policies and groups
  deliveries; `NotificationManager` handles native notify calls. Delivery facts
  return to the manager for live/history records. Configuration transactions defer
  their notification events until successful commit.
- Configuration mutations acquire `_config_mutation_lock` before notification
  `_runtime_lock`. Callbacks awaited under the notification lock must never
  acquire the configuration lock; preserve the guard comment in
  `notification_runtime.py`.

A change to a public data shape normally requires coordinated updates to its model,
validation, storage migration, manager behavior, WebSocket serialization, frontend,
translations, and tests. Trace the complete path before editing.

## Implementation rules

- Search for an existing helper, constant, validator, serializer, or UI pattern before
  adding one. Maintain one source of truth for each rule or transformation.
- Do not copy near-identical logic across manager modules, packs, transports, or tests.
  Extract a narrowly named shared helper when the semantics are genuinely identical;
  do not create speculative abstractions for a single use.
- Keep transports thin and put behavior in the appropriate manager, model, validation,
  or storage layer. Keep pure state transitions free of Home Assistant side effects.
- Use Home Assistant async APIs. Never perform blocking filesystem or network work on
  the event loop. Register every listener and timer with a corresponding unload path.
- Serialize configuration mutations, validate before changing live state, and roll
  back in-memory state if persistence fails.
- Stored-data migrations must be idempotent, tolerate malformed legacy entries, and
  preserve valid user configuration.
- Avoid catching broad exceptions unless isolating a persistence or integration
  boundary; log enough context and leave state consistent.
- Add a regression test for each bug fix and focused tests for each behavior change.
  Never delete or weaken a meaningful assertion merely to make a change pass.
- Preserve the repository's existing style: typed Python, double quotes, 88 columns,
  concise docstrings, deterministic ordering, and no unnecessary dependencies.

## Validation

Install test dependencies with `python -m pip install -r requirements_test.txt`.

For Python or integration changes, run:

```sh
ruff check .
ruff format --check .
pytest -q
python -m compileall -q custom_components
```

For frontend changes, follow `frontend-src/AGENTS.md`. Before declaring a code change
complete, run every relevant command and report failures honestly. Documentation-only
changes need a careful diff review; CI remains authoritative.

## Release publication

Publish only when explicitly requested, from the branch named by the user. Pushing
changes to `main` or synchronizing it also requires an explicit request.

### Prepare the release

1. Fetch the target branch and tags, inspect the working tree and branch history,
   and check the latest GitHub releases. Preserve unrelated local changes. Choose
   an unused version and confirm that its `v<version>` tag does not already exist.
   Use `2.2.0-rc.N` for a release candidate, `2.2.0-beta.N` for a beta, and `2.2.0`
   for the stable release. Never remove the prerelease suffix unless stable
   publication was requested.
2. Update all four required files together:

   | File | Required change |
   | --- | --- |
   | `custom_components/alert_manager/manifest.json` | Set `version` to the new release version. This file triggers publication. |
   | `custom_components/alert_manager/const.py` | Set `INTEGRATION_VERSION` to exactly the same version. `FRONTEND_CACHE_VERSION` derives from it; preserve that relationship. Its existing extra suffix does not need a separate bump when `INTEGRATION_VERSION` changes. |
   | `package.json` | Set `version` to exactly the same version. |
   | `CHANGELOG.md` | Add a dated entry describing the actual changes and identify beta/RC versions as prereleases. |

   Do not update only the manifest and package: the Python constant is also the
   frontend cache key and is covered by a version-consistency regression test.
3. Run `npm run build` and include
   `custom_components/alert_manager/frontend/alert-manager-panel.js` if the
   generated bundle changes. Never edit this file manually. Update frontend
   sources, both translations, and documentation when the release's functional
   changes require them. README files describe current functionality; they do not
   need a release changelog or a version-only edit.

### Validate the final release contents

Run these checks **after all version edits and the frontend build**, not just
before bumping the version:

```sh
python -m pytest -q tests/test_models.py::test_backend_and_frontend_versions_stay_in_sync
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
python -m compileall -q custom_components
npm run lint:frontend
npm run test:frontend
git diff --check
```

Review the complete diff and commit the release contents together. A fresh frontend
build must reproduce the committed bundle without a diff. Do not push a release
with failing checks: publication is independent of CI and does not wait for it.

### Publish and verify

- Inspect `.github/workflows/release.yml` before pushing. Currently a push that
  changes the manifest on `main` or `release/2.2` automatically creates the tag
  `v<version>` at the pushed commit and a GitHub release with generated notes.
  Versions containing a hyphen are published with `prerelease: true`.
- Push the validated commit to the requested branch. Let the workflow create the
  tag and release; do not also create them manually.
- Verify the Release workflow, CI (Python, frontend, Home Assistant validation and
  HACS), the published tag's commit, and the release's draft/prerelease flags.
  Report failures honestly. Once a tag is published, never move or overwrite it;
  if a correction is needed, prepare and validate a new version.
- Synchronize `main` only when requested, preserving any independent commits. If
  both branches can be fast-forwarded to the same commit, verify that they match.
  With the current workflow, synchronizing a manifest change also triggers release
  publication on `main`; it refuses the already existing tag. Verify that this is
  the cause of that workflow failure and that the original release is correct.
  Do not overwrite the tag, invent another version solely for branch synchronization,
  or skip CI to hide the duplicate-publication failure.
