from __future__ import annotations

import pytest

from github_org_sync.models.repo_state import RepoState
from github_org_sync.models.sync_plan import SyncAction
from github_org_sync.services.planner import SyncPlanner


@pytest.mark.unit
def test_plan_missing_repo_clones() -> None:
    state = RepoState(exists=False, is_git_repo=False)
    plan = SyncPlanner.plan_repository("my-repo", state)
    assert plan.action == SyncAction.CLONE
    assert plan.action_summary == "CLONE"
    assert not plan.requires_attention
    assert any("CLONE" in s for s in plan.steps)
    assert any("ATOMIC MOVE" in s for s in plan.steps)


@pytest.mark.unit
def test_plan_not_git_repo_blocked() -> None:
    state = RepoState(exists=True, is_git_repo=False)
    plan = SyncPlanner.plan_repository("my-repo", state)
    assert plan.action == SyncAction.BLOCKED
    assert plan.requires_attention is True
    assert plan.blocked_reason == "NOT_A_REPOSITORY"


@pytest.mark.unit
def test_plan_wrong_remote_blocked() -> None:
    state = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/other-org/my-repo.git",
        remote_matches=False,
    )
    plan = SyncPlanner.plan_repository("my-repo", state)
    assert plan.action == SyncAction.BLOCKED
    assert plan.requires_attention is True
    assert plan.blocked_reason == "WRONG_REMOTE"


@pytest.mark.unit
def test_plan_diverged_blocked() -> None:
    state = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        branch="main",
        upstream="origin/main",
        ahead=2,
        behind=3,
    )
    plan = SyncPlanner.plan_repository("my-repo", state)
    assert plan.action == SyncAction.BLOCKED
    assert plan.requires_attention is True
    assert plan.blocked_reason == "DIVERGED"


@pytest.mark.unit
def test_plan_behind_clean_fast_forwards() -> None:
    state = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        branch="main",
        upstream="origin/main",
        ahead=0,
        behind=4,
        dirty=False,
    )
    plan = SyncPlanner.plan_repository("my-repo", state)
    assert plan.action == SyncAction.FAST_FORWARD
    assert not plan.requires_attention
    assert any("FAST-FORWARD main by 4 commits" in s for s in plan.steps)


@pytest.mark.unit
def test_plan_behind_dirty_autostash() -> None:
    state = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        branch="main",
        upstream="origin/main",
        ahead=0,
        behind=2,
        dirty=True,
        dirty_files_count=3,
    )
    plan = SyncPlanner.plan_repository("my-repo", state, options={"preserve_local_changes": True})
    assert plan.action == SyncAction.STASH_FF_RESTORE
    assert plan.action_summary == "STASH → FF → RESTORE"
    assert not plan.requires_attention
    assert any("STASH 3 changed files" in s for s in plan.steps)
    assert any("FAST-FORWARD main by 2 commits" in s for s in plan.steps)
    assert any("RESTORE stash" in s for s in plan.steps)


@pytest.mark.unit
def test_plan_behind_dirty_no_stash_blocks() -> None:
    state = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        branch="main",
        upstream="origin/main",
        ahead=0,
        behind=2,
        dirty=True,
        dirty_files_count=3,
    )
    plan = SyncPlanner.plan_repository("my-repo", state, options={"preserve_local_changes": False})
    assert plan.action == SyncAction.BLOCKED
    assert plan.requires_attention is True
    assert plan.blocked_reason == "DIRTY"


@pytest.mark.unit
def test_plan_checkout_default_blocked_when_dirty() -> None:
    state = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        branch="feature/payment-api",
        upstream="origin/feature/payment-api",
        dirty=True,
        dirty_files_count=2,
    )
    plan = SyncPlanner.plan_repository(
        "my-repo",
        state,
        options={"checkout_default": True},
        default_branch="main",
    )
    assert plan.action == SyncAction.BLOCKED
    assert plan.requires_attention is True
    assert plan.blocked_reason == "DIRTY_SWITCH_BLOCKED"


@pytest.mark.unit
def test_plan_checkout_default_allowed_when_clean() -> None:
    state = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        branch="feature/clean-branch",
        upstream="origin/feature/clean-branch",
        dirty=False,
        ahead=0,
        behind=1,
    )
    plan = SyncPlanner.plan_repository(
        "my-repo",
        state,
        options={"checkout_default": True},
        default_branch="main",
    )
    assert plan.action == SyncAction.FAST_FORWARD
    assert not plan.requires_attention
    assert any("CHECKOUT main" in s for s in plan.steps)


@pytest.mark.unit
def test_create_plan_collection() -> None:
    states = {
        "repo1": RepoState(exists=False, is_git_repo=False),
        "repo2": RepoState(
            exists=True,
            is_git_repo=True,
            remote_url="https://github.com/my-org/repo2.git",
            remote_matches=True,
            branch="main",
            upstream="origin/main",
            behind=2,
            dirty=False,
        ),
    }
    sync_plan = SyncPlanner.create_plan(
        organization="my-org",
        workspace="/tmp/ws",
        states=states,
    )
    assert sync_plan.total_count == 2
    assert sync_plan.requires_attention_count == 0
    assert sync_plan.has_mutations is True

    serialized = sync_plan.to_dict()
    assert serialized["total_repositories"] == 2
    assert len(serialized["repositories"]) == 2


@pytest.mark.unit
def test_plan_detached_head_blocked() -> None:
    state = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        detached_head=True,
    )
    plan = SyncPlanner.plan_repository("my-repo", state)
    assert plan.action == SyncAction.BLOCKED
    assert plan.requires_attention is True
    assert plan.blocked_reason == "DETACHED_HEAD"


@pytest.mark.unit
def test_plan_no_upstream_blocked() -> None:
    state = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        branch="main",
        upstream=None,
    )
    plan = SyncPlanner.plan_repository("my-repo", state)
    assert plan.action == SyncAction.BLOCKED
    assert plan.requires_attention is True
    assert plan.blocked_reason == "NO_UPSTREAM"


@pytest.mark.unit
def test_plan_conflicts_blocked() -> None:
    state = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        branch="main",
        upstream="origin/main",
        has_conflicts=True,
        conflict_files=("file.txt",),
    )
    plan = SyncPlanner.plan_repository("my-repo", state)
    assert plan.action == SyncAction.BLOCKED
    assert plan.requires_attention is True
    assert plan.blocked_reason == "CONFLICT"


@pytest.mark.unit
def test_plan_fetch_only_mode() -> None:
    state = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        branch="main",
        upstream="origin/main",
        ahead=0,
        behind=3,
    )
    plan = SyncPlanner.plan_repository("my-repo", state, options={"fetch_only": True})
    assert plan.action == SyncAction.FETCH
    assert not plan.requires_attention
    assert any("FETCH" in s for s in plan.steps)


@pytest.mark.unit
def test_plan_ahead_only() -> None:
    # Ahead and clean
    state_clean = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        branch="main",
        upstream="origin/main",
        ahead=3,
        behind=0,
        dirty=False,
    )
    plan1 = SyncPlanner.plan_repository("my-repo", state_clean)
    assert plan1.action == SyncAction.NONE
    assert "ahead" in plan1.reason

    # Ahead and dirty
    state_dirty = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        branch="main",
        upstream="origin/main",
        ahead=2,
        behind=0,
        dirty=True,
    )
    plan2 = SyncPlanner.plan_repository("my-repo", state_dirty)
    assert plan2.action == SyncAction.NONE
    assert "ahead" in plan2.reason


@pytest.mark.unit
def test_plan_up_to_date_clean_and_dirty() -> None:
    # Up to date clean
    state_clean = RepoState(
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
    plan1 = SyncPlanner.plan_repository("my-repo", state_clean)
    assert plan1.action == SyncAction.NONE
    assert "already up to date" in plan1.reason

    # Up to date with uncommitted dirty files
    state_dirty = RepoState(
        exists=True,
        is_git_repo=True,
        remote_url="https://github.com/my-org/my-repo.git",
        remote_matches=True,
        branch="main",
        upstream="origin/main",
        ahead=0,
        behind=0,
        dirty=True,
        dirty_files_count=2,
    )
    plan2 = SyncPlanner.plan_repository("my-repo", state_dirty)
    assert plan2.action == SyncAction.NONE
    assert "uncommitted changes" in plan2.reason


@pytest.mark.unit
def test_sync_plan_metrics_and_filtering() -> None:
    states = {
        "c_repo": RepoState(exists=False, is_git_repo=False),
        "b_repo": RepoState(
            exists=True,
            is_git_repo=True,
            remote_url="https://github.com/my-org/b_repo.git",
            remote_matches=True,
            branch="main",
            upstream="origin/main",
            behind=1,
            dirty=False,
        ),
        "a_repo": RepoState(
            exists=True,
            is_git_repo=True,
            remote_url="https://github.com/other-org/a_repo.git",
            remote_matches=False,
        ),
        "d_repo": RepoState(
            exists=True,
            is_git_repo=True,
            remote_url="https://github.com/my-org/d_repo.git",
            remote_matches=True,
            branch="main",
            upstream="origin/main",
            ahead=0,
            behind=0,
            dirty=False,
        ),
    }
    sync_plan = SyncPlanner.create_plan(
        organization="my-org",
        workspace="/tmp/ws",
        states=states,
    )
    assert sync_plan.total_count == 4
    assert sync_plan.clones_count == 1
    assert sync_plan.updates_count == 1
    assert sync_plan.up_to_date_count == 1
    assert sync_plan.blocked_count == 1
    assert sync_plan.requires_attention_count == 1

    # Check to_dict structure
    d = sync_plan.to_dict()
    assert d["clones_count"] == 1
    assert d["updates_count"] == 1
    assert d["up_to_date_count"] == 1
    assert d["blocked_count"] == 1
