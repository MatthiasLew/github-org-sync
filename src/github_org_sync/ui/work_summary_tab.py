"""Work Summary Tab for viewing and generating monthly GitHub contribution reports."""

from typing import Any

from PySide6.QtCore import QDate, Qt, Slot
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from github_org_sync.i18n import _t
from github_org_sync.services.work_summary_service import WorkSummaryService
from github_org_sync.workers.work_summary_worker import WorkSummaryWorker


class WorkSummaryTab(QWidget):
    def __init__(self, main_window: Any) -> None:
        super().__init__(main_window)
        self.main_window = main_window
        self.service = WorkSummaryService()
        self.worker: WorkSummaryWorker | None = None
        self.current_report: dict[str, Any] | None = None
        self.current_user: str = ""

        self._setup_ui()
        self.retranslate_ui()
        self._detect_user()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Control Panel GroupBox
        self.card_controls = QGroupBox(self)
        self.card_controls.setObjectName("cardContainer")
        controls_layout = QVBoxLayout(self.card_controls)
        controls_layout.setContentsMargins(12, 12, 12, 12)
        controls_layout.setSpacing(10)

        # Top row: User info & Date selectors
        row_top = QHBoxLayout()
        row_top.setSpacing(12)

        self.account_label = QLabel(self)
        self.account_label.setStyleSheet("font-weight: bold;")
        row_top.addWidget(self.account_label)
        row_top.addStretch()

        self.label_year = QLabel(self)
        row_top.addWidget(self.label_year)
        self.year_combo = QComboBox(self)
        now = QDate.currentDate()
        for y in range(now.year() - 5, now.year() + 2):
            self.year_combo.addItem(str(y), y)
        self.year_combo.setCurrentText(str(now.year()))
        row_top.addWidget(self.year_combo)

        self.label_month = QLabel(self)
        row_top.addWidget(self.label_month)
        self.month_combo = QComboBox(self)
        for m in range(1, 13):
            self.month_combo.addItem(f"{m:02d}", m)
        self.month_combo.setCurrentIndex(now.month() - 1)
        row_top.addWidget(self.month_combo)

        controls_layout.addLayout(row_top)

        # Middle row: Filters (Scope and Exclude)
        row_filters = QHBoxLayout()
        row_filters.setSpacing(12)

        self.scope_combo = QComboBox(self)
        self.scope_combo.addItem("", "all")
        self.scope_combo.addItem("", "org")
        row_filters.addWidget(self.scope_combo)

        self.label_exclude = QLabel(self)
        row_filters.addWidget(self.label_exclude)
        self.exclude_input = QLineEdit(self)
        self.exclude_input.setPlaceholderText("MatthiasLew")
        row_filters.addWidget(self.exclude_input)

        self.btn_generate = QPushButton(self)
        self.btn_generate.setObjectName("btnAction")
        self.btn_generate.clicked.connect(self.generate_summary)
        row_filters.addWidget(self.btn_generate)

        controls_layout.addLayout(row_filters)
        layout.addWidget(self.card_controls)

        # Stats banner
        self.stats_card = QGroupBox(self)
        self.stats_card.setObjectName("cardContainer")
        stats_layout = QHBoxLayout(self.stats_card)
        stats_layout.setContentsMargins(12, 8, 12, 8)
        self.stats_label = QLabel(self)
        self.stats_label.setStyleSheet("font-size: 13px; font-weight: 600;")
        stats_layout.addWidget(self.stats_label)
        layout.addWidget(self.stats_card)

        # Splitter with details
        splitter = QSplitter(self)
        splitter.setOrientation(Qt.Orientation.Horizontal)

        # Left column: Projects and Key Areas
        left_widget = QWidget(splitter)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self.label_projects = QLabel(self)
        self.label_projects.setStyleSheet("font-weight: bold;")
        left_layout.addWidget(self.label_projects)
        self.projects_edit = QTextEdit(self)
        self.projects_edit.setReadOnly(True)
        left_layout.addWidget(self.projects_edit)

        self.label_learned = QLabel(self)
        self.label_learned.setStyleSheet("font-weight: bold;")
        left_layout.addWidget(self.label_learned)
        self.learned_edit = QTextEdit(self)
        self.learned_edit.setReadOnly(True)
        left_layout.addWidget(self.learned_edit)

        splitter.addWidget(left_widget)

        # Right column: Markdown view
        right_widget = QWidget(splitter)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.label_markdown = QLabel(self)
        self.label_markdown.setStyleSheet("font-weight: bold;")
        right_layout.addWidget(self.label_markdown)

        self.markdown_edit = QTextEdit(self)
        self.markdown_edit.setObjectName("consoleLog")
        self.markdown_edit.setReadOnly(True)
        font = QFont("Consolas, Courier New, monospace")
        font.setPointSize(10)
        self.markdown_edit.setFont(font)
        right_layout.addWidget(self.markdown_edit)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        # Bottom Action Buttons
        row_actions = QHBoxLayout()
        row_actions.setSpacing(10)

        self.btn_copy = QPushButton(self)
        self.btn_copy.setObjectName("btnOutline")
        self.btn_copy.clicked.connect(self.copy_report)
        row_actions.addWidget(self.btn_copy)

        self.btn_export_md = QPushButton(self)
        self.btn_export_md.setObjectName("btnOutline")
        self.btn_export_md.clicked.connect(self.export_markdown)
        row_actions.addWidget(self.btn_export_md)

        self.btn_export_json = QPushButton(self)
        self.btn_export_json.setObjectName("btnOutline")
        self.btn_export_json.clicked.connect(self.export_json)
        row_actions.addWidget(self.btn_export_json)

        row_actions.addStretch()
        self.status_label = QLabel(self)
        row_actions.addWidget(self.status_label)

        layout.addLayout(row_actions)

    def _detect_user(self) -> None:
        if not self.service.check_gh():
            self.account_label.setText(_t("summary_error_gh"))
            self.btn_generate.setEnabled(False)
            return
        try:
            self.current_user = self.service.get_current_user()
            self.account_label.setText(_t("summary_account_label", account=self.current_user))
            if not self.exclude_input.text():
                self.exclude_input.setText(self.current_user)
        except Exception:
            self.account_label.setText(_t("summary_account_label", account="unknown"))

    def retranslate_ui(self) -> None:
        """Update texts upon language change."""
        self.card_controls.setTitle(_t("tab_summary"))
        user_display = self.current_user or "—"
        self.account_label.setText(_t("summary_account_label", account=user_display))
        self.label_year.setText(_t("summary_year_label"))
        self.label_month.setText(_t("summary_month_label"))
        self.label_exclude.setText(_t("summary_exclude_label"))
        self.btn_generate.setText(_t("summary_generate_btn"))

        org_name = ""
        if hasattr(self.main_window, "org_input") and self.main_window.org_input.text().strip():
            org_name = self.main_window.org_input.text().strip()
        elif hasattr(self.main_window, "current_org") and self.main_window.current_org:
            org_name = str(self.main_window.current_org)
        else:
            org_name = "org"

        self.scope_combo.setItemText(0, _t("summary_scope_all"))
        self.scope_combo.setItemText(1, _t("summary_scope_org", org=org_name))

        if self.current_report:
            self.stats_label.setText(
                _t(
                    "summary_stats_label",
                    repos=len(self.current_report.get("repositories", [])),
                    commits=self.current_report.get("total_commits", 0),
                    prs=self.current_report.get("total_prs", 0),
                )
            )
        else:
            self.stats_label.setText(_t("summary_stats_label", repos=0, commits=0, prs=0))

        self.label_projects.setText(_t("summary_projects_label"))
        self.label_learned.setText(_t("summary_learned_label"))
        self.label_markdown.setText(_t("summary_markdown_label"))
        self.btn_copy.setText(_t("summary_btn_copy"))
        self.btn_export_md.setText(_t("summary_btn_export_md"))
        self.btn_export_json.setText(_t("summary_btn_export_json"))

    def generate_summary(self) -> None:
        """Trigger asynchronous work summary generation."""
        if not self.current_user:
            self._detect_user()
            if not self.current_user:
                QMessageBox.warning(self, "GitHub CLI", _t("summary_error_gh"))
                return

        year = int(self.year_combo.currentData())
        month = int(self.month_combo.currentData())
        scope = str(self.scope_combo.currentData())

        target_org = None
        if scope == "org":
            if hasattr(self.main_window, "org_input") and self.main_window.org_input.text().strip():
                target_org = self.main_window.org_input.text().strip()
            elif hasattr(self.main_window, "current_org") and self.main_window.current_org:
                target_org = str(self.main_window.current_org)

        exclude_owner = self.exclude_input.text().strip() or None

        self.btn_generate.setEnabled(False)
        self.status_label.setText(_t("summary_generating"))

        self.worker = WorkSummaryWorker(
            login=self.current_user,
            year=year,
            month=month,
            excluded_owner=exclude_owner,
            target_org=target_org,
            parent=self,
        )
        self.worker.signals.finished.connect(self._on_summary_finished)
        self.worker.signals.error_occurred.connect(self._on_summary_error)
        self.worker.signals.log_emitted.connect(
            lambda msg: self.main_window.append_log(msg) if hasattr(self.main_window, "append_log") else None
        )
        self.worker.start()

    @Slot(dict)
    def _on_summary_finished(self, result: dict[str, Any]) -> None:
        self.current_report = result
        self.btn_generate.setEnabled(True)
        self.status_label.setText(_t("status_done"))

        repos_count = len(result.get("repositories", []))
        commits_count = result.get("total_commits", 0)
        prs_count = result.get("total_prs", 0)

        self.stats_label.setText(_t("summary_stats_label", repos=repos_count, commits=commits_count, prs=prs_count))

        projects_lines = [
            f"• {p['name']} ({p.get('language') or '—'}): {p.get('commits', 0)} commits, {p.get('prs', 0)} PRs"
            for p in result.get("projects", [])
        ]
        self.projects_edit.setPlainText("\n".join(projects_lines) if projects_lines else _t("summary_no_data"))

        learned_lines = [f"• {item}" for item in result.get("what_learned", [])]
        self.learned_edit.setPlainText("\n".join(learned_lines) if learned_lines else _t("summary_no_data"))

        md_content = self.service.generate_markdown(result)
        self.markdown_edit.setPlainText(md_content)

    @Slot(str)
    def _on_summary_error(self, err_msg: str) -> None:
        self.btn_generate.setEnabled(True)
        self.status_label.setText(err_msg)
        QMessageBox.critical(self, "Error", err_msg)

    def copy_report(self) -> None:
        text = self.markdown_edit.toPlainText()
        if not text:
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
            self.status_label.setText(_t("summary_copied_msg"))

    def export_markdown(self) -> None:
        if not self.current_report:
            return
        month = self.current_report.get("month", "summary")
        default_name = f"work-summary-{month}.md"
        path, _ = QFileDialog.getSaveFileName(self, _t("summary_btn_export_md"), default_name, "Markdown (*.md)")
        if path:
            saved_path, _ = self.service.save_reports(self.current_report, md_path=path)
            if saved_path:
                self.status_label.setText(_t("summary_saved_msg", path=str(saved_path)))

    def export_json(self) -> None:
        if not self.current_report:
            return
        month = self.current_report.get("month", "summary")
        default_name = f"work-summary-{month}.json"
        path, _ = QFileDialog.getSaveFileName(self, _t("summary_btn_export_json"), default_name, "JSON (*.json)")
        if path:
            _, saved_path = self.service.save_reports(self.current_report, json_path=path)
            if saved_path:
                self.status_label.setText(_t("summary_saved_msg", path=str(saved_path)))
