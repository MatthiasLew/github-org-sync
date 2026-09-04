from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from github_org_sync.i18n import _t
from github_org_sync.models.repository import Repository
from github_org_sync.services.git_service import GitService


class PruneBranchesDialog(QDialog):
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

        self.setWindowTitle(_t("prune_dialog_title", repo=repo.name))
        self.resize(640, 420)
        self._setup_ui()
        self._scan_and_prune()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        desc_label = QLabel(_t("prune_desc_label"), self)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        self.remote_status_label = QLabel(self)
        self.remote_status_label.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(self.remote_status_label)

        layout.addWidget(QLabel(_t("prune_stale_branches_label"), self))

        self.branch_table = QTableWidget(self)
        self.branch_table.setColumnCount(3)
        self.branch_table.setHorizontalHeaderLabels(
            [
                _t("prune_col_branch"),
                _t("prune_col_reason"),
                _t("prune_col_upstream"),
            ]
        )
        header = self.branch_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.branch_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.branch_table)

        self.empty_label = QLabel(_t("prune_no_stale"), self)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #10b981; font-weight: bold; padding: 20px;")
        self.empty_label.setVisible(False)
        layout.addWidget(self.empty_label)

        btn_row = QHBoxLayout()
        self.btn_select_all = QPushButton(_t("btn_select_all"), self)
        self.btn_select_all.clicked.connect(self._select_all)
        btn_row.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton(_t("btn_deselect_all"), self)
        self.btn_deselect_all.clicked.connect(self._deselect_all)
        btn_row.addWidget(self.btn_deselect_all)

        btn_row.addStretch()

        self.btn_scan = QPushButton(_t("btn_prune_scan"), self)
        self.btn_scan.clicked.connect(self._scan_and_prune)
        btn_row.addWidget(self.btn_scan)

        self.btn_delete = QPushButton(_t("btn_prune_delete"), self)
        self.btn_delete.setObjectName("btnDanger")
        self.btn_delete.clicked.connect(self._on_delete_selected)
        btn_row.addWidget(self.btn_delete)

        self.btn_close = QPushButton(_t("btn_close"), self)
        self.btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_close)

        layout.addLayout(btn_row)

    def _scan_and_prune(self) -> None:
        if not self.repo.local_path:
            return

        ok, remote_out = self.git_service.prune_remote_branches(self.repo_path)
        if ok and remote_out:
            lines = [line.strip() for line in remote_out.splitlines() if "[pruned]" in line]
            if lines:
                self.remote_status_label.setText(_t("prune_remote_summary") + " " + ", ".join(lines))
            else:
                self.remote_status_label.setText(_t("prune_remote_summary") + " OK (0 pruned)")
        else:
            self.remote_status_label.setText(_t("prune_remote_summary") + " OK")

        stale_branches = self.git_service.get_stale_branches(self.repo_path)
        self.branch_table.setRowCount(0)

        if not stale_branches:
            self.branch_table.setVisible(False)
            self.empty_label.setVisible(True)
            self.btn_delete.setEnabled(False)
            self.btn_select_all.setEnabled(False)
            self.btn_deselect_all.setEnabled(False)
            return

        self.branch_table.setVisible(True)
        self.empty_label.setVisible(False)
        self.btn_delete.setEnabled(True)
        self.btn_select_all.setEnabled(True)
        self.btn_deselect_all.setEnabled(True)

        for b in stale_branches:
            row = self.branch_table.rowCount()
            self.branch_table.insertRow(row)

            branch_item = QTableWidgetItem(b["name"])
            branch_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable
            )
            branch_item.setCheckState(Qt.CheckState.Checked)
            self.branch_table.setItem(row, 0, branch_item)

            reason_str = _t("prune_reason_gone") if b["reason"] == "gone" else _t("prune_reason_merged")
            reason_item = QTableWidgetItem(reason_str)
            reason_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.branch_table.setItem(row, 1, reason_item)

            upstream_item = QTableWidgetItem(b.get("upstream", "") or "-")
            upstream_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.branch_table.setItem(row, 2, upstream_item)

    def _select_all(self) -> None:
        for row in range(self.branch_table.rowCount()):
            item = self.branch_table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked)

    def _deselect_all(self) -> None:
        for row in range(self.branch_table.rowCount()):
            item = self.branch_table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)

    def _get_selected_branches(self) -> list[str]:
        selected = []
        for row in range(self.branch_table.rowCount()):
            item = self.branch_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())
        return selected

    def _on_delete_selected(self) -> None:
        selected = self._get_selected_branches()
        if not selected:
            QMessageBox.warning(self, _t("title_warning"), _t("prune_no_selection"))
            return

        branches_str = "\n".join(f"- {b}" for b in selected)
        reply = QMessageBox.question(
            self,
            _t("prune_confirm_title"),
            _t("prune_confirm_msg", branches=branches_str),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted_count = 0
        errors: list[str] = []

        for b in selected:
            ok, err = self.git_service.delete_local_branch(self.repo_path, b, force=True)
            if ok:
                deleted_count += 1
            else:
                errors.append(f"{b}: {err}")

        if errors:
            QMessageBox.warning(
                self,
                _t("title_error"),
                "\n".join(errors),
            )
        elif deleted_count > 0:
            QMessageBox.information(
                self,
                _t("title_success"),
                _t("prune_success_msg", count=deleted_count),
            )

        self._scan_and_prune()
