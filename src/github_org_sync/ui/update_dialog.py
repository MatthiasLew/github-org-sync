import logging
from typing import Any

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from github_org_sync import __version__
from github_org_sync.i18n import _t
from github_org_sync.workers.update_worker import UpdateDownloadWorker

logger = logging.getLogger(__name__)


class UpdateDialog(QDialog):
    def __init__(
        self,
        latest_version: str,
        release_notes: str,
        download_url: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.latest_version = latest_version
        self.release_notes = release_notes
        self.download_url = download_url
        self.download_worker: UpdateDownloadWorker | None = None
        self._is_updating = False

        self.setWindowTitle(_t("update_dialog_title"))
        self.resize(500, 400)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Title / Header
        self.header_label = QLabel(_t("update_dialog_header"), self)
        self.header_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        layout.addWidget(self.header_label)

        # Versions info
        self.versions_label = QLabel(
            _t("update_dialog_versions", current=__version__, latest=self.latest_version), self
        )
        layout.addWidget(self.versions_label)

        # Release Notes label & browser
        self.notes_label = QLabel(_t("update_dialog_release_notes"), self)
        self.notes_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.notes_label)

        self.notes_browser = QTextBrowser(self)
        # Convert simple line breaks to HTML breaks if not already HTML
        html_notes = self.release_notes.replace("\n", "<br>")
        self.notes_browser.setHtml(html_notes)
        layout.addWidget(self.notes_browser)

        # Progress elements (hidden initially)
        self.progress_label = QLabel(self)
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Actions buttons
        self.buttons_layout = QHBoxLayout()
        self.btn_update = QPushButton(_t("btn_update_now"), self)
        self.btn_update.setStyleSheet("font-weight: bold; min-height: 28px;")
        self.btn_update.clicked.connect(self._start_update)

        self.btn_later = QPushButton(_t("btn_update_later"), self)
        self.btn_later.setMinimumHeight(28)
        self.btn_later.clicked.connect(self.reject)

        self.buttons_layout.addStretch()
        self.buttons_layout.addWidget(self.btn_later)
        self.buttons_layout.addWidget(self.btn_update)
        layout.addLayout(self.buttons_layout)

    def _start_update(self) -> None:
        if not self.download_url:
            QMessageBox.warning(
                self,
                _t("update_error_title"),
                _t("update_error_msg", error="No download URL found for your platform."),
            )
            return

        self._is_updating = True
        self.btn_update.setEnabled(False)
        self.btn_later.setEnabled(False)

        self.progress_label.setText(_t("update_downloading"))
        self.progress_label.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        self.download_worker = UpdateDownloadWorker(self.download_url, self.latest_version, self)
        self.download_worker.progress_updated.connect(self._on_progress)
        self.download_worker.download_finished.connect(self._on_download_finished)
        self.download_worker.applying_update.connect(self._on_applying_update)
        self.download_worker.finished.connect(self._on_finished)
        self.download_worker.error_occurred.connect(self._on_error)
        self.download_worker.start()

    def _on_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            pct = int((downloaded / total) * 100)
            self.progress_bar.setValue(pct)
            # Format sizes in MB
            dl_mb = downloaded / (1024 * 1024)
            tot_mb = total / (1024 * 1024)
            self.progress_label.setText(f"{_t('update_downloading')} ({dl_mb:.2f} MB / {tot_mb:.2f} MB)")
        else:
            self.progress_label.setText(_t("update_downloading"))

    def _on_download_finished(self) -> None:
        self.progress_label.setText(_t("update_extracting"))

    def _on_applying_update(self) -> None:
        self.progress_label.setText(_t("update_applying"))

    def _on_finished(self) -> None:
        self._is_updating = False
        QMessageBox.information(
            self,
            _t("update_dialog_title"),
            _t("update_restart_msg"),
        )
        self.accept()

    def _on_error(self, error_msg: str) -> None:
        self._is_updating = False
        self.btn_update.setEnabled(True)
        self.btn_later.setEnabled(True)
        self.progress_label.setVisible(False)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(
            self,
            _t("update_error_title"),
            _t("update_error_msg", error=error_msg),
        )

    def closeEvent(self, event: Any) -> None:
        # Ignore close event if currently downloading/applying update
        if self._is_updating:
            event.ignore()
        else:
            super().closeEvent(event)
