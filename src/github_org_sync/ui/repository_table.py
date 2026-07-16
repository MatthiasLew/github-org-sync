from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QCheckBox, QHBoxLayout, QWidget
from typing import List, Dict
from github_org_sync.models.repository import Repository

class RepositoryTable(QTableWidget):
    COLUMNS = [
        "Selected", "Repository", "Visibility", "Archived", 
        "Local Status", "Branch", "Ahead", "Behind", "Action", "Result"
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repositories: List[Repository] = []
        self.checkbox_map: Dict[str, QCheckBox] = {}
        
        self.setColumnCount(len(self.COLUMNS))
        self.setHorizontalHeaderLabels(self.COLUMNS)
        
        # Table configuration
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setStyleSheet("QTableWidget { alternate-background-color: #1e293b; background-color: #111827; }")
        
        # Header sizing
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        
        # Let's set some default widths
        self.setColumnWidth(0, 70)   # Selected
        self.setColumnWidth(1, 160)  # Repository
        self.setColumnWidth(2, 90)   # Visibility
        self.setColumnWidth(3, 80)   # Archived
        self.setColumnWidth(4, 120)  # Local Status
        self.setColumnWidth(5, 100)  # Branch
        self.setColumnWidth(6, 60)   # Ahead
        self.setColumnWidth(7, 60)   # Behind
        self.setColumnWidth(8, 90)   # Action

    def set_repositories(self, repos: List[Repository]) -> None:
        """Populates the table with repository data."""
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
            self.setItem(idx, 1, QTableWidgetItem(repo.name))
            
            # Column 2: Visibility
            self.setItem(idx, 2, QTableWidgetItem(repo.visibility.upper()))
            
            # Column 3: Archived
            arch_text = "YES" if repo.is_archived else "NO"
            self.setItem(idx, 3, QTableWidgetItem(arch_text))
            
            # Column 4: Local Status
            status_item = QTableWidgetItem(repo.status)
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
            res_val = repo.result or ""
            self.setItem(idx, 9, QTableWidgetItem(res_val))

    def update_repository_status(self, repo_name: str, status: str, message: str | None = None) -> None:
        """Dynamically updates a repository row's status, action, and result."""
        for row in range(self.rowCount()):
            name_item = self.item(row, 1)
            if name_item and name_item.text() == repo_name:
                # Find matching repo model to update local attributes too
                for repo in self.repositories:
                    if repo.name == repo_name:
                        repo.status = status
                        if message is not None:
                            repo.result = message
                        
                        # Update status item
                        status_item = self.item(row, 4)
                        if status_item:
                            status_item.setText(status)
                            self._style_status_item(status_item, status)
                            
                        # Update action item
                        action_item = self.item(row, 8)
                        if action_item:
                            action_item.setText(self._determine_action(repo))
                            
                        # Update result item
                        res_item = self.item(row, 9)
                        if res_item and message is not None:
                            res_item.setText(message)
                        
                        # Update branch/ahead/behind from repo state if updated
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

    def get_selected_repositories(self) -> List[Repository]:
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
            item.setForeground(QBrush(QColor("#10b981"))) # Soft emerald
        elif status in ("FAILED", "CONFLICT"):
            item.setForeground(QBrush(QColor("#f43f5e"))) # Soft rose red
        elif status in ("DIRTY", "AHEAD", "BEHIND", "DIVERGED", "WRONG_REMOTE"):
            item.setForeground(QBrush(QColor("#f59e0b"))) # Soft amber
        else:
            item.setForeground(QBrush(QColor("#94a3b8"))) # Soft slate gray

    def _determine_action(self, repo: Repository) -> str:
        if repo.status == "MISSING":
            return "CLONE"
        elif repo.status in ("BEHIND", "DIRTY", "DIVERGED", "UP_TO_DATE", "AHEAD"):
            return "UPDATE"
        return "SKIP"
