from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from github_org_sync.models.repo_state import RepoState


class SyncAction(StrEnum):
    NONE = "NONE"
    CLONE = "CLONE"
    FETCH = "FETCH"
    FAST_FORWARD = "FAST_FORWARD"
    STASH_FF_RESTORE = "STASH_FF_RESTORE"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class RepoPlan:
    """Deterministic planned execution steps for a single repository."""

    repo_name: str
    state: RepoState
    action: SyncAction
    steps: tuple[str, ...]
    reason: str
    requires_attention: bool = False
    blocked_reason: str | None = None

    @property
    def action_summary(self) -> str:
        """Human-readable concise summary of the planned action (e.g. STASH → FF → RESTORE)."""
        if self.action == SyncAction.STASH_FF_RESTORE:
            return "STASH → FF → RESTORE"
        if self.action == SyncAction.FAST_FORWARD:
            if self.state.behind > 0:
                return f"FAST_FORWARD ({self.state.behind} behind)"
            return "FAST_FORWARD"
        if self.action == SyncAction.CLONE:
            return "CLONE"
        if self.action == SyncAction.FETCH:
            return "FETCH"
        if self.action == SyncAction.BLOCKED:
            return "BLOCKED"
        if self.action == SyncAction.SKIPPED:
            return "SKIPPED"
        return "NONE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_name": self.repo_name,
            "action": self.action.value,
            "action_summary": self.action_summary,
            "steps": list(self.steps),
            "reason": self.reason,
            "requires_attention": self.requires_attention,
            "blocked_reason": self.blocked_reason,
            "state": self.state.to_dict(),
        }


@dataclass(frozen=True)
class SyncPlan:
    """Complete collection of planned actions for a workspace sync run."""

    organization: str
    workspace: str
    plans: tuple[RepoPlan, ...] = field(default_factory=tuple)

    @property
    def total_count(self) -> int:
        return len(self.plans)

    @property
    def requires_attention_count(self) -> int:
        return sum(1 for p in self.plans if p.requires_attention)

    @property
    def clones_count(self) -> int:
        return sum(1 for p in self.plans if p.action == SyncAction.CLONE)

    @property
    def updates_count(self) -> int:
        return sum(1 for p in self.plans if p.action in (SyncAction.FAST_FORWARD, SyncAction.STASH_FF_RESTORE))

    @property
    def up_to_date_count(self) -> int:
        return sum(1 for p in self.plans if p.action == SyncAction.NONE)

    @property
    def blocked_count(self) -> int:
        return sum(1 for p in self.plans if p.action == SyncAction.BLOCKED)

    @property
    def has_mutations(self) -> bool:
        return any(
            p.action in (SyncAction.CLONE, SyncAction.FAST_FORWARD, SyncAction.STASH_FF_RESTORE, SyncAction.FETCH)
            for p in self.plans
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "organization": self.organization,
            "workspace": self.workspace,
            "total_repositories": self.total_count,
            "clones_count": self.clones_count,
            "updates_count": self.updates_count,
            "up_to_date_count": self.up_to_date_count,
            "blocked_count": self.blocked_count,
            "requires_attention_count": self.requires_attention_count,
            "repositories": [p.to_dict() for p in self.plans],
        }
