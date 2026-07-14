"""Regression tests for the pull-request version classification policy."""

import subprocess
from pathlib import Path

import pytest

POLICY_SCRIPT = Path(__file__).parents[1] / ".github" / "scripts" / "check-version-policy.sh"
CHANGED_FILES_SCRIPT = Path(__file__).parents[1] / ".github" / "scripts" / "list-pr-changes.sh"


def _run_policy(base_version: str, current_version: str, changed_paths: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(POLICY_SCRIPT), base_version, current_version],
        input="\n".join(changed_paths),
        capture_output=True,
        check=False,
        text=True,
    )


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def _commit_file(repo: Path, path: str, content: str, message: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    _git(repo, "add", path)
    _git(repo, "commit", "-m", message)


def _initialize_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Version Policy Test")
    _git(repo, "config", "user.email", "version-policy@example.com")
    _commit_file(repo, "README.md", "initial\n", "initial")


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


def test_pr_changes_use_merge_base_when_feature_branch_is_behind_main(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _initialize_repo(repo)
    _git(repo, "branch", "feature")

    _commit_file(repo, "ezrules/main_only.py", "released = True\n", "main release")
    base_sha = _git(repo, "rev-parse", "main")

    _git(repo, "checkout", "feature")
    _commit_file(repo, "docs/pr-only.md", "documentation\n", "docs only")
    head_sha = _git(repo, "rev-parse", "feature")

    changed = subprocess.run(
        ["bash", str(CHANGED_FILES_SCRIPT), base_sha, head_sha],
        cwd=repo,
        capture_output=True,
        check=True,
        text=True,
    )

    assert changed.stdout.splitlines() == ["docs/pr-only.md"]
    policy = _run_policy("1.29.0", "1.29.0", changed.stdout.splitlines())
    assert policy.returncode == 0
    assert policy.stdout.strip() == "changed=false"


def test_pr_changes_include_deleted_paths_without_git_quoting(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _initialize_repo(repo)
    _commit_file(repo, "ezrules/retiré.py", "retired = True\n", "add unicode path")
    _git(repo, "branch", "feature")
    base_sha = _git(repo, "rev-parse", "main")

    _git(repo, "checkout", "feature")
    (repo / "ezrules" / "retiré.py").unlink()
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", "remove unicode path")
    head_sha = _git(repo, "rev-parse", "feature")

    changed = subprocess.run(
        ["bash", str(CHANGED_FILES_SCRIPT), base_sha, head_sha],
        cwd=repo,
        capture_output=True,
        check=True,
        text=True,
    )

    assert changed.stdout.splitlines() == ["ezrules/retiré.py"]
