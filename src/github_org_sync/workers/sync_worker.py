from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

from github_org_sync.models.repository import Repository
from github_org_sync.models.sync_result import SyncResult
from github_org_sync.services.git_service import GitService
from github_org_sync.services.sync_service import SyncService


class SyncWorker(QThread):
    # Signals
    progress_updated = Signal(int, int, str, str, str)  # current, total, repo_name, status, message
    log_emitted = Signal(str)  # log message
    finished = Signal(list, bool)  # results (list of SyncResult), was_cancelled
    error_occurred = Signal(str)  # error message if global failure

    def __init__(
        self,
        repositories: list[Repository],
        workspace: Path,
        org_name: str,
        options: dict[str, Any],
        mode: str = "sync",  # "inspect" or "sync"
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.repositories = repositories
        self.workspace = workspace
        self.org_name = org_name
        self.options = options
        self.mode = mode

        self.git_service = GitService()
        self.sync_service = SyncService(git_service=self.git_service)
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True
        self.log_emitted.emit("Cancellation requested. Safe shutdown in progress...")

    def run(self) -> None:
        try:
            if self.mode == "inspect":
                self.run_inspection()
            else:
                self.run_sync()
        except Exception as e:
            self.error_occurred.emit(str(e))

    def run_inspection(self) -> None:
        self.log_emitted.emit(f"Starting status inspection for organization: {self.org_name}")
        len(self.repositories)

        def local_progress(index: int, total_count: int, repo_name: str) -> None:
            self.progress_updated.emit(index, total_count, repo_name, "CHECKING", "Inspecting local status...")
            self.log_emitted.emit(f"[{index}/{total_count}] Inspecting local directory for '{repo_name}'")

        self.sync_service.check_local_statuses(
            repositories=self.repositories,
            workspace=self.workspace,
            org_name=self.org_name,
            progress_callback=local_progress,
        )

        self.log_emitted.emit("Local status inspection finished.")
        # Wrap repos as results to emit them
        self.finished.emit([], False)

    def run_sync(self) -> None:
        self.log_emitted.emit(f"Starting synchronization of {len(self.repositories)} repositories...")

        def sync_progress(index: int, total_count: int, repo: Repository, res: SyncResult) -> None:
            status_text = res.status
            msg_text = res.message or res.error or ""

            # Emit log details
            log_line = f"[{index}/{total_count}] Repository '{repo.name}' -> Operation: {res.operation.upper()} | Status: {status_text}"
            if msg_text:
                log_line += f" | Details: {msg_text}"
            self.log_emitted.emit(log_line)

            # Emit progress signal
            self.progress_updated.emit(index, total_count, repo.name, status_text, msg_text)

        def check_cancelled() -> bool:
            return self._is_cancelled

        results = self.sync_service.sync_repositories(
            repositories=self.repositories,
            workspace=self.workspace,
            org_name=self.org_name,
            options=self.options,
            progress_callback=sync_progress,
            is_cancelled_callback=check_cancelled,
        )

        if self._is_cancelled:
            self.log_emitted.emit("Synchronization cancelled by user.")
        else:
            self.log_emitted.emit("Synchronization finished successfully.")

        self.finished.emit(results, self._is_cancelled)
