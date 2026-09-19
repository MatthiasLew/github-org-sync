from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RepoState:
    """
    Multidimensional representation of a local git repository's state.
    Preserves all orthogonal status dimensions (dirty worktree, ahead/behind counts,
    conflicts, detached HEAD, upstream presence, and exact remote identity).
    """

    exists: bool
    is_git_repo: bool
    branch: str | None = None
    upstream: str | None = None
    dirty: bool = False
    dirty_files_count: int = 0
    ahead: int = 0
    behind: int = 0
    detached_head: bool = False
    has_conflicts: bool = False
    conflict_files: tuple[str, ...] = field(default_factory=tuple)
    remote_url: str | None = None
    remote_host: str | None = None
    remote_owner: str | None = None
    remote_repo: str | None = None
    remote_matches: bool = False
    has_lfs: bool = False
    failed: bool = False
    error_message: str | None = None

    @property
    def primary_status(self) -> str:
        """
        Derives a single status string for display and backwards compatibility.
        Evaluation order prioritizes fatal errors, structural problems, and conflicts.
        """
        if not self.exists:
            return "MISSING"
        if not self.is_git_repo:
            return "NOT_A_REPOSITORY"
        if self.failed:
            return "FAILED"
        if not self.remote_url:
            return "NO_UPSTREAM"
        if not self.remote_matches:
            return "WRONG_REMOTE"
        if self.detached_head:
            return "DETACHED_HEAD"
        if not self.upstream:
            return "NO_UPSTREAM"
        if self.has_conflicts:
            return "CONFLICT"
        if self.dirty:
            return "DIRTY"
        if self.ahead > 0 and self.behind > 0:
            return "DIVERGED"
        if self.ahead > 0:
            return "AHEAD"
        if self.behind > 0:
            return "BEHIND"
        return "UP_TO_DATE"

    @property
    def is_clean(self) -> bool:
        """True if the repository exists, is up-to-date, and has no local uncommitted changes."""
        return (
            self.exists
            and self.is_git_repo
            and not self.failed
            and self.remote_matches
            and not self.dirty
            and self.ahead == 0
            and self.behind == 0
            and not self.has_conflicts
            and not self.detached_head
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        return {
            "exists": self.exists,
            "is_git_repo": self.is_git_repo,
            "failed": self.failed,
            "branch": self.branch,
            "upstream": self.upstream,
            "dirty": self.dirty,
            "dirty_files_count": self.dirty_files_count,
            "ahead": self.ahead,
            "behind": self.behind,
            "detached_head": self.detached_head,
            "has_conflicts": self.has_conflicts,
            "conflict_files": list(self.conflict_files),
            "remote_url": self.remote_url,
            "remote_host": self.remote_host,
            "remote_owner": self.remote_owner,
            "remote_repo": self.remote_repo,
            "remote_matches": self.remote_matches,
            "has_lfs": self.has_lfs,
            "primary_status": self.primary_status,
            "error_message": self.error_message,
        }
