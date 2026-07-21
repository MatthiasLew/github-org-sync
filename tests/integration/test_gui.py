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
