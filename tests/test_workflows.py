"""Security invariants for GitHub Actions workflows."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_third_party_actions_are_pinned_to_commit_shas() -> None:
    """Mutable action tags and branches must not enter privileged workflows."""
    workflows = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    )
    uses = re.findall(r"^\s*-?\s*uses:\s*([^\s#]+)", workflows, re.MULTILINE)

    assert uses
    assert all(re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", action) for action in uses)


def test_release_workflow_never_rewrites_an_existing_tag() -> None:
    """A published version is rejected instead of being silently replaced."""
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "git/ref/tags/$TAG" in workflow
    assert "already exists" in workflow
    assert "force=true" not in workflow
    assert "release edit" not in workflow
