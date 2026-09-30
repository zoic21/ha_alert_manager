"""Security invariants for GitHub Actions workflows."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
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


@pytest.mark.parametrize(
    ("version", "prerelease", "missing_notes"),
    [
        ("2.5.0", "false", False),
        ("2.5.0-beta.3", "true", False),
        ("2.5.1", "false", True),
    ],
)
def test_release_uses_user_notes_and_rejects_missing_stable_notes(
    tmp_path: Path, version: str, prerelease: str, missing_notes: bool
) -> None:
    """Execute publication with a fake gh; stable notes must match the version."""
    workflow = yaml.load(
        (ROOT / ".github" / "workflows" / "release.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    step = workflow["jobs"]["release"]["steps"][-1]
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 2.5.0 — September 30, 2026\n\n"
        "### New features\n\nUser-friendly release notes.\n\n"
        "## 2.4.0 — September 22, 2026\n\nPrevious release notes.\n"
    )
    bin_path = tmp_path / "bin"
    bin_path.mkdir()
    gh = bin_path / "gh"
    gh.write_text(
        '#!/bin/bash\nif [[ "$1" == "api" ]]; then exit 1; fi\n'
        'printf "%s\\n" "$@" > "$RELEASE_ARGS"\n'
    )
    gh.chmod(0o755)
    args_file = tmp_path / "args.txt"
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{bin_path}{os.pathsep}{os.environ['PATH']}",
            "VERSION": version,
            "TAG": f"v{version}",
            "PRERELEASE": prerelease,
            "RUNNER_TEMP": str(tmp_path),
            "RELEASE_ARGS": str(args_file),
            "GITHUB_REPOSITORY": "zoic21/ha_alert_manager",
            "GITHUB_SHA": "candidate-sha",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    if missing_notes:
        assert result.returncode != 0
        assert "Missing changelog entry" in result.stderr
        assert not args_file.exists()
        return

    assert result.returncode == 0, result.stderr
    args = args_file.read_text().splitlines()
    assert args[:3] == ["release", "create", f"v{version}"]
    if prerelease == "true":
        assert "--prerelease" in args
        assert "--generate-notes" in args
        assert "--notes-file" not in args
    else:
        assert "--prerelease" not in args
        assert "--generate-notes" not in args
        notes = Path(args[args.index("--notes-file") + 1]).read_text().strip()
        assert notes == "### New features\n\nUser-friendly release notes."
