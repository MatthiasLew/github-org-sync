import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, List
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QProgressBar,
    QTextEdit,
    QFileDialog,
    QMessageBox,
    QFrame
)
from github_org_sync.config import ConfigManager
from github_org_sync.models.repository import Repository
from github_org_sync.models.sync_result import SyncResult
from github_org_sync.services.github_service import GitHubService, GitHubServiceError
from github_org_sync.services.validation_service import ValidationService
from github_org_sync.services.report_service import ReportService
from github_org_sync.ui.repository_table import RepositoryTable
from github_org_sync.ui.styles import get_stylesheet
from github_org_sync.workers.sync_worker import SyncWorker

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GitHub Organization Sync")
        
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load()
        
        self.github_service = GitHubService()
        self.repositories: List[Repository] = []
        self.sync_worker: SyncWorker | None = None
        self.auth_user = "unknown"
        
        # Reports tracker
        self.last_json_report: Path | None = None
        self.last_md_report: Path | None = None

        self._setup_ui()
        self._load_saved_settings()
        self.apply_styles()
        self.check_github_auth()

    def _setup_ui(self) -> None:
        # Central widget
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # Header Title
        title_label = QLabel("GitHub Organization Sync", self)
        title_label.setObjectName("headerTitle")
        main_layout.addWidget(title_label)

        # Auth Banner Warning
        self.auth_banner = QFrame(self)
        self.auth_banner.setStyleSheet("background-color: #7f1d1d; border-radius: 6px; border: 1px solid #b91c1c;")
        banner_layout = QHBoxLayout(self.auth_banner)
        banner_layout.setContentsMargins(12, 8, 12, 8)
        self.auth_label = QLabel("Checking GitHub CLI authentication status...", self)
        self.auth_label.setStyleSheet("color: #fca5a5; font-weight: bold;")
        banner_layout.addWidget(self.auth_label)
        self.btn_auth_retry = QPushButton("Retry Auth Check", self)
        self.btn_auth_retry.setObjectName("btnOutline")
        self.btn_auth_retry.clicked.connect(self.check_github_auth)
        banner_layout.addWidget(self.btn_auth_retry)
        main_layout.addWidget(self.auth_banner)
        self.auth_banner.hide()

        # Inputs Grid
        grid_widget = QWidget(self)
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(10)

        # Row 0: GitHub organization
        grid_layout.addWidget(QLabel("GitHub Organization / URL:", self), 0, 0)
        self.org_input = QLineEdit(self)
        self.org_input.setPlaceholderText("e.g. subactor or https://github.com/subactor")
        grid_layout.addWidget(self.org_input, 0, 1)
        self.btn_load = QPushButton("Load Repositories", self)
        self.btn_load.clicked.connect(self.load_repositories)
        grid_layout.addWidget(self.btn_load, 0, 2)

        # Row 1: Workspace Folder
        grid_layout.addWidget(QLabel("Local Workspace Folder:", self), 1, 0)
        self.workspace_input = QLineEdit(self)
        self.workspace_input.setReadOnly(True)
        self.workspace_input.setPlaceholderText("Select folder where repositories will be synced")
        grid_layout.addWidget(self.workspace_input, 1, 1)
        self.btn_choose_dir = QPushButton("Choose Folder", self)
        self.btn_choose_dir.setObjectName("btnOutline")
        self.btn_choose_dir.clicked.connect(self.choose_workspace)
        grid_layout.addWidget(self.btn_choose_dir, 1, 2)

        main_layout.addWidget(grid_widget)

        # Options Box
        options_widget = QWidget(self)
        options_layout = QHBoxLayout(options_widget)
        options_layout.setContentsMargins(0, 4, 0, 4)
        options_layout.setSpacing(15)

        self.cb_include_archived = QCheckBox("Include Archived", self)
        self.cb_include_forks = QCheckBox("Include Forks", self)
        self.cb_use_ssh = QCheckBox("Use SSH", self)
        self.cb_preserve_changes = QCheckBox("Preserve changes (stash)", self)
        self.cb_fetch_only = QCheckBox("Fetch only", self)
        self.cb_dry_run = QCheckBox("Dry run", self)

        options_layout.addWidget(self.cb_include_archived)
        options_layout.addWidget(self.cb_include_forks)
        options_layout.addWidget(self.cb_use_ssh)
        options_layout.addWidget(self.cb_preserve_changes)
        options_layout.addWidget(self.cb_fetch_only)
        options_layout.addWidget(self.cb_dry_run)
        options_layout.addStretch()

        main_layout.addWidget(options_widget)

        # Selection Control Row
        selection_widget = QWidget(self)
        sel_layout = QHBoxLayout(selection_widget)
        sel_layout.setContentsMargins(0, 0, 0, 0)
        sel_layout.setSpacing(8)

        btn_sel_all = QPushButton("Select All", self)
        btn_sel_all.setObjectName("btnOutline")
        btn_sel_all.clicked.connect(lambda: self.table.select_all())
        
        btn_sel_none = QPushButton("Select None", self)
        btn_sel_none.setObjectName("btnOutline")
        btn_sel_none.clicked.connect(lambda: self.table.select_none())
        
        btn_sel_missing = QPushButton("Select Missing", self)
        btn_sel_missing.setObjectName("btnOutline")
        btn_sel_missing.clicked.connect(lambda: self.table.select_missing())
        
        btn_sel_outdated = QPushButton("Select Outdated", self)
        btn_sel_outdated.setObjectName("btnOutline")
        btn_sel_outdated.clicked.connect(lambda: self.table.select_outdated())

        sel_layout.addWidget(btn_sel_all)
        sel_layout.addWidget(btn_sel_none)
        sel_layout.addWidget(btn_sel_missing)
        sel_layout.addWidget(btn_sel_outdated)
        sel_layout.addStretch()
        
        main_layout.addWidget(selection_widget)

        # Repositories Table
        self.table = RepositoryTable(self)
        main_layout.addWidget(self.table)

        # Progress Section
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Progress: %v/%m (%p%)")
        main_layout.addWidget(self.progress_bar)

        # Operations Buttons Row
        operations_widget = QWidget(self)
        ops_layout = QHBoxLayout(operations_widget)
        ops_layout.setContentsMargins(0, 0, 0, 0)
        ops_layout.setSpacing(10)

        self.btn_sync = QPushButton("Sync Selected", self)
        self.btn_sync.setObjectName("btnAction")
        self.btn_sync.clicked.connect(self.sync_selected)
        ops_layout.addWidget(self.btn_sync)

        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_sync)
        ops_layout.addWidget(self.btn_cancel)

        self.btn_open_report = QPushButton("Open Report", self)
        self.btn_open_report.setObjectName("btnOutline")
        self.btn_open_report.setEnabled(False)
        self.btn_open_report.clicked.connect(self.open_last_report)
        ops_layout.addWidget(self.btn_open_report)

        self.btn_open_ws = QPushButton("Open Workspace", self)
        self.btn_open_ws.setObjectName("btnOutline")
        self.btn_open_ws.clicked.connect(self.open_workspace_folder)
        ops_layout.addWidget(self.btn_open_ws)

        ops_layout.addStretch()
        main_layout.addWidget(operations_widget)

        # Monospaced Console Log
        self.console_log = QTextEdit(self)
        self.console_log.setObjectName("consoleLog")
        self.console_log.setReadOnly(True)
        self.console_log.setPlaceholderText("Console Output...")
        main_layout.addWidget(self.console_log)

    def apply_styles(self) -> None:
        self.setStyleSheet(get_stylesheet())

    def _load_saved_settings(self) -> None:
        self.org_input.setText(self.config.get("last_organization", ""))
        self.workspace_input.setText(self.config.get("last_workspace", ""))
        
        self.cb_include_archived.setChecked(self.config.get("include_archived", False))
        self.cb_include_forks.setChecked(self.config.get("include_forks", True))
        self.cb_use_ssh.setChecked(self.config.get("use_ssh", False))
        self.cb_preserve_changes.setChecked(self.config.get("preserve_local_changes", True))
        self.cb_fetch_only.setChecked(self.config.get("fetch_only", False))
        self.cb_dry_run.setChecked(self.config.get("dry_run", False))
        
        width = self.config.get("window_width", 1000)
        height = self.config.get("window_height", 700)
        self.resize(width, height)

    def closeEvent(self, event: Any) -> None:
        # Save settings on exit
        self.config["last_organization"] = self.org_input.text().strip()
        self.config["last_workspace"] = self.workspace_input.text().strip()
        self.config["include_archived"] = self.cb_include_archived.isChecked()
        self.config["include_forks"] = self.cb_include_forks.isChecked()
        self.config["use_ssh"] = self.cb_use_ssh.isChecked()
        self.config["preserve_local_changes"] = self.cb_preserve_changes.isChecked()
        self.config["fetch_only"] = self.cb_fetch_only.isChecked()
        self.config["dry_run"] = self.cb_dry_run.isChecked()
        
        # Window size
        self.config["window_width"] = self.width()
        self.config["window_height"] = self.height()
        
        self.config_manager.save(self.config)
        
        # Stop worker if running
        if self.sync_worker and self.sync_worker.isRunning():
            self.sync_worker.cancel()
            self.sync_worker.wait()
            
        super().closeEvent(event)

    def check_github_auth(self) -> None:
        try:
            self.github_service.check_cli_installed()
            auth_info = self.github_service.check_auth_status()
            
            # extract username if possible
            # e.g., "Logged in to github.com account MatthiasLew"
            self.auth_user = "unknown"
            for line in auth_info.splitlines():
                if "logged in" in line.lower():
                    parts = line.split()
                    if parts:
                        self.auth_user = parts[-1]
            
            self.auth_banner.hide()
            self.log(f"GitHub CLI initialized. Logged in as: {self.auth_user}")
        except GitHubServiceError as e:
            self.auth_label.setText(str(e))
            self.auth_banner.show()
            self.log(f"GitHub CLI Auth Warning: {e}")

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.console_log.append(f"[{timestamp}] {message}")

    def choose_workspace(self) -> None:
        current_dir = self.workspace_input.text().strip() or str(Path.home())
        selected_dir = QFileDialog.getExistingDirectory(self, "Select Workspace Folder", current_dir)
        if selected_dir:
            self.workspace_input.setText(selected_dir)

    def load_repositories(self) -> None:
        org_text = self.org_input.text().strip()
        if not org_text:
            QMessageBox.warning(self, "Validation Error", "Please provide a GitHub organization name or URL.")
            return

        try:
            org_name = ValidationService.normalize_org_name(org_text)
        except ValueError as e:
            QMessageBox.warning(self, "Validation Error", str(e))
            return

        self.log(f"Querying GitHub for organization: {org_name}")
        self._set_ui_busy(True)
        
        try:
            # We list repositories first (blocking UI temporarily, or we could thread it, 
            # but list is usually fast). To follow the instruction "GUI nie może się zawieszać"
            # we should avoid long blocking calls. But listing takes a brief moment. Let's do it
            # and then run the local inspection inside SyncWorker thread so the directory checking
            # (which can be slow on large workspaces) is fully async.
            all_repos = self.github_service.list_repositories(org_name)
            
            # Apply filters
            include_archived = self.cb_include_archived.isChecked()
            include_forks = self.cb_include_forks.isChecked()
            
            filtered_repos = []
            for repo in all_repos:
                if repo.is_archived and not include_archived:
                    continue
                if repo.is_fork and not include_forks:
                    continue
                filtered_repos.append(repo)
                
            self.repositories = filtered_repos
            self.log(f"Discovered {len(filtered_repos)} matching repositories.")
            
            ws_path_str = self.workspace_input.text().strip()
            if not ws_path_str:
                # If workspace is empty, we just fill the table as MISSING
                self.table.set_repositories(self.repositories)
                self._set_ui_busy(False)
                return
                
            ws_path = Path(ws_path_str)
            
            # Start asynchronous local inspection
            self.progress_bar.setMaximum(len(self.repositories))
            self.progress_bar.setValue(0)
            
            self.sync_worker = SyncWorker(
                repositories=self.repositories,
                workspace=ws_path,
                org_name=org_name,
                options={},
                mode="inspect",
                parent=self
            )
            self.sync_worker.progress_updated.connect(self._on_inspect_progress)
            self.sync_worker.log_emitted.connect(self.log)
            self.sync_worker.finished.connect(self._on_inspect_finished)
            self.sync_worker.error_occurred.connect(self._on_worker_error)
            self.sync_worker.start()
            
        except Exception as e:
            self._set_ui_busy(False)
            QMessageBox.critical(self, "GitHub Error", f"Failed to load repositories:\n{e}")
            self.log(f"GitHub Error: {e}")

    @Slot(int, int, str, str, str)
    def _on_inspect_progress(self, index: int, total: int, repo_name: str, status: str, message: str) -> None:
        self.progress_bar.setValue(index)

    @Slot(list, bool)
    def _on_inspect_finished(self, results: list, was_cancelled: bool) -> None:
        self.table.set_repositories(self.repositories)
        self._set_ui_busy(False)
        self.progress_bar.setValue(0)
        self.log("Workspace local inspection complete.")

    def sync_selected(self) -> None:
        selected_repos = self.table.get_selected_repositories()
        if not selected_repos:
            QMessageBox.warning(self, "Selection Error", "Please select at least one repository to sync.")
            return

        org_text = self.org_input.text().strip()
        ws_text = self.workspace_input.text().strip()
        
        try:
            org_name = ValidationService.normalize_org_name(org_text)
            ws_path = ValidationService.validate_workspace(ws_text)
        except Exception as e:
            QMessageBox.warning(self, "Validation Error", f"Invalid parameters: {e}")
            return

        # Ensure directory exists
        ws_path.mkdir(parents=True, exist_ok=True)

        self._set_ui_busy(True)
        self.btn_cancel.setEnabled(True)
        
        self.progress_bar.setMaximum(len(selected_repos))
        self.progress_bar.setValue(0)

        options = {
            "use_ssh": self.cb_use_ssh.isChecked(),
            "preserve_local_changes": self.cb_preserve_changes.isChecked(),
            "fetch_only": self.cb_fetch_only.isChecked(),
            "dry_run": self.cb_dry_run.isChecked(),
            "checkout_default": True # Always fetch and update using default branch option matching script
        }

        self.sync_worker = SyncWorker(
            repositories=selected_repos,
            workspace=ws_path,
            org_name=org_name,
            options=options,
            mode="sync",
            parent=self
        )
        self.sync_worker.progress_updated.connect(self._on_sync_progress)
        self.sync_worker.log_emitted.connect(self.log)
        self.sync_worker.finished.connect(self._on_sync_finished)
        self.sync_worker.error_occurred.connect(self._on_worker_error)
        self.sync_worker.start()

    @Slot(int, int, str, str, str)
    def _on_sync_progress(self, index: int, total: int, repo_name: str, status: str, message: str) -> None:
        self.progress_bar.setValue(index)
        self.table.update_repository_status(repo_name, status, message)

    @Slot(list, bool)
    def _on_sync_finished(self, results: List[SyncResult], was_cancelled: bool) -> None:
        self._set_ui_busy(False)
        self.btn_cancel.setEnabled(False)
        
        if not results:
            self.log("Synchronization completed with empty results.")
            return

        # Generate Reports
        org_name = ValidationService.normalize_org_name(self.org_input.text().strip())
        ws_path = Path(self.workspace_input.text().strip())
        
        options = {
            "use_ssh": self.cb_use_ssh.isChecked(),
            "preserve_local_changes": self.cb_preserve_changes.isChecked(),
            "fetch_only": self.cb_fetch_only.isChecked(),
            "dry_run": self.cb_dry_run.isChecked(),
        }
        
        try:
            json_path, md_path = ReportService.generate_reports(
                organization=org_name,
                workspace=ws_path,
                auth_user=self.auth_user,
                protocol="ssh" if self.cb_use_ssh.isChecked() else "https",
                options=options,
                results=results
            )
            self.last_json_report = json_path
            self.last_md_report = md_path
            self.btn_open_report.setEnabled(True)
            self.log(f"Generated JSON report: {json_path}")
            self.log(f"Generated Markdown report: {md_path}")
        except Exception as e:
            self.log(f"Failed to generate reports: {e}")

        # Show final summary box
        if not was_cancelled:
            success_count = sum(1 for r in results if r.status in ("CLONED", "UPDATED", "UP_TO_DATE", "FETCHED"))
            fail_count = sum(1 for r in results if r.status in ("FAILED", "CONFLICT"))
            QMessageBox.information(
                self, 
                "Sync Finished", 
                f"Synchronization completed.\n\nSuccessful: {success_count}\nFailed/Conflicts: {fail_count}"
            )

    @Slot(str)
    def _on_worker_error(self, error_message: str) -> None:
        self._set_ui_busy(False)
        self.btn_cancel.setEnabled(False)
        QMessageBox.critical(self, "Sync Error", f"Sync process encountered an error:\n{error_message}")
        self.log(f"Error: {error_message}")

    def cancel_sync(self) -> None:
        if self.sync_worker and self.sync_worker.isRunning():
            self.btn_cancel.setEnabled(False)
            self.sync_worker.cancel()

    def open_last_report(self) -> None:
        if self.last_md_report and self.last_md_report.exists():
            try:
                # Open markdown file in default system editor
                if os.name == "nt":
                    os.startfile(self.last_md_report)
                else:
                    subprocess.run(["xdg-open", str(self.last_md_report)])
            except Exception as e:
                QMessageBox.warning(self, "Open Report Failed", f"Could not open report file:\n{e}")

    def open_workspace_folder(self) -> None:
        ws_text = self.workspace_input.text().strip()
        if ws_text and Path(ws_text).exists():
            try:
                if os.name == "nt":
                    os.startfile(ws_text)
                else:
                    subprocess.run(["xdg-open", ws_text])
            except Exception as e:
                QMessageBox.warning(self, "Open Workspace Failed", f"Could not open workspace:\n{e}")
        else:
            QMessageBox.warning(self, "Open Workspace Failed", "Workspace folder does not exist or has not been chosen.")

    def _set_ui_busy(self, busy: bool) -> None:
        self.btn_load.setEnabled(not busy)
        self.btn_choose_dir.setEnabled(not busy)
        self.btn_sync.setEnabled(not busy)
        self.org_input.setEnabled(not busy)
        
        self.cb_include_archived.setEnabled(not busy)
        self.cb_include_forks.setEnabled(not busy)
        self.cb_use_ssh.setEnabled(not busy)
        self.cb_preserve_changes.setEnabled(not busy)
        self.cb_fetch_only.setEnabled(not busy)
        self.cb_dry_run.setEnabled(not busy)
