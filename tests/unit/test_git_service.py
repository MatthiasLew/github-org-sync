from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from github_org_sync.models.repository import Repository
from github_org_sync.services.git_service import GitService


@pytest.fixture
def git_service() -> GitService:
    service = GitService()
    service.git_path = "/usr/bin/git"
    return service


def test_is_wrong_remote(git_service: GitService) -> None:
    assert not git_service.is_wrong_remote("https://github.com/subactor/repo.git", "subactor")
    assert not git_service.is_wrong_remote("git@github.com:subactor/repo.git", "subactor")
    assert not git_service.is_wrong_remote("https://github.com/subactor/repo", "subactor")
    assert not git_service.is_wrong_remote("git@github.com:subactor/repo", "subactor")

    assert git_service.is_wrong_remote("https://github.com/other-org/repo.git", "subactor")
    assert git_service.is_wrong_remote("git@github.com:other-org/repo.git", "subactor")


@patch("pathlib.Path.is_dir")
@patch("pathlib.Path.exists")
def test_is_git_repository(mock_exists: MagicMock, mock_is_dir: MagicMock, git_service: GitService) -> None:
    mock_is_dir.return_value = True
    mock_exists.return_value = True
    assert git_service.is_git_repository(Path("/dummy/repo"))

    mock_exists.return_value = False
    with patch.object(git_service, "_run_git") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        assert not git_service.is_git_repository(Path("/dummy/repo"))


@patch.object(GitService, "_run_git")
@patch.object(GitService, "is_git_repository")
def test_get_local_status_missing(mock_is_repo: MagicMock, mock_run: MagicMock, git_service: GitService) -> None:
    # Path doesn't exist
    with patch("pathlib.Path.exists") as mock_exists:
        mock_exists.return_value = False
        status, _, _, _, _ = git_service.get_local_status(Path("/dummy"), "org")
        assert status == "MISSING"


@patch.object(GitService, "_run_git")
@patch.object(GitService, "is_git_repository")
def test_get_local_status_not_a_repo(mock_is_repo: MagicMock, mock_run: MagicMock, git_service: GitService) -> None:
    with patch("pathlib.Path.exists") as mock_exists:
        mock_exists.return_value = True
        mock_is_repo.return_value = False
        status, _, _, _, _ = git_service.get_local_status(Path("/dummy"), "org")
        assert status == "NOT_A_REPOSITORY"


@patch.object(GitService, "_run_git")
@patch.object(GitService, "is_git_repository")
def test_get_local_status_up_to_date(mock_is_repo: MagicMock, mock_run: MagicMock, git_service: GitService) -> None:
    with patch("pathlib.Path.exists") as mock_exists:
        mock_exists.return_value = True
        mock_is_repo.return_value = True

        # Mock git commands in get_local_status
        # 1. remote get-url
        cp_url = MagicMock(returncode=0, stdout="https://github.com/org/repo")
        # 2. rev-parse HEAD
        cp_branch = MagicMock(returncode=0, stdout="main")
        # 3. rev-parse @{u}
        cp_up = MagicMock(returncode=0, stdout="origin/main")
        # 4. rev-list HEAD...@{u}
        cp_ab = MagicMock(returncode=0, stdout="0\t0")
        # 5. status --porcelain
        cp_status = MagicMock(returncode=0, stdout="")

        mock_run.side_effect = [cp_url, cp_branch, cp_up, cp_ab, cp_status]

        status, branch, ahead, behind, _ = git_service.get_local_status(Path("/dummy"), "org")
        assert status == "UP_TO_DATE"
        assert branch == "main"
        assert ahead == 0
        assert behind == 0


@patch.object(GitService, "_run_git")
@patch.object(GitService, "is_git_repository")
def test_get_local_status_dirty(mock_is_repo: MagicMock, mock_run: MagicMock, git_service: GitService) -> None:
    with patch("pathlib.Path.exists") as mock_exists:
        mock_exists.return_value = True
        mock_is_repo.return_value = True

        cp_url = MagicMock(returncode=0, stdout="https://github.com/org/repo")
        cp_branch = MagicMock(returncode=0, stdout="main")
        cp_up = MagicMock(returncode=0, stdout="origin/main")
        cp_ab = MagicMock(returncode=0, stdout="0\t0")
        cp_status = MagicMock(returncode=0, stdout=" M file.txt\n")

        mock_run.side_effect = [cp_url, cp_branch, cp_up, cp_ab, cp_status]

        status, branch, ahead, behind, _ = git_service.get_local_status(Path("/dummy"), "org")
        assert status == "DIRTY"
        assert branch == "main"


@patch.object(GitService, "_run_git")
@patch.object(GitService, "is_git_repository")
def test_get_local_status_diverged(mock_is_repo: MagicMock, mock_run: MagicMock, git_service: GitService) -> None:
    with patch("pathlib.Path.exists") as mock_exists:
        mock_exists.return_value = True
        mock_is_repo.return_value = True

        cp_url = MagicMock(returncode=0, stdout="https://github.com/org/repo")
        cp_branch = MagicMock(returncode=0, stdout="main")
        cp_up = MagicMock(returncode=0, stdout="origin/main")
        cp_ab = MagicMock(returncode=0, stdout="2\t3")
        cp_status = MagicMock(returncode=0, stdout="")

        mock_run.side_effect = [cp_url, cp_branch, cp_up, cp_ab, cp_status]

        status, branch, ahead, behind, _ = git_service.get_local_status(Path("/dummy"), "org")
        assert status == "DIVERGED"
        assert ahead == 2
        assert behind == 3


@patch.object(GitService, "_run_git")
def test_clone_success(mock_run: MagicMock, git_service: GitService) -> None:
    mock_run.return_value = MagicMock(returncode=0)
    repo = Repository(name="myrepo", url="https://github.com/org/myrepo", ssh_url="git@github.com:org/myrepo.git")

    with patch("pathlib.Path.mkdir") as mock_mkdir:
        res = git_service.clone(repo, Path("/dummy/myrepo"), use_ssh=False, dry_run=False)
        assert res.status == "CLONED"
        assert res.operation == "clone"
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
        dest_path_str = str(Path("/dummy/myrepo"))
        mock_run.assert_called_once_with(None, ["clone", "https://github.com/org/myrepo", dest_path_str])


@patch.object(GitService, "get_local_status")
@patch.object(GitService, "_run_git")
def test_sync_success_clean(mock_run: MagicMock, mock_get_status: MagicMock, git_service: GitService) -> None:
    repo = Repository(
        name="myrepo",
        url="https://github.com/org/myrepo",
        ssh_url="git@github.com:org/myrepo.git",
        local_path=Path("/dummy/myrepo"),
    )

    # get_local_status before fetch: BEHIND
    # then get_local_status after fetch: BEHIND
    # then get_local_status final check: UP_TO_DATE
    mock_get_status.side_effect = [
        ("BEHIND", "main", 0, 1, None),
        ("BEHIND", "main", 0, 1, None),
        ("UP_TO_DATE", "main", 0, 0, None),
    ]

    # 1. Fetch prune
    cp_fetch = MagicMock(returncode=0)
    # 2. Pull ff-only
    cp_pull = MagicMock(returncode=0)
    mock_run.side_effect = [cp_fetch, cp_pull]

    with patch("pathlib.Path.exists") as mock_exists:
        mock_exists.return_value = True
        res = git_service.sync(
            repo, "org", preserve_local_changes=True, fetch_only=False, checkout_default=False, dry_run=False
        )
        assert res.status == "UPDATED"
        assert res.before_status == "BEHIND"
        assert res.after_status == "UP_TO_DATE"

        # Verify pull was called
        mock_run.assert_any_call(Path("/dummy/myrepo"), ["pull", "--ff-only"])
