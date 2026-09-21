from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from github_org_sync.cli import (
    EXIT_ATTENTION,
    EXIT_ERROR,
    EXIT_SUCCESS,
    EXIT_USAGE,
    main,
    print_summary,
)
from github_org_sync.models.repo_state import RepoState
from github_org_sync.models.repository import Repository
from github_org_sync.models.sync_result import SyncResult

pytestmark = [pytest.mark.integration]


@pytest.fixture
def mock_cli_services() -> Generator[tuple[MagicMock, MagicMock, MagicMock], None, None]:
    with (
        patch("github_org_sync.cli.GitHubService") as mock_gh_cls,
        patch("github_org_sync.cli.SyncService") as mock_sync_cls,
        patch("github_org_sync.cli.ReportService") as mock_report_cls,
    ):
        mock_gh = mock_gh_cls.return_value
        mock_gh.check_cli_installed.return_value = "gh version 2.30.0"
        mock_gh.check_auth_status.return_value = "Logged in to github.com account TestUser"
        mock_gh.list_repositories.return_value = [
            Repository("repo-1", "url-1", "ssh-1"),
        ]

        mock_sync = mock_sync_cls.return_value
        mock_sync.filter_repositories.side_effect = lambda repos, *args, **kwargs: repos
        mock_sync.check_local_statuses.side_effect = lambda repos, *args, **kwargs: repos
        mock_sync.sync_repositories.return_value = [
            SyncResult(
                repo_name="repo-1",
                requested_action="CLONE",
                performed_action="CLONED",
                before_status="MISSING",
                after_status="UP_TO_DATE",
                duration=1.0,
                result="Cloned",
            )
        ]

        mock_report = mock_report_cls
        mock_report.generate_reports.return_value = ("/dummy/report.json", "/dummy/report.md")

        yield mock_gh, mock_sync, mock_report


def test_cli_list(mock_cli_services: tuple[MagicMock, MagicMock, MagicMock]) -> None:
    # Run list subcommand
    rc = main(["list", "--org", "myorg"])
    assert rc == 0
    mock_gh, _, _ = mock_cli_services
    mock_gh.list_repositories.assert_called_once_with("myorg")


def test_cli_status(mock_cli_services: tuple[MagicMock, MagicMock, MagicMock], tmp_path: Path) -> None:
    # Run status subcommand
    rc = main(["status", "--org", "myorg", "--workspace", str(tmp_path)])
    assert rc == 0
    _, mock_sync, _ = mock_cli_services
    mock_sync.check_local_statuses.assert_called_once()


def test_cli_sync(mock_cli_services: tuple[MagicMock, MagicMock, MagicMock], tmp_path: Path) -> None:
    # Run sync subcommand
    rc = main(["sync", "--org", "myorg", "--workspace", str(tmp_path), "--dry-run"])
    assert rc == 0
    _, mock_sync, mock_report = mock_cli_services
    mock_sync.sync_repositories.assert_called_once()
    mock_report.generate_reports.assert_called_once()


def test_cli_version(capsys: Any) -> None:
    from github_org_sync import __version__

    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    # Argparse may output to stdout or stderr depending on Python versions/environments
    output = captured.out or captured.err
    assert f"github-org-sync {__version__}" in output


def test_print_summary_exit_codes() -> None:
    r_ok = SyncResult("r1", "SYNC", "UPDATED", "BEHIND", "UP_TO_DATE", 1.0)
    assert print_summary([r_ok]) == EXIT_SUCCESS

    r_att = SyncResult("r2", "SYNC", "BLOCKED", "CONFLICT", "CONFLICT", 1.0)
    assert print_summary([r_ok, r_att]) == EXIT_ATTENTION

    r_err = SyncResult("r3", "SYNC", "FAILED", "MISSING", "FAILED", 1.0)
    assert print_summary([r_ok, r_att, r_err]) == EXIT_ERROR


def test_cli_no_command(capsys: Any) -> None:
    rc = main([])
    assert rc == EXIT_SUCCESS
    captured = capsys.readouterr()
    assert "usage:" in captured.out


def test_cli_smoke_test(monkeypatch: Any) -> None:
    # Smoke test success
    with patch("github_org_sync.app.main") as mock_app_main:
        rc = main(["--smoke-test"])
        assert rc == EXIT_SUCCESS
        mock_app_main.assert_called_once()

    # Smoke test ImportError
    with patch("github_org_sync.app.main", side_effect=ImportError("No PySide6")):
        rc_err = main(["--smoke-test"])
        assert rc_err == EXIT_ERROR


def test_cli_gui_command() -> None:
    with patch("github_org_sync.app.main") as mock_app_main:
        assert main(["gui"]) == EXIT_SUCCESS
        mock_app_main.assert_called_once()

    with patch("github_org_sync.app.main", side_effect=ImportError("No PySide6")):
        # Without JSON
        assert main(["gui"]) == EXIT_ERROR
        # With JSON
        assert main(["--json", "gui"]) == EXIT_ERROR


def test_cli_doctor_command(capsys: Any) -> None:
    from github_org_sync.services.diagnostics_service import DiagnosticsService

    fake_report = {
        "status": "warning",
        "passed_checks": 5,
        "total_checks": 6,
        "checks": [
            {"key": "c1", "label": "Check 1", "status": "ok", "message": "Good", "required": True},
            {"key": "c2", "label": "Check 2", "status": "warning", "message": "Slow", "required": False},
        ],
    }
    with patch.object(DiagnosticsService, "run_doctor", return_value=fake_report):
        # Text mode
        rc = main(["doctor"])
        assert rc == EXIT_ATTENTION
        captured = capsys.readouterr()
        assert "Environment Doctor" in captured.out
        assert "Check 1" in captured.out

        # JSON mode
        rc_json = main(["doctor", "--json"])
        assert rc_json == EXIT_ATTENTION
        captured_json = capsys.readouterr()
        assert '"command": "doctor"' in captured_json.out


def test_cli_summary_command(tmp_path: Path) -> None:
    from github_org_sync.services.work_summary_service import WorkSummaryService

    with patch.object(WorkSummaryService, "check_gh", return_value=False):
        assert main(["summary", "--month", "2026-01"]) == EXIT_ERROR

    with (
        patch.object(WorkSummaryService, "check_gh", return_value=True),
        patch.object(WorkSummaryService, "generate_summary") as mock_gen,
        patch.object(WorkSummaryService, "save_reports", return_value=("rep.md", "rep.json")),
    ):
        rc = main(["summary", "--month", "2026-01"])
        assert rc == EXIT_SUCCESS
        mock_gen.assert_called_once()

    with (
        patch.object(WorkSummaryService, "check_gh", return_value=True),
        patch.object(WorkSummaryService, "generate_summary", side_effect=RuntimeError("API error")),
    ):
        assert main(["summary", "--month", "2026-01"]) == EXIT_ERROR


def test_cli_gh_prechecks_and_org_validation(capsys: Any, tmp_path: Path) -> None:
    with patch("github_org_sync.cli.GitHubService") as mock_gh_cls:
        mock_gh = mock_gh_cls.return_value

        # 1. GH not installed
        mock_gh.check_cli_installed.return_value = False
        assert main(["list", "--org", "myorg"]) == EXIT_ERROR
        assert main(["list", "--org", "myorg", "--json"]) == EXIT_ERROR

        # 2. GH not authenticated
        mock_gh.check_cli_installed.return_value = True
        mock_gh.check_auth_status.return_value = ""
        assert main(["list", "--org", "myorg"]) == EXIT_ERROR
        assert main(["list", "--org", "myorg", "--json"]) == EXIT_ERROR

        # 3. Invalid org name
        mock_gh.check_auth_status.return_value = "Logged in as test"
        assert main(["list", "--org", "invalid/org/name"]) == EXIT_USAGE
        assert main(["list", "--org", "invalid/org/name", "--json"]) == EXIT_USAGE

        # 4. List repositories exception
        mock_gh.list_repositories.side_effect = RuntimeError("Rate limited")
        assert main(["list", "--org", "myorg"]) == EXIT_ERROR
        assert main(["list", "--org", "myorg", "--json"]) == EXIT_ERROR


def test_cli_list_json(mock_cli_services: tuple[MagicMock, MagicMock, MagicMock], capsys: Any) -> None:
    rc = main(["list", "--org", "myorg", "--json"])
    assert rc == EXIT_SUCCESS
    captured = capsys.readouterr()
    import json

    payload = json.loads(captured.out)
    assert payload["command"] == "list"
    assert len(payload["data"]) == 1


def test_cli_invalid_workspace(mock_cli_services: tuple[MagicMock, MagicMock, MagicMock], tmp_path: Path) -> None:
    non_existent = tmp_path / "missing_parent" / "sub" / "ws"

    assert main(["status", "--org", "myorg", "--workspace", str(non_existent)]) == EXIT_USAGE
    assert main(["status", "--org", "myorg", "--workspace", str(non_existent), "--json"]) == EXIT_USAGE


def test_cli_status_details_and_json(
    mock_cli_services: tuple[MagicMock, MagicMock, MagicMock], tmp_path: Path, capsys: Any
) -> None:
    _, mock_sync, _ = mock_cli_services
    repo_clean = Repository("clean-repo", "url", "ssh", status="UP_TO_DATE")
    repo_clean.state = RepoState(exists=True, is_git_repo=True, dirty=False)

    repo_dirty = Repository("dirty-repo", "url", "ssh", status="DIRTY", ahead=1, behind=2)
    repo_dirty.state = RepoState(exists=True, is_git_repo=True, dirty=True)

    mock_sync.filter_repositories.side_effect = None
    mock_sync.filter_repositories.return_value = [repo_clean, repo_dirty]
    mock_sync.check_local_statuses.side_effect = None
    mock_sync.check_local_statuses.return_value = [repo_clean, repo_dirty]

    # Text mode returns EXIT_ATTENTION due to dirty repo
    rc = main(["status", "--org", "myorg", "--workspace", str(tmp_path)])
    assert rc == EXIT_ATTENTION
    captured = capsys.readouterr()
    assert "dirty-repo" in captured.out

    # JSON mode
    rc_json = main(["status", "--org", "myorg", "--workspace", str(tmp_path), "--json"])
    assert rc_json == EXIT_ATTENTION
    captured_json = capsys.readouterr()
    import json

    payload = json.loads(captured_json.out)
    assert payload["command"] == "status"
    assert "dirty-repo" in payload["data"]


def test_cli_plan_command(
    mock_cli_services: tuple[MagicMock, MagicMock, MagicMock], tmp_path: Path, capsys: Any
) -> None:
    repo = Repository("my-repo", "url", "ssh", default_branch="main")
    _, mock_sync, _ = mock_cli_services
    mock_sync.filter_repositories.return_value = [repo]

    with patch("github_org_sync.cli.GitService") as mock_git_cls:
        mock_git = mock_git_cls.return_value
        mock_git.inspect_repo_state.return_value = RepoState(exists=False, is_git_repo=False)

        # Text mode
        rc = main(["plan", "--org", "myorg", "--workspace", str(tmp_path)])
        assert rc == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "Planned actions" in captured.out

        # JSON mode
        rc_json = main(["plan", "--org", "myorg", "--workspace", str(tmp_path), "--json"])
        assert rc_json == EXIT_SUCCESS
        captured_json = capsys.readouterr()
        import json

        payload = json.loads(captured_json.out)
        assert payload["command"] == "plan"
        assert payload["status"] == "success"


def test_cli_sync_outcomes(
    mock_cli_services: tuple[MagicMock, MagicMock, MagicMock], tmp_path: Path, capsys: Any
) -> None:
    _, mock_sync, mock_report = mock_cli_services
    mock_report.generate_reports.return_value = (tmp_path / "rep.json", tmp_path / "rep.md")

    # 1. Sync with failure
    mock_sync.sync_repositories.return_value = [
        SyncResult("repo-fail", "SYNC", "FAILED", "UP_TO_DATE", "FAILED", 1.0, error="network error")
    ]
    rc_fail = main(["sync", "--org", "myorg", "--workspace", str(tmp_path), "--json"])
    assert rc_fail == EXIT_ERROR

    # 2. Sync with attention (conflict)
    mock_sync.sync_repositories.return_value = [
        SyncResult("repo-conf", "SYNC", "BLOCKED", "UP_TO_DATE", "CONFLICT", 1.0, error="merge conflict")
    ]
    rc_att = main(["sync", "--org", "myorg", "--workspace", str(tmp_path), "--json"])
    assert rc_att == EXIT_ATTENTION

    # 3. Sync success text mode without dry-run
    mock_sync.sync_repositories.return_value = [
        SyncResult("repo-ok", "SYNC", "UPDATED", "BEHIND", "UP_TO_DATE", 1.0, result="Updated")
    ]
    rc_ok = main(["sync", "--org", "myorg", "--workspace", str(tmp_path)])
    assert rc_ok == EXIT_SUCCESS
    captured = capsys.readouterr()
    assert "Reports generated successfully" in captured.out
