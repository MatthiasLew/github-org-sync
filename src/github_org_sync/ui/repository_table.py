import os
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QBrush, QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
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


class CheckboxTableWidgetItem(QTableWidgetItem):
    def __init__(self, checkbox: QCheckBox) -> None:
        super().__init__()
        self.checkbox = checkbox

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, CheckboxTableWidgetItem):
            return int(self.checkbox.isChecked()) < int(other.checkbox.isChecked())
        return super().__lt__(other)


class NumericTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other: QTableWidgetItem) -> bool:
        try:
            self_val = int(self.text())
        except ValueError:
            self_val = -1 if self.text() == "" else 0
        try:
            other_val = int(other.text())
        except ValueError:
            other_val = -1 if other.text() == "" else 0
        return self_val < other_val


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
        self.follow_active_repo: bool = False

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

    def _get_repo_name(self, item: QTableWidgetItem | None) -> str:
        if not item:
            return ""
        val = item.data(Qt.ItemDataRole.UserRole)
        if val is not None:
            return str(val)
        text = item.text()
        if text.startswith("[") and "] " in text:
            return text.split("] ", 1)[-1]
        return text

    def retranslate_ui(self) -> None:
        """Translates the headers and any visible translatable fields."""
        labels = [_t(key) for key in self.COLUMNS]
        self.setHorizontalHeaderLabels(labels)
        for idx, col_key in enumerate(self.COLUMNS):
            item = self.horizontalHeaderItem(idx)
            if item:
                item.setToolTip(_t(f"tip_{col_key}"))

        # Retranslate row statuses if repositories are loaded
        for idx in range(self.rowCount()):
            name_item = self.item(idx, 1)
            if name_item:
                repo_name = self._get_repo_name(name_item)
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
            self.setItem(idx, 0, CheckboxTableWidgetItem(cb))

            # Column 1: Repository Name
            host = getattr(repo, "computed_hosting", "GitHub") if hasattr(repo, "computed_hosting") else "GitHub"
            display_name = f"[{host}] {repo.name}" if host != "GitHub" else repo.name
            name_item = QTableWidgetItem(display_name)
            name_item.setData(Qt.ItemDataRole.UserRole, repo.name)
            name_item.setToolTip(repo.name)
            self.setItem(idx, 1, name_item)

            # Column 2: Visibility
            self.setItem(idx, 2, QTableWidgetItem(repo.visibility.upper()))

            # Column 3: Archived
            arch_text = _t("yes_word") if repo.is_archived else _t("no_word")
            self.setItem(idx, 3, QTableWidgetItem(arch_text))

            # Column 4: Local Status
            status_item = QTableWidgetItem(_t(f"state_{repo.status}"))
            self._style_status_item(status_item, repo.status)
            status_item.setToolTip(status_item.text())
            self.setItem(idx, 4, status_item)

            # Column 5: Branch
            branch_val = repo.branch or ""
            branch_item = QTableWidgetItem(branch_val)
            branch_item.setToolTip(branch_val)
            self.setItem(idx, 5, branch_item)

            # Column 6: Ahead
            ahead_val = str(repo.ahead) if repo.ahead is not None else ""
            self.setItem(idx, 6, NumericTableWidgetItem(ahead_val))

            # Column 7: Behind
            behind_val = str(repo.behind) if repo.behind is not None else ""
            self.setItem(idx, 7, NumericTableWidgetItem(behind_val))

            # Column 8: Action
            action_text = self._determine_action(repo)
            action_item = QTableWidgetItem(action_text)
            action_item.setToolTip(action_text)
            self.setItem(idx, 8, action_item)

            # Column 9: Result / Message
            if repo.status in ("WRONG_REMOTE", "NOT_A_REPOSITORY", "NO_UPSTREAM"):
                res_val = _t(f"desc_{repo.status}")
            else:
                res_val = repo.result or ""
            res_item = QTableWidgetItem(res_val)
            res_item.setToolTip(res_val)
            self.setItem(idx, 9, res_item)

        self.setSortingEnabled(True)

    def update_repository_status(self, repo_name: str, status: str, message: str | None = None) -> None:
        """Dynamically updates a repository row's status, action, and result."""
        # Save selection, scrollbars, focus, sorting
        v_val = self.verticalScrollBar().value()
        h_val = self.horizontalScrollBar().value()

        selected_names = []
        for r in range(self.rowCount()):
            name_item = self.item(r, 1)
            if name_item and name_item.isSelected():
                selected_names.append(self._get_repo_name(name_item))

        curr_row = self.currentRow()
        curr_col = self.currentColumn()

        header = self.horizontalHeader()
        sort_col = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        sorting_was_enabled = self.isSortingEnabled()
        self.setSortingEnabled(False)

        # Perform single update
        for row in range(self.rowCount()):
            name_item = self.item(row, 1)
            if name_item and self._get_repo_name(name_item) == repo_name:
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
                            status_item.setToolTip(status_item.text())

                        # Update action item
                        action_item = self.item(row, 8)
                        if action_item:
                            action_text = self._determine_action(repo)
                            action_item.setText(action_text)
                            action_item.setToolTip(action_text)

                        # Update result item
                        res_item = self.item(row, 9)
                        if res_item and message is not None:
                            if status in ("WRONG_REMOTE", "NOT_A_REPOSITORY", "NO_UPSTREAM"):
                                res_val = _t(f"desc_{status}")
                            else:
                                res_val = message
                            res_item.setText(res_val)
                            res_item.setToolTip(res_val)

                        # Update branch/ahead/behind from repo state
                        branch_item = self.item(row, 5)
                        if branch_item:
                            branch_item.setText(repo.branch or "")
                            branch_item.setToolTip(repo.branch or "")
                        ahead_item = self.item(row, 6)
                        if ahead_item:
                            ahead_item.setText(str(repo.ahead) if repo.ahead is not None else "")
                        behind_item = self.item(row, 7)
                        if behind_item:
                            behind_item.setText(str(repo.behind) if repo.behind is not None else "")

                        # Handle Follow Mode
                        if getattr(self, "follow_active_repo", False):
                            self.scrollToItem(name_item, QAbstractItemView.ScrollHint.PositionAtCenter)
                        break

        if sorting_was_enabled:
            self.setSortingEnabled(True)
            self.sortByColumn(sort_col, sort_order)

        self.clearSelection()
        for r in range(self.rowCount()):
            name_item = self.item(r, 1)
            if name_item and self._get_repo_name(name_item) in selected_names:
                self.selectRow(r)

        if curr_row >= 0 and curr_row < self.rowCount():
            self.setCurrentCell(curr_row, curr_col)

        # Restore scrollbars if not follow mode or follow mode didn't trigger
        if not getattr(self, "follow_active_repo", False):
            self.verticalScrollBar().setValue(v_val)
        self.horizontalScrollBar().setValue(h_val)

    def update_repositories_in_place(self, repos: list[Repository]) -> None:
        """Updates the table cells in place based on repository name matching to preserve selections, scrollbars, etc."""
        v_val = self.verticalScrollBar().value()
        h_val = self.horizontalScrollBar().value()

        selected_names = []
        for r in range(self.rowCount()):
            name_item = self.item(r, 1)
            if name_item and name_item.isSelected():
                selected_names.append(self._get_repo_name(name_item))

        curr_row = self.currentRow()
        curr_col = self.currentColumn()

        header = self.horizontalHeader()
        sort_col = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        sorting_was_enabled = self.isSortingEnabled()
        self.setSortingEnabled(False)

        self.repositories = repos
        for repo in repos:
            found_row = -1
            for r in range(self.rowCount()):
                name_item = self.item(r, 1)
                if name_item and self._get_repo_name(name_item) == repo.name:
                    found_row = r
                    break

            if found_row != -1:
                # Update cells
                self.setItem(found_row, 2, QTableWidgetItem(repo.visibility.upper()))

                arch_text = _t("yes_word") if repo.is_archived else _t("no_word")
                self.setItem(found_row, 3, QTableWidgetItem(arch_text))

                status_item = self.item(found_row, 4)
                if status_item:
                    status_item.setText(_t(f"state_{repo.status}"))
                    self._style_status_item(status_item, repo.status)
                    status_item.setToolTip(status_item.text())

                branch_item = self.item(found_row, 5)
                if branch_item:
                    branch_item.setText(repo.branch or "")
                    branch_item.setToolTip(repo.branch or "")

                ahead_item = self.item(found_row, 6)
                if ahead_item:
                    ahead_item.setText(str(repo.ahead) if repo.ahead is not None else "")

                behind_item = self.item(found_row, 7)
                if behind_item:
                    behind_item.setText(str(repo.behind) if repo.behind is not None else "")

                action_item = self.item(found_row, 8)
                if action_item:
                    action_text = self._determine_action(repo)
                    action_item.setText(action_text)
                    action_item.setToolTip(action_text)

                res_item = self.item(found_row, 9)
                if res_item:
                    if repo.status in ("WRONG_REMOTE", "NOT_A_REPOSITORY", "NO_UPSTREAM"):
                        res_val = _t(f"desc_{repo.status}")
                    else:
                        res_val = repo.result or ""
                    res_item.setText(res_val)
                    res_item.setToolTip(res_val)

        if sorting_was_enabled:
            self.setSortingEnabled(True)
            self.sortByColumn(sort_col, sort_order)

        self.clearSelection()
        for r in range(self.rowCount()):
            name_item = self.item(r, 1)
            if name_item and self._get_repo_name(name_item) in selected_names:
                self.selectRow(r)

        if curr_row >= 0 and curr_row < self.rowCount():
            self.setCurrentCell(curr_row, curr_col)

        self.verticalScrollBar().setValue(v_val)
        self.horizontalScrollBar().setValue(h_val)

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
        repo_name = self._get_repo_name(name_item)
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

        repo_name = self._get_repo_name(name_item)
        repo = next((r for r in self.repositories if r.name == repo_name), None)
        if not repo:
            return

        menu = QMenu(self)

        # Context action 0: Copy cell
        act_copy_cell = QAction(_t("ctx_copy_log"), self)
        act_copy_cell.triggered.connect(lambda: self._copy_cell(row, item.column()))
        menu.addAction(act_copy_cell)

        # Context action 0.5: Copy row
        act_copy_row = QAction(_t("ctx_copy_log") + " (row)", self)  # We can customize this label
        act_copy_row.setText("Copy row") if sys.platform != "win32" or _t(
            "yes_word"
        ) == "Yes" else act_copy_row.setText("Kopiuj wiersz")
        act_copy_row.triggered.connect(lambda: self._copy_row(row))
        menu.addAction(act_copy_row)

        menu.addSeparator()

        # Context action 1: Open local directory
        act_open_folder = QAction(_t("ctx_open_folder"), self)
        act_open_folder.setEnabled(repo.local_path is not None and repo.local_path.exists())
        act_open_folder.triggered.connect(lambda: self._open_folder(Path(repo.local_path)) if repo.local_path else None)
        menu.addAction(act_open_folder)

        # Context action 2: Open Remote repo page
        host = getattr(repo, "computed_hosting", "GitHub") if hasattr(repo, "computed_hosting") else "GitHub"
        if host == "GitHub":
            text_open_remote = _t("ctx_open_github")
        elif host == "GitLab":
            text_open_remote = "Otwórz stronę GitLab" if _t("yes_word") != "Yes" else "Open GitLab page"
        elif host == "Bitbucket":
            text_open_remote = "Otwórz stronę Bitbucket" if _t("yes_word") != "Yes" else "Open Bitbucket page"
        else:
            text_open_remote = "Otwórz stronę remote" if _t("yes_word") != "Yes" else "Open remote page"

        act_open_github = QAction(text_open_remote, self)
        act_open_github.setEnabled(bool(repo.url))
        act_open_github.triggered.connect(lambda: self._open_url(repo.url))
        menu.addAction(act_open_github)

        menu.addSeparator()

        # Context action 3: Compare Changes
        act_compare = QAction(_t("ctx_compare_changes"), self)
        act_compare.setEnabled(repo.local_path is not None and repo.local_path.exists())
        act_compare.triggered.connect(lambda: self._compare_changes(repo))
        menu.addAction(act_compare)

        # Context action 4: Resolve Issue
        act_resolve = QAction(_t("ctx_resolve_issue"), self)
        act_resolve.setEnabled(repo.local_path is not None and repo.local_path.exists())
        act_resolve.triggered.connect(lambda: self._resolve_issue(repo))
        menu.addAction(act_resolve)

        menu.exec(self.viewport().mapToGlobal(pos))

    def _copy_cell(self, row: int, col: int) -> None:
        cell_item = self.item(row, col)
        text = cell_item.text() if cell_item else ""
        QApplication.clipboard().setText(text)

    def _copy_row(self, row: int) -> None:
        row_texts = []
        for col in range(self.columnCount()):
            cell_item = self.item(row, col)
            if cell_item:
                row_texts.append(cell_item.text())
            else:
                row_texts.append("")
        QApplication.clipboard().setText("\t".join(row_texts))

    def _compare_changes(self, repo: Repository) -> None:
        from github_org_sync.ui.dialogs import CompareChangesDialog

        main_win = self.window()
        git_service = getattr(main_win, "git_service", None)
        org_text = main_win.org_input.text().strip() if hasattr(main_win, "org_input") else ""
        if not git_service:
            from github_org_sync.services.git_service import GitService

            git_service = GitService()
        dialog = CompareChangesDialog(repo, git_service, org_text, self)
        dialog.exec()

    def _resolve_issue(self, repo: Repository) -> None:
        from github_org_sync.ui.dialogs import ResolveIssueDialog

        main_win = self.window()
        git_service = getattr(main_win, "git_service", None)
        org_text = main_win.org_input.text().strip() if hasattr(main_win, "org_input") else ""
        if not git_service:
            from github_org_sync.services.git_service import GitService

            git_service = GitService()
        if repo.local_path is None:
            return
        dialog = ResolveIssueDialog(repo, git_service, org_text, self)
        res = dialog.exec()
        if res == QDialog.DialogCode.Accepted:
            # Refresh local status of this repo and update in table
            status, branch, ahead, behind, msg = git_service.get_local_status(repo.local_path, org_text)
            self.update_repository_status(repo.name, status, msg)
            if hasattr(main_win, "log"):
                main_win.log(f"Repository {repo.name} resolved. Status is now: {status}.")

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

    def filter_rows(self, search_text: str, status_filter: str, group_filter: str | None = None) -> None:
        """Hides rows that do not match search query, status filter, and group filter."""
        search_text = search_text.lower().strip()

        # Resolve status filter translation back to translation key
        status_key = None
        for key in [
            "filter_status_all",
            "state_MISSING",
            "state_UP_TO_DATE",
            "state_DIRTY",
            "state_BEHIND",
            "state_AHEAD",
            "state_DIVERGED",
            "filter_status_errors",
        ]:
            if _t(key) == status_filter:
                status_key = key
                break

        for row in range(self.rowCount()):
            name_item = self.item(row, 1)
            repo_name = self._get_repo_name(name_item)

            # Check status filter & find repo
            matches_status = True
            repo = next((r for r in self.repositories if r.name == repo_name), None)
            if repo:
                if status_key and status_key != "filter_status_all":
                    raw_status = repo.status
                    if status_key == "filter_status_errors":
                        matches_status = raw_status in ("FAILED", "CONFLICT", "WRONG_REMOTE")
                    elif status_key == "state_MISSING":
                        matches_status = raw_status == "MISSING"
                    elif status_key == "state_DIRTY":
                        matches_status = raw_status == "DIRTY"
                    elif status_key == "state_BEHIND":
                        matches_status = raw_status == "BEHIND"
                    elif status_key == "state_AHEAD":
                        matches_status = raw_status == "AHEAD"
                    elif status_key == "state_DIVERGED":
                        matches_status = raw_status == "DIVERGED"
                    elif status_key == "state_UP_TO_DATE":
                        matches_status = raw_status == "UP_TO_DATE"

                # Check group filter
                matches_group = True
                if group_filter and group_filter != "all":
                    host = getattr(repo, "computed_hosting", "GitHub")
                    owner = getattr(repo, "computed_owner", "No remote")
                    repo_group = f"{host} / {owner}"
                    matches_group = repo_group == group_filter

                matches_search = not search_text or (search_text in repo.name.lower())
                self.setRowHidden(row, not (matches_search and matches_status and matches_group))

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        if self.rowCount() == 0:
            painter = QPainter(self.viewport())
            font = painter.font()
            font.setPointSize(11)
            painter.setFont(font)
            painter.setPen(QColor("#64748b"))
            text = _t("empty_state_text")
            painter.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter, text)
