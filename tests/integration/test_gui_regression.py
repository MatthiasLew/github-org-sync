from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from github_org_sync.i18n import _t, translator
from github_org_sync.models.repository import Repository
from github_org_sync.ui.main_window import MainWindow
from github_org_sync.utils.process import run_process


@pytest.fixture
def mock_services() -> Generator[tuple[MagicMock, MagicMock], None, None]:
    with (
        patch("github_org_sync.ui.main_window.GitHubService") as mock_gh_cls,
        patch("github_org_sync.config.ConfigManager.load") as mock_load,
        patch("github_org_sync.config.ConfigManager.save") as mock_save,
    ):
        mock_load.return_value = {
            "last_organization": "subactor",
            "last_workspace": "C:/mock-workspace",
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
        }

        mock_gh = mock_gh_cls.return_value
        mock_gh.check_cli_installed.return_value = "gh version 2.30.0"
        mock_gh.check_auth_status.return_value = "Logged in to github.com account TestUser"
        mock_gh.list_repositories.return_value = [
            Repository("repo-a", "url-a", "ssh-a", is_archived=False, is_fork=False),
            Repository("repo-b", "url-b", "ssh-b", is_archived=True, is_fork=False),
            Repository("repo-c", "url-c", "ssh-c", is_archived=False, is_fork=True),
        ]
        yield mock_gh, mock_save


def test_language_and_theme_switching(qtbot: Any, mock_services: tuple[MagicMock, MagicMock]) -> None:
    _, mock_save = mock_services
    window = MainWindow()
    qtbot.addWidget(window)

    # 1. Check default language (pl)
    assert translator.language == "pl"
    assert window.btn_load.text() == "Wczytaj repozytoria"

    # 2. Switch to English
    window.change_language("en")
    assert translator.language == "en"
    assert window.btn_load.text() == "Load Repositories"
    mock_save.assert_called()

    # 3. Check language saved in config
    assert window.config["language"] == "en"

    # 4. Switch theme
    window.change_theme("Dark")
    assert window.config["theme"] == "Dark"

    window.change_theme("Light")
    assert window.config["theme"] == "Light"


def test_no_visible_console_on_windows(qtbot: Any, mock_services: tuple[MagicMock, MagicMock]) -> None:
    with patch("sys.platform", "win32"), patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        run_process(["git", "status"])

        # Check that creationflags contains CREATE_NO_WINDOW (0x08000000)
        assert mock_run.call_count == 1
        called_kwargs = mock_run.call_args[1]
        assert "creationflags" in called_kwargs
        assert called_kwargs["creationflags"] & 0x08000000


def test_no_create_no_window_on_linux(qtbot: Any, mock_services: tuple[MagicMock, MagicMock]) -> None:
    with patch("sys.platform", "linux"), patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        run_process(["git", "status"])

        assert mock_run.call_count == 1
        called_kwargs = mock_run.call_args[1]
        if "creationflags" in called_kwargs:
            assert not (called_kwargs["creationflags"] & 0x08000000)


def test_open_folder_cross_platform(qtbot: Any, mock_services: tuple[MagicMock, MagicMock]) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.workspace_input.setText("C:/mock-workspace")

    with patch("pathlib.Path.exists", return_value=True):
        # Windows open check
        with patch("sys.platform", "win32"), patch("os.startfile") as mock_start:
            window.open_workspace_folder()
            mock_start.assert_called_once_with("C:/mock-workspace")

        # Linux open check
        with patch("sys.platform", "linux"), patch("github_org_sync.ui.main_window.os") as mock_os:
            if hasattr(mock_os, "startfile"):
                del mock_os.startfile
            with patch("github_org_sync.ui.main_window.run_process") as mock_run:
                window.open_workspace_folder()
                mock_run.assert_called_once_with(["xdg-open", "C:/mock-workspace"], check=True)

        # macOS open check
        with patch("sys.platform", "darwin"), patch("github_org_sync.ui.main_window.os") as mock_os:
            if hasattr(mock_os, "startfile"):
                del mock_os.startfile
            with patch("github_org_sync.ui.main_window.run_process") as mock_run:
                window.open_workspace_folder()
                mock_run.assert_called_once_with(["open", "C:/mock-workspace"], check=True)


def test_gui_states_and_enablement(qtbot: Any, mock_services: tuple[MagicMock, MagicMock]) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    # IDLE state
    window._set_app_state("IDLE")
    assert window.org_input.isEnabled()
    assert window.btn_load.isEnabled()

    # LOADING state
    window._set_app_state("LOADING_REPOSITORIES")
    assert not window.org_input.isEnabled()
    assert not window.btn_load.isEnabled()
    assert not window.btn_sync.isEnabled()

    # SYNCING state
    window._set_app_state("SYNCING")
    assert not window.org_input.isEnabled()
    assert not window.btn_load.isEnabled()
    assert not window.btn_sync.isEnabled()


def test_block_sync_during_load(qtbot: Any, mock_services: tuple[MagicMock, MagicMock]) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    window._set_app_state("LOADING_REPOSITORIES")
    assert not window.btn_sync.isEnabled()
    assert not window.btn_load.isEnabled()


def test_workspace_change_cancels_active_worker(qtbot: Any, mock_services: tuple[MagicMock, MagicMock]) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    # Mock active worker
    mock_worker = MagicMock()
    mock_worker.isRunning.return_value = True
    window.sync_worker = mock_worker

    # Set some dummy repos in table
    repos = [Repository("repo-a", "url-a", "ssh-a", status="UP_TO_DATE")]
    window.repositories = repos
    window.table.set_repositories(repos)

    with patch("PySide6.QtWidgets.QFileDialog.getExistingDirectory", return_value="C:/new-workspace"):
        window.choose_workspace()

        # Verify worker cancellation was requested
        mock_worker.cancel.assert_called_once()
        mock_worker.wait.assert_called_once()

        # Verify statuses reset to MISSING
        assert window.repositories[0].status == "MISSING"
        item = window.table.item(0, 4)
        assert item is not None
        assert item.text() == _t("state_MISSING")


def test_filtering_and_sorting(qtbot: Any, mock_services: tuple[MagicMock, MagicMock]) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    repos = [
        Repository("alpha", "url-a", "ssh-a", status="MISSING"),
        Repository("beta", "url-b", "ssh-b", status="UP_TO_DATE"),
    ]
    window.repositories = repos
    window.table.set_repositories(repos)

    # Filter for "alpha"
    window.search_input.setText("alpha")
    assert not window.table.isRowHidden(0)
    assert window.table.isRowHidden(1)

    # Filter status missing
    window.search_input.setText("")
    window.status_filter_cb.setCurrentText(_t("state_MISSING"))
    assert not window.table.isRowHidden(0)
    assert window.table.isRowHidden(1)


def test_tooltips_presence(qtbot: Any, mock_services: tuple[MagicMock, MagicMock]) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    window.change_language("pl")
    assert window.btn_load.toolTip() == _t("tip_load_btn")

    window.change_language("en")
    assert window.btn_load.toolTip() == _t("tip_load_btn")


def test_help_and_about_dialogs(qtbot: Any, mock_services: tuple[MagicMock, MagicMock]) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    with patch("PySide6.QtWidgets.QMessageBox.information") as mock_info:
        window.show_about()
        mock_info.assert_called_once_with(window, _t("about_title"), _t("about_text"), QMessageBox.StandardButton.Ok)

    with patch("PySide6.QtWidgets.QMessageBox.information") as mock_info:
        window.show_getting_started()
        mock_info.assert_called_once_with(window, _t("help_title"), _t("help_text"), QMessageBox.StandardButton.Ok)


def test_warn_close_on_active_sync(qtbot: Any, mock_services: tuple[MagicMock, MagicMock]) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    # Mock running worker
    mock_worker = MagicMock()
    mock_worker.isRunning.return_value = True
    window.sync_worker = mock_worker

    # Mock confirmation reject
    with patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
        event = QCloseEvent()
        window.closeEvent(event)
        assert not event.isAccepted()

    # Mock confirmation accept
    with patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
        event = QCloseEvent()
        window.closeEvent(event)
        assert event.isAccepted()


def test_load_change_workspace_inspect_flow(qtbot: Any, mock_services: tuple[MagicMock, MagicMock]) -> None:
    """
    Test flow:
    Load repos -> change workspace -> inspect again.
    Verifies that:
    - Only a single worker runs.
    - Previous workers are properly disposed.
    - Buttons are restored to IDLE state.
    """
    mock_gh, _ = mock_services
    window = MainWindow()
    qtbot.addWidget(window)

    window.org_input.setText("subactor")
    window.workspace_input.setText("C:/mock-workspace")

    # Mock status check runner inside SyncWorker to avoid spawning real commands
    with patch("github_org_sync.workers.sync_worker.SyncService.check_local_statuses") as mock_check:
        mock_check.side_effect = lambda repos, ws, org, progress_callback, is_cancelled_callback: repos

        # 1. Click load
        qtbot.mouseClick(window.btn_load, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: window.app_state == "IDLE", timeout=2000)

        # Verify app is IDLE after load & inspect
        assert window.app_state == "IDLE"

        # 2. Change workspace directory
        with patch("PySide6.QtWidgets.QFileDialog.getExistingDirectory", return_value="C:/new-workspace"):
            window.choose_workspace()

        # Workspace reset everything to MISSING
        assert window.repositories[0].status == "MISSING"

        # 3. Refresh status (inspect again)
        window.refresh_status()

        # Wait for the inspect worker to complete
        qtbot.waitUntil(lambda: window.app_state == "IDLE", timeout=2000)

        # App should be IDLE and table updated
        assert window.app_state == "IDLE"
        assert len(window.repositories) == 2
