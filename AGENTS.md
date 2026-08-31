# Alert Manager contributor instructions

## Scope

These instructions apply to the whole repository. A closer `AGENTS.md` may add
directory-specific rules; follow both, with the closest file taking precedence.

Keep each change focused on the requested behavior. Do not perform unrelated
cleanup, change versions, edit the changelog, publish releases, or relax tests
unless the task explicitly requires it.

## Product invariants

- Alert Manager is a single-entry, admin-only Home Assistant integration.
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
  Validate on the backend and keep the panel restricted to administrators.

## Architecture

| Area | Responsibility |
| --- | --- |
| `custom_components/alert_manager/__init__.py` | Integration lifecycle, services, platforms, WebSocket registration, and panel registration. |
| `manager.py` | `AlertManager` composition root: owned state, listeners, setup, and unload. |
| `manager_api.py` | Public queries and serialized configuration mutations used by transports and entities. |
| `manager_recovery.py` | Valid configuration backups, recovery state, scheduling, downloads, and explicit restoration. |
| `manager_runtime.py` | Event routing, dependency-aware evaluation, automatic packs, and candidate construction. |
| `manager_state.py` | Alert lifecycle, timers, persistence scheduling, history, events, and public snapshots. |
| `manager_templates.py` | Jinja rendering, dependency tracking, rule indexing, and source protection. |
| `models.py` | Data models and pure alert state-machine behavior. |
| `validation.py` | Authoritative validation and normalization boundary. |
| `storage.py` | Versioned storage and idempotent migrations. |
| `websocket.py`, `services.py` | Thin Home Assistant transport adapters; business logic stays in the manager. |
| `packs/` | Isolated automatic detectors implementing the shared pack contract. |
| `coherence.py` | Explicit or low-frequency configuration scan, with file work off the event loop. |
| `sensor.py`, `switch.py`, `button.py` | Home Assistant entity adapters over manager state. |
| `frontend-src/` | Editable panel sources; see its local `AGENTS.md`. |
| `custom_components/alert_manager/frontend/` | Generated distribution bundle. Never edit it directly. |
| `tests/` | Python behavior tests and Node panel regression tests. |

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
