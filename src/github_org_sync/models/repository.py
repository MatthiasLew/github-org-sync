from dataclasses import dataclass
from pathlib import Path


@dataclass
class Repository:
    name: str
    url: str
    ssh_url: str
    is_archived: bool = False
    is_fork: bool = False
    default_branch: str = "main"
    visibility: str = "private"

    # Local sync state
    local_path: Path | None = None
    status: str = "MISSING"
    branch: str | None = None
    ahead: int | None = None
    behind: int | None = None
    requested_action: str | None = None
    performed_action: str | None = None
    result: str | None = None
