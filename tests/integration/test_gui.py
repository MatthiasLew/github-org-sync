from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt

from github_org_sync.models.repository import Repository
from github_org_sync.ui.main_window import MainWindow


@pytest.fixture
def mock_services() -> tuple[MagicMock, MagicMock]:
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


def test_main_window_creation(qtbot, mock_services) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "GitHub Organization Sync"
    assert window.org_input.text() == ""
    assert window.auth_banner.isHidden()


def test_load_repositories_flow(qtbot, mock_services) -> None:
    mock_gh, _ = mock_services
    window = MainWindow()
    qtbot.addWidget(window)

    # 1. Validation warning for empty org name
    with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warn:
        qtbot.mouseClick(window.btn_load, Qt.MouseButton.LeftButton)
        mock_warn.assert_called_once()

    # 2. Set valid org and load
    window.org_input.setText("subactor")

    # We patch check_local_statuses to execute synchronously or mock it
    with patch("github_org_sync.workers.sync_worker.SyncService.check_local_statuses") as mock_check:
        mock_check.side_effect = lambda repos, ws, org, progress_callback: repos

        qtbot.mouseClick(window.btn_load, Qt.MouseButton.LeftButton)

        # Give some time for thread if it ran, but since it starts a QThread we might need qtbot.waitUntil
        qtbot.waitUntil(lambda: not window.btn_load.isEnabled() or len(window.repositories) > 0, timeout=2000)

    # Table should show filtered repositories (Include Archived: False, Include Forks: True)
    # Repo-a (archived: False, fork: False) -> shown
    # Repo-b (archived: True, fork: False) -> skipped
    # Repo-c (archived: False, fork: True) -> shown
    assert len(window.repositories) == 2
    assert window.repositories[0].name == "repo-a"
    assert window.repositories[1].name == "repo-c"


def test_selection_buttons(qtbot, mock_services) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    window.repositories = [
        Repository("repo-a", "url-a", "ssh-a", status="MISSING"),
        Repository("repo-b", "url-b", "ssh-b", status="UP_TO_DATE"),
    ]
    window.table.set_repositories(window.repositories)

    # Initial: MISSING is checked, UP_TO_DATE is checked?
    # In table code, checkbox is checked by default if MISSING or BEHIND/DIVERGED.
    # So repo-a is checked, repo-b is unchecked.
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

    # Click select missing
    window.table.select_missing()
    assert window.table.checkbox_map["repo-a"].isChecked()
    assert not window.table.checkbox_map["repo-b"].isChecked()
