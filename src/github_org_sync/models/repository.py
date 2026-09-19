from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from github_org_sync.models.repo_state import RepoState


@dataclass
class Repository:
    name: str
    url: str
    ssh_url: str
    is_archived: bool = False
    is_fork: bool = False
    default_branch: str = "main"
    visibility: str = "private"

    # Multidimensional domain state
    state: RepoState | None = None

    # Local sync state (kept in sync for GUI/table backwards compatibility)
    local_path: Path | None = None
    status: str = "MISSING"
    branch: str | None = None
    ahead: int | None = None
    behind: int | None = None
    requested_action: str | None = None
    performed_action: str | None = None
    result: str | None = None
    error_message: str | None = None

    # Custom grouping attributes
    computed_hosting: str = "GitHub"
    computed_owner: str = "No remote"
    has_lfs: bool = False

    def apply_state(self, state: RepoState) -> None:
        """Applies a verified RepoState to this repository model."""
        self.state = state
        self.status = state.primary_status
        self.branch = state.branch
        self.ahead = state.ahead if state.upstream else None
        self.behind = state.behind if state.upstream else None
        self.has_lfs = state.has_lfs
        if state.remote_host:
            self.computed_hosting = state.remote_host
        if state.remote_owner:
            self.computed_owner = state.remote_owner
        if state.error_message:
            self.result = state.error_message
            self.error_message = state.error_message
