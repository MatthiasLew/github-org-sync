from pathlib import Path
from unittest.mock import MagicMock

import pytest

from github_org_sync.models.repository import Repository
from github_org_sync.models.sync_result import SyncResult
from github_org_sync.services.sync_service import SyncService


@pytest.mark.unit
def test_parallel_check_local_statuses() -> None:
    git_service_mock = MagicMock()

    def mock_get_status(path, org):
        path_str = str(path)
        if "repo-1" in path_str:
            return "SYNCED", "main", 0, 0, "Up to date"
        if "repo-2" in path_str:
            return "BEHIND", "dev", 0, 2, "2 commits behind"
        return "MISSING", None, None, None, "Directory missing"

    git_service_mock.get_local_status.side_effect = mock_get_status

    repos = [
        Repository(
            name="repo-1",
            url="https://github.com/my-org/repo-1",
            ssh_url="git@github.com:my-org/repo-1.git",
            is_fork=False,
            is_archived=False,
        ),
        Repository(
            name="repo-2",
            url="https://github.com/my-org/repo-2",
            ssh_url="git@github.com:my-org/repo-2.git",
            is_fork=False,
            is_archived=False,
        ),
        Repository(
            name="repo-3",
            url="https://github.com/my-org/repo-3",
            ssh_url="git@github.com:my-org/repo-3.git",
            is_fork=False,
            is_archived=False,
        ),
    ]

    progress_calls = []

    def progress_cb(index: int, total: int, repo_name: str) -> None:
        progress_calls.append((index, total, repo_name))

    sync_service = SyncService(git_service=git_service_mock)
    sync_service.check_local_statuses(
        repositories=repos,
        workspace=Path("/workspace"),
        org_name="my-org",
        progress_callback=progress_cb,
        max_workers=2,
    )

    # Verify all repos updated
    assert repos[0].status == "SYNCED"
    assert repos[0].branch == "main"
    assert repos[1].status == "BEHIND"
    assert repos[1].branch == "dev"
    assert repos[2].status == "MISSING"

    # Verify progress callback called for each repo
    assert len(progress_calls) == 3
    # Ensure they reflect total size
    for call in progress_calls:
        assert call[1] == 3


@pytest.mark.unit
def test_parallel_sync_repositories() -> None:
    git_service_mock = MagicMock()

    # Mock clone for MISSING repos
    git_service_mock.clone.return_value = SyncResult(
        repo_name="repo-1",
        requested_action="clone",
        performed_action="clone",
        before_status="MISSING",
        after_status="SYNCED",
        result="Cloned successfully",
    )

    # Mock sync for updatable repos
    git_service_mock.sync.return_value = SyncResult(
        repo_name="repo-2",
        requested_action="sync",
        performed_action="pull",
        before_status="BEHIND",
        after_status="SYNCED",
        result="Pulled successfully",
    )

    repos = [
        Repository(
            name="repo-1",
            url="https://github.com/my-org/repo-1",
            ssh_url="git@github.com:my-org/repo-1.git",
            is_fork=False,
            is_archived=False,
        ),
        Repository(
            name="repo-2",
            url="https://github.com/my-org/repo-2",
            ssh_url="git@github.com:my-org/repo-2.git",
            is_fork=False,
            is_archived=False,
        ),
    ]
    repos[0].status = "MISSING"
    repos[1].status = "BEHIND"

    sync_service = SyncService(git_service=git_service_mock)
    results = sync_service.sync_repositories(
        repositories=repos,
        workspace=Path("/workspace"),
        org_name="my-org",
        options={"use_ssh": False},
        max_workers=2,
    )

    # Verify results
    assert len(results) == 2
    res_map = {r.repo_name: r for r in results}
    assert res_map["repo-1"].performed_action == "clone"
    assert res_map["repo-1"].after_status == "SYNCED"
    assert res_map["repo-2"].performed_action == "pull"
    assert res_map["repo-2"].after_status == "SYNCED"


@pytest.mark.unit
def test_parallel_sync_cancellation() -> None:
    git_service_mock = MagicMock()

    repos = [
        Repository(
            name="repo-1",
            url="https://github.com/my-org/repo-1",
            ssh_url="git@github.com:my-org/repo-1.git",
            is_fork=False,
            is_archived=False,
        ),
        Repository(
            name="repo-2",
            url="https://github.com/my-org/repo-2",
            ssh_url="git@github.com:my-org/repo-2.git",
            is_fork=False,
            is_archived=False,
        ),
    ]
    repos[0].status = "BEHIND"
    repos[1].status = "BEHIND"

    def cancel_check() -> bool:
        return True

    sync_service = SyncService(git_service=git_service_mock)
    results = sync_service.sync_repositories(
        repositories=repos,
        workspace=Path("/workspace"),
        org_name="my-org",
        options={},
        is_cancelled_callback=cancel_check,
        max_workers=2,
    )

    # Verify both repos marked as CANCELLED
    assert len(results) == 2
    for r in results:
        assert r.performed_action == "CANCELLED"
        assert r.result == "Sync cancelled by user."
