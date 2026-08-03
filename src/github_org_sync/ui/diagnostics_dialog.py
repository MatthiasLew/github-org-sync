from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from github_org_sync.i18n import _t
from github_org_sync.services.diagnostics_service import DiagnosticsResult, DiagnosticsService


class DiagnosticsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.results: list[DiagnosticsResult] = []
        self._setup_ui()
        self.run_diagnostics()

    def _setup_ui(self) -> None:
        self.resize(550, 450)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header Title
        self.title_label = QLabel(self)
        self.title_label.setObjectName("headerTitle")
        layout.addWidget(self.title_label)

        # Checklist Table
        self.table = QTableWidget(self)
        self.table.setColumnCount(2)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table)

        # Details Label
        self.details_label = QLabel(self)
        layout.addWidget(self.details_label)

        # Detailed Output Box
        self.details_box = QTextEdit(self)
        self.details_box.setReadOnly(True)
        self.details_box.setObjectName("consoleLog")
        layout.addWidget(self.details_box)

        # Buttons Row
        btn_layout = QHBoxLayout()
        self.btn_run = QPushButton(self)
        self.btn_run.setObjectName("btnAction")
        self.btn_run.clicked.connect(self.run_diagnostics)
        btn_layout.addWidget(self.btn_run)

        btn_layout.addStretch()

        self.btn_close = QPushButton(self)
        self.btn_close.setObjectName("btnOutline")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.setWindowTitle(_t("diagnostics_title"))
        self.title_label.setText(_t("diagnostics_title"))
        self.table.setHorizontalHeaderLabels([_t("diagnostics_col_check"), _t("diagnostics_col_status")])
        self.details_label.setText(_t("diagnostics_details_label"))
        self.btn_run.setText(_t("diagnostics_run_btn"))
        self.btn_close.setText(_t("btn_close"))

        # Re-run rendering of status texts in table if results exist
        if self.results:
            self._render_results()

    def run_diagnostics(self) -> None:
        self.btn_run.setEnabled(False)
        self.table.setRowCount(0)
        self.details_box.clear()

        # Run diagnostic checks
        self.results = DiagnosticsService.run_all_checks()

        self._render_results()
        self.btn_run.setEnabled(True)

        if self.results:
            self.table.selectRow(0)

    def _render_results(self) -> None:
        self.table.setRowCount(len(self.results))
        for idx, res in enumerate(self.results):
            item_check = QTableWidgetItem(res.label)
            item_check.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(idx, 0, item_check)

            status_val = _t("diagnostics_status_success") if res.success else _t("diagnostics_status_fail")
            status_text = f"● {status_val}"
            item_status = QTableWidgetItem(status_text)
            item_status.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            if res.success:
                item_status.setForeground(Qt.GlobalColor.green)
            else:
                item_status.setForeground(Qt.GlobalColor.red)
            self.table.setItem(idx, 1, item_status)

    def _on_selection_changed(self) -> None:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self.details_box.clear()
            return
        row = selected_rows[0].row()
        if 0 <= row < len(self.results):
            self.details_box.setText(self.results[row].message)
