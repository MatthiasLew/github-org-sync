from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from github_org_sync.cli import (
    EXIT_ATTENTION,
    EXIT_ERROR,
    EXIT_SUCCESS,
    EXIT_USAGE,
    format_json_envelope,
    main,
)
from github_org_sync.models.repo_state import RepoState
from github_org_sync.models.repository import Repository


@pytest.mark.integration
def test_format_json_envelope_schema() -> None:
    data = {"key": "val"}
    raw = format_json_envelope("test-cmd", "success", EXIT_SUCCESS, data, "All good")
    parsed = json.loads(raw)

    assert parsed["schema_version"] == "1.0"
    assert parsed["tool_version"] == "1.10.0"
    assert parsed["command"] == "test-cmd"
    assert parsed["status"] == "success"
    assert parsed["exit_code"] == 0
    assert parsed["summary"] == "All good"
    assert parsed["data"] == data
    assert parsed["errors"] == []


@pytest.mark.integration
def test_cli_doctor_json(capsys: Any) -> None:
    rc = main(["doctor", "--json"])
    assert rc in (EXIT_SUCCESS, EXIT_ATTENTION, EXIT_ERROR)

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["schema_version"] == "1.0"
    assert payload["tool_version"] == "1.10.0"
    assert payload["command"] == "doctor"
    assert payload["exit_code"] == rc
    assert "checks" in payload["data"]


@pytest.mark.integration
def test_cli_invalid_org_syntax_returns_exit_usage(capsys: Any, tmp_path: Path) -> None:
    with patch("github_org_sync.cli.GitHubService"):
        # Invalid organization name (e.g. contains illegal characters)
        rc = main(["plan", "--org", "invalid/org/name!", "--workspace", str(tmp_path), "--json"])
    assert rc == EXIT_USAGE

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["exit_code"] == EXIT_USAGE
    assert payload["status"] == "error"


@pytest.mark.integration
def test_cli_plan_json(capsys: Any, tmp_path: Path) -> None:
    with (
        patch("github_org_sync.cli.GitHubService") as mock_gh_cls,
        patch("github_org_sync.cli.GitService") as mock_git_cls,
    ):
        mock_gh = mock_gh_cls.return_value
        mock_gh.check_cli_installed.return_value = "gh 2.0"
        mock_gh.check_auth_status.return_value = "Logged in"
        mock_gh.list_repositories.return_value = [
            Repository("service-api", "https://github.com/myorg/service-api.git", "ssh://..."),
        ]

        mock_git = mock_git_cls.return_value
        # Missing repo -> plan should recommend CLONE
        mock_git.inspect_repo_state.return_value = RepoState(exists=False, is_git_repo=False)

        rc = main(["plan", "--org", "myorg", "--workspace", str(tmp_path), "--json"])

    assert rc == EXIT_SUCCESS
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["command"] == "plan"
    assert payload["status"] == "success"
    assert len(payload["data"]["repositories"]) == 1
    assert payload["data"]["repositories"][0]["action"] == "CLONE"


@pytest.mark.integration
def test_cli_sync_dry_run_json(capsys: Any, tmp_path: Path) -> None:
    with (
        patch("github_org_sync.cli.GitHubService") as mock_gh_cls,
        patch("github_org_sync.cli.GitService") as mock_git_cls,
    ):
        mock_gh = mock_gh_cls.return_value
        mock_gh.check_cli_installed.return_value = "gh 2.0"
        mock_gh.check_auth_status.return_value = "Logged in"
        mock_gh.list_repositories.return_value = [
            Repository("service-api", "https://github.com/myorg/service-api.git", "ssh://..."),
        ]

        mock_git = mock_git_cls.return_value
        mock_git.inspect_repo_state.return_value = RepoState(exists=False, is_git_repo=False)

        rc = main(["sync", "--org", "myorg", "--workspace", str(tmp_path), "--dry-run", "--json"])

    assert rc == EXIT_SUCCESS
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["command"] == "sync"
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["results"][0]["requested_action"] == "CLONE"
    assert "clone" in payload["data"]["results"][0]["result"].lower()
