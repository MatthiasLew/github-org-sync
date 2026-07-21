from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.integration]

from github_org_sync.cli import main
from github_org_sync.models.repository import Repository
from github_org_sync.models.sync_result import SyncResult


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
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    # Argparse may output to stdout or stderr depending on Python versions/environments
    output = captured.out or captured.err
    assert "github-org-sync 1.2.0" in output
