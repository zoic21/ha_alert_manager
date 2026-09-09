"""Explicit integration checks used by the single coherence traversal.

Each check exposes REFERENCE_TYPE, snapshot(hass) -> (identifiers, status), and
references(node) -> literal YAML nodes. Snapshot identifiers must be immutable,
normalized strings; None skips the check. Only snapshot may access live HA data.
The scanner owns exclusions, matching, counts, source context and persistence.
"""

from . import zha

CHECKS = (zha,)
