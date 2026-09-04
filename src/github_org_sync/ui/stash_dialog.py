from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from github_org_sync.i18n import _t
from github_org_sync.models.repository import Repository
from github_org_sync.services.git_service import GitService


class StashDialog(QDialog):
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

        self.setWindowTitle(_t("stash_dialog_title", repo=repo.name))
        self.resize(650, 480)
        self._setup_ui()
        self._refresh_stash_list()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        splitter = QSplitter(Qt.Orientation.Vertical, self)

        top_widget = QWidget(self)
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(QLabel(_t("stash_list_label"), self))

        self.stash_list = QListWidget(self)
        self.stash_list.currentRowChanged.connect(self._on_stash_selected)
        top_layout.addWidget(self.stash_list)

        btn_row = QHBoxLayout()
        self.btn_pop = QPushButton(_t("btn_stash_pop"), self)
        self.btn_pop.setObjectName("btnAction")
        self.btn_pop.clicked.connect(self._on_pop)
        btn_row.addWidget(self.btn_pop)

        self.btn_drop = QPushButton(_t("btn_stash_drop"), self)
        self.btn_drop.setStyleSheet("background-color: #7f1d1d; color: #fca5a5;")
        self.btn_drop.clicked.connect(self._on_drop)
        btn_row.addWidget(self.btn_drop)

        self.btn_create = QPushButton(_t("btn_stash_create"), self)
        self.btn_create.clicked.connect(self._on_create)
        btn_row.addWidget(self.btn_create)

        btn_row.addStretch()
        top_layout.addLayout(btn_row)

        splitter.addWidget(top_widget)

        bottom_widget = QWidget(self)
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addWidget(QLabel(_t("stash_details_label"), self))

        self.details_area = QTextEdit(self)
        self.details_area.setReadOnly(True)
        self.details_area.setStyleSheet(
            "font-family: Consolas, Courier New, monospace; background-color: #0f172a; color: #f8fafc;"
        )
        bottom_layout.addWidget(self.details_area)

        splitter.addWidget(bottom_widget)
        layout.addWidget(splitter, 1)

        close_layout = QHBoxLayout()
        close_layout.addStretch()
        self.btn_close = QPushButton(_t("btn_cancel"), self)
        self.btn_close.clicked.connect(self.accept)
        close_layout.addWidget(self.btn_close)
        layout.addLayout(close_layout)

    def _refresh_stash_list(self) -> None:
        self.stash_list.clear()
        self.details_area.clear()
        stashes = self.git_service.get_stash_list(self.repo_path)
        if not stashes:
            self.btn_pop.setEnabled(False)
            self.btn_drop.setEnabled(False)
            self.details_area.setPlainText(_t("stash_empty_label"))
            return

        self.btn_pop.setEnabled(True)
        self.btn_drop.setEnabled(True)
        for s in stashes:
            self.stash_list.addItem(s)
        self.stash_list.setCurrentRow(0)

    def _on_stash_selected(self, row: int) -> None:
        if row < 0:
            self.details_area.clear()
            return
        details = self.git_service.get_stash_show(self.repo_path, row)
        self.details_area.setPlainText(details or _t("stash_empty_label"))

    def _on_pop(self) -> None:
        row = self.stash_list.currentRow()
        if row < 0:
            return
        ok, out = self.git_service.stash_pop(self.repo_path, row)
        if ok:
            QMessageBox.information(self, _t("title_success"), _t("stash_pop_success"))
            self._refresh_stash_list()
        else:
            QMessageBox.warning(self, _t("title_warning"), _t("stash_pop_conflict", error=out))
            self._refresh_stash_list()

    def _on_drop(self) -> None:
        row = self.stash_list.currentRow()
        if row < 0:
            return
        item_text = self.stash_list.item(row).text() if self.stash_list.item(row) else ""
        res = QMessageBox.question(
            self,
            _t("stash_drop_confirm_title"),
            _t("stash_drop_confirm_msg", stash=item_text),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            ok, out = self.git_service.stash_drop(self.repo_path, row)
            if ok:
                QMessageBox.information(self, _t("title_success"), _t("stash_drop_success"))
            else:
                QMessageBox.warning(self, _t("title_error"), out)
            self._refresh_stash_list()

    def _on_create(self) -> None:
        desc, ok = QInputDialog.getText(
            self,
            _t("stash_push_prompt_title"),
            _t("stash_push_prompt_msg"),
        )
        if ok:
            succ, out = self.git_service.stash_push(self.repo_path, desc.strip(), include_untracked=True)
            if succ:
                self._refresh_stash_list()
            else:
                QMessageBox.warning(self, _t("title_error"), out)
