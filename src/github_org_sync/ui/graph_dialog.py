from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from github_org_sync.i18n import _t
from github_org_sync.models.repository import Repository
from github_org_sync.services.git_service import GitService


class LogGraphDialog(QDialog):
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

        self.setWindowTitle(_t("graph_dialog_title", repo=repo.name))
        self.resize(800, 560)
        self._setup_ui()
        self._load_graph()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        # Controls bar
        controls_layout = QHBoxLayout()

        controls_layout.addWidget(QLabel(_t("graph_limit_label"), self))
        self.limit_combo = QComboBox(self)
        for lim in ("25", "50", "100", "200"):
            self.limit_combo.addItem(lim)
        self.limit_combo.currentTextChanged.connect(self._load_graph)
        controls_layout.addWidget(self.limit_combo)

        controls_layout.addSpacing(12)
        self.all_branches_cb = QCheckBox(_t("graph_all_branches"), self)
        self.all_branches_cb.setChecked(True)
        self.all_branches_cb.stateChanged.connect(self._load_graph)
        controls_layout.addWidget(self.all_branches_cb)

        controls_layout.addStretch()

        self.btn_refresh = QPushButton(_t("btn_refresh_graph"), self)
        self.btn_refresh.clicked.connect(self._load_graph)
        controls_layout.addWidget(self.btn_refresh)

        layout.addLayout(controls_layout)

        # Monospaced text viewer
        self.graph_view = QPlainTextEdit(self)
        self.graph_view.setReadOnly(True)
        self.graph_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Consolas, Courier New, monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(10)
        self.graph_view.setFont(font)
        layout.addWidget(self.graph_view)

        # Bottom buttons
        bottom_layout = QHBoxLayout()
        self.btn_copy = QPushButton(_t("btn_copy"), self)
        self.btn_copy.clicked.connect(self._copy_graph)
        bottom_layout.addWidget(self.btn_copy)

        bottom_layout.addStretch()

        self.btn_close = QPushButton(_t("btn_close"), self)
        self.btn_close.clicked.connect(self.accept)
        bottom_layout.addWidget(self.btn_close)

        layout.addLayout(bottom_layout)

    def _load_graph(self) -> None:
        if not self.repo.local_path:
            self.graph_view.setPlainText(_t("graph_no_repo"))
            return

        try:
            limit = int(self.limit_combo.currentText())
        except ValueError:
            limit = 25

        all_b = self.all_branches_cb.isChecked()
        graph_text = self.git_service.get_log_graph(self.repo_path, limit=limit, all_branches=all_b)
        if not graph_text:
            self.graph_view.setPlainText(_t("graph_empty"))
        else:
            self.graph_view.setPlainText(graph_text)

    def _copy_graph(self) -> None:
        QApplication.clipboard().setText(self.graph_view.toPlainText())
