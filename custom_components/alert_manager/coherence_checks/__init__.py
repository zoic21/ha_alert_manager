"""Explicit integration checks used by the single coherence traversal.

Each check exposes REFERENCE_TYPE and these functions:
- snapshot(hass) -> (identifiers, status), collected once on the event loop;
- child_scope(scope, key, source_kind, object_root=...) -> scope for a mapping child;
- references(node, scope) -> literal YAML nodes, inspected in the executor.

Scopes are check-owned strings (or None initially), passed unchanged through
sequence items. Only the check interprets them and decides which nodes matter.
Scopes belong to a traversal branch, never shared mutable scan state.

Snapshot identifiers must be immutable, normalized strings; None skips the check.
Only snapshot may access live HA data.
The scanner owns exclusions, matching, counts, source context and persistence.
"""

from . import zha

CHECKS = (zha,)
