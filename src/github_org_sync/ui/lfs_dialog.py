from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from github_org_sync.i18n import _t
from github_org_sync.models.repository import Repository
from github_org_sync.services.git_service import GitService


class LfsDialog(QDialog):
    def __init__(
        self,
        repo: Repository,
        git_service: GitService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repo = repo
        self.git_service = git_service
        self.repo_path = Path(repo.local_path) if repo.local_path else Path()

        self.setWindowTitle(_t("lfs_dialog_title", repo=repo.name))
        self.resize(700, 480)
        self._setup_ui()
        self._load_lfs_info()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        self.header_label = QLabel(self)
        self.header_label.setWordWrap(True)
        layout.addWidget(self.header_label)

        splitter = QSplitter(Qt.Orientation.Vertical, self)

        # Top: tracked files
        top_widget = QWidget(self)
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(QLabel(_t("lfs_tracked_files_label"), self))

        self.files_list = QListWidget(self)
        top_layout.addWidget(self.files_list)
        splitter.addWidget(top_widget)

        # Bottom: lfs status
        bottom_widget = QWidget(self)
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addWidget(QLabel(_t("lfs_status_label"), self))

        self.status_view = QPlainTextEdit(self)
        self.status_view.setReadOnly(True)
        bottom_layout.addWidget(self.status_view)
        splitter.addWidget(bottom_widget)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        # Close button row
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_close = QPushButton(_t("btn_close"), self)
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def _load_lfs_info(self) -> None:
        if not self.repo.local_path:
            self.header_label.setText(_t("lfs_not_used"))
            return

        info = self.git_service.get_lfs_status(self.repo_path)
        if info.get("error"):
            self.header_label.setText(str(info["error"]))
            return

        if not info.get("has_lfs"):
            self.header_label.setText(_t("lfs_not_used"))
            self.files_list.addItem(_t("lfs_no_files"))
            return

        self.header_label.setText(_t("lfs_badge_tooltip"))

        files = info.get("files", [])
        if files:
            for f in files:
                self.files_list.addItem(f)
        else:
            self.files_list.addItem(_t("lfs_no_files"))

        status_text = info.get("status", "")
        self.status_view.setPlainText(status_text)
