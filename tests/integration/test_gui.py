from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt

from github_org_sync.models.repository import Repository
from github_org_sync.ui.main_window import MainWindow


@pytest.fixture
def mock_services() -> Generator[tuple[MagicMock, MagicMock], None, None]:
    with (
        patch("github_org_sync.ui.main_window.GitHubService") as mock_gh_cls,
        patch("github_org_sync.config.ConfigManager.load") as mock_load,
        patch("github_org_sync.config.ConfigManager.save"),
    ):
        mock_load.return_value = {
            "last_organization": "",
            "last_workspace": "",
            "use_ssh": False,
            "preserve_local_changes": True,
            "fetch_only": False,
            "dry_run": False,
            "include_archived": False,
            "include_forks": True,
            "window_width": 1000,
            "window_height": 700,
        }

        mock_gh = mock_gh_cls.return_value
        mock_gh.check_cli_installed.return_value = "gh version 2.30.0"
        mock_gh.check_auth_status.return_value = "Logged in to github.com account TestUser"
        mock_gh.list_repositories.return_value = [
            Repository("repo-a", "url-a", "ssh-a", is_archived=False, is_fork=False),
            Repository("repo-b", "url-b", "ssh-b", is_archived=True, is_fork=False),
            Repository("repo-c", "url-c", "ssh-c", is_archived=False, is_fork=True),
        ]
        yield mock_gh, mock_gh_cls


@pytest.mark.gui
@pytest.mark.integration
def test_main_window_creation(qtbot: Any, mock_services: tuple[MagicMock, MagicMock]) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert "GitHub" in window.windowTitle()
    assert window.org_input.text() == ""
    assert window.auth_banner.isHidden()


@pytest.mark.gui
@pytest.mark.integration
def test_load_repositories_flow(qtbot: Any, mock_services: tuple[MagicMock, MagicMock]) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    # 1. Check that load button is disabled initially since org name is empty
    assert not window.btn_load.isEnabled()

    # 2. Set valid org and load
    window.org_input.setText("subactor")
    qtbot.waitUntil(lambda: window.btn_load.isEnabled(), timeout=1000)

    with patch("github_org_sync.workers.sync_worker.SyncService.check_local_statuses") as mock_check:
        mock_check.side_effect = lambda repositories, workspace, org_name, progress_callback, is_cancelled_callback: (
            repositories
        )

        qtbot.mouseClick(window.btn_load, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: len(window.repositories) > 0, timeout=2000)

    # Table should show filtered repositories (Include Archived: False, Include Forks: True)
    assert len(window.repositories) == 2
    assert window.repositories[0].name == "repo-a"
    assert window.repositories[1].name == "repo-c"


@pytest.mark.gui
@pytest.mark.integration
def test_selection_buttons(qtbot: Any, mock_services: tuple[MagicMock, MagicMock]) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    window.repositories = [
        Repository("repo-a", "url-a", "ssh-a", status="MISSING"),
        Repository("repo-b", "url-b", "ssh-b", status="UP_TO_DATE"),
    ]
    window.table.set_repositories(window.repositories)

    # repo-a should be checked by default (MISSING)
    assert window.table.checkbox_map["repo-a"].isChecked()
    assert not window.table.checkbox_map["repo-b"].isChecked()

    # Click select all
    window.table.select_all()
    assert window.table.checkbox_map["repo-a"].isChecked()
    assert window.table.checkbox_map["repo-b"].isChecked()

    # Click select none
    window.table.select_none()
    assert not window.table.checkbox_map["repo-a"].isChecked()
    assert not window.table.checkbox_map["repo-b"].isChecked()


@pytest.mark.gui
@pytest.mark.integration
def test_scroll_selection_retention(qtbot: Any, mock_services: tuple[MagicMock, MagicMock]) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    repos = [
        Repository("repo-a", "url-a", "ssh-a", status="MISSING"),
        Repository("repo-b", "url-b", "ssh-b", status="UP_TO_DATE"),
    ]
    window.table.set_repositories(repos)

    # Check a box manually
    window.table.checkbox_map["repo-b"].setChecked(True)

    # Update repositories in-place and check that selection is retained
    updated_repos = [
        Repository("repo-a", "url-a", "ssh-a", status="UP_TO_DATE"),
        Repository("repo-b", "url-b", "ssh-b", status="UP_TO_DATE"),
    ]
    window.table.update_repositories_in_place(updated_repos)

    assert window.table.checkbox_map["repo-b"].isChecked()


@pytest.mark.gui
@pytest.mark.integration
def test_language_and_theme_switching(qtbot: Any, mock_services: tuple[MagicMock, MagicMock]) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    # Switch to English
    window.act_lang_en.trigger()
    assert window.act_lang_en.isChecked()

    # Switch to Dark Theme
    window.act_theme_dark.trigger()
    assert window.act_theme_dark.isChecked()


@pytest.mark.gui
@pytest.mark.integration
def test_double_click_resolve(qtbot: Any, mock_services: tuple[MagicMock, MagicMock]) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    repos = [Repository("repo-a", "url-a", "ssh-a", status="DIVERGED")]
    repos[0].local_path = Path("/dummy/path")

    # 1. Test double-click opens local folder
    with patch.object(window.table, "_open_folder") as mock_open, patch("pathlib.Path.exists") as mock_exists:
        mock_exists.return_value = True
        window.table.set_repositories(repos)

        # Trigger double click on the first row
        index = window.table.model().index(0, 1)
        window.table.doubleClicked.emit(index)
        mock_open.assert_called_once_with(Path("/dummy/path"))

    # 2. Test _resolve_issue triggers dialog
    with patch("github_org_sync.ui.dialogs.ResolveIssueDialog") as mock_dialog:
        from PySide6.QtWidgets import QDialog

        mock_dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted

        window.table._resolve_issue(repos[0])
        mock_dialog.assert_called_once()


@pytest.mark.gui
@pytest.mark.integration
def test_shutdown_lifecycle(qtbot: Any, mock_services: tuple[MagicMock, MagicMock]) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    # Close main window
    window.close()
    # Check that there are no active threads or background runs registered
    assert window.sync_worker is None or not window.sync_worker.isRunning()


@pytest.mark.gui
@pytest.mark.integration
def test_commit_dialog_flow(qtbot: Any) -> None:
    from github_org_sync.services.git_service import GitService
    from github_org_sync.ui.dialogs import CommitDialog

    repo = Repository("test-repo", "url", "ssh", status="DIRTY")
    repo.local_path = Path("/dummy")
    mock_git = MagicMock(spec=GitService)
    mock_git.get_staged_and_unstaged_files.return_value = (["staged.txt"], ["unstaged.txt"])
    mock_git.commit_changes.return_value = (True, "Committed")

    dialog = CommitDialog(repo, mock_git)
    qtbot.addWidget(dialog)

    assert dialog.staged_list.count() == 1
    assert dialog.unstaged_list.count() == 1

    dialog.msg_edit.setText("test commit")
    dialog._on_commit()

    assert dialog.committed is True
    mock_git.commit_changes.assert_called_once_with(Path("/dummy"), "test commit")


@pytest.mark.gui
@pytest.mark.integration
def test_stash_dialog_flow(qtbot: Any) -> None:
    from github_org_sync.services.git_service import GitService
    from github_org_sync.ui.stash_dialog import StashDialog

    repo = Repository("test-repo", "url", "ssh", status="DIRTY")
    repo.local_path = Path("/dummy")
    mock_git = MagicMock(spec=GitService)
    mock_git.get_stash_list.return_value = ["stash@{0}: WIP on main", "stash@{1}: test stash"]
    mock_git.get_stash_show.return_value = "file.py | 2 +-"
    mock_git.stash_pop.return_value = (True, "Applied stash@{0}")

    dialog = StashDialog(repo, mock_git)
    qtbot.addWidget(dialog)

    assert dialog.stash_list.count() == 2
    assert "file.py" in dialog.details_area.toPlainText()

    with patch("PySide6.QtWidgets.QMessageBox.information"):
        dialog._on_pop()
    mock_git.stash_pop.assert_called_once_with(Path("/dummy"), 0)


@pytest.mark.gui
@pytest.mark.integration
def test_prune_dialog_flow(qtbot: Any) -> None:
    from PySide6.QtWidgets import QMessageBox

    from github_org_sync.services.git_service import GitService
    from github_org_sync.ui.prune_dialog import PruneBranchesDialog

    repo = Repository("test-repo", "url", "ssh", status="UP_TO_DATE")
    repo.local_path = Path("/dummy")
    mock_git = MagicMock(spec=GitService)
    mock_git.prune_remote_branches.return_value = (True, "Pruning origin\n * [pruned] origin/old-branch")
    mock_git.get_stale_branches.return_value = [
        {"name": "old-branch", "upstream": "origin/old-branch", "reason": "gone"},
        {"name": "merged-feature", "upstream": "origin/merged-feature", "reason": "merged"},
    ]
    mock_git.delete_local_branch.return_value = (True, "Deleted")

    dialog = PruneBranchesDialog(repo, mock_git)
    qtbot.addWidget(dialog)

    assert dialog.branch_table.rowCount() == 2
    assert dialog.branch_table.item(0, 0) is not None
    assert dialog.branch_table.item(0, 0).text() == "old-branch"
    assert dialog.branch_table.item(1, 0) is not None
    assert dialog.branch_table.item(1, 0).text() == "merged-feature"

    with (
        patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes),
        patch("PySide6.QtWidgets.QMessageBox.information"),
    ):
        dialog._on_delete_selected()

    assert mock_git.delete_local_branch.call_count == 2


@pytest.mark.gui
@pytest.mark.integration
def test_log_graph_dialog_flow(qtbot: Any) -> None:
    from github_org_sync.services.git_service import GitService
    from github_org_sync.ui.graph_dialog import LogGraphDialog

    repo = Repository("test-repo", "url", "ssh", status="UP_TO_DATE")
    repo.local_path = Path("/dummy")
    mock_git = MagicMock(spec=GitService)
    mock_git.get_log_graph.return_value = "* 1234abc (HEAD -> main) Add feature"

    dialog = LogGraphDialog(repo, mock_git)
    qtbot.addWidget(dialog)

    assert "* 1234abc" in dialog.graph_view.toPlainText()
    mock_git.get_log_graph.assert_called_with(Path("/dummy"), limit=25, all_branches=True)

    dialog.limit_combo.setCurrentText("50")
    mock_git.get_log_graph.assert_called_with(Path("/dummy"), limit=50, all_branches=True)


@pytest.mark.gui
@pytest.mark.integration
def test_lfs_dialog_flow(qtbot: Any) -> None:
    from github_org_sync.services.git_service import GitService
    from github_org_sync.ui.lfs_dialog import LfsDialog

    repo = Repository("test-repo", "url", "ssh", status="UP_TO_DATE", has_lfs=True)
    repo.local_path = Path("/dummy")
    mock_git = MagicMock(spec=GitService)
    mock_git.get_lfs_status.return_value = {
        "has_lfs": True,
        "files": ["model.onnx", "dataset.zip"],
        "status": "Git LFS objects: 2 committed",
        "error": None,
    }

    dialog = LfsDialog(repo, mock_git)
    qtbot.addWidget(dialog)

    assert dialog.files_list.count() == 2
    assert "Git LFS objects" in dialog.status_view.toPlainText()
    mock_git.get_lfs_status.assert_called_once_with(Path("/dummy"))
