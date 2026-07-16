from dataclasses import dataclass

@dataclass
class SyncResult:
    repo_name: str
    status: str
    before_status: str
    after_status: str
    duration: float
    operation: str
    error: str | None = None
    message: str | None = None
