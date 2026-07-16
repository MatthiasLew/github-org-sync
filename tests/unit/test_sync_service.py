import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from github_org_sync.models.repository import Repository
from github_org_sync.models.sync_result import SyncResult
from github_org_sync.services.git_service import GitService
from github_org_sync.services.report_service import ReportService
from github_org_sync.services.sync_service import SyncService


@pytest.fixture
def mock_git_service() -> MagicMock:
    return MagicMock(spec=GitService)


@pytest.fixture
def sync_service(mock_git_service: MagicMock) -> SyncService:
    return SyncService(git_service=mock_git_service)


def test_filter_repositories(sync_service: SyncService) -> None:
    repos = [
        Repository("repo1", "url1", "ssh1", is_archived=False, is_fork=False),
        Repository("repo2", "url2", "ssh2", is_archived=True, is_fork=False),
        Repository("repo3", "url3", "ssh3", is_archived=False, is_fork=True),
        Repository("repo4", "url4", "ssh4", is_archived=True, is_fork=True),
    ]

    # 1. No archived, with forks
    f1 = sync_service.filter_repositories(repos, include_archived=False, include_forks=True)
    assert len(f1) == 2
    assert [r.name for r in f1] == ["repo1", "repo3"]

    # 2. With archived, no forks
    f2 = sync_service.filter_repositories(repos, include_archived=True, include_forks=False)
    assert len(f2) == 2
    assert [r.name for r in f2] == ["repo1", "repo2"]

    # 3. With both
    f3 = sync_service.filter_repositories(repos, include_archived=True, include_forks=True)
    assert len(f3) == 4


def test_check_local_statuses(sync_service: SyncService, mock_git_service: MagicMock) -> None:
    repos = [
        Repository("repo1", "url1", "ssh1"),
        Repository("repo2", "url2", "ssh2"),
    ]

    mock_git_service.get_local_status.side_effect = [
        ("UP_TO_DATE", "main", 0, 0, None),
        ("MISSING", None, None, None, None),
    ]

    workspace = Path("/dummy/workspace")
    checked = sync_service.check_local_statuses(repos, workspace, "org")

    assert checked[0].status == "UP_TO_DATE"
    assert checked[0].branch == "main"
    assert checked[0].local_path == workspace / "repo1"

    assert checked[1].status == "MISSING"
    assert checked[1].local_path == workspace / "repo2"


def test_sync_repositories_clone_and_skip(sync_service: SyncService, mock_git_service: MagicMock) -> None:
    repos = [
        Repository("repo1", "url1", "ssh1", status="MISSING"),
        Repository("repo2", "url2", "ssh2", status="WRONG_REMOTE"),
        Repository("repo3", "url3", "ssh3", status="UP_TO_DATE"),
    ]

    mock_git_service.clone.return_value = SyncResult(
        repo_name="repo1",
        status="CLONED",
        before_status="MISSING",
        after_status="UP_TO_DATE",
        duration=1.0,
        operation="clone",
        message="Cloned",
    )
    mock_git_service.sync.return_value = SyncResult(
        repo_name="repo3",
        status="UP_TO_DATE",
        before_status="UP_TO_DATE",
        after_status="UP_TO_DATE",
        duration=0.5,
        operation="sync",
        message="Sync",
    )

    workspace = Path("/dummy/workspace")
    results = sync_service.sync_repositories(repos, workspace, "org", {"use_ssh": False})

    assert len(results) == 3

    # repo1
    assert results[0].repo_name == "repo1"
    assert results[0].status == "CLONED"

    # repo2 skipped
    assert results[1].repo_name == "repo2"
    assert results[1].status == "WRONG_REMOTE"
    assert results[1].operation == "skip"

    # repo3 sync
    assert results[2].repo_name == "repo3"
    assert results[2].status == "UP_TO_DATE"


def test_sync_repositories_cancellation(sync_service: SyncService, mock_git_service: MagicMock) -> None:
    repos = [
        Repository("repo1", "url1", "ssh1", status="MISSING"),
        Repository("repo2", "url2", "ssh2", status="MISSING"),
    ]

    mock_git_service.clone.return_value = SyncResult(
        repo_name="repo1",
        status="CLONED",
        before_status="MISSING",
        after_status="UP_TO_DATE",
        duration=1.0,
        operation="clone",
        message="Cloned",
    )

    # Cancel after first repo is synced
    call_count = 0

    def is_cancelled() -> bool:
        nonlocal call_count
        call_count += 1
        return call_count > 1

    workspace = Path("/dummy/workspace")
    results = sync_service.sync_repositories(
        repos, workspace, "org", {"use_ssh": False}, is_cancelled_callback=is_cancelled
    )

    assert len(results) == 2
    assert results[0].status == "CLONED"
    assert results[1].status == "CANCELLED"


def test_report_service_generation(tmp_path: Path) -> None:
    results = [
        SyncResult("repo1", "CLONED", "MISSING", "UP_TO_DATE", 1.2, "clone", message="Cloned"),
        SyncResult("repo2", "FAILED", "UP_TO_DATE", "UP_TO_DATE", 0.5, "sync", error="Error message"),
    ]

    with patch.object(ReportService, "get_reports_dir") as mock_reports_dir:
        mock_reports_dir.return_value = tmp_path

        json_path, md_path = ReportService.generate_reports(
            organization="myorg",
            workspace=Path("/dummy/workspace"),
            auth_user="MatthiasLew",
            protocol="https",
            options={"dry_run": False},
            results=results,
        )

        assert json_path.exists()
        assert md_path.exists()

        # Verify JSON content
        with json_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
            assert data["organization"] == "myorg"
            assert data["authenticated_user"] == "MatthiasLew"
            assert len(data["results"]) == 2
            assert data["results"][0]["repository"] == "repo1"
            assert data["results"][1]["error"] == "Error message"

        # Verify MD content
        md_text = md_path.read_text(encoding="utf-8")
        assert "# Sync Report - myorg" in md_text
        assert "repo1" in md_text
        assert "repo2" in md_text
