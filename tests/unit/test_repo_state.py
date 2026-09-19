from __future__ import annotations

import pytest

from github_org_sync.models.repo_state import RepoState


@pytest.mark.unit
def test_repo_state_missing() -> None:
    state = RepoState(exists=False, is_git_repo=False)
    assert state.primary_status == "MISSING"
    assert not state.is_clean


@pytest.mark.unit
def test_repo_state_not_git_repo() -> None:
    state = RepoState(exists=True, is_git_repo=False)
    assert state.primary_status == "NOT_A_REPOSITORY"
    assert not state.is_clean


@pytest.mark.unit
def test_repo_state_wrong_remote() -> None:
    state = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/other/repo.git",
        remote_matches=False,
    )
    assert state.primary_status == "WRONG_REMOTE"
    assert not state.is_clean


@pytest.mark.unit
def test_repo_state_detached_head() -> None:
    state = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        detached_head=True,
    )
    assert state.primary_status == "DETACHED_HEAD"
    assert not state.is_clean


@pytest.mark.unit
def test_repo_state_no_upstream() -> None:
    state = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        branch="feature-x",
        upstream=None,
    )
    assert state.primary_status == "NO_UPSTREAM"


@pytest.mark.unit
def test_repo_state_has_conflicts() -> None:
    state = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        branch="main",
        upstream="origin/main",
        has_conflicts=True,
        conflict_files=("file1.txt", "file2.txt"),
    )
    assert state.primary_status == "CONFLICT"
    assert len(state.conflict_files) == 2


@pytest.mark.unit
def test_repo_state_multidimensional_dirty_ahead_behind() -> None:
    # Critical requirement: multi-dimensional status preserves orthogonal dimensions
    state = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        branch="main",
        upstream="origin/main",
        dirty=True,
        dirty_files_count=3,
        ahead=2,
        behind=5,
    )
    # Primary classification marks it DIRTY because worktree has uncommitted changes
    assert state.primary_status == "DIRTY"
    # But all orthogonal dimensions are preserved without data loss
    assert state.dirty is True
    assert state.dirty_files_count == 3
    assert state.ahead == 2
    assert state.behind == 5
    assert not state.is_clean


@pytest.mark.unit
def test_repo_state_diverged() -> None:
    state = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        branch="main",
        upstream="origin/main",
        ahead=3,
        behind=2,
    )
    assert state.primary_status == "DIVERGED"


@pytest.mark.unit
def test_repo_state_ahead_and_behind() -> None:
    state_ahead = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        branch="main",
        upstream="origin/main",
        ahead=4,
        behind=0,
    )
    assert state_ahead.primary_status == "AHEAD"

    state_behind = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        branch="main",
        upstream="origin/main",
        ahead=0,
        behind=4,
    )
    assert state_behind.primary_status == "BEHIND"


@pytest.mark.unit
def test_repo_state_clean_up_to_date() -> None:
    state = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        branch="main",
        upstream="origin/main",
        ahead=0,
        behind=0,
        dirty=False,
    )
    assert state.primary_status == "UP_TO_DATE"
    assert state.is_clean is True

    # JSON serialization
    serialized = state.to_dict()
    assert serialized["primary_status"] == "UP_TO_DATE"
    assert serialized["is_git_repo"] is True
    assert serialized["ahead"] == 0
    assert serialized["behind"] == 0
