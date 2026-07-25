import contextlib
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from github_org_sync import __version__
from github_org_sync.config import ConfigManager
from github_org_sync.i18n import _t, translator
from github_org_sync.models.repository import Repository
from github_org_sync.models.sync_result import SyncResult
from github_org_sync.services.git_service import GitService
from github_org_sync.services.github_service import GitHubService, GitHubServiceError
from github_org_sync.services.report_service import ReportService
from github_org_sync.services.validation_service import ValidationService
from github_org_sync.ui.repository_table import RepositoryTable
from github_org_sync.ui.styles import get_stylesheet
from github_org_sync.ui.update_dialog import UpdateDialog
from github_org_sync.utils.process import run_process
from github_org_sync.workers.sync_worker import SyncWorker
from github_org_sync.workers.update_worker import UpdateCheckWorker
from github_org_sync.workers.workspace_scan_worker import WorkspaceScanWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("MainWindow")

        # Set taskbar app ID for Windows grouping
        if sys.platform == "win32":
            import ctypes

            with contextlib.suppress(Exception):
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("github-org-sync.v1")

        self.config_manager = ConfigManager()
        self.config = self.config_manager.load()

        # Set window icon
        from PySide6.QtGui import QIcon

        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            assets_dir = Path(sys._MEIPASS) / "assets"
        else:
            assets_dir = Path(__file__).resolve().parent.parent.parent.parent / "assets"
        logo_png = assets_dir / "icons" / "app-256.png"
        if logo_png.exists():
            self.setWindowIcon(QIcon(str(logo_png)))

        # Set default language from config
        lang = self.config.get("language", "pl")
        translator.set_language(lang)

        self.github_service = GitHubService()
        self.git_service = GitService()
        self.gh_cli_available = False
        self.repositories: list[Repository] = []
        self.sync_worker: SyncWorker | WorkspaceScanWorker | None = None
        self.auth_user = "unknown"
        self.app_state = "IDLE"

        # Debounce timer for org input
        self.org_debounce_timer = QTimer(self)
        self.org_debounce_timer.setSingleShot(True)
        self.org_debounce_timer.timeout.connect(self._on_org_debounce_timeout)

        # Reports tracker
        self.last_json_report: Path | None = None
        self.last_md_report: Path | None = None
        self.table: RepositoryTable

        self._setup_ui()
        self._load_saved_settings()
        self.apply_styles()
        self.check_github_auth()

        # Enforce initial IDLE state
        self._set_app_state("IDLE")

        self.check_for_updates_silently()

    def _setup_ui(self) -> None:
        # Central widget
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # Header Title
        self.title_label = QLabel("GitHub Organization Sync", self)
        self.title_label.setObjectName("headerTitle")
        main_layout.addWidget(self.title_label)

        # Auth Banner Warning
        self.auth_banner = QFrame(self)
        self.auth_banner.setStyleSheet("background-color: #7f1d1d; border-radius: 6px; border: 1px solid #b91c1c;")
        banner_layout = QHBoxLayout(self.auth_banner)
        banner_layout.setContentsMargins(12, 8, 12, 8)
        self.auth_label = QLabel(self.auth_banner)
        self.auth_label.setStyleSheet("color: #fca5a5; font-weight: bold;")
        banner_layout.addWidget(self.auth_label)
        self.btn_auth_retry = QPushButton(self.auth_banner)
        self.btn_auth_retry.setObjectName("btnOutline")
        self.btn_auth_retry.clicked.connect(self.check_github_auth)
        banner_layout.addWidget(self.btn_auth_retry)
        main_layout.addWidget(self.auth_banner)
        self.auth_banner.hide()

        # Update Notification Banner
        self.update_banner = QFrame(self)
        self.update_banner.setStyleSheet("background-color: #1e3a8a; border-radius: 6px; border: 1px solid #3b82f6;")
        update_banner_layout = QHBoxLayout(self.update_banner)
        update_banner_layout.setContentsMargins(12, 8, 12, 8)
        self.update_label = QLabel(self.update_banner)
        self.update_label.setStyleSheet("color: #93c5fd; font-weight: bold;")
        update_banner_layout.addWidget(self.update_label)
        self.btn_update_action = QPushButton(self.update_banner)
        self.btn_update_action.setObjectName("btnOutline")
        self.btn_update_action.clicked.connect(self._show_update_dialog_from_banner)
        update_banner_layout.addWidget(self.btn_update_action)
        main_layout.addWidget(self.update_banner)
        self.update_banner.hide()

        # Mode Switch Selector Row
        self.mode_widget = QWidget(self)
        mode_layout = QHBoxLayout(self.mode_widget)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(8)

        self.btn_mode_clone = QPushButton(self)
        self.btn_mode_clone.setObjectName("btnMode")
        self.btn_mode_clone.setCheckable(True)
        self.btn_mode_clone.setAutoExclusive(True)
        self.btn_mode_clone.clicked.connect(lambda: self.switch_mode("clone"))
        mode_layout.addWidget(self.btn_mode_clone)

        self.btn_mode_workspace = QPushButton(self)
        self.btn_mode_workspace.setObjectName("btnMode")
        self.btn_mode_workspace.setCheckable(True)
        self.btn_mode_workspace.setAutoExclusive(True)
        self.btn_mode_workspace.clicked.connect(lambda: self.switch_mode("workspace"))
        mode_layout.addWidget(self.btn_mode_workspace)

        mode_layout.addStretch()
        main_layout.addWidget(self.mode_widget)

        # Workspace Path Selector (Common to both modes)
        ws_widget = QWidget(self)
        ws_layout = QGridLayout(ws_widget)
        ws_layout.setContentsMargins(0, 0, 0, 0)
        ws_layout.setSpacing(10)

        self.label_workspace = QLabel(self)
        ws_layout.addWidget(self.label_workspace, 0, 0)
        self.workspace_input = QLineEdit(self)
        self.workspace_input.setReadOnly(True)
        ws_layout.addWidget(self.workspace_input, 0, 1)
        self.btn_choose_dir = QPushButton(self)
        self.btn_choose_dir.setObjectName("btnOutline")
        self.btn_choose_dir.clicked.connect(self.choose_workspace)
        ws_layout.addWidget(self.btn_choose_dir, 0, 2)

        main_layout.addWidget(ws_widget)

        # Stacked Panel
        self.stacked_widget = QStackedWidget(self)

        # Page 0: Clone Organization Panel
        page_clone = QWidget()
        page_clone_layout = QVBoxLayout(page_clone)
        page_clone_layout.setContentsMargins(0, 0, 0, 0)
        page_clone_layout.setSpacing(10)

        clone_grid = QWidget()
        clone_grid_layout = QGridLayout(clone_grid)
        clone_grid_layout.setContentsMargins(0, 0, 0, 0)
        clone_grid_layout.setSpacing(10)

        self.label_org = QLabel(self)
        clone_grid_layout.addWidget(self.label_org, 0, 0)
        self.org_input = QLineEdit(self)
        self.org_input.textChanged.connect(self._on_org_text_changed)
        clone_grid_layout.addWidget(self.org_input, 0, 1)

        load_btn_layout = QHBoxLayout()
        load_btn_layout.setSpacing(6)
        self.btn_load = QPushButton(self)
        self.btn_load.clicked.connect(self.load_repositories)
        load_btn_layout.addWidget(self.btn_load)

        self.btn_refresh = QPushButton(self)
        self.btn_refresh.setObjectName("btnOutline")
        self.btn_refresh.clicked.connect(self.refresh_status)
        load_btn_layout.addWidget(self.btn_refresh)

        clone_grid_layout.addLayout(load_btn_layout, 0, 2)
        page_clone_layout.addWidget(clone_grid)

        # Options Box
        self.options_widget = QWidget(self)
        options_layout = QHBoxLayout(self.options_widget)
        options_layout.setContentsMargins(0, 4, 0, 4)
        options_layout.setSpacing(15)

        self.cb_include_archived = QCheckBox(self)
        self.cb_include_forks = QCheckBox(self)
        self.cb_use_ssh = QCheckBox(self)
        self.cb_preserve_changes = QCheckBox(self)
        self.cb_fetch_only = QCheckBox(self)
        self.cb_dry_run = QCheckBox(self)
        self.cb_follow = QCheckBox(self)
        self.cb_follow.toggled.connect(self._on_follow_toggled)

        options_layout.addWidget(self.cb_include_archived)
        options_layout.addWidget(self.cb_include_forks)
        options_layout.addWidget(self.cb_use_ssh)
        options_layout.addWidget(self.cb_preserve_changes)
        options_layout.addWidget(self.cb_fetch_only)
        options_layout.addWidget(self.cb_dry_run)
        options_layout.addWidget(self.cb_follow)
        options_layout.addStretch()

        page_clone_layout.addWidget(self.options_widget)
        self.stacked_widget.addWidget(page_clone)

        # Page 1: Open Existing Workspace Panel
        page_ws = QWidget()
        page_ws_layout = QVBoxLayout(page_ws)
        page_ws_layout.setContentsMargins(0, 0, 0, 0)
        page_ws_layout.setSpacing(10)

        ws_grid = QWidget()
        ws_grid_layout = QGridLayout(ws_grid)
        ws_grid_layout.setContentsMargins(0, 0, 0, 0)
        ws_grid_layout.setSpacing(10)

        self.cb_scan_recursive = QCheckBox(self)
        ws_grid_layout.addWidget(self.cb_scan_recursive, 0, 0, 1, 2)

        scan_btn_layout = QHBoxLayout()
        scan_btn_layout.setSpacing(6)
        self.btn_scan_workspace = QPushButton(self)
        self.btn_scan_workspace.clicked.connect(self.scan_workspace)
        scan_btn_layout.addWidget(self.btn_scan_workspace)

        self.btn_refresh_ws = QPushButton(self)
        self.btn_refresh_ws.setObjectName("btnOutline")
        self.btn_refresh_ws.clicked.connect(self.refresh_status)
        scan_btn_layout.addWidget(self.btn_refresh_ws)

        ws_grid_layout.addLayout(scan_btn_layout, 0, 2)

        # Row 1: Group filter & Detected org
        self.label_group_filter = QLabel(self)
        ws_grid_layout.addWidget(self.label_group_filter, 1, 0)
        self.group_filter_cb = QComboBox(self)
        self.group_filter_cb.currentTextChanged.connect(self.apply_table_filters)
        ws_grid_layout.addWidget(self.group_filter_cb, 1, 1)

        self.detected_org_label = QLabel(self)
        self.detected_org_label.setStyleSheet("font-weight: bold; color: #10b981;")
        ws_grid_layout.addWidget(self.detected_org_label, 1, 2)

        # Row 2: Compare org button
        self.btn_compare_org = QPushButton(self)
        self.btn_compare_org.setObjectName("btnOutline")
        self.btn_compare_org.clicked.connect(self.compare_workspace_with_org)
        ws_grid_layout.addWidget(self.btn_compare_org, 2, 0, 1, 3)

        page_ws_layout.addWidget(ws_grid)
        self.stacked_widget.addWidget(page_ws)

        main_layout.addWidget(self.stacked_widget)

        # Selection Control Row
        selection_widget = QWidget(self)
        sel_layout = QHBoxLayout(selection_widget)
        sel_layout.setContentsMargins(0, 0, 0, 0)
        sel_layout.setSpacing(8)

        self.btn_sel_all = QPushButton(self)
        self.btn_sel_all.setObjectName("btnOutline")
        self.btn_sel_all.clicked.connect(lambda: self.table.select_all())

        self.btn_sel_none = QPushButton(self)
        self.btn_sel_none.setObjectName("btnOutline")
        self.btn_sel_none.clicked.connect(lambda: self.table.select_none())

        self.btn_sel_missing = QPushButton(self)
        self.btn_sel_missing.setObjectName("btnOutline")
        self.btn_sel_missing.clicked.connect(lambda: self.table.select_missing())

        self.btn_sel_outdated = QPushButton(self)
        self.btn_sel_outdated.setObjectName("btnOutline")
        self.btn_sel_outdated.clicked.connect(lambda: self.table.select_outdated())

        sel_layout.addWidget(self.btn_sel_all)
        sel_layout.addWidget(self.btn_sel_none)
        sel_layout.addWidget(self.btn_sel_missing)
        sel_layout.addWidget(self.btn_sel_outdated)
        sel_layout.addStretch()

        main_layout.addWidget(selection_widget)

        # Search & Filter Row
        filter_widget = QWidget(self)
        filter_layout = QHBoxLayout(filter_widget)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(10)

        self.search_input = QLineEdit(self)
        self.search_input.textChanged.connect(self.apply_table_filters)
        filter_layout.addWidget(self.search_input)

        self.status_filter_cb = QComboBox(self)
        self.status_filter_cb.currentTextChanged.connect(self.apply_table_filters)
        filter_layout.addWidget(self.status_filter_cb)

        filter_layout.addStretch()
        main_layout.addWidget(filter_widget)

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

        self.btn_sync = QPushButton(self)
        self.btn_sync.setObjectName("btnAction")
        self.btn_sync.clicked.connect(self.sync_selected)
        ops_layout.addWidget(self.btn_sync)

        self.btn_wizard = QPushButton(self)
        self.btn_wizard.setObjectName("btnOutline")
        self.btn_wizard.clicked.connect(self.run_workspace_wizard)
        ops_layout.addWidget(self.btn_wizard)

        self.btn_cancel = QPushButton(self)
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_sync)
        ops_layout.addWidget(self.btn_cancel)

        self.btn_open_report = QPushButton(self)
        self.btn_open_report.setObjectName("btnOutline")
        self.btn_open_report.setEnabled(False)
        self.btn_open_report.clicked.connect(self.open_last_report)
        ops_layout.addWidget(self.btn_open_report)

        self.btn_open_ws = QPushButton(self)
        self.btn_open_ws.setObjectName("btnOutline")
        self.btn_open_ws.clicked.connect(self.open_workspace_folder)
        ops_layout.addWidget(self.btn_open_ws)

        ops_layout.addStretch()
        main_layout.addWidget(operations_widget)

        # Labeled Logs Panel
        log_header_widget = QWidget(self)
        log_header_layout = QHBoxLayout(log_header_widget)
        log_header_layout.setContentsMargins(0, 0, 0, 0)

        self.label_logs = QLabel(self)
        log_header_layout.addWidget(self.label_logs)
        log_header_layout.addStretch()

        self.btn_clear_log = QPushButton(self)
        self.btn_clear_log.setObjectName("btnOutline")
        self.btn_clear_log.clicked.connect(self.console_log_clear)
        log_header_layout.addWidget(self.btn_clear_log)
        main_layout.addWidget(log_header_widget)

        # Monospaced Console Log
        self.console_log = QTextEdit(self)
        self.console_log.setObjectName("consoleLog")
        self.console_log.setReadOnly(True)
        self.console_log.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.console_log.customContextMenuRequested.connect(self._show_log_context_menu)
        main_layout.addWidget(self.console_log)

        # Setup Menu Bar
        self._setup_menu_bar()

        # Keyboard shortcuts
        self._setup_shortcuts()

    def _setup_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        # Settings
        self.menu_settings = menu_bar.addMenu("")

        # Language Submenu
        self.menu_language = self.menu_settings.addMenu("")
        self.act_lang_pl = self.menu_language.addAction("Polski")
        self.act_lang_pl.setCheckable(True)
        self.act_lang_pl.triggered.connect(lambda: self.change_language("pl"))

        self.act_lang_en = self.menu_language.addAction("English")
        self.act_lang_en.setCheckable(True)
        self.act_lang_en.triggered.connect(lambda: self.change_language("en"))

        # Theme Submenu
        self.menu_theme = self.menu_settings.addMenu("")
        self.act_theme_sys = self.menu_theme.addAction("")
        self.act_theme_sys.setCheckable(True)
        self.act_theme_sys.triggered.connect(lambda: self.change_theme("System"))

        self.act_theme_light = self.menu_theme.addAction("")
        self.act_theme_light.setCheckable(True)
        self.act_theme_light.triggered.connect(lambda: self.change_theme("Light"))

        self.act_theme_dark = self.menu_theme.addAction("")
        self.act_theme_dark.setCheckable(True)
        self.act_theme_dark.triggered.connect(lambda: self.change_theme("Dark"))

        # Help
        self.menu_help = menu_bar.addMenu("")
        self.act_getting_started = self.menu_help.addAction("")
        self.act_getting_started.triggered.connect(self.show_getting_started)

        self.act_about = self.menu_help.addAction("")
        self.act_about.triggered.connect(self.show_about)

        self.menu_help.addSeparator()
        self.act_check_updates = self.menu_help.addAction("")
        self.act_check_updates.triggered.connect(self.check_for_updates_manually)

        self.retranslate_ui()
        self.update_menu_checks()

    def _setup_shortcuts(self) -> None:
        self.shortcut_load = QShortcut(QKeySequence("Ctrl+L"), self)
        self.shortcut_load.activated.connect(self.load_repositories)

        self.shortcut_refresh = QShortcut(QKeySequence("Ctrl+R"), self)
        self.shortcut_refresh.activated.connect(self.refresh_status)

        self.shortcut_sync = QShortcut(QKeySequence("Ctrl+Shift+S"), self)
        self.shortcut_sync.activated.connect(self.sync_selected)

        self.shortcut_search = QShortcut(QKeySequence("Ctrl+F"), self)
        self.shortcut_search.activated.connect(self.search_input.setFocus)

        self.shortcut_help = QShortcut(QKeySequence("F1"), self)
        self.shortcut_help.activated.connect(self.show_getting_started)

    def retranslate_ui(self) -> None:
        """Applies translations to all user-facing GUI elements in real-time."""
        self.setWindowTitle("GitHub Organization Sync")
        self.title_label.setText("GitHub Organization Sync")

        # Mode selector buttons
        self.btn_mode_clone.setText(_t("mode_clone"))
        self.btn_mode_workspace.setText(_t("mode_workspace"))

        # Workspace scanning panel buttons & labels
        self.cb_scan_recursive.setText(_t("label_scan_recursive"))
        self.btn_scan_workspace.setText(_t("btn_scan"))
        self.btn_refresh_ws.setText(_t("btn_refresh"))
        self.btn_refresh_ws.setToolTip(_t("tip_refresh_btn"))
        self.label_group_filter.setText(_t("label_group_filter"))
        self.btn_compare_org.setText(_t("btn_compare_org"))

        # Inputs labels & placeholders
        self.label_org.setText(_t("label_org"))
        self.org_input.setPlaceholderText(_t("tip_org_input"))
        self.org_input.setToolTip(_t("tip_org_input"))
        self.label_workspace.setText(_t("label_workspace"))
        self.workspace_input.setPlaceholderText(_t("tip_workspace_input"))
        self.workspace_input.setToolTip(_t("tip_workspace_input"))

        # Top Buttons
        self.btn_load.setText(_t("btn_load"))
        self.btn_load.setToolTip(_t("tip_load_btn"))
        self.btn_refresh.setText(_t("btn_refresh"))
        self.btn_refresh.setToolTip(_t("tip_refresh_btn"))
        self.btn_choose_dir.setText(_t("btn_choose_dir"))
        self.btn_choose_dir.setToolTip(_t("tip_choose_dir"))

        # Option Checkboxes
        self.cb_include_archived.setText(_t("label_include_archived"))
        self.cb_include_archived.setToolTip(_t("tip_include_archived"))
        self.cb_include_forks.setText(_t("label_include_forks"))
        self.cb_include_forks.setToolTip(_t("tip_include_forks"))
        self.cb_use_ssh.setText(_t("label_use_ssh"))
        self.cb_use_ssh.setToolTip(_t("tip_use_ssh"))
        self.cb_preserve_changes.setText(_t("label_preserve_changes"))
        self.cb_preserve_changes.setToolTip(_t("tip_preserve_changes"))
        self.cb_fetch_only.setText(_t("label_fetch_only"))
        self.cb_fetch_only.setToolTip(_t("tip_fetch_only"))
        self.cb_dry_run.setText(_t("label_dry_run"))
        self.cb_dry_run.setToolTip(_t("tip_dry_run"))
        self.cb_follow.setText(_t("chk_follow"))

        # Selection Control Row
        self.btn_sel_all.setText(_t("btn_sel_all"))
        self.btn_sel_none.setText(_t("btn_sel_none"))
        self.btn_sel_missing.setText(_t("btn_sel_missing"))
        self.btn_sel_outdated.setText(_t("btn_sel_outdated"))

        # Search & Filter
        self.search_input.setPlaceholderText(_t("search_placeholder"))
        self.search_input.setToolTip(_t("tip_search"))
        self.status_filter_cb.setToolTip(_t("tip_status_filter"))
        self.populate_status_filter()

        # Progress bar default format
        self.progress_bar.setFormat(_t("col_select") + ": %v/%m (%p%)")

        # Operations Buttons Row
        self.btn_sync.setText(_t("btn_sync"))
        self.btn_sync.setToolTip(_t("tip_sync_btn"))
        self.btn_wizard.setText(_t("btn_check_update_workspace"))
        self.btn_wizard.setToolTip(_t("btn_check_update_workspace"))
        self.btn_cancel.setText(_t("btn_cancel"))
        self.btn_cancel.setToolTip(_t("tip_cancel_btn"))
        self.btn_open_report.setText(_t("btn_open_report"))
        self.btn_open_report.setToolTip(_t("tip_open_report"))
        self.btn_open_ws.setText(_t("btn_open_ws"))
        self.btn_open_ws.setToolTip(_t("tip_open_ws"))

        # Logs panel
        self.label_logs.setText(_t("col_result") + " / Log:")
        self.btn_clear_log.setText(_t("btn_clear_log"))
        self.btn_clear_log.setToolTip(_t("tip_clear_btn"))
        self.console_log.setPlaceholderText(_t("col_result") + "...")

        # Menu Titles
        self.menu_settings.setTitle(_t("menu_settings"))
        self.menu_language.setTitle(_t("menu_language"))
        self.menu_theme.setTitle(_t("menu_theme"))
        self.menu_help.setTitle(_t("menu_help"))

        self.act_theme_sys.setText(_t("theme_system"))
        self.act_theme_light.setText(_t("theme_light"))
        self.act_theme_dark.setText(_t("theme_dark"))

        self.act_getting_started.setText(_t("menu_getting_started"))
        self.act_about.setText(_t("menu_about"))
        self.act_check_updates.setText(_t("menu_check_updates"))

        if hasattr(self, "latest_version") and self.latest_version:
            self.update_label.setText(_t("update_available_banner", version=self.latest_version))
            self.btn_update_action.setText(_t("btn_update_now"))

        self.btn_auth_retry.setText(_t("btn_refresh"))

        # Refresh table translation
        self.table.retranslate_ui()

        # Update Status Bar Text
        self._update_status_bar()

    def _update_status_bar(self) -> None:
        if self.app_state == "IDLE":
            self.statusBar().showMessage(_t("status_ready"))
        elif self.app_state == "LOADING_REPOSITORIES":
            self.statusBar().showMessage(_t("status_loading_org"))
        elif self.app_state == "INSPECTING_WORKSPACE":
            self.statusBar().showMessage(_t("status_checking_cli"))
        elif self.app_state == "SCANNING_WORKSPACE":
            self.statusBar().showMessage(
                _t("status_scanning", current=self.progress_bar.value(), total=self.progress_bar.maximum(), name="...")
            )
        elif self.app_state == "SYNCING":
            self.statusBar().showMessage(
                _t("status_syncing", current=self.progress_bar.value(), total=self.progress_bar.maximum(), name="...")
            )
        elif self.app_state == "CANCELLING":
            self.statusBar().showMessage(_t("status_cancelling"))

    def change_language(self, lang: str) -> None:
        self.config["language"] = lang
        self.config_manager.save(self.config)
        translator.set_language(lang)
        self.retranslate_ui()
        self.update_menu_checks()
        self.log(f"Language changed to: {lang.upper()}")

    def change_theme(self, theme: str) -> None:
        self.config["theme"] = theme
        self.config_manager.save(self.config)
        self.apply_styles()
        self.update_menu_checks()
        self.log(f"Theme changed to: {theme}")

    def update_menu_checks(self) -> None:
        lang = self.config.get("language", "pl")
        self.act_lang_pl.setChecked(lang == "pl")
        self.act_lang_en.setChecked(lang == "en")

        theme = self.config.get("theme", "System")
        self.act_theme_sys.setChecked(theme == "System")
        self.act_theme_light.setChecked(theme == "Light")
        self.act_theme_dark.setChecked(theme == "Dark")

    def apply_styles(self) -> None:
        theme = self.config.get("theme", "System")
        self.setStyleSheet(get_stylesheet(theme))

    def _load_saved_settings(self) -> None:
        self.org_input.setText(self.config.get("last_organization", ""))
        self.workspace_input.setText(self.config.get("last_workspace", ""))

        self.cb_scan_recursive.setChecked(self.config.get("scan_recursive", False))
        mode = self.config.get("last_mode", "clone")
        self.switch_mode(mode)

        self.cb_include_archived.setChecked(self.config.get("include_archived", False))
        self.cb_include_forks.setChecked(self.config.get("include_forks", True))
        self.cb_use_ssh.setChecked(self.config.get("use_ssh", False))
        self.cb_preserve_changes.setChecked(self.config.get("preserve_local_changes", True))
        self.cb_fetch_only.setChecked(self.config.get("fetch_only", False))
        self.cb_dry_run.setChecked(self.config.get("dry_run", False))
        self.cb_follow.setChecked(self.config.get("follow_active_repo", False))

        width = self.config.get("window_width", 1000)
        height = self.config.get("window_height", 700)
        self.resize(width, height)

        x = self.config.get("window_x", -1)
        y = self.config.get("window_y", -1)
        if x >= 0 and y >= 0:
            self.move(x, y)

        widths = self.config.get("column_widths", [])
        if widths:
            self.table.set_column_widths(widths)

    def closeEvent(self, event: Any) -> None:
        # Check active runs
        if self.sync_worker and self.sync_worker.isRunning():
            reply = QMessageBox.question(
                self,
                _t("dialog_close_title"),
                _t("dialog_close_msg"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        # Save settings on exit
        self.config["last_organization"] = self.org_input.text().strip()
        self.config["last_workspace"] = self.workspace_input.text().strip()
        self.config["include_archived"] = self.cb_include_archived.isChecked()
        self.config["include_forks"] = self.cb_include_forks.isChecked()
        self.config["use_ssh"] = self.cb_use_ssh.isChecked()
        self.config["preserve_local_changes"] = self.cb_preserve_changes.isChecked()
        self.config["fetch_only"] = self.cb_fetch_only.isChecked()
        self.config["dry_run"] = self.cb_dry_run.isChecked()
        self.config["follow_active_repo"] = self.cb_follow.isChecked()
        self.config["scan_recursive"] = self.cb_scan_recursive.isChecked()
        self.config["last_mode"] = self.current_mode

        # Window size & position
        self.config["window_width"] = self.width()
        self.config["window_height"] = self.height()
        self.config["window_x"] = self.x()
        self.config["window_y"] = self.y()

        # Save column widths
        self.config["column_widths"] = self.table.get_column_widths()

        self.config_manager.save(self.config)

        # Cancel thread
        self._cancel_active_worker()

        super().closeEvent(event)

    def check_github_auth(self) -> None:
        try:
            self.github_service.check_cli_installed()
            auth_info = self.github_service.check_auth_status()

            # extract username if possible
            self.auth_user = "unknown"
            for line in auth_info.splitlines():
                if "logged in" in line.lower():
                    parts = line.split()
                    if parts:
                        self.auth_user = parts[-1]

            self.auth_banner.hide()
            self.log(f"GitHub CLI initialized. Logged in as: {self.auth_user}")
            self.gh_cli_available = True
        except GitHubServiceError as e:
            self.auth_label.setText(_t("error_gh_msg", error=str(e)))
            self.auth_banner.show()
            self.log(f"GitHub CLI Auth Warning: {e}")
            self.gh_cli_available = False

        self._update_load_button_state()

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.console_log.append(f"[{timestamp}] {message}")

    def console_log_clear(self) -> None:
        self.console_log.clear()
        self.log("Log cleared.")

    def choose_workspace(self) -> None:
        current_dir = self.workspace_input.text().strip() or str(Path.home())
        selected_dir = QFileDialog.getExistingDirectory(self, "Select Workspace Folder", current_dir)
        if selected_dir:
            self._cancel_active_worker()
            self.workspace_input.setText(selected_dir)

            # Invalidate local statuses
            for repo in self.repositories:
                repo.local_path = Path(selected_dir) / repo.name
                repo.status = "MISSING"
                repo.branch = None
                repo.ahead = None
                repo.behind = None
                repo.requested_action = None
                repo.result = None

            # Reset table and filters
            self.table.set_repositories(self.repositories)
            self.apply_table_filters()
            self.log(f"Workspace folder changed to: {selected_dir}. Local status invalidated.")

    def _cancel_active_worker(self) -> None:
        if self.sync_worker:
            if self.sync_worker.isRunning():
                self.log("Cancelling running worker thread...")
                with contextlib.suppress(Exception):
                    self.sync_worker.progress_updated.disconnect()
                with contextlib.suppress(Exception):
                    self.sync_worker.finished.disconnect()
                with contextlib.suppress(Exception):
                    self.sync_worker.log_emitted.disconnect()
                with contextlib.suppress(Exception):
                    self.sync_worker.error_occurred.disconnect()
                self.sync_worker.cancel()
                self.sync_worker.wait()
            self.sync_worker = None

    def load_repositories(self) -> None:
        org_text = self.org_input.text().strip()
        if not org_text:
            QMessageBox.warning(self, _t("error_gh_title"), _t("tip_org_input"))
            return

        try:
            org_name = ValidationService.normalize_org_name(org_text)
        except ValueError as e:
            QMessageBox.warning(self, _t("error_gh_title"), str(e))
            return

        self._cancel_active_worker()
        self.log(f"Querying GitHub for organization: {org_name}")
        self._set_app_state("LOADING_REPOSITORIES")
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()

        try:
            all_repos = self.github_service.list_repositories(org_name)

            # Filter
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
                self.table.set_repositories(self.repositories)
                self.apply_table_filters()
                self._set_app_state("IDLE")
                return

            ws_path = Path(ws_path_str)

            # Start local status inspection
            self._set_app_state("INSPECTING_WORKSPACE")
            self.progress_bar.setMaximum(len(self.repositories))
            self.progress_bar.setValue(0)

            self.sync_worker = SyncWorker(
                repositories=self.repositories,
                workspace=ws_path,
                org_name=org_name,
                options={},
                mode="inspect",
                parent=self,
            )
            self.sync_worker.progress_updated.connect(self._on_inspect_progress)
            self.sync_worker.log_emitted.connect(self.log)
            self.sync_worker.finished.connect(self._on_inspect_finished)
            self.sync_worker.error_occurred.connect(self._on_worker_error)
            self.sync_worker.start()

        except Exception as e:
            self._set_app_state("IDLE")
            QMessageBox.critical(self, _t("error_gh_title"), _t("error_gh_msg", error=str(e)))
            self.log(f"GitHub Error: {e}")

    def refresh_status(self) -> None:
        """Inspects only the local repositories status in workspace."""
        if not self.repositories:
            return

        ws_path_str = self.workspace_input.text().strip()
        if not ws_path_str:
            return

        org_text = self.org_input.text().strip()
        try:
            org_name = ValidationService.normalize_org_name(org_text)
        except Exception:
            return

        ws_path = Path(ws_path_str)
        self._cancel_active_worker()

        self.log("Refreshing status of local repositories...")
        self._set_app_state("INSPECTING_WORKSPACE")
        self.progress_bar.setMaximum(len(self.repositories))
        self.progress_bar.setValue(0)

        self.sync_worker = SyncWorker(
            repositories=self.repositories,
            workspace=ws_path,
            org_name=org_name,
            options={},
            mode="inspect",
            parent=self,
        )
        self.sync_worker.progress_updated.connect(self._on_inspect_progress)
        self.sync_worker.log_emitted.connect(self.log)
        self.sync_worker.finished.connect(self._on_inspect_finished)
        self.sync_worker.error_occurred.connect(self._on_worker_error)
        self.sync_worker.start()

    @Slot(int, int, str, str, str)
    def _on_inspect_progress(self, index: int, total: int, repo_name: str, status: str, message: str) -> None:
        self.progress_bar.setValue(index)
        self.statusBar().showMessage(_t("status_inspecting", current=index, total=total, name=repo_name))

    @Slot(list, bool)
    def _on_inspect_finished(self, results: list, was_cancelled: bool) -> None:
        self.table.set_repositories(self.repositories)
        self.apply_table_filters()
        self._set_app_state("IDLE")
        self.progress_bar.setValue(0)
        if was_cancelled:
            self.log("Workspace local inspection cancelled.")
        else:
            self.log("Workspace local inspection complete.")

    def sync_selected(self) -> None:
        selected_repos = self.table.get_selected_repositories()
        if not selected_repos:
            QMessageBox.warning(self, _t("error_open_title"), "No repositories selected.")
            return

        org_text = self.org_input.text().strip()
        ws_text = self.workspace_input.text().strip()

        try:
            org_name = ValidationService.normalize_org_name(org_text)
            ws_path = ValidationService.validate_workspace(ws_text)
        except Exception as e:
            QMessageBox.warning(self, _t("error_open_title"), f"Invalid configuration: {e}")
            return

        is_dry_run = self.cb_dry_run.isChecked()
        is_stash = self.cb_preserve_changes.isChecked()

        # Summary confirmation dialog for non-dry runs
        if not is_dry_run:
            reply = QMessageBox.question(
                self,
                _t("dialog_sync_title"),
                _t(
                    "dialog_sync_msg",
                    org=org_name,
                    workspace=ws_text,
                    count=len(selected_repos),
                    dry=_t("no_word"),
                    stash=_t("yes_word") if is_stash else _t("no_word"),
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        ws_path.mkdir(parents=True, exist_ok=True)

        self._cancel_active_worker()
        self._set_app_state("SYNCING")

        self.progress_bar.setMaximum(len(selected_repos))
        self.progress_bar.setValue(0)

        options = {
            "use_ssh": self.cb_use_ssh.isChecked(),
            "preserve_local_changes": is_stash,
            "fetch_only": self.cb_fetch_only.isChecked(),
            "dry_run": is_dry_run,
            "checkout_default": True,
        }

        self.sync_worker = SyncWorker(
            repositories=selected_repos, workspace=ws_path, org_name=org_name, options=options, mode="sync", parent=self
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
        self.statusBar().showMessage(_t("status_syncing", current=index, total=total, name=repo_name))

    @Slot(list, bool)
    def _on_sync_finished(self, results: list[SyncResult], was_cancelled: bool) -> None:
        self._set_app_state("IDLE")
        self.progress_bar.setValue(0)

        if not results:
            self.log("Synchronization finished with empty results.")
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
                results=results,
            )
            self.last_json_report = json_path
            self.last_md_report = md_path
            self.btn_open_report.setEnabled(True)
            self.log(f"Report generated successfully: {md_path.name}")
        except Exception as e:
            self.log(f"Report Generation Failed: {e}")

    @Slot(str)
    def _on_worker_error(self, error_message: str) -> None:
        self._set_app_state("IDLE")
        self.progress_bar.setValue(0)
        QMessageBox.critical(self, "Sync Error", f"Process error occurred:\n{error_message}")
        self.log(f"Process Error: {error_message}")

    def cancel_sync(self) -> None:
        if self.sync_worker and self.sync_worker.isRunning():
            self._set_app_state("CANCELLING")
            self.sync_worker.cancel()

    def open_last_report(self) -> None:
        if self.last_md_report and self.last_md_report.exists():
            try:
                if hasattr(os, "startfile"):
                    os.startfile(self.last_md_report)
                elif sys.platform == "darwin":
                    run_process(["open", str(self.last_md_report)], check=True)
                else:
                    run_process(["xdg-open", str(self.last_md_report)], check=True)
            except Exception as e:
                QMessageBox.warning(self, _t("error_open_title"), _t("error_open_msg", error=str(e)))

    def open_workspace_folder(self) -> None:
        ws_text = self.workspace_input.text().strip()
        if ws_text and Path(ws_text).exists():
            try:
                if hasattr(os, "startfile"):
                    os.startfile(ws_text)
                elif sys.platform == "darwin":
                    run_process(["open", ws_text], check=True)
                else:
                    run_process(["xdg-open", ws_text], check=True)
            except Exception as e:
                QMessageBox.warning(self, _t("error_open_title"), _t("error_open_msg", error=str(e)))
        else:
            QMessageBox.warning(self, _t("error_open_title"), _t("tip_workspace_input"))

    def _set_app_state(self, state: str) -> None:
        """Sets internal app state and controls widget enablement accordingly."""
        self.app_state = state
        self._update_status_bar()

        is_idle = state == "IDLE"
        is_loading = state == "LOADING_REPOSITORIES"
        is_inspecting = state == "INSPECTING_WORKSPACE"
        is_scanning = state == "SCANNING_WORKSPACE"
        is_syncing = state == "SYNCING"
        is_cancelling = state == "CANCELLING"

        # Mode Selection Buttons
        self.btn_mode_clone.setEnabled(is_idle)
        self.btn_mode_workspace.setEnabled(is_idle)

        # Grid inputs
        self.org_input.setEnabled(is_idle)
        self.btn_choose_dir.setEnabled(is_idle)
        self._update_load_button_state()

        # Workspace Panel Controls
        self.cb_scan_recursive.setEnabled(is_idle)
        self.btn_scan_workspace.setEnabled(is_idle)
        has_repos = len(self.repositories) > 0
        self.btn_refresh.setEnabled(is_idle and has_repos)
        self.btn_refresh_ws.setEnabled(is_idle and has_repos)
        self.group_filter_cb.setEnabled(is_idle)
        self.btn_compare_org.setEnabled(is_idle)

        # Options check boxes
        self.cb_include_archived.setEnabled(is_idle)
        self.cb_include_forks.setEnabled(is_idle)
        self.cb_use_ssh.setEnabled(is_idle)
        self.cb_preserve_changes.setEnabled(is_idle)
        self.cb_fetch_only.setEnabled(is_idle)
        self.cb_dry_run.setEnabled(is_idle)

        # Table rows & filter inputs
        self.table.setEnabled(is_idle)
        self.search_input.setEnabled(is_idle)
        self.status_filter_cb.setEnabled(is_idle)

        # Selection Control Row buttons
        self.btn_sel_all.setEnabled(is_idle and has_repos)
        self.btn_sel_none.setEnabled(is_idle and has_repos)
        self.btn_sel_missing.setEnabled(is_idle and has_repos)
        self.btn_sel_outdated.setEnabled(is_idle and has_repos)

        # Operation Row buttons
        self.btn_sync.setEnabled(is_idle and has_repos)
        self.btn_cancel.setEnabled((is_loading or is_inspecting or is_syncing or is_scanning) and not is_cancelling)
        self.btn_open_ws.setEnabled(not is_syncing)

        # Report button state
        has_report = self.last_md_report is not None and self.last_md_report.exists()
        self.btn_open_report.setEnabled(is_idle and has_report)

    def apply_table_filters(self) -> None:
        search_text = self.search_input.text()
        status_filter = self.status_filter_cb.currentText()
        self.table.filter_rows(search_text, status_filter)

    def populate_status_filter(self) -> None:
        current_text = self.status_filter_cb.currentText()
        self.status_filter_cb.blockSignals(True)
        self.status_filter_cb.clear()

        items = [
            _t("filter_status_all"),
            _t("state_MISSING"),
            _t("state_UP_TO_DATE"),
            _t("state_DIRTY"),
            _t("state_BEHIND"),
            _t("state_AHEAD"),
            _t("state_DIVERGED"),
            _t("state_FAILED"),
        ]
        self.status_filter_cb.addItems(items)

        # Restore text choice
        idx = self.status_filter_cb.findText(current_text)
        if idx >= 0:
            self.status_filter_cb.setCurrentIndex(idx)
        else:
            self.status_filter_cb.setCurrentIndex(0)

        self.status_filter_cb.blockSignals(False)

    def show_getting_started(self) -> None:
        QMessageBox.information(self, _t("help_title"), _t("help_text"), QMessageBox.StandardButton.Ok)

    def show_about(self) -> None:
        QMessageBox.information(self, _t("about_title"), _t("about_text"), QMessageBox.StandardButton.Ok)

    def check_for_updates_silently(self) -> None:
        """Starts a background thread to check for updates silently on startup."""
        if "pytest" in sys.modules or "--smoke-test" in sys.argv:
            return
        self._silent_update_worker = UpdateCheckWorker(self)
        self._silent_update_worker.finished.connect(self._on_silent_update_check_finished)
        self._silent_update_worker.start()

    def _on_silent_update_check_finished(
        self, has_update: bool, latest_version: str, release_notes: str, download_url: str
    ) -> None:
        if has_update and download_url:
            self.latest_version = latest_version
            self.release_notes = release_notes
            self.download_url = download_url
            self.update_label.setText(_t("update_available_banner", version=latest_version))
            self.btn_update_action.setText(_t("btn_update_now"))
            self.update_banner.show()

    def _show_update_dialog_from_banner(self) -> None:
        if hasattr(self, "latest_version") and self.latest_version:
            dialog = UpdateDialog(self.latest_version, self.release_notes, self.download_url, self)
            dialog.exec()

    def check_for_updates_manually(self) -> None:
        """Starts a manual check for updates, showing progress and result dialogs."""
        self.statusBar().showMessage(_t("status_checking_updates"))
        self._manual_update_worker = UpdateCheckWorker(self)
        self._manual_update_worker.finished.connect(self._on_manual_update_check_finished)
        self._manual_update_worker.error_occurred.connect(self._on_manual_update_check_failed)
        self._manual_update_worker.start()

    def _on_manual_update_check_finished(
        self, has_update: bool, latest_version: str, release_notes: str, download_url: str
    ) -> None:
        self.statusBar().clearMessage()
        if has_update and download_url:
            self.latest_version = latest_version
            self.release_notes = release_notes
            self.download_url = download_url
            dialog = UpdateDialog(latest_version, release_notes, download_url, self)
            dialog.exec()
        else:
            QMessageBox.information(
                self,
                _t("update_no_updates_title"),
                _t("update_no_updates_msg", version=__version__),
            )

    def _on_manual_update_check_failed(self, error_msg: str) -> None:
        self.statusBar().clearMessage()
        QMessageBox.critical(
            self,
            _t("update_error_title"),
            _t("update_error_msg", error=error_msg),
        )

    def _show_log_context_menu(self, pos: Any) -> None:
        from PySide6.QtWidgets import QApplication

        menu = self.console_log.createStandardContextMenu(pos)

        # Add custom translated Copy Action if selected
        cursor = self.console_log.textCursor()
        if cursor.hasSelection():
            selected_text = cursor.selectedText()
            menu.addSeparator()
            act_copy = menu.addAction(_t("ctx_copy_log"))

            def do_copy() -> None:
                clipboard = QApplication.clipboard()
                clipboard.setText(selected_text)

            act_copy.triggered.connect(do_copy)

        menu.exec(self.console_log.viewport().mapToGlobal(pos))

    def _on_org_text_changed(self, text: str) -> None:
        self.org_debounce_timer.start(300)

    def _on_org_debounce_timeout(self) -> None:
        # Save org name to config
        org_text = self.org_input.text().strip()
        self.config["last_organization"] = org_text
        self.config_manager.save(self.config)
        self._update_load_button_state()

    def _is_org_valid(self) -> bool:
        org_text = self.org_input.text().strip()
        if not org_text:
            return False
        try:
            ValidationService.normalize_org_name(org_text)
            return True
        except ValueError:
            return False

    def _update_load_button_state(self) -> None:
        is_idle = self.app_state == "IDLE"
        is_org_valid = self._is_org_valid()
        is_gh_cli_available = getattr(self, "gh_cli_available", True)
        self.btn_load.setEnabled(is_idle and is_org_valid and is_gh_cli_available)

    def _on_follow_toggled(self, checked: bool) -> None:
        self.table.follow_active_repo = checked

    def run_workspace_wizard(self) -> None:
        from github_org_sync.ui.dialogs import WorkspaceWizardDialog

        ws_text = self.workspace_input.text().strip()
        if not ws_text or not Path(ws_text).exists():
            QMessageBox.warning(self, _t("error_open_title"), "Please choose a valid workspace folder first.")
            return

        org_name = ValidationService.normalize_org_name(self.org_input.text().strip())
        if not org_name:
            QMessageBox.warning(self, _t("error_open_title"), "Please provide a valid GitHub organization name first.")
            return

        if not self.repositories:
            QMessageBox.warning(self, _t("error_open_title"), "No repositories loaded. Please load repositories first.")
            return

        # Disable main window state to prevent concurrency
        self._set_app_state("SYNCING")
        QApplication.processEvents()

        try:
            dialog = WorkspaceWizardDialog(
                repositories=self.repositories,
                workspace=Path(ws_text),
                org_name=org_name,
                git_service=self.git_service,
                parent=self,
            )
            dialog.exec()

            # Update table in place and apply filters
            self.table.update_repositories_in_place(self.repositories)
            self.apply_table_filters()

            if dialog.results:
                self.log("Wizard completed. Saving update report...")
                from github_org_sync.services.report_service import ReportService

                options = {
                    "use_ssh": self.cb_use_ssh.isChecked(),
                    "preserve_local_changes": self.cb_preserve_changes.isChecked(),
                    "fetch_only": self.cb_fetch_only.isChecked(),
                    "dry_run": self.cb_dry_run.isChecked(),
                    "checkout_default": True,
                    "wizard_run": True,
                }
                json_path, md_path = ReportService.generate_reports(
                    organization=org_name,
                    workspace=Path(ws_text),
                    auth_user=self.auth_user,
                    protocol="ssh" if self.cb_use_ssh.isChecked() else "https",
                    options=options,
                    results=dialog.results,
                )
                self.last_json_report = json_path
                self.last_md_report = md_path
                self.btn_open_report.setEnabled(True)
                self.log(f"Report JSON: {json_path}")
                self.log(f"Report MD: {md_path}")

        finally:
            self._set_app_state("IDLE")

    def switch_mode(self, mode: str) -> None:
        self.current_mode = mode
        self.btn_mode_clone.setChecked(mode == "clone")
        self.btn_mode_workspace.setChecked(mode == "workspace")

        if mode == "clone":
            self.stacked_widget.setCurrentIndex(0)
            if self.gh_cli_available:
                self.auth_banner.hide()
            else:
                self.auth_banner.show()
        else:
            self.stacked_widget.setCurrentIndex(1)
            self.auth_banner.hide()

        # Clear active scan/sync and table state on mode switch
        self._cancel_active_worker()
        self.repositories = []
        self.table.set_repositories([])
        self.apply_table_filters()
        self._set_app_state("IDLE")

    def scan_workspace(self) -> None:
        ws_text = self.workspace_input.text().strip()
        if not ws_text:
            QMessageBox.warning(self, _t("error_open_title"), _t("tip_workspace_input"))
            return

        try:
            ws_path = ValidationService.validate_workspace(ws_text)
        except ValueError as e:
            QMessageBox.warning(self, _t("error_open_title"), str(e))
            return

        self._cancel_active_worker()
        self.log(f"Scanning local workspace: {ws_path}")
        self._set_app_state("SCANNING_WORKSPACE")
        self.progress_bar.setValue(0)

        # Clear current repo list
        self.repositories = []
        self.table.set_repositories([])

        from github_org_sync.workers.workspace_scan_worker import WorkspaceScanWorker

        recursive = self.cb_scan_recursive.isChecked()

        self.sync_worker = WorkspaceScanWorker(ws_path, recursive=recursive)
        self.sync_worker.progress_updated.connect(self._on_scan_progress)
        self.sync_worker.log_emitted.connect(self.log)
        self.sync_worker.finished.connect(self._on_scan_finished)
        self.sync_worker.error_occurred.connect(self._on_worker_error)
        self.sync_worker.start()

    @Slot(int, int, str)
    def _on_scan_progress(self, index: int, total: int, repo_path: str) -> None:
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(index)
        self.statusBar().showMessage(_t("status_scanning", current=index, total=total, name=Path(repo_path).name))

    @Slot(list, bool)
    def _on_scan_finished(self, repos: list, was_cancelled: bool) -> None:
        self._set_app_state("IDLE")
        self.progress_bar.setValue(0)

        if was_cancelled:
            self.log("Workspace scan cancelled.")
            return

        # Convert dictionary to Repository objects
        from github_org_sync.utils.git_url_parser import parse_git_url

        self.repositories = []
        for r_dict in repos:
            # Safely get remote url details
            remote_url = r_dict.get("origin_url") or ""
            # Fallback hosting/owner logic
            host = "No remote"
            owner = "No remote"
            if remote_url:
                parsed = parse_git_url(remote_url)
                if parsed:
                    host_val = parsed["host"]
                    owner = parsed["owner"]
                    if "github.com" in host_val.lower():
                        host = "GitHub"
                    elif "gitlab.com" in host_val.lower():
                        host = "GitLab"
                    elif "bitbucket.org" in host_val.lower():
                        host = "Bitbucket"
                    else:
                        host = host_val
                else:
                    host = "Custom"
                    owner = "Unknown"

            r_obj = Repository(
                name=r_dict["repo_name"],
                url=remote_url,
                ssh_url=remote_url,
                is_archived=False,
                is_fork=False,
                default_branch=r_dict["branch"] or "main",
                local_path=r_dict["path"],
                status=r_dict["status"],
                branch=r_dict["branch"],
                ahead=r_dict["ahead"],
                behind=r_dict["behind"],
                result=r_dict["message"],
            )
            # Tag with computed attributes for grouping
            r_obj.computed_hosting = host
            r_obj.computed_owner = owner
            self.repositories.append(r_obj)

        self.log(f"Scan complete. Found {len(self.repositories)} repositories.")

        # Populate group filtering combo box
        self._populate_group_filter()

        # Handle auto-detection of organization
        github_owners = [r.computed_owner for r in self.repositories if getattr(r, "computed_hosting", "") == "GitHub"]
        unique_owners = sorted(set(github_owners))

        if len(unique_owners) == 1:
            detected_org = unique_owners[0]
            self.detected_org_label.setText(_t("detected_org_label", org=detected_org))
            self.org_input.setText(detected_org)
        else:
            self.detected_org_label.setText("")

        self.table.set_repositories(self.repositories)
        self.apply_table_filters()

    def _populate_group_filter(self) -> None:
        self.group_filter_cb.blockSignals(True)
        self.group_filter_cb.clear()
        self.group_filter_cb.addItem(_t("group_filter_all"), "all")

        groups: dict[str, int] = {}
        for r in self.repositories:
            host = getattr(r, "computed_hosting", "No remote")
            owner = getattr(r, "computed_owner", "No remote")
            grp_key = f"{host} / {owner}"
            groups[grp_key] = groups.get(grp_key, 0) + 1

        for grp_name, count in sorted(groups.items()):
            self.group_filter_cb.addItem(f"{grp_name} ({count})", grp_name)

        self.group_filter_cb.blockSignals(False)

    def compare_workspace_with_org(self) -> None:
        org_text = self.org_input.text().strip()
        if not org_text:
            QMessageBox.warning(self, _t("error_gh_title"), _t("tip_org_input"))
            return

        try:
            org_name = ValidationService.normalize_org_name(org_text)
        except ValueError as e:
            QMessageBox.warning(self, _t("error_gh_title"), str(e))
            return

        ws_text = self.workspace_input.text().strip()
        if not ws_text:
            QMessageBox.warning(self, _t("error_open_title"), _t("tip_workspace_input"))
            return

        self.log(f"Comparing workspace with GitHub organization: {org_name}")
        self._set_app_state("LOADING_REPOSITORIES")
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()

        try:
            org_repos = self.github_service.list_repositories(org_name)

            # Map existing repositories by name
            existing_repos_map = {r.name: r for r in self.repositories}
            new_repositories = []

            for o_repo in org_repos:
                if o_repo.name in existing_repos_map:
                    # Update/keep existing scanned repository
                    r_obj = existing_repos_map[o_repo.name]
                    r_obj.is_archived = o_repo.is_archived
                    r_obj.is_fork = o_repo.is_fork
                    new_repositories.append(r_obj)
                else:
                    # Missing repository locally! Create missing repo object
                    r_obj = Repository(
                        name=o_repo.name,
                        url=o_repo.url,
                        ssh_url=o_repo.ssh_url,
                        is_archived=o_repo.is_archived,
                        is_fork=o_repo.is_fork,
                        default_branch=o_repo.default_branch,
                        status="MISSING",
                    )
                    r_obj.computed_hosting = "GitHub"
                    r_obj.computed_owner = org_name
                    new_repositories.append(r_obj)

            # Highlight local repositories not in organization
            org_repo_names = {r.name for r in org_repos}
            for local_name, r_obj in existing_repos_map.items():
                if getattr(r_obj, "computed_hosting", "") == "GitHub" and local_name not in org_repo_names:
                    r_obj.result = "Not in organization"

            self.repositories = new_repositories
            self.log(f"Comparison finished. Total repositories in view: {len(self.repositories)}")
            self._populate_group_filter()
            self.table.set_repositories(self.repositories)
            self.apply_table_filters()

        except Exception as e:
            QMessageBox.critical(self, _t("error_gh_title"), f"Failed to compare: {e}")
            self.log(f"Compare error: {e}")
        finally:
            self._set_app_state("IDLE")
