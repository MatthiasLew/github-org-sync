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
from github_org_sync.utils.process import open_terminal, run_process


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
        "col_host",
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

        # Header sizing
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)

        # Set default widths
        self.setColumnWidth(0, 70)  # Selected
        self.setColumnWidth(1, 180)  # Repository
        self.setColumnWidth(2, 60)  # Host
        self.setColumnWidth(3, 90)  # Visibility
        self.setColumnWidth(4, 85)  # Archived
        self.setColumnWidth(5, 120)  # Local Status
        self.setColumnWidth(6, 100)  # Branch
        self.setColumnWidth(7, 65)  # Ahead
        self.setColumnWidth(8, 65)  # Behind
        self.setColumnWidth(9, 90)  # Action

        # Double click & Context menu
        self.doubleClicked.connect(self._on_double_clicked)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Sorting
        self.setSortingEnabled(True)

    def _col(self, key: str) -> int:
        return self.COLUMNS.index(key)

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
            name_item = self.item(idx, self._col("col_name"))
            if name_item:
                repo_name = self._get_repo_name(name_item)
                repo = next((r for r in self.repositories if r.name == repo_name), None)
                if repo:
                    # Update translated local status text
                    status_item = self.item(idx, self._col("col_status"))
                    if status_item:
                        status_item.setText(_t(f"state_{repo.status}"))

                    # Update translated message if it is a standard description
                    res_item = self.item(idx, self._col("col_result"))
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
            self.setCellWidget(idx, self._col("col_select"), checkbox_widget)
            self.checkbox_map[repo.name] = cb
            self.setItem(idx, self._col("col_select"), CheckboxTableWidgetItem(cb))

            # Column 1: Repository Name
            name_item = QTableWidgetItem(repo.name)
            name_item.setData(Qt.ItemDataRole.UserRole, repo.name)
            name_item.setToolTip(repo.name)
            self.setItem(idx, self._col("col_name"), name_item)

            # Column 2: Host (Badge)
            host = getattr(repo, "computed_hosting", "GitHub") if hasattr(repo, "computed_hosting") else "GitHub"
            host_item = QTableWidgetItem(host)
            host_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if host == "GitHub":
                host_item.setForeground(QColor("#60a5fa"))
            elif host == "GitLab":
                host_item.setForeground(QColor("#fb923c"))
            elif host == "Bitbucket":
                host_item.setForeground(QColor("#38bdf8"))
            self.setItem(idx, self._col("col_host"), host_item)

            # Column 3: Visibility
            self.setItem(idx, self._col("col_visibility"), QTableWidgetItem(repo.visibility.upper()))

            # Column 4: Archived
            arch_text = _t("yes_word") if repo.is_archived else _t("no_word")
            self.setItem(idx, self._col("col_archived"), QTableWidgetItem(arch_text))

            # Column 5: Local Status
            st_text = _t(f"state_{repo.status}")
            if getattr(repo, "has_lfs", False):
                st_text = f"{st_text} [LFS]"
            status_item = QTableWidgetItem(st_text)
            self._style_status_item(status_item, repo.status)
            if getattr(repo, "has_lfs", False):
                status_item.setToolTip(f"{st_text} - {_t('lfs_badge_tooltip')}")
            else:
                status_item.setToolTip(status_item.text())
            self.setItem(idx, self._col("col_status"), status_item)

            # Column 6: Branch
            branch_val = repo.branch or ""
            branch_item = QTableWidgetItem(branch_val)
            branch_item.setToolTip(branch_val)
            self.setItem(idx, self._col("col_branch"), branch_item)

            # Column 7: Ahead
            ahead_val = str(repo.ahead) if repo.ahead is not None else ""
            self.setItem(idx, self._col("col_ahead"), NumericTableWidgetItem(ahead_val))

            # Column 8: Behind
            behind_val = str(repo.behind) if repo.behind is not None else ""
            self.setItem(idx, self._col("col_behind"), NumericTableWidgetItem(behind_val))

            # Column 9: Action
            action_text = self._determine_action(repo)
            action_item = QTableWidgetItem(action_text)
            action_item.setToolTip(action_text)
            self.setItem(idx, self._col("col_action"), action_item)

            # Column 10: Result / Message
            if repo.status in ("WRONG_REMOTE", "NOT_A_REPOSITORY", "NO_UPSTREAM"):
                res_val = _t(f"desc_{repo.status}")
            else:
                res_val = repo.result or ""
            res_item = QTableWidgetItem(res_val)
            res_item.setToolTip(res_val)
            self.setItem(idx, self._col("col_result"), res_item)

        self.setSortingEnabled(True)

    def update_repository_status(self, repo_name: str, status: str, message: str | None = None) -> None:
        """Dynamically updates a repository row's status, action, and result."""
        # Save selection, scrollbars, focus, sorting
        v_val = self.verticalScrollBar().value()
        h_val = self.horizontalScrollBar().value()

        selected_names = []
        for r in range(self.rowCount()):
            name_item = self.item(r, self._col("col_name"))
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
            name_item = self.item(row, self._col("col_name"))
            if name_item and self._get_repo_name(name_item) == repo_name:
                for repo in self.repositories:
                    if repo.name == repo_name:
                        repo.status = status
                        if message is not None:
                            repo.result = message

                        # Update status item
                        status_item = self.item(row, self._col("col_status"))
                        if status_item:
                            st_text = _t(f"state_{status}")
                            if getattr(repo, "has_lfs", False):
                                st_text = f"{st_text} [LFS]"
                            status_item.setText(st_text)
                            self._style_status_item(status_item, status)
                            if getattr(repo, "has_lfs", False):
                                status_item.setToolTip(f"{st_text} - {_t('lfs_badge_tooltip')}")
                            else:
                                status_item.setToolTip(status_item.text())

                        # Update action item
                        action_item = self.item(row, self._col("col_action"))
                        if action_item:
                            action_text = self._determine_action(repo)
                            action_item.setText(action_text)
                            action_item.setToolTip(action_text)

                        # Update result item
                        res_item = self.item(row, self._col("col_result"))
                        if res_item and message is not None:
                            if status in ("WRONG_REMOTE", "NOT_A_REPOSITORY", "NO_UPSTREAM"):
                                res_val = _t(f"desc_{status}")
                            else:
                                res_val = message
                            res_item.setText(res_val)
                            res_item.setToolTip(res_val)

                        # Update branch/ahead/behind from repo state
                        branch_item = self.item(row, self._col("col_branch"))
                        if branch_item:
                            branch_item.setText(repo.branch or "")
                            branch_item.setToolTip(repo.branch or "")
                        ahead_item = self.item(row, self._col("col_ahead"))
                        if ahead_item:
                            ahead_item.setText(str(repo.ahead) if repo.ahead is not None else "")
                        behind_item = self.item(row, self._col("col_behind"))
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
                name_item = self.item(r, self._col("col_name"))
                if name_item and self._get_repo_name(name_item) == repo.name:
                    found_row = r
                    break

            if found_row != -1:
                # Update cells
                self.setItem(found_row, self._col("col_visibility"), QTableWidgetItem(repo.visibility.upper()))

                arch_text = _t("yes_word") if repo.is_archived else _t("no_word")
                self.setItem(found_row, self._col("col_archived"), QTableWidgetItem(arch_text))

                status_item = self.item(found_row, self._col("col_status"))
                if status_item:
                    status_item.setText(_t(f"state_{repo.status}"))
                    self._style_status_item(status_item, repo.status)
                    status_item.setToolTip(status_item.text())

                branch_item = self.item(found_row, self._col("col_branch"))
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
        name_item = self.item(row, self._col("col_name"))
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
        name_item = self.item(row, self._col("col_name"))
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

        # Context action 1.5: Open in terminal
        act_open_terminal = QAction(_t("ctx_open_terminal"), self)
        act_open_terminal.setEnabled(repo.local_path is not None and repo.local_path.exists())
        act_open_terminal.triggered.connect(
            lambda: self._open_terminal(Path(repo.local_path)) if repo.local_path else None
        )
        menu.addAction(act_open_terminal)

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

        # Context action 5: Switch Branch
        act_switch_branch = QAction(_t("ctx_switch_branch"), self)
        act_switch_branch.setEnabled(repo.local_path is not None and repo.local_path.exists())
        act_switch_branch.triggered.connect(lambda: self._switch_branch(repo))
        menu.addAction(act_switch_branch)

        # Context action 6: Stage & Commit
        if repo.status == "DIRTY":
            act_commit = QAction(_t("btn_stage_commit"), self)
            act_commit.setEnabled(repo.local_path is not None and repo.local_path.exists())
            act_commit.triggered.connect(lambda: self._commit_changes(repo))
            menu.addAction(act_commit)

        # Context action 7: Manage Stash Stack
        act_stash = QAction(_t("ctx_manage_stash"), self)
        act_stash.setEnabled(repo.local_path is not None and repo.local_path.exists())
        act_stash.triggered.connect(lambda: self._manage_stash(repo))
        menu.addAction(act_stash)

        # Context action 8: Prune Stale Branches
        act_prune = QAction(_t("ctx_prune_branches"), self)
        act_prune.setEnabled(repo.local_path is not None and repo.local_path.exists())
        act_prune.triggered.connect(lambda: self._prune_branches(repo))
        menu.addAction(act_prune)

        # Context action 9: View Git Log Graph
        act_graph = QAction(_t("ctx_view_log_graph"), self)
        act_graph.setEnabled(repo.local_path is not None and repo.local_path.exists())
        act_graph.triggered.connect(lambda: self._view_git_graph(repo))
        menu.addAction(act_graph)

        # Context action 10: Git LFS Status
        act_lfs = QAction(_t("ctx_lfs_status"), self)
        act_lfs.setEnabled(repo.local_path is not None and repo.local_path.exists())
        act_lfs.triggered.connect(lambda: self._view_lfs_status(repo))
        menu.addAction(act_lfs)

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

    def _switch_branch(self, repo: Repository) -> None:
        from github_org_sync.ui.dialogs import SwitchBranchDialog

        main_win = self.window()
        git_service = getattr(main_win, "git_service", None)
        if not git_service:
            from github_org_sync.services.git_service import GitService

            git_service = GitService()
        if repo.local_path is None:
            return

        branches = git_service.get_local_branches(Path(repo.local_path))
        if not branches:
            QMessageBox.warning(self, _t("error_open_title"), "No local branches found.")
            return

        dialog = SwitchBranchDialog(repo.name, branches, repo.branch, self)
        res = dialog.exec()
        if res == QDialog.DialogCode.Accepted and dialog.selected_branch:
            ok, output = git_service.checkout_branch(Path(repo.local_path), dialog.selected_branch)
            if ok:
                org_text = main_win.org_input.text().strip() if hasattr(main_win, "org_input") else ""
                status, branch, ahead, behind, msg = git_service.get_local_status(Path(repo.local_path), org_text)
                self.update_repository_status(repo.name, status, msg)
                repo.branch = branch
                repo.status = status
                repo.ahead = ahead
                repo.behind = behind
                for row in range(self.rowCount()):
                    name_item = self.item(row, self._col("col_name"))
                    if name_item and self._get_repo_name(name_item) == repo.name:
                        self.setItem(row, self._col("col_branch"), QTableWidgetItem(branch or ""))
                        self.setItem(
                            row, self._col("col_ahead"), NumericTableWidgetItem(str(ahead) if ahead is not None else "")
                        )
                        self.setItem(
                            row,
                            self._col("col_behind"),
                            NumericTableWidgetItem(str(behind) if behind is not None else ""),
                        )
                        break

                if hasattr(main_win, "log"):
                    main_win.log(f"Switched repository {repo.name} to branch {dialog.selected_branch}.")
            else:
                QMessageBox.warning(self, "Error", f"Failed to switch branch:\n{output}")

    def _commit_changes(self, repo: Repository) -> None:
        from github_org_sync.ui.dialogs import CommitDialog

        main_win = self.window()
        git_service = getattr(main_win, "git_service", None)
        org_text = main_win.org_input.text().strip() if hasattr(main_win, "org_input") else ""
        if not git_service:
            from github_org_sync.services.git_service import GitService

            git_service = GitService()
        if repo.local_path is None:
            return

        dialog = CommitDialog(repo, git_service, self)
        res = dialog.exec()
        if res == QDialog.DialogCode.Accepted and dialog.committed:
            status, branch, ahead, behind, msg = git_service.get_local_status(Path(repo.local_path), org_text)
            self.update_repository_status(repo.name, status, msg)
            repo.status = status
            repo.branch = branch
            repo.ahead = ahead
            repo.behind = behind
            for row in range(self.rowCount()):
                name_item = self.item(row, self._col("col_name"))
                if name_item and self._get_repo_name(name_item) == repo.name:
                    self.setItem(row, self._col("col_branch"), QTableWidgetItem(branch or ""))
                    self.setItem(
                        row, self._col("col_ahead"), NumericTableWidgetItem(str(ahead) if ahead is not None else "")
                    )
                    self.setItem(
                        row, self._col("col_behind"), NumericTableWidgetItem(str(behind) if behind is not None else "")
                    )
                    break
            if hasattr(main_win, "log"):
                main_win.log(f"Committed changes in repository {repo.name}. Status: {status}.")

    def _manage_stash(self, repo: Repository) -> None:
        from github_org_sync.ui.stash_dialog import StashDialog

        main_win = self.window()
        git_service = getattr(main_win, "git_service", None)
        org_text = main_win.org_input.text().strip() if hasattr(main_win, "org_input") else ""
        if not git_service:
            from github_org_sync.services.git_service import GitService

            git_service = GitService()
        if repo.local_path is None:
            return

        dialog = StashDialog(repo, git_service, self)
        dialog.exec()
        status, branch, ahead, behind, msg = git_service.get_local_status(Path(repo.local_path), org_text)
        self.update_repository_status(repo.name, status, msg)
        repo.status = status
        repo.branch = branch
        repo.ahead = ahead
        repo.behind = behind
        for row in range(self.rowCount()):
            name_item = self.item(row, self._col("col_name"))
            if name_item and self._get_repo_name(name_item) == repo.name:
                self.setItem(row, self._col("col_branch"), QTableWidgetItem(branch or ""))
                self.setItem(
                    row, self._col("col_ahead"), NumericTableWidgetItem(str(ahead) if ahead is not None else "")
                )
                self.setItem(
                    row, self._col("col_behind"), NumericTableWidgetItem(str(behind) if behind is not None else "")
                )
                break

    def _prune_branches(self, repo: Repository) -> None:
        from github_org_sync.ui.prune_dialog import PruneBranchesDialog

        main_win = self.window()
        git_service = getattr(main_win, "git_service", None)
        org_text = main_win.org_input.text().strip() if hasattr(main_win, "org_input") else ""
        if not git_service:
            from github_org_sync.services.git_service import GitService

            git_service = GitService()
        if repo.local_path is None:
            return

        dialog = PruneBranchesDialog(repo, git_service, self)
        dialog.exec()
        status, branch, ahead, behind, msg = git_service.get_local_status(Path(repo.local_path), org_text)
        self.update_repository_status(repo.name, status, msg)
        repo.status = status
        repo.branch = branch
        repo.ahead = ahead
        repo.behind = behind
        for row in range(self.rowCount()):
            name_item = self.item(row, self._col("col_name"))
            if name_item and self._get_repo_name(name_item) == repo.name:
                self.setItem(row, self._col("col_branch"), QTableWidgetItem(branch or ""))
                self.setItem(
                    row, self._col("col_ahead"), NumericTableWidgetItem(str(ahead) if ahead is not None else "")
                )
                self.setItem(
                    row, self._col("col_behind"), NumericTableWidgetItem(str(behind) if behind is not None else "")
                )
                break

    def _view_git_graph(self, repo: Repository) -> None:
        from github_org_sync.ui.graph_dialog import LogGraphDialog

        main_win = self.window()
        git_service = getattr(main_win, "git_service", None)
        if not git_service:
            from github_org_sync.services.git_service import GitService

            git_service = GitService()
        if repo.local_path is None:
            return

        dialog = LogGraphDialog(repo, git_service, self)
        dialog.exec()

    def _view_lfs_status(self, repo: Repository) -> None:
        from github_org_sync.ui.lfs_dialog import LfsDialog

        main_win = self.window()
        git_service = getattr(main_win, "git_service", None)
        if not git_service:
            from github_org_sync.services.git_service import GitService

            git_service = GitService()
        if repo.local_path is None:
            return

        dialog = LfsDialog(repo, git_service, self)
        dialog.exec()

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

    def _open_terminal(self, path: Path) -> None:
        try:
            if not open_terminal(path):
                raise RuntimeError("Could not find or launch terminal emulator.")
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
            name_item = self.item(row, self._col("col_name"))
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
