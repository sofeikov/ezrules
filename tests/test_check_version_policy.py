"""Regression tests for the pull-request version classification policy."""

import subprocess
from pathlib import Path

import pytest

POLICY_SCRIPT = Path(__file__).parents[1] / ".github" / "scripts" / "check-version-policy.sh"


def _run_policy(base_version: str, current_version: str, changed_paths: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(POLICY_SCRIPT), base_version, current_version],
        input="\n".join(changed_paths),
        capture_output=True,
        check=False,
        text=True,
    )


def test_unchanged_version_allows_explicit_non_release_paths() -> None:
    result = _run_policy(
        "1.29.0",
        "1.29.0",
        [
            "tests/test_example.py",
            "docs/api-reference/manager-api.md",
            ".github/workflows/tests.yml",
            ".vscode/launch.json",
            ".codex/notes.md",
            ".omx/plans/test-plan.md",
            "AGENTS.md",
            "DOCUMENTATION_MAP.md",
            "README.md",
            "mkdocs.yml",
        ],
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "changed=false"
    assert result.stderr == ""


@pytest.mark.parametrize(
    "release_path",
    (
        "ezrules/backend/api_v2/main.py",
        "ezrules/frontend/src/app/app.component.ts",
        "alembic/versions/20260714_contract.py",
        "pyproject.toml",
        "docker-compose.yml",
        "scripts/start-agent-stack.sh",
    ),
)
def test_unchanged_version_rejects_unclassified_release_paths(release_path: str) -> None:
    result = _run_policy("1.29.0", "1.29.0", ["tests/test_example.py", release_path])

    assert result.returncode == 1
    assert result.stdout == ""
    assert release_path in result.stderr
    assert "Bump the version" in result.stderr


def test_changed_version_runs_downstream_pypi_check_for_any_path() -> None:
    result = _run_policy("1.29.0", "1.29.1", ["ezrules/backend/api_v2/main.py"])

    assert result.returncode == 0
    assert result.stdout.strip() == "changed=true"
    assert result.stderr == ""


@pytest.mark.parametrize(("base_version", "current_version"), (("", "1.29.1"), ("1.29.0", "")))
def test_missing_version_fails_closed(base_version: str, current_version: str) -> None:
    result = _run_policy(base_version, current_version, ["tests/test_example.py"])

    assert result.returncode == 2
    assert result.stdout == ""
    assert "Could not parse" in result.stderr
