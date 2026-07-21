from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from github_org_sync.i18n import _t
from github_org_sync.models.repository import Repository
from github_org_sync.ui.main_window import MainWindow
from tests.integration.test_workspace_scan_integration import init_git_repo

pytestmark = [pytest.mark.gui, pytest.mark.integration]


@pytest.fixture
def mock_gui_services() -> Any:
    with (
        patch("github_org_sync.ui.main_window.GitHubService") as mock_gh_cls,
        patch("github_org_sync.config.ConfigManager.load") as mock_load,
        patch("github_org_sync.config.ConfigManager.save") as mock_save,
    ):
        mock_load.return_value = {
            "last_organization": "subactor",
            "last_workspace": "",
            "use_ssh": False,
            "preserve_local_changes": True,
            "fetch_only": False,
            "dry_run": False,
            "include_archived": False,
            "include_forks": True,
            "window_width": 1000,
            "window_height": 700,
            "window_x": 10,
            "window_y": 10,
            "language": "pl",
            "theme": "System",
            "column_widths": [80] * 10,
            "last_mode": "clone",
            "scan_recursive": False,
        }
        mock_gh = mock_gh_cls.return_value
        mock_gh.check_cli_installed.return_value = "gh version 2.30.0"
        mock_gh.check_auth_status.return_value = "Logged in to github.com account TestUser"
        mock_gh.list_repositories.return_value = [
            Repository("repo-a", "https://github.com/my-org/repo-a.git", "git@github.com:my-org/repo-a.git"),
            Repository("repo-b", "https://github.com/my-org/repo-b.git", "git@github.com:my-org/repo-b.git"),
        ]
        yield mock_gh, mock_save


def test_mode_toggle_and_ui_states(qtbot: Any, mock_gui_services: Any) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    # By default, starts in clone mode
    assert window.current_mode == "clone"
    assert window.stacked_widget.currentIndex() == 0

    # Switch to workspace mode
    window.switch_mode("workspace")
    assert window.current_mode == "workspace"
    assert window.stacked_widget.currentIndex() == 1
    assert window.btn_mode_workspace.isChecked() is True

    # Switch back to clone mode
    window.switch_mode("clone")
    assert window.current_mode == "clone"
    assert window.stacked_widget.currentIndex() == 0
    assert window.btn_mode_clone.isChecked() is True


@pytest.mark.git
def test_workspace_scanning_flow(qtbot: Any, mock_gui_services: Any, tmp_path: Path) -> None:
    # Set up mock local repos:
    # tmp_path / repo-github (GitHub / org-a)
    # tmp_path / repo-gitlab (GitLab / org-b)
    # tmp_path / repo-none (No remote)
    repo_gh = tmp_path / "repo-github"
    repo_gl = tmp_path / "repo-gitlab"
    repo_no = tmp_path / "repo-none"

    init_git_repo(repo_gh, remote_url="https://github.com/org-a/repo-github.git")
    init_git_repo(repo_gl, remote_url="https://gitlab.com/org-b/repo-gitlab.git")
    init_git_repo(repo_no)

    window = MainWindow()
    qtbot.addWidget(window)

    window.switch_mode("workspace")
    window.workspace_input.setText(str(tmp_path))

    # Trigger scan
    window.btn_scan_workspace.click()

    # Wait until scanning finished
    qtbot.waitUntil(lambda: window.app_state == "IDLE", timeout=10000)

    # Check table count and host prefixes in Column 1
    assert window.table.rowCount() == 3

    # Check that repositories were correctly prefix-tagged
    # Sort or check all rows
    row_texts = [window.table.item(r, 1).text() for r in range(3)]
    assert "repo-github" in row_texts or "[GitHub] repo-github" in row_texts  # GitHub has no prefix display
    assert "[GitLab] repo-gitlab" in row_texts
    assert "[No remote] repo-none" in row_texts

    # Check group filter dropdown contents
    assert window.group_filter_cb.count() == 4  # All + 3 groups
    groups = [window.group_filter_cb.itemData(i) for i in range(window.group_filter_cb.count())]
    assert "all" in groups
    assert "GitHub / org-a" in groups
    assert "GitLab / org-b" in groups
    assert "No remote / No remote" in groups


@pytest.mark.git
def test_compare_workspace_with_org(qtbot: Any, mock_gui_services: Any, tmp_path: Path) -> None:
    mock_gh, _ = mock_gui_services
    # organization list contains repo-a and repo-b.
    # Local workspace contains repo-a only.
    repo_a = tmp_path / "repo-a"
    init_git_repo(repo_a, remote_url="https://github.com/my-org/repo-a.git")

    window = MainWindow()
    qtbot.addWidget(window)

    window.switch_mode("workspace")
    window.workspace_input.setText(str(tmp_path))
    window.org_input.setText("my-org")

    # Scan workspace first
    window.btn_scan_workspace.click()
    qtbot.waitUntil(lambda: window.app_state == "IDLE", timeout=5000)

    assert window.table.rowCount() == 1

    # Compare with organization
    window.btn_compare_org.click()
    qtbot.waitUntil(lambda: window.app_state == "IDLE", timeout=5000)

    # Now table should show repo-a and repo-b (repo-b is MISSING)
    assert window.table.rowCount() == 2

    # repo-b should be marked MISSING
    repo_b_row = -1
    for r in range(window.table.rowCount()):
        if window.table._get_repo_name(window.table.item(r, 1)) == "repo-b":
            repo_b_row = r
            break

    assert repo_b_row != -1
    assert window.table.item(repo_b_row, 4).text() == _t("state_MISSING")
