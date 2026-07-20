from dataclasses import dataclass, field


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
