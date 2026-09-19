from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SyncResult:
    repo_name: str
    requested_action: str
    performed_action: str
    before_status: str
    after_status: str
    local_branch: str | None = None
    upstream_branch: str | None = None
    ahead: int | None = None
    behind: int | None = None
    dirty_file_count: int = 0
    conflict_files: list[str] = field(default_factory=list)
    user_decision: str | None = None
    backup_created: str | None = None
    result: str | None = None
    duration: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        return {
            "repo_name": self.repo_name,
            "requested_action": self.requested_action,
            "performed_action": self.performed_action,
            "before_status": self.before_status,
            "after_status": self.after_status,
            "local_branch": self.local_branch,
            "upstream_branch": self.upstream_branch,
            "ahead": self.ahead,
            "behind": self.behind,
            "dirty_file_count": self.dirty_file_count,
            "conflict_files": list(self.conflict_files),
            "user_decision": self.user_decision,
            "backup_created": self.backup_created,
            "result": self.result,
            "duration": round(self.duration, 4),
            "error": self.error,
        }
