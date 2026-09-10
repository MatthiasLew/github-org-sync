"""Worker thread for generating monthly work summaries asynchronously."""

from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from github_org_sync.services.work_summary_service import WorkSummaryError, WorkSummaryService


class WorkSummaryWorkerSignals(QObject):
    status_changed = Signal(str)
    log_emitted = Signal(str)
    finished = Signal(dict)
    error_occurred = Signal(str)


class WorkSummaryWorker(QThread):
    def __init__(
        self,
        login: str,
        year: int,
        month: int,
        excluded_owner: str | None = None,
        target_org: str | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.login = login
        self.year = year
        self.month = month
        self.excluded_owner = excluded_owner
        self.target_org = target_org
        self.signals = WorkSummaryWorkerSignals(self)
        self.service = WorkSummaryService()
        self._is_cancelled = False

    def cancel(self) -> None:
        """Flags the worker for cancellation."""
        self._is_cancelled = True
        self.signals.log_emitted.emit("Work summary generation cancelled by user.")

    def is_cancelled(self) -> bool:
        """Checks if cancellation was requested."""
        return self._is_cancelled

    def run(self) -> None:
        """Executes the GraphQL query and contribution analysis."""
        try:
            if self.is_cancelled():
                return

            self.signals.status_changed.emit(f"Pobieranie wkładu dla {self.login} ({self.year}-{self.month:02d})...")
            self.signals.log_emitted.emit(
                f"Fetching contribution collection for {self.login} for {self.year}-{self.month:02d}..."
            )

            result = self.service.generate_summary(
                login=self.login,
                year=self.year,
                month=self.month,
                excluded_owner=self.excluded_owner,
                target_org=self.target_org,
            )

            if self.is_cancelled():
                return

            self.signals.finished.emit(result)
        except WorkSummaryError as exc:
            if not self.is_cancelled():
                self.signals.error_occurred.emit(str(exc))
        except Exception as exc:
            if not self.is_cancelled():
                self.signals.error_occurred.emit(f"Unexpected error: {exc}")
