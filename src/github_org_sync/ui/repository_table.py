import os
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from github_org_sync.i18n import _t
from github_org_sync.models.repository import Repository
from github_org_sync.utils.process import run_process


class RepositoryTable(QTableWidget):
    COLUMNS = [
        "col_select",
        "col_name",
        "col_visibility",
        "col_archived",
        "col_status",
        "col_branch",
        "col_ahead",
        "col_behind",
        "col_action",
        "col_result",
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repositories: list[Repository] = []
        self.checkbox_map: dict[str, QCheckBox] = {}

        self.setColumnCount(len(self.COLUMNS))
        self.retranslate_ui()

        # Table configuration
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)

        # We will set stylesheet dynamically matching theme colors in styles.py

        # Header sizing
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)

        # Set default widths
        self.setColumnWidth(0, 70)  # Selected
        self.setColumnWidth(1, 180)  # Repository
        self.setColumnWidth(2, 90)  # Visibility
        self.setColumnWidth(3, 85)  # Archived
        self.setColumnWidth(4, 120)  # Local Status
        self.setColumnWidth(5, 100)  # Branch
        self.setColumnWidth(6, 65)  # Ahead
        self.setColumnWidth(7, 65)  # Behind
        self.setColumnWidth(8, 90)  # Action

        # Double click & Context menu
        self.doubleClicked.connect(self._on_double_clicked)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Sorting
        self.setSortingEnabled(True)

    def retranslate_ui(self) -> None:
        """Translates the headers and any visible translatable fields."""
        labels = [_t(key) for key in self.COLUMNS]
        self.setHorizontalHeaderLabels(labels)

        # Retranslate row statuses if repositories are loaded
        for idx in range(self.rowCount()):
            name_item = self.item(idx, 1)
            if name_item:
                repo_name = name_item.text()
                repo = next((r for r in self.repositories if r.name == repo_name), None)
                if repo:
                    # Update translated local status text
                    status_item = self.item(idx, 4)
                    if status_item:
                        status_item.setText(_t(f"state_{repo.status}"))

                    # Update translated message if it is a standard description
                    res_item = self.item(idx, 9)
                    if res_item and repo.status in ("WRONG_REMOTE", "NOT_A_REPOSITORY", "NO_UPSTREAM"):
                        res_item.setText(_t(f"desc_{repo.status}"))

    def get_column_widths(self) -> list[int]:
        return [self.columnWidth(i) for i in range(self.columnCount())]

    def set_column_widths(self, widths: list[int]) -> None:
        if widths and len(widths) <= self.columnCount():
            for i, w in enumerate(widths):
                self.setColumnWidth(i, w)

    def set_repositories(self, repos: list[Repository]) -> None:
        """Populates the table with repository data."""
        self.setSortingEnabled(False)
        self.repositories = repos
        self.checkbox_map.clear()
        self.setRowCount(0)
        self.setRowCount(len(repos))

        for idx, repo in enumerate(repos):
            # Column 0: Checkbox
            checkbox_widget = QWidget()
            layout = QHBoxLayout(checkbox_widget)
            cb = QCheckBox()
            cb.setChecked(repo.status == "MISSING" or repo.status in ("BEHIND", "DIVERGED"))
            layout.addWidget(cb)
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.setContentsMargins(0, 0, 0, 0)
            self.setCellWidget(idx, 0, checkbox_widget)
            self.checkbox_map[repo.name] = cb

            # Column 1: Repository Name
            name_item = QTableWidgetItem(repo.name)
            self.setItem(idx, 1, name_item)

            # Column 2: Visibility
            self.setItem(idx, 2, QTableWidgetItem(repo.visibility.upper()))

            # Column 3: Archived
            arch_text = _t("yes_word") if repo.is_archived else _t("no_word")
            self.setItem(idx, 3, QTableWidgetItem(arch_text))

            # Column 4: Local Status
            status_item = QTableWidgetItem(_t(f"state_{repo.status}"))
            self._style_status_item(status_item, repo.status)
            self.setItem(idx, 4, status_item)

            # Column 5: Branch
            branch_val = repo.branch or ""
            self.setItem(idx, 5, QTableWidgetItem(branch_val))

            # Column 6: Ahead
            ahead_val = str(repo.ahead) if repo.ahead is not None else ""
            self.setItem(idx, 6, QTableWidgetItem(ahead_val))

            # Column 7: Behind
            behind_val = str(repo.behind) if repo.behind is not None else ""
            self.setItem(idx, 7, QTableWidgetItem(behind_val))

            # Column 8: Action
            action_text = self._determine_action(repo)
            self.setItem(idx, 8, QTableWidgetItem(action_text))

            # Column 9: Result / Message
            if repo.status in ("WRONG_REMOTE", "NOT_A_REPOSITORY", "NO_UPSTREAM"):
                res_val = _t(f"desc_{repo.status}")
            else:
                res_val = repo.result or ""
            self.setItem(idx, 9, QTableWidgetItem(res_val))

        self.setSortingEnabled(True)

    def update_repository_status(self, repo_name: str, status: str, message: str | None = None) -> None:
        """Dynamically updates a repository row's status, action, and result."""
        # Temporal disable sorting while modifying rows
        sorting_was_enabled = self.isSortingEnabled()
        self.setSortingEnabled(False)

        for row in range(self.rowCount()):
            name_item = self.item(row, 1)
            if name_item and name_item.text() == repo_name:
                for repo in self.repositories:
                    if repo.name == repo_name:
                        repo.status = status
                        if message is not None:
                            repo.result = message

                        # Update status item
                        status_item = self.item(row, 4)
                        if status_item:
                            status_item.setText(_t(f"state_{status}"))
                            self._style_status_item(status_item, status)

                        # Update action item
                        action_item = self.item(row, 8)
                        if action_item:
                            action_item.setText(self._determine_action(repo))

                        # Update result item
                        res_item = self.item(row, 9)
                        if res_item and message is not None:
                            if status in ("WRONG_REMOTE", "NOT_A_REPOSITORY", "NO_UPSTREAM"):
                                res_item.setText(_t(f"desc_{status}"))
                            else:
                                res_item.setText(message)

                        # Update branch/ahead/behind from repo state
                        branch_item = self.item(row, 5)
                        if branch_item:
                            branch_item.setText(repo.branch or "")
                        ahead_item = self.item(row, 6)
                        if ahead_item:
                            ahead_item.setText(str(repo.ahead) if repo.ahead is not None else "")
                        behind_item = self.item(row, 7)
                        if behind_item:
                            behind_item.setText(str(repo.behind) if repo.behind is not None else "")
                        break

        self.setSortingEnabled(sorting_was_enabled)

    def get_selected_repositories(self) -> list[Repository]:
        """Returns the list of repositories that have their checkbox checked."""
        selected = []
        for repo in self.repositories:
            cb = self.checkbox_map.get(repo.name)
            if cb and cb.isChecked():
                selected.append(repo)
        return selected

    def select_all(self) -> None:
        self._set_checked_all(True)

    def select_none(self) -> None:
        self._set_checked_all(False)

    def select_missing(self) -> None:
        for repo in self.repositories:
            cb = self.checkbox_map.get(repo.name)
            if cb:
                cb.setChecked(repo.status == "MISSING")

    def select_outdated(self) -> None:
        for repo in self.repositories:
            cb = self.checkbox_map.get(repo.name)
            if cb:
                cb.setChecked(repo.status in ("BEHIND", "DIVERGED"))

    def _set_checked_all(self, checked: bool) -> None:
        for cb in self.checkbox_map.values():
            cb.setChecked(checked)

    def _style_status_item(self, item: QTableWidgetItem, status: str) -> None:
        """Applies consistent soft status coloring."""
        if status in ("UP_TO_DATE", "CLONED", "UPDATED", "CLEAN"):
            item.setForeground(QBrush(QColor("#10b981")))  # Soft emerald
        elif status in ("FAILED", "CONFLICT", "CANCELLED"):
            item.setForeground(QBrush(QColor("#f43f5e")))  # Soft rose red
        elif status in ("DIRTY", "AHEAD", "BEHIND", "DIVERGED", "WRONG_REMOTE"):
            item.setForeground(QBrush(QColor("#f59e0b")))  # Soft amber
        else:
            item.setForeground(QBrush(QColor("#94a3b8")))  # Soft slate gray

    def _determine_action(self, repo: Repository) -> str:
        if repo.status == "MISSING":
            return "CLONE"
        if repo.status in ("BEHIND", "DIRTY", "DIVERGED", "UP_TO_DATE", "AHEAD"):
            return "UPDATE"
        return "SKIP"

    def _on_double_clicked(self, index: Any) -> None:
        row = index.row()
        name_item = self.item(row, 1)
        if not name_item:
            return
        repo_name = name_item.text()
        repo = next((r for r in self.repositories if r.name == repo_name), None)
        if repo and repo.local_path and repo.local_path.exists():
            self._open_folder(Path(repo.local_path))

    def _show_context_menu(self, pos: Any) -> None:
        item = self.itemAt(pos)
        if not item:
            return

        row = item.row()
        name_item = self.item(row, 1)
        if not name_item:
            return

        repo_name = name_item.text()
        repo = next((r for r in self.repositories if r.name == repo_name), None)
        if not repo:
            return

        menu = QMenu(self)

        # Context action 1: Open local directory
        act_open_folder = QAction(_t("ctx_open_folder"), self)
        act_open_folder.setEnabled(repo.local_path is not None and repo.local_path.exists())
        act_open_folder.triggered.connect(lambda: self._open_folder(Path(repo.local_path)) if repo.local_path else None)
        menu.addAction(act_open_folder)

        # Context action 2: Open GitHub repo page
        act_open_github = QAction(_t("ctx_open_github"), self)
        act_open_github.setEnabled(bool(repo.url))
        act_open_github.triggered.connect(lambda: self._open_url(repo.url))
        menu.addAction(act_open_github)

        menu.exec(self.viewport().mapToGlobal(pos))

    def _open_folder(self, path: Path) -> None:
        try:
            if hasattr(os, "startfile"):
                os.startfile(path)
            elif sys.platform == "darwin":
                run_process(["open", str(path)], check=True)
            else:
                run_process(["xdg-open", str(path)], check=True)
        except Exception as e:
            QMessageBox.warning(self, _t("error_open_title"), _t("error_open_msg", error=str(e)))

    def _open_url(self, url: str) -> None:
        try:
            if hasattr(os, "startfile"):
                os.startfile(url)
            elif sys.platform == "darwin":
                run_process(["open", url], check=True)
            else:
                run_process(["xdg-open", url], check=True)
        except Exception as e:
            QMessageBox.warning(self, _t("error_open_title"), _t("error_open_msg", error=str(e)))

    def filter_rows(self, search_text: str, status_filter: str) -> None:
        """Hides rows that do not match search query and status filter."""
        search_text = search_text.lower().strip()
        status_filter_lower = status_filter.lower().strip()

        for row in range(self.rowCount()):
            name_item = self.item(row, 1)
            name = name_item.text().lower() if name_item else ""

            # Check status filter
            matches_status = True
            if (
                status_filter_lower
                and status_filter_lower != "all"
                and status_filter_lower != _t("filter_status_all").lower()
            ):
                repo_name = name_item.text() if name_item else ""
                repo = next((r for r in self.repositories if r.name == repo_name), None)
                if repo:
                    raw_status = repo.status.lower()
                    if status_filter_lower in ("errors", "błędy"):
                        matches_status = raw_status in ("failed", "conflict", "wrong_remote")
                    elif status_filter_lower in ("missing", "brak"):
                        matches_status = raw_status == "missing"
                    elif status_filter_lower in ("dirty", "lokalne zmiany"):
                        matches_status = raw_status == "dirty"
                    elif status_filter_lower in ("behind", "zaległe commity"):
                        matches_status = raw_status == "behind"
                    elif status_filter_lower in ("ahead", "lokalne commity"):
                        matches_status = raw_status == "ahead"
                    elif status_filter_lower in ("diverged", "rozbieżne"):
                        matches_status = raw_status == "diverged"
                    elif status_filter_lower in ("up to date", "aktualne"):
                        matches_status = raw_status == "up_to_date"
                    else:
                        matches_status = status_filter_lower in raw_status

            matches_search = not search_text or (search_text in name)
            self.setRowHidden(row, not (matches_search and matches_status))
