from __future__ import annotations

from typing import Any

from github_org_sync.models.repo_state import RepoState
from github_org_sync.models.sync_plan import RepoPlan, SyncAction, SyncPlan


class SyncPlanner:
    """
    Deterministic planning engine for workspace synchronizations.
    Given repository states and options, computes exact planned steps.
    """

    @staticmethod
    def plan_repository(
        repo_name: str,
        state: RepoState,
        options: dict[str, Any] | None = None,
        default_branch: str = "main",
    ) -> RepoPlan:
        opts = options or {}
        preserve_local_changes = opts.get("preserve_local_changes", True)
        fetch_only = opts.get("fetch_only", False)
        checkout_default = opts.get("checkout_default", False)

        # 1. Missing directory -> CLONE
        if not state.exists:
            clone_steps = (
                f"CLONE {repo_name} into temporary workspace isolation folder",
                "VERIFY clone integrity, .git structure, and remote origin identity",
                f"ATOMIC MOVE temporary clone into workspace/{repo_name}",
            )
            return RepoPlan(
                repo_name=repo_name,
                state=state,
                action=SyncAction.CLONE,
                steps=clone_steps,
                reason="Repository directory is missing locally.",
                requires_attention=False,
            )

        # 2. Exists but not a git repo -> BLOCKED
        if not state.is_git_repo:
            return RepoPlan(
                repo_name=repo_name,
                state=state,
                action=SyncAction.BLOCKED,
                steps=(),
                reason="Target directory exists but is not a valid Git repository.",
                requires_attention=True,
                blocked_reason="NOT_A_REPOSITORY",
            )

        # 3. Wrong remote identity -> BLOCKED
        if not state.remote_matches:
            reason = (
                f"Remote identity mismatch: origin points to "
                f"'{state.remote_owner}/{state.remote_repo}' on host '{state.remote_host}'."
            )
            return RepoPlan(
                repo_name=repo_name,
                state=state,
                action=SyncAction.BLOCKED,
                steps=(),
                reason=reason,
                requires_attention=True,
                blocked_reason="WRONG_REMOTE",
            )

        # 4. Detached HEAD -> BLOCKED
        if state.detached_head:
            return RepoPlan(
                repo_name=repo_name,
                state=state,
                action=SyncAction.BLOCKED,
                steps=(),
                reason="Repository is in detached HEAD state.",
                requires_attention=True,
                blocked_reason="DETACHED_HEAD",
            )

        # 5. Missing upstream tracking -> BLOCKED
        if not state.upstream:
            return RepoPlan(
                repo_name=repo_name,
                state=state,
                action=SyncAction.BLOCKED,
                steps=(),
                reason=f"Current branch '{state.branch}' has no tracking upstream branch configured.",
                requires_attention=True,
                blocked_reason="NO_UPSTREAM",
            )

        # 6. Unresolved merge/rebase conflicts -> BLOCKED
        if state.has_conflicts:
            conflict_count = len(state.conflict_files)
            return RepoPlan(
                repo_name=repo_name,
                state=state,
                action=SyncAction.BLOCKED,
                steps=(),
                reason=f"Repository contains unresolved conflicts ({conflict_count} conflicting files).",
                requires_attention=True,
                blocked_reason="CONFLICT",
            )

        # 7. Fetch-only mode
        if fetch_only:
            return RepoPlan(
                repo_name=repo_name,
                state=state,
                action=SyncAction.FETCH,
                steps=("FETCH origin --prune",),
                reason="Fetch-only requested; updating remote tracking branches without merging.",
                requires_attention=False,
            )

        # 8. Check checkout-default opt-in
        planned_steps: list[str] = ["FETCH origin --prune"]
        branch_to_sync = state.branch or default_branch

        if checkout_default and state.branch and state.branch != default_branch:
            if state.dirty:
                return RepoPlan(
                    repo_name=repo_name,
                    state=state,
                    action=SyncAction.BLOCKED,
                    steps=(),
                    reason=(
                        f"Requested checkout to default branch '{default_branch}' is blocked because "
                        f"current branch '{state.branch}' has uncommitted changes."
                    ),
                    requires_attention=True,
                    blocked_reason="DIRTY_SWITCH_BLOCKED",
                )
            planned_steps.append(f"CHECKOUT {default_branch}")
            branch_to_sync = default_branch

        # 9. Diverged branches -> BLOCKED
        if state.ahead > 0 and state.behind > 0:
            return RepoPlan(
                repo_name=repo_name,
                state=state,
                action=SyncAction.BLOCKED,
                steps=(),
                reason=(
                    f"Branch '{state.branch}' has diverged from upstream "
                    f"({state.ahead} local commits ahead, {state.behind} remote commits behind). "
                    "Manual rebase or merge is required."
                ),
                requires_attention=True,
                blocked_reason="DIVERGED",
            )

        # 10. Behind upstream commits -> FAST_FORWARD or STASH_FF_RESTORE
        if state.behind > 0:
            if state.dirty:
                if not preserve_local_changes:
                    return RepoPlan(
                        repo_name=repo_name,
                        state=state,
                        action=SyncAction.BLOCKED,
                        steps=(),
                        reason=(
                            f"Branch '{branch_to_sync}' is behind by {state.behind} commits, "
                            "but worktree has uncommitted changes and auto-stash is disabled."
                        ),
                        requires_attention=True,
                        blocked_reason="DIRTY",
                    )
                dirty_desc = f"{state.dirty_files_count} changed files" if state.dirty_files_count else "worktree"
                ff_desc = f"FAST-FORWARD {branch_to_sync} by {state.behind} commits"
                stash_steps = (
                    "FETCH origin --prune",
                    f"STASH {dirty_desc}",
                    ff_desc,
                    "RESTORE stash",
                )
                return RepoPlan(
                    repo_name=repo_name,
                    state=state,
                    action=SyncAction.STASH_FF_RESTORE,
                    steps=stash_steps,
                    reason=f"Behind remote by {state.behind} commits with {dirty_desc}.",
                    requires_attention=False,
                )

            ff_desc = f"FAST-FORWARD {branch_to_sync} by {state.behind} commits"
            planned_steps.append(ff_desc)
            return RepoPlan(
                repo_name=repo_name,
                state=state,
                action=SyncAction.FAST_FORWARD,
                steps=tuple(planned_steps),
                reason=f"Behind remote by {state.behind} commits; will fast-forward cleanly.",
                requires_attention=False,
            )

        # 11. Ahead only -> NONE
        if state.ahead > 0:
            dirty_msg = " and uncommitted changes" if state.dirty else ""
            return RepoPlan(
                repo_name=repo_name,
                state=state,
                action=SyncAction.NONE,
                steps=(),
                reason=f"Branch '{state.branch}' is ahead of upstream by {state.ahead} commits{dirty_msg}.",
                requires_attention=False,
            )

        # 12. Up to date (clean or dirty but behind == 0)
        if state.dirty:
            return RepoPlan(
                repo_name=repo_name,
                state=state,
                action=SyncAction.NONE,
                steps=(),
                reason=f"Worktree has {state.dirty_files_count} uncommitted changes; remote is already up to date.",
                requires_attention=False,
            )

        return RepoPlan(
            repo_name=repo_name,
            state=state,
            action=SyncAction.NONE,
            steps=(),
            reason="Repository is already up to date.",
            requires_attention=False,
        )

    @classmethod
    def create_plan(
        cls,
        organization: str,
        workspace: str,
        states: dict[str, RepoState],
        options: dict[str, Any] | None = None,
        default_branches: dict[str, str] | None = None,
    ) -> SyncPlan:
        branches = default_branches or {}
        plans: list[RepoPlan] = []
        for name in sorted(states.keys()):
            repo_plan = cls.plan_repository(
                repo_name=name,
                state=states[name],
                options=options,
                default_branch=branches.get(name, "main"),
            )
            plans.append(repo_plan)
        return SyncPlan(
            organization=organization,
            workspace=workspace,
            plans=tuple(plans),
        )
