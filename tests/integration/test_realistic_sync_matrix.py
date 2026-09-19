from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from github_org_sync.cli import EXIT_ATTENTION, EXIT_SUCCESS, main
from github_org_sync.models.repo_state import RepoState
from github_org_sync.models.repository import Repository
from github_org_sync.models.sync_plan import SyncAction
from github_org_sync.services.planner import SyncPlanner


@pytest.fixture
def realistic_repository_matrix() -> dict[str, tuple[Repository, RepoState, SyncAction, str | None]]:
    """
    Complete state matrix fixtures covering:
    - MISSING
    - UP_TO_DATE
    - BEHIND
    - AHEAD
    - DIRTY (with preserve_local_changes)
    - DIVERGED
    - WRONG_REMOTE
    - DETACHED_HEAD
    """
    matrix: dict[str, tuple[Repository, RepoState, SyncAction, str | None]] = {
        # 1. MISSING
        "repo-missing": (
            Repository(
                "repo-missing", "https://github.com/myorg/repo-missing.git", "git@github.com:myorg/repo-missing.git"
            ),
            RepoState(exists=False, is_git_repo=False),
            SyncAction.CLONE,
            None,
        ),
        # 2. UP_TO_DATE
        "repo-uptodate": (
            Repository(
                "repo-uptodate", "https://github.com/myorg/repo-uptodate.git", "git@github.com:myorg/repo-uptodate.git"
            ),
            RepoState(
                exists=True,
                is_git_repo=True,
                remote_url="https://github.com/myorg/repo-uptodate.git",
                remote_matches=True,
                branch="main",
                upstream="origin/main",
                ahead=0,
                behind=0,
                dirty=False,
            ),
            SyncAction.NONE,
            None,
        ),
        # 3. BEHIND
        "repo-behind": (
            Repository(
                "repo-behind", "https://github.com/myorg/repo-behind.git", "git@github.com:myorg/repo-behind.git"
            ),
            RepoState(
                exists=True,
                is_git_repo=True,
                remote_url="https://github.com/myorg/repo-behind.git",
                remote_matches=True,
                branch="main",
                upstream="origin/main",
                ahead=0,
                behind=3,
                dirty=False,
            ),
            SyncAction.FAST_FORWARD,
            None,
        ),
        # 4. AHEAD
        "repo-ahead": (
            Repository("repo-ahead", "https://github.com/myorg/repo-ahead.git", "git@github.com:myorg/repo-ahead.git"),
            RepoState(
                exists=True,
                is_git_repo=True,
                remote_url="https://github.com/myorg/repo-ahead.git",
                remote_matches=True,
                branch="main",
                upstream="origin/main",
                ahead=2,
                behind=0,
                dirty=False,
            ),
            SyncAction.NONE,
            None,
        ),
        # 5. DIRTY (preserve_local_changes)
        "repo-dirty": (
            Repository("repo-dirty", "https://github.com/myorg/repo-dirty.git", "git@github.com:myorg/repo-dirty.git"),
            RepoState(
                exists=True,
                is_git_repo=True,
                remote_url="https://github.com/myorg/repo-dirty.git",
                remote_matches=True,
                branch="main",
                upstream="origin/main",
                ahead=0,
                behind=1,
                dirty=True,
                dirty_files_count=2,
            ),
            SyncAction.STASH_FF_RESTORE,
            None,
        ),
        # 6. DIVERGED
        "repo-diverged": (
            Repository(
                "repo-diverged", "https://github.com/myorg/repo-diverged.git", "git@github.com:myorg/repo-diverged.git"
            ),
            RepoState(
                exists=True,
                is_git_repo=True,
                remote_url="https://github.com/myorg/repo-diverged.git",
                remote_matches=True,
                branch="main",
                upstream="origin/main",
                ahead=2,
                behind=3,
                dirty=False,
            ),
            SyncAction.BLOCKED,
            "DIVERGED",
        ),
        # 7. WRONG_REMOTE
        "repo-wrongremote": (
            Repository(
                "repo-wrongremote",
                "https://github.com/myorg/repo-wrongremote.git",
                "git@github.com:myorg/repo-wrongremote.git",
            ),
            RepoState(
                exists=True,
                is_git_repo=True,
                remote_url="https://github.com/other-org/repo-wrongremote.git",
                remote_matches=False,
            ),
            SyncAction.BLOCKED,
            "WRONG_REMOTE",
        ),
        # 8. DETACHED_HEAD
        "repo-detached": (
            Repository(
                "repo-detached", "https://github.com/myorg/repo-detached.git", "git@github.com:myorg/repo-detached.git"
            ),
            RepoState(
                exists=True,
                is_git_repo=True,
                remote_url="https://github.com/myorg/repo-detached.git",
                remote_matches=True,
                detached_head=True,
            ),
            SyncAction.BLOCKED,
            "DETACHED_HEAD",
        ),
    }
    return matrix


@pytest.mark.integration
def test_realistic_plan_matrix(
    realistic_repository_matrix: dict[str, tuple[Repository, RepoState, SyncAction, str | None]],
    tmp_path: Path,
) -> None:
    """Validates that planning across the entire realistic state matrix produces expected actions."""
    states = {name: item[1] for name, item in realistic_repository_matrix.items()}
    plan = SyncPlanner.create_plan(
        organization="myorg",
        workspace=str(tmp_path),
        states=states,
        options={"preserve_local_changes": True},
    )

    assert plan.total_count == 8
    # Diverged, Wrong Remote, and Detached HEAD must require attention
    assert plan.requires_attention_count == 3
    assert plan.blocked_count == 3

    for repo_plan in plan.plans:
        _, expected_state, expected_action, expected_blocked = realistic_repository_matrix[repo_plan.repo_name]
        assert repo_plan.action == expected_action, f"Mismatch for {repo_plan.repo_name}: got {repo_plan.action}"
        if expected_blocked:
            assert repo_plan.blocked_reason == expected_blocked
            assert repo_plan.requires_attention is True


@pytest.mark.integration
def test_cli_realistic_plan_and_sync_dry_run(
    realistic_repository_matrix: dict[str, tuple[Repository, RepoState, SyncAction, str | None]],
    tmp_path: Path,
    capsys: Any,
) -> None:
    """Tests CLI 'plan' and 'sync --dry-run' outputs with full structured JSON envelopes."""
    repos = [item[0] for item in realistic_repository_matrix.values()]
    state_map = {name: item[1] for name, item in realistic_repository_matrix.items()}

    def mock_inspect(path: Path, *args: Any, **kwargs: Any) -> RepoState:
        return state_map[path.name]

    with (
        patch("github_org_sync.cli.GitHubService") as mock_gh_cls,
        patch("github_org_sync.cli.GitService") as mock_git_cls,
    ):
        mock_gh = mock_gh_cls.return_value
        mock_gh.check_cli_installed.return_value = "gh 2.50.0"
        mock_gh.check_auth_status.return_value = "Logged in"
        mock_gh.list_repositories.return_value = repos

        mock_git = mock_git_cls.return_value
        mock_git.inspect_repo_state.side_effect = mock_inspect

        # 1. Test CLI plan
        rc_plan = main(["plan", "--org", "myorg", "--workspace", str(tmp_path), "--json"])
        assert rc_plan in (EXIT_SUCCESS, EXIT_ATTENTION)

        captured_plan = capsys.readouterr()
        plan_data = json.loads(captured_plan.out)
        assert plan_data["schema_version"] == "1.0"
        assert plan_data["tool_version"] == "1.10.0"
        assert plan_data["command"] == "plan"
        assert plan_data["data"]["total_repositories"] == 8
        assert plan_data["data"]["requires_attention_count"] == 3

        # 2. Test CLI sync --dry-run
        rc_sync = main(["sync", "--org", "myorg", "--workspace", str(tmp_path), "--dry-run", "--json"])
        assert rc_sync in (EXIT_SUCCESS, EXIT_ATTENTION)

        captured_sync = capsys.readouterr()
        sync_data = json.loads(captured_sync.out)
        assert sync_data["command"] == "sync"
        assert sync_data["data"]["dry_run"] is True
        results = sync_data["data"]["results"]
        assert len(results) == 8

        # Verify no mutations occurred on filesystem during dry run
        for name in realistic_repository_matrix:
            if name != "repo-missing":
                assert not (tmp_path / "repo-missing").exists()
