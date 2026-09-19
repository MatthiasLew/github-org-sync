from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from github_org_sync.models.repo_state import RepoState
from github_org_sync.models.repository import Repository
from github_org_sync.services.git_service import GitService


@pytest.mark.unit
def test_stash_recovery_when_pull_fails(tmp_path: Path) -> None:
    """If pull fails after stashing, stash must be restored to preserve working tree changes."""
    service = GitService()
    repo_dir = tmp_path / "repo1"
    repo_dir.mkdir()
    repo = Repository("repo1", "https://github.com/myorg/repo1.git", "ssh://git@github.com/myorg/repo1.git")
    repo.local_path = repo_dir

    init_state = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/myorg/repo1.git",
        remote_matches=True,
        branch="main",
        upstream="origin/main",
        behind=1,
        dirty=True,
        dirty_files_count=2,
    )

    def mock_run_git(cwd: Path | None, args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        cmd = " ".join(args)
        if "fetch" in cmd:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        if "stash push" in cmd:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="Saved working directory", stderr="")
        if "pull --ff-only" in cmd:
            # Emulate network or merge failure
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr="fatal: not possible to fast-forward"
            )
        if "stash pop" in cmd:
            # Cleanly restore stash
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="Dropped refs/stash@{0}", stderr="")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    with (
        patch.object(service, "inspect_repo_state", return_value=init_state),
        patch.object(service, "_run_git", side_effect=mock_run_git),
    ):
        res = service.sync(repo, "myorg", preserve_local_changes=True, fetch_only=False)

    assert res.performed_action == "FAILED"
    assert res.after_status == "DIRTY"
    assert "Local uncommitted changes were safely restored" in (res.result or "")


@pytest.mark.unit
def test_stash_recovery_conflict_preserves_stash(tmp_path: Path) -> None:
    """If stash pop produces a conflict, changes must be preserved in stash and conflict reported."""
    service = GitService()
    repo_dir = tmp_path / "repo2"
    repo_dir.mkdir()
    repo = Repository("repo2", "https://github.com/myorg/repo2.git", "ssh://git@github.com/myorg/repo2.git")
    repo.local_path = repo_dir

    init_state = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/myorg/repo2.git",
        remote_matches=True,
        branch="main",
        upstream="origin/main",
        behind=1,
        dirty=True,
        dirty_files_count=1,
    )

    def mock_run_git(cwd: Path | None, args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        cmd = " ".join(args)
        if "fetch" in cmd:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        if "stash push" in cmd:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="Saved working directory", stderr="")
        if "pull --ff-only" in cmd:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="Fast-forwarded main", stderr="")
        if "stash pop" in cmd:
            # Stash pop conflict
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="CONFLICT (content)", stderr="error: could not restore"
            )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    with (
        patch.object(service, "inspect_repo_state", return_value=init_state),
        patch.object(service, "_run_git", side_effect=mock_run_git),
        patch.object(service, "get_conflict_files", return_value=["app.py"]),
    ):
        res = service.sync(repo, "myorg", preserve_local_changes=True, fetch_only=False)

    assert res.performed_action == "CONFLICT"
    assert res.after_status == "CONFLICT"
    assert res.conflict_files == ["app.py"]
    assert "preserved in git stash" in (res.result or "")
    assert "stash drop" in (res.result or "")
