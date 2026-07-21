import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from github_org_sync.services.github_service import (
    GitHubAuthError,
    GitHubCLIMissingError,
    GitHubService,
    GitHubServiceError,
    OrganizationNotFoundError,
)


@pytest.mark.unit
@patch("shutil.which")
def test_check_cli_installed_missing(mock_which: MagicMock) -> None:
    mock_which.return_value = None
    service = GitHubService()
    with pytest.raises(GitHubCLIMissingError):
        service.check_cli_installed()


@pytest.mark.unit
@patch("shutil.which")
@patch("github_org_sync.services.github_service.run_process")
def test_check_cli_installed_present(mock_run: MagicMock, mock_which: MagicMock) -> None:
    mock_which.return_value = "/usr/bin/gh"

    mock_proc = MagicMock()
    mock_proc.stdout = "gh version 2.30.0 (2023-06-01)\nhttps://github.com/cli/cli/releases/tag/v2.30.0"
    mock_run.return_value = mock_proc

    service = GitHubService()
    ver = service.check_cli_installed()
    assert ver == "gh version 2.30.0 (2023-06-01)"
    mock_run.assert_called_once_with(["/usr/bin/gh", "--version"], check=True)


@pytest.mark.unit
@patch("shutil.which")
@patch("github_org_sync.services.github_service.run_process")
def test_check_auth_status_success(mock_run: MagicMock, mock_which: MagicMock) -> None:
    mock_which.return_value = "/usr/bin/gh"

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "Logged in to github.com account MatthiasLew"
    mock_proc.stderr = ""
    mock_run.return_value = mock_proc

    service = GitHubService()
    status = service.check_auth_status()
    assert "MatthiasLew" in status


@pytest.mark.unit
@patch("shutil.which")
@patch("github_org_sync.services.github_service.run_process")
def test_check_auth_status_failed(mock_run: MagicMock, mock_which: MagicMock) -> None:
    mock_which.return_value = "/usr/bin/gh"

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stdout = ""
    mock_proc.stderr = "To get started with GitHub CLI, please run: gh auth login"
    mock_run.return_value = mock_proc

    service = GitHubService()
    with pytest.raises(GitHubAuthError):
        service.check_auth_status()


@pytest.mark.unit
@patch("shutil.which")
@patch("github_org_sync.services.github_service.run_process")
def test_list_repositories_success(mock_run: MagicMock, mock_which: MagicMock) -> None:
    mock_which.return_value = "/usr/bin/gh"

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(
        [
            {
                "name": "repo1",
                "url": "https://github.com/org/repo1",
                "sshUrl": "git@github.com:org/repo1.git",
                "isArchived": False,
                "isFork": False,
                "defaultBranchRef": {"name": "main"},
                "visibility": "PUBLIC",
            },
            {
                "name": "repo2",
                "url": "https://github.com/org/repo2",
                "sshUrl": "git@github.com:org/repo2.git",
                "isArchived": True,
                "isFork": True,
                "defaultBranchRef": {"name": "master"},
                "visibility": "PRIVATE",
            },
        ]
    )
    mock_run.return_value = mock_proc

    service = GitHubService()
    repos = service.list_repositories("org")

    assert len(repos) == 2
    assert repos[0].name == "repo1"
    assert repos[0].default_branch == "main"
    assert repos[0].visibility == "public"
    assert not repos[0].is_archived

    assert repos[1].name == "repo2"
    assert repos[1].default_branch == "master"
    assert repos[1].visibility == "private"
    assert repos[1].is_archived
    assert repos[1].is_fork


@pytest.mark.unit
@patch("shutil.which")
@patch("github_org_sync.services.github_service.run_process")
def test_list_repositories_not_found(mock_run: MagicMock, mock_which: MagicMock) -> None:
    mock_which.return_value = "/usr/bin/gh"

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "HTTP 404: Not Found (https://api.github.com/orgs/nonexistent/repos)"
    mock_run.return_value = mock_proc

    service = GitHubService()
    with pytest.raises(OrganizationNotFoundError):
        service.list_repositories("nonexistent")


@pytest.mark.unit
@patch("shutil.which")
@patch("github_org_sync.services.github_service.run_process")
def test_list_repositories_json_error(mock_run: MagicMock, mock_which: MagicMock) -> None:
    mock_which.return_value = "/usr/bin/gh"

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "invalid-json-data"
    mock_run.return_value = mock_proc

    service = GitHubService()
    with pytest.raises(GitHubServiceError, match="Failed to parse GitHub CLI response"):
        service.list_repositories("org")


@pytest.mark.unit
@patch("shutil.which")
@patch("github_org_sync.services.github_service.run_process")
def test_list_repositories_empty_response(mock_run: MagicMock, mock_which: MagicMock) -> None:
    mock_which.return_value = "/usr/bin/gh"

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = ""
    mock_run.return_value = mock_proc

    service = GitHubService()
    repos = service.list_repositories("org")
    assert repos == []


@pytest.mark.unit
@patch("shutil.which")
@patch("github_org_sync.services.github_service.run_process")
def test_list_repositories_timeout(mock_run: MagicMock, mock_which: MagicMock) -> None:
    mock_which.return_value = "/usr/bin/gh"
    # Simulate a timeout from subprocess.run
    mock_run.side_effect = subprocess.TimeoutExpired(cmd=["gh"], timeout=30.0)

    service = GitHubService()
    with pytest.raises(GitHubServiceError, match="Subprocess error listing repositories"):
        service.list_repositories("org")


@pytest.mark.unit
@patch("shutil.which")
@patch("github_org_sync.services.github_service.run_process")
def test_list_repositories_no_credentials_leak(mock_run: MagicMock, mock_which: MagicMock) -> None:
    mock_which.return_value = "/usr/bin/gh"

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    # Stderr contains a hypothetical token scope or secret URL
    mock_proc.stderr = "HTTP 401: Unauthorized (gho_abcdef1234567890 token expired)"
    mock_run.return_value = mock_proc

    service = GitHubService()
    with pytest.raises(GitHubServiceError) as exc_info:
        service.list_repositories("org")

    err_str = str(exc_info.value)
    # Token must be redacted/masked or not present in output
    assert "gho_" not in err_str
    assert "abcdef" not in err_str
