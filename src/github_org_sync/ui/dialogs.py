import time
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from github_org_sync.i18n import _t
from github_org_sync.models.repository import Repository
from github_org_sync.models.sync_result import SyncResult
from github_org_sync.services.git_service import GitService
from github_org_sync.utils.process import open_terminal


class CompareChangesDialog(QDialog):
    def __init__(self, repo: Repository, git_service: GitService, org_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repo = repo
        self.git_service = git_service
        self.org_name = org_name
        self.path = repo.local_path

        self.setWindowTitle(_t("compare_title", repo=repo.name))
        self.resize(800, 600)
        self._setup_ui()
        self._load_changes()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Info Header
        self.info_label = QLabel(self)
        self.info_label.setStyleSheet("font-weight: bold; font-size: 11pt; color: #e2e8f0;")
        layout.addWidget(self.info_label)

        # Main Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left list widget
        self.list_widget = QListWidget(self)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        splitter.addWidget(self.list_widget)

        # Right text area for diff / details
        self.text_area = QTextEdit(self)
        self.text_area.setReadOnly(True)
        self.text_area.setStyleSheet(
            "font-family: Consolas, Courier New, monospace; background-color: #0f172a; color: #f8fafc;"
        )
        splitter.addWidget(self.text_area)

        splitter.setSizes([300, 500])
        layout.addWidget(splitter)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_copy = QPushButton(_t("btn_copy_instructions"), self)
        self.btn_copy.clicked.connect(self._copy_instructions)
        btn_layout.addWidget(self.btn_copy)

        btn_layout.addStretch()

        self.btn_close = QPushButton(_t("btn_cancel"), self)
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _load_changes(self) -> None:
        path = self.path
        if not path or not path.exists():
            self.info_label.setText("Local path does not exist.")
            return

        status, branch, ahead, behind, msg = self.git_service.get_local_status(path, self.org_name)
        upstream = f"origin/{branch}" if branch else "origin"
        self.info_label.setText(
            f"Branch: {branch or 'HEAD'} | Upstream: {upstream} | Ahead: {ahead or 0} | Behind: {behind or 0}"
        )

        self.list_widget.clear()

        # Helper to style list category headers
        def style_header(item_obj: QListWidgetItem, color_hex: str) -> None:
            font = item_obj.font()
            font.setBold(True)
            item_obj.setFont(font)
            item_obj.setForeground(QBrush(QColor(color_hex)))
            item_obj.setBackground(QBrush(QColor("#1e293b")))

        # 1. Uncommitted (dirty) files
        dirty_files = self.git_service.get_dirty_files(path)
        if dirty_files:
            item = QListWidgetItem(_t("compare_dirty_files"))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            style_header(item, "#fbbf24")
            self.list_widget.addItem(item)
            for status_code, fpath in dirty_files:
                file_item = QListWidgetItem(f"  [{status_code}] {fpath}")
                file_item.setData(Qt.ItemDataRole.UserRole, {"type": "dirty", "path": fpath})
                self.list_widget.addItem(file_item)

        # 2. Local unpushed commits (ahead)
        if branch and ahead:
            unpushed = self.git_service.get_unpushed_commits(path, branch, upstream)
            if unpushed:
                item = QListWidgetItem(_t("compare_local_commits"))
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                style_header(item, "#60a5fa")
                self.list_widget.addItem(item)
                for c in unpushed:
                    c_item = QListWidgetItem(f"  {c['sha'][:8]} - {c['subject']}")
                    c_item.setData(Qt.ItemDataRole.UserRole, {"type": "commit", "sha": c["sha"]})
                    self.list_widget.addItem(c_item)

        # 3. Remote commits (behind)
        if branch and behind:
            _, remote_commits, _ = self.git_service.get_diverged_commits(path, branch, upstream)
            if remote_commits:
                item = QListWidgetItem(_t("compare_remote_commits"))
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                style_header(item, "#f43f5e")
                self.list_widget.addItem(item)
                for c in remote_commits:
                    c_item = QListWidgetItem(f"  {c['sha'][:8]} - {c['subject']}")
                    c_item.setData(Qt.ItemDataRole.UserRole, {"type": "commit", "sha": c["sha"]})
                    self.list_widget.addItem(c_item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        path = self.path
        if not data or not path:
            return

        if data["type"] == "dirty":
            diff = self.git_service.get_file_diff(path, data["path"])
            self.text_area.setPlainText(diff if diff.strip() else "No differences found (binary or untracked).")
        elif data["type"] == "commit":
            details = self.git_service.get_commit_show(path, data["sha"])
            self.text_area.setPlainText(details)

    def _copy_instructions(self) -> None:
        instructions = _t("instructions_dirty")
        QApplication.clipboard().setText(instructions)
        QMessageBox.information(self, "Copy", "Instructions copied to clipboard.")


class ResolveIssueDialog(QDialog):
    def __init__(self, repo: Repository, git_service: GitService, org_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repo = repo
        self.git_service = git_service
        self.org_name = org_name
        self.path = repo.local_path
        self.decision = "KEEP_AND_SKIP"
        self.backup_path: str | None = None

        self.setWindowTitle(_t("resolve_title", repo=repo.name))
        self.resize(550, 400)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Status description
        self.desc_label = QLabel(self)
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("font-weight: bold; font-size: 11pt; color: #fbbf24;")
        layout.addWidget(self.desc_label)

        # Detailed view widget
        self.details_area = QTextEdit(self)
        self.details_area.setReadOnly(True)
        self.details_area.setStyleSheet(
            "font-family: Consolas, Courier New, monospace; background-color: #0f172a; color: #f8fafc;"
        )
        layout.addWidget(self.details_area)

        # Buttons layout
        self.btn_layout = QVBoxLayout()
        layout.addLayout(self.btn_layout)

        # Bottom row options
        bottom_layout = QHBoxLayout()
        self.btn_terminal = QPushButton(_t("btn_open_terminal"), self)
        self.btn_terminal.clicked.connect(self._open_terminal)
        bottom_layout.addWidget(self.btn_terminal)

        bottom_layout.addStretch()

        self.btn_cancel = QPushButton(_t("btn_cancel"), self)
        self.btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(self.btn_cancel)
        layout.addLayout(bottom_layout)

        self._populate_state_options()

    def _populate_state_options(self) -> None:
        path = self.path
        if path is None:
            return

        status = self.repo.status
        self.desc_label.setText(_t(f"resolve_{status.lower()}_desc"))

        # Clear layouts in a type-safe way
        for i in reversed(range(self.btn_layout.count())):
            item = self.btn_layout.itemAt(i)
            if item:
                w = item.widget()
                if w:
                    w.setParent(None)

        if status == "DIRTY":
            dirty = self.git_service.get_dirty_files(path)
            self.details_area.setPlainText("\n".join(f"[{code}] {fpath}" for code, fpath in dirty))

            btn_keep = QPushButton(_t("btn_keep_skip"), self)
            btn_keep.clicked.connect(lambda: self._accept_decision("KEEP_AND_SKIP"))
            self.btn_layout.addWidget(btn_keep)

            btn_stash = QPushButton(_t("btn_stash_update"), self)
            btn_stash.clicked.connect(lambda: self._accept_decision("STASH_AND_UPDATE"))
            self.btn_layout.addWidget(btn_stash)

            btn_discard = QPushButton(_t("btn_discard_changes"), self)
            btn_discard.setStyleSheet("background-color: #7f1d1d; color: #fca5a5;")
            btn_discard.clicked.connect(self._on_discard_changes)
            self.btn_layout.addWidget(btn_discard)

        elif status == "AHEAD":
            upstream_branch = f"origin/{self.repo.branch or 'main'}"
            branch_name = self.repo.branch or "main"
            commits = self.git_service.get_unpushed_commits(path, branch_name, upstream_branch)
            self.details_area.setPlainText("\n".join(f"{c['sha'][:8]} - {c['subject']}" for c in commits))

            btn_keep = QPushButton(_t("btn_keep_skip"), self)
            btn_keep.clicked.connect(lambda: self._accept_decision("KEEP_AND_SKIP"))
            self.btn_layout.addWidget(btn_keep)

            btn_push = QPushButton(_t("btn_push_commits"), self)
            btn_push.clicked.connect(self._on_push_commits)
            self.btn_layout.addWidget(btn_push)

            btn_backup = QPushButton(_t("btn_create_backup_branch"), self)
            btn_backup.clicked.connect(self._on_create_backup_branch)
            self.btn_layout.addWidget(btn_backup)

        elif status == "BEHIND":
            upstream_branch = f"origin/{self.repo.branch or 'main'}"
            branch_name = self.repo.branch or "main"
            _, remote_commits, _ = self.git_service.get_diverged_commits(path, branch_name, upstream_branch)
            self.details_area.setPlainText("\n".join(f"{c['sha'][:8]} - {c['subject']}" for c in remote_commits))

            btn_pull = QPushButton(_t("btn_pull_ff"), self)
            btn_pull.clicked.connect(self._on_pull_ff)
            self.btn_layout.addWidget(btn_pull)

            btn_stash = QPushButton(_t("btn_stash_update"), self)
            btn_stash.clicked.connect(lambda: self._accept_decision("STASH_AND_UPDATE"))
            self.btn_layout.addWidget(btn_stash)

            btn_keep = QPushButton(_t("btn_keep_skip"), self)
            btn_keep.clicked.connect(lambda: self._accept_decision("KEEP_AND_SKIP"))
            self.btn_layout.addWidget(btn_keep)

        elif status == "DIVERGED":
            upstream_branch = f"origin/{self.repo.branch or 'main'}"
            branch_name = self.repo.branch or "main"
            local_commits, remote_commits, base = self.git_service.get_diverged_commits(
                path, branch_name, upstream_branch
            )
            details = f"Common Base: {base[:8] if base else 'unknown'}\n\nLocal Commits (Ahead):\n"
            details += "\n".join(f"  {c['sha'][:8]} - {c['subject']}" for c in local_commits)
            details += "\n\nRemote Commits (Behind):\n"
            details += "\n".join(f"  {c['sha'][:8]} - {c['subject']}" for c in remote_commits)
            self.details_area.setPlainText(details)

            btn_keep = QPushButton(_t("btn_keep_skip"), self)
            btn_keep.clicked.connect(lambda: self._accept_decision("KEEP_AND_SKIP"))
            self.btn_layout.addWidget(btn_keep)

            btn_merge = QPushButton(_t("btn_merge"), self)
            btn_merge.clicked.connect(self._on_merge)
            self.btn_layout.addWidget(btn_merge)

            btn_rebase = QPushButton(_t("btn_rebase"), self)
            btn_rebase.clicked.connect(self._on_rebase)
            self.btn_layout.addWidget(btn_rebase)

            btn_reset = QPushButton(_t("btn_reset_remote"), self)
            btn_reset.setStyleSheet("background-color: #7f1d1d; color: #fca5a5;")
            btn_reset.clicked.connect(self._on_reset_remote)
            self.btn_layout.addWidget(btn_reset)

        elif status == "CONFLICT":
            conflicts = self.git_service.get_conflict_files(path)
            self.details_area.setPlainText("\n".join(conflicts))

            btn_abort_merge = QPushButton(_t("btn_abort_merge"), self)
            btn_abort_merge.clicked.connect(lambda: self._run_git_action(self.git_service.abort_merge, "ABORTED"))
            self.btn_layout.addWidget(btn_abort_merge)

            btn_abort_rebase = QPushButton(_t("btn_abort_rebase"), self)
            btn_abort_rebase.clicked.connect(lambda: self._run_git_action(self.git_service.abort_rebase, "ABORTED"))
            self.btn_layout.addWidget(btn_abort_rebase)

            btn_keep = QPushButton(_t("btn_keep_skip"), self)
            btn_keep.clicked.connect(lambda: self._accept_decision("KEEP_AND_SKIP"))
            self.btn_layout.addWidget(btn_keep)

        elif status == "NO_UPSTREAM":
            self.details_area.setPlainText(
                f"Local branch: {self.repo.branch or 'HEAD'}\nRemote origin does not track this branch."
            )

            btn_upstream = QPushButton(_t("btn_set_upstream"), self)
            btn_upstream.clicked.connect(self._on_set_upstream)
            self.btn_layout.addWidget(btn_upstream)

            btn_keep = QPushButton(_t("btn_keep_skip"), self)
            btn_keep.clicked.connect(lambda: self._accept_decision("KEEP_AND_SKIP"))
            self.btn_layout.addWidget(btn_keep)

        elif status == "DETACHED_HEAD":
            self.details_area.setPlainText(
                "Currently detached at HEAD.\nCommits made in this state might be lost unless a branch is created."
            )

            btn_create = QPushButton(_t("btn_create_branch"), self)
            btn_create.clicked.connect(self._on_create_branch)
            self.btn_layout.addWidget(btn_create)

            btn_keep = QPushButton(_t("btn_keep_skip"), self)
            btn_keep.clicked.connect(lambda: self._accept_decision("KEEP_AND_SKIP"))
            self.btn_layout.addWidget(btn_keep)

    def _accept_decision(self, decision: str) -> None:
        self.decision = decision
        self.accept()

    def _open_terminal(self) -> None:
        path = self.path
        if path:
            open_terminal(path)

    def _on_discard_changes(self) -> None:
        path = self.path
        if path is None:
            return

        # Double confirmation
        ans1 = QMessageBox.warning(
            self,
            _t("confirm_discard_title"),
            _t("confirm_discard_msg"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans1 != QMessageBox.StandardButton.Yes:
            return

        ans2 = QMessageBox.critical(
            self,
            _t("confirm_discard_title"),
            "Warning: This is the second confirmation. Click YES to permanently wipe local modifications.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans2 != QMessageBox.StandardButton.Yes:
            return

        # Perform Backup
        zip_path = self.git_service.backup_repository(path, self.org_name, self.repo.name)
        if zip_path:
            self.backup_path = str(zip_path)
            QMessageBox.information(self, "Backup", f"Backup created successfully:\n{zip_path}")
        else:
            QMessageBox.warning(self, "Backup Error", "Could not create zip backup. Aborting discard operation.")
            return

        # Discard
        if self.git_service.discard_changes(path):
            QMessageBox.information(self, "Success", "Local changes discarded.")
            self._accept_decision("DISCARDED")
        else:
            QMessageBox.warning(self, "Error", "Failed to discard local changes.")

    def _on_push_commits(self) -> None:
        path = self.path
        branch_name = self.repo.branch
        if path is None or branch_name is None:
            return

        # Verify push does not require force
        cp_dry = self.git_service._run_git(path, ["push", "--dry-run", "origin", branch_name])
        if cp_dry.returncode != 0:
            err_msg = (cp_dry.stderr or cp_dry.stdout).strip()
            QMessageBox.warning(self, "Push Warning", f"Push requires force or is rejected:\n{err_msg}")
            return

        cp = self.git_service.push_commits(path, branch_name)
        if cp.returncode == 0:
            QMessageBox.information(self, "Success", "Commits pushed to origin.")
            self._accept_decision("PUSHED")
        else:
            QMessageBox.warning(self, "Error", f"Push failed: {cp.stderr or cp.stdout}")

    def _on_create_backup_branch(self) -> None:
        path = self.path
        branch_name = self.repo.branch
        if path is None or branch_name is None:
            return

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_name = f"backup-{branch_name}-{timestamp}"
        cp = self.git_service.create_branch(path, backup_name)
        if cp.returncode == 0:
            # Checkout old branch back
            self.git_service._run_git(path, ["checkout", branch_name])
            QMessageBox.information(self, "Success", f"Backup branch created:\n{backup_name}")
        else:
            QMessageBox.warning(self, "Error", f"Failed to create branch: {cp.stderr or cp.stdout}")

    def _on_pull_ff(self) -> None:
        path = self.path
        if path is None:
            return

        cp = self.git_service._run_git(path, ["pull", "--ff-only"])
        if cp.returncode == 0:
            QMessageBox.information(self, "Success", "Repository updated via Pull Fast-Forward.")
            self._accept_decision("PULLED")
        else:
            QMessageBox.warning(self, "Error", f"Pull failed:\n{cp.stderr or cp.stdout}")

    def _on_merge(self) -> None:
        path = self.path
        branch_name = self.repo.branch
        if path is None or branch_name is None:
            return

        upstream = f"origin/{branch_name}"
        cp = self.git_service.merge_branch(path, upstream)
        if cp.returncode == 0:
            QMessageBox.information(self, "Success", f"Merged {upstream} successfully.")
            self._accept_decision("MERGED")
        else:
            # Check for conflict
            conflicts = self.git_service.get_conflict_files(path)
            if conflicts:
                QMessageBox.warning(self, "Merge Conflict", "Merge ended with conflicts. Resolve files manually.")
                self.repo.status = "CONFLICT"
                self._populate_state_options()
            else:
                QMessageBox.warning(self, "Error", f"Merge failed:\n{cp.stderr or cp.stdout}")

    def _on_rebase(self) -> None:
        path = self.path
        branch_name = self.repo.branch
        if path is None or branch_name is None:
            return

        upstream = f"origin/{branch_name}"
        cp = self.git_service.rebase_branch(path, upstream)
        if cp.returncode == 0:
            QMessageBox.information(self, "Success", f"Rebased onto {upstream} successfully.")
            self._accept_decision("REBASED")
        else:
            conflicts = self.git_service.get_conflict_files(path)
            if conflicts:
                QMessageBox.warning(self, "Rebase Conflict", "Rebase ended with conflicts. Resolve files manually.")
                self.repo.status = "CONFLICT"
                self._populate_state_options()
            else:
                QMessageBox.warning(self, "Error", f"Rebase failed:\n{cp.stderr or cp.stdout}")

    def _on_reset_remote(self) -> None:
        path = self.path
        branch_name = self.repo.branch
        if path is None or branch_name is None:
            return

        ans1 = QMessageBox.warning(
            self,
            _t("confirm_reset_title"),
            _t("confirm_reset_msg"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans1 != QMessageBox.StandardButton.Yes:
            return

        # Perform Backup
        zip_path = self.git_service.backup_repository(path, self.org_name, self.repo.name)
        if zip_path:
            self.backup_path = str(zip_path)
            QMessageBox.information(self, "Backup", f"Backup created successfully:\n{zip_path}")
        else:
            QMessageBox.warning(self, "Backup Error", "Could not create zip backup. Aborting reset operation.")
            return

        upstream = f"origin/{branch_name}"
        cp = self.git_service._run_git(path, ["reset", "--hard", upstream])
        if cp.returncode == 0:
            QMessageBox.information(self, "Success", f"Branch reset to {upstream}.")
            self._accept_decision("RESET")
        else:
            QMessageBox.warning(self, "Error", f"Reset failed:\n{cp.stderr or cp.stdout}")

    def _on_set_upstream(self) -> None:
        path = self.path
        branch_name = self.repo.branch
        if path is None or branch_name is None:
            return

        # Try pushing and setting upstream
        cp = self.git_service.push_set_upstream(path, branch_name)
        if cp.returncode == 0:
            QMessageBox.information(self, "Success", "Branch pushed and upstream tracked.")
            self._accept_decision("UPSTREAM_SET")
        else:
            QMessageBox.warning(self, "Error", f"Push and set-upstream failed:\n{cp.stderr or cp.stdout}")

    def _on_create_branch(self) -> None:
        path = self.path
        if path is None:
            return

        text, ok = QInputDialog.getText(self, "Create Branch", "Enter new branch name:")
        if ok and text.strip():
            cp = self.git_service.create_branch(path, text.strip())
            if cp.returncode == 0:
                QMessageBox.information(self, "Success", f"Checked out new branch: {text.strip()}")
                self._accept_decision("BRANCH_CREATED")
            else:
                QMessageBox.warning(self, "Error", f"Branch creation failed:\n{cp.stderr or cp.stdout}")

    def _run_git_action(self, func: Any, decision: str) -> None:
        path = self.path
        if path is None:
            return
        cp = func(path)
        if cp.returncode == 0:
            QMessageBox.information(self, "Success", "Operation succeeded.")
            self._accept_decision(decision)
        else:
            QMessageBox.warning(self, "Error", f"Operation failed:\n{cp.stderr or cp.stdout}")


class WorkspaceWizardDialog(QDialog):
    def __init__(
        self,
        repositories: list[Repository],
        workspace: Path,
        org_name: str,
        git_service: GitService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repositories = repositories
        self.workspace = workspace
        self.org_name = org_name
        self.git_service = git_service
        self.decision_queue: list[Repository] = []
        self.results: list[SyncResult] = []

        # Counts for summary
        self.c_updated = 0
        self.c_uptodate = 0
        self.c_resolved = 0
        self.c_skipped = 0
        self.c_conflict = 0
        self.c_failed = 0

        self.setWindowTitle(_t("wizard_title"))
        self.resize(500, 350)
        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)

        self.info_label = QLabel(_t("wizard_intro"), self)
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("font-size: 11pt; color: #e2e8f0; line-height: 1.4;")
        main_layout.addWidget(self.info_label)

        self.progress_label = QLabel(self)
        self.progress_label.setWordWrap(True)
        self.progress_label.setStyleSheet("font-size: 10pt; color: #94a3b8;")
        main_layout.addWidget(self.progress_label)
        self.progress_label.hide()

        main_layout.addStretch()

        self.btn_layout = QHBoxLayout()
        self.btn_start = QPushButton(_t("wizard_start"), self)
        self.btn_start.clicked.connect(self._run_wizard)
        self.btn_layout.addWidget(self.btn_start)

        self.btn_cancel = QPushButton(_t("btn_cancel"), self)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_layout.addWidget(self.btn_cancel)

        main_layout.addLayout(self.btn_layout)

    def _run_wizard(self) -> None:
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.info_label.setText(_t("wizard_running"))
        self.progress_label.show()
        QApplication.processEvents()

        total = len(self.repositories)
        for idx, repo in enumerate(self.repositories):
            self.progress_label.setText(f"Checking {idx + 1}/{total}: {repo.name}...")
            QApplication.processEvents()

            # 1. Ensure local path is set
            repo.local_path = self.workspace / repo.name
            local_path = repo.local_path

            # If missing locally, skip or we can mark it
            if repo.status == "MISSING" or not local_path.exists():
                self.c_skipped += 1
                res = SyncResult(
                    repo_name=repo.name,
                    requested_action="SYNC",
                    performed_action="SKIPPED",
                    before_status="MISSING",
                    after_status="MISSING",
                    result="Skipped missing repository",
                )
                self.results.append(res)
                continue

            # 2. Run Fetch
            cp_fetch = self.git_service._run_git(local_path, ["fetch", "--prune"])
            if cp_fetch.returncode != 0:
                self.c_failed += 1
                res = SyncResult(
                    repo_name=repo.name,
                    requested_action="SYNC",
                    performed_action="FAILED",
                    before_status=repo.status,
                    after_status=repo.status,
                    error=cp_fetch.stderr.strip(),
                    result="Fetch failed",
                )
                self.results.append(res)
                continue

            # 3. Classify status
            status, branch, ahead, behind, msg = self.git_service.get_local_status(local_path, self.org_name)
            repo.status = status
            repo.branch = branch
            repo.ahead = ahead
            repo.behind = behind
            repo.result = msg

            if status == "UP_TO_DATE":
                self.c_uptodate += 1
                res = SyncResult(
                    repo_name=repo.name,
                    requested_action="SYNC",
                    performed_action="NO_CHANGE",
                    before_status=status,
                    after_status=status,
                    result="Repository was already up to date.",
                )
                self.results.append(res)

            elif status == "BEHIND" and len(self.git_service.get_dirty_files(local_path)) == 0:
                # Safe auto fast-forward update case
                start_time = time.time()
                cp_pull = self.git_service._run_git(local_path, ["pull", "--ff-only"])
                duration = time.time() - start_time
                if cp_pull.returncode == 0:
                    self.c_updated += 1
                    post_status, _, _, _, _ = self.git_service.get_local_status(local_path, self.org_name)
                    repo.status = post_status
                    res = SyncResult(
                        repo_name=repo.name,
                        requested_action="SYNC",
                        performed_action="UPDATED",
                        before_status=status,
                        after_status=post_status,
                        duration=duration,
                        result="Auto-updated via fast-forward pull.",
                    )
                    self.results.append(res)
                else:
                    self.decision_queue.append(repo)
            else:
                # Requires decision
                self.decision_queue.append(repo)

        # Process Decision Queue
        total_decisions = len(self.decision_queue)
        for d_idx, repo in enumerate(self.decision_queue):
            self.progress_label.setText(_t("wizard_queue", current=d_idx + 1, total=total_decisions))
            QApplication.processEvents()

            dialog = ResolveIssueDialog(repo, self.git_service, self.org_name, self)
            res_code = dialog.exec()

            final_path = repo.local_path
            if final_path is None:
                continue

            # Recheck final status
            final_status, _, final_ahead, final_behind, _ = self.git_service.get_local_status(final_path, self.org_name)
            repo.status = final_status

            # Map action performed
            perf = "SKIPPED"
            if res_code == QDialog.DialogCode.Accepted:
                if dialog.decision in (
                    "DISCARDED",
                    "PUSHED",
                    "PULLED",
                    "MERGED",
                    "REBASED",
                    "RESET",
                    "UPSTREAM_SET",
                    "BRANCH_CREATED",
                ):
                    perf = "UPDATED"
                elif dialog.decision == "STASH_AND_UPDATE":
                    # run pull
                    self.git_service._run_git(
                        final_path, ["stash", "push", "--include-untracked", "-m", "wizard stash"]
                    )
                    cp_p = self.git_service._run_git(final_path, ["pull", "--ff-only"])
                    self.git_service._run_git(final_path, ["stash", "pop"])
                    perf = "UPDATED" if cp_p.returncode == 0 else "CONFLICT"

            if final_status == "CONFLICT" or perf == "CONFLICT":
                self.c_conflict += 1
            elif final_status == "FAILED" or perf == "FAILED":
                self.c_failed += 1
            else:
                self.c_resolved += 1

            res = SyncResult(
                repo_name=repo.name,
                requested_action="SYNC",
                performed_action=perf,
                before_status=repo.status,
                after_status=final_status,
                user_decision=dialog.decision,
                backup_created=dialog.backup_path,
                result=f"Resolved via decision: {dialog.decision}.",
            )
            self.results.append(res)

        # Show Summary
        self.progress_label.hide()
        self.info_label.setText(_t("wizard_done"))
        summary = _t(
            "wizard_summary",
            updated=self.c_updated,
            uptodate=self.c_uptodate,
            resolved=self.c_resolved,
            skipped=self.c_skipped,
            conflict=self.c_conflict,
            failed=self.c_failed,
        )

        QMessageBox.information(self, _t("wizard_title"), summary)
        self.accept()
