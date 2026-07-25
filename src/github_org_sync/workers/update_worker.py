import logging
import sys
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

from github_org_sync.services.update_service import UpdateService

logger = logging.getLogger(__name__)


class UpdateCheckWorker(QThread):
    # Signals: has_update, latest_version, release_notes, download_url
    finished = Signal(bool, str, str, str)
    error_occurred = Signal(str)

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.update_service = UpdateService()

    def run(self) -> None:
        try:
            update_info = self.update_service.check_for_updates()
            if update_info:
                self.finished.emit(
                    True,
                    update_info["version"],
                    update_info["release_notes"],
                    update_info["download_url"] or "",
                )
            else:
                self.finished.emit(False, "", "", "")
        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            self.error_occurred.emit(str(e))


class UpdateDownloadWorker(QThread):
    # Signals
    progress_updated = Signal(int, int)  # downloaded, total
    download_finished = Signal()
    applying_update = Signal()
    finished = Signal()
    error_occurred = Signal(str)

    def __init__(self, download_url: str, latest_version: str, parent: Any = None) -> None:
        super().__init__(parent)
        self.download_url = download_url
        self.latest_version = latest_version
        self.update_service = UpdateService()

    def run(self) -> None:
        try:
            # Determine archive extension
            suffix = ".zip" if sys.platform in ("win32", "darwin") else ".tar.gz"
            temp_archive = Path(tempfile.gettempdir()) / f"github-org-sync-update-{self.latest_version}{suffix}"

            # Download update
            self.update_service.download_update(
                self.download_url, temp_archive, progress_callback=self._progress_callback
            )
            self.download_finished.emit()

            # Apply update if frozen (packaged PyInstaller app)
            if getattr(sys, "frozen", False):
                self.applying_update.emit()
                install_dir = Path(sys.executable).parent
                self.update_service.apply_update(temp_archive, install_dir)
            else:
                logger.info("Running from source code - skipping actual binary replacement.")
                # For development/testing, simulate extraction and cleanup without overwriting files
                temp_extract = Path(tempfile.mkdtemp(prefix="github-org-sync-dev-mock-"))
                self.update_service.apply_update(temp_archive, temp_extract)

            self.finished.emit()
        except Exception as e:
            logger.error(f"Error downloading/applying update: {e}")
            self.error_occurred.emit(str(e))

    def _progress_callback(self, downloaded: int, total: int) -> None:
        self.progress_updated.emit(downloaded, total)
