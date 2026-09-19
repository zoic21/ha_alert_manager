"""Security invariants for GitHub Actions workflows."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_third_party_actions_are_pinned_to_commit_shas() -> None:
    """Mutable action tags and branches must not enter privileged workflows."""
    workflows = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    )
    uses = re.findall(r"^\s*-?\s*uses:\s*([^\s#]+)", workflows, re.MULTILINE)

    assert uses
    for action in uses:
        if action == "./.github/workflows/ci.yml":
            # Local reusable workflows execute from the caller's exact commit.
            assert (ROOT / action).is_file()
        else:
            assert re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", action)


def test_release_requires_validation_without_mutating_the_commit() -> None:
    """The published SHA must contain the same bundles that passed all CI gates."""
    directory = ROOT / ".github" / "workflows"
    ci = yaml.load((directory / "ci.yml").read_text(), Loader=yaml.BaseLoader)
    release = yaml.load((directory / "release.yml").read_text(), Loader=yaml.BaseLoader)
    assert "workflow_call" in ci["on"]
    assert release["jobs"]["validate"]["uses"] == "./.github/workflows/ci.yml"
    assert release["jobs"]["release"]["needs"] == "validate"
    frontend = ci["jobs"]["frontend"]
    assert frontend.get("permissions", ci["permissions"])["contents"] == "read"
    checks = [
        step
        for step in frontend["steps"]
        if "git diff --exit-code" in step.get("run", "")
    ]
    assert len(checks) == 1 and "if" not in checks[0]
    assert all("git push" not in step.get("run", "") for step in frontend["steps"])


def test_release_workflow_never_rewrites_an_existing_tag() -> None:
    """A published version is rejected instead of being silently replaced."""
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "git/ref/tags/$TAG" in workflow
    assert "already exists" in workflow
    assert "force=true" not in workflow
    assert "release edit" not in workflow
