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
        assert res.performed_action == "CLONED"
        assert res.requested_action == "CLONE"
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
        ("BEHIND", "main", 0, 1, None),
        ("UP_TO_DATE", "main", 0, 0, None),
    ]

    # 1. Dirty check
    cp_dirty = MagicMock(returncode=0, stdout="")
    # 2. Fetch prune
    cp_fetch = MagicMock(returncode=0)
    # 3. Pull ff-only
    cp_pull = MagicMock(returncode=0)
    mock_run.side_effect = [cp_dirty, cp_fetch, cp_pull]

    with patch("pathlib.Path.exists") as mock_exists:
        mock_exists.return_value = True
        res = git_service.sync(
            repo, "org", preserve_local_changes=True, fetch_only=False, checkout_default=False, dry_run=False
        )
        assert res.performed_action == "UPDATED"
        assert res.before_status == "BEHIND"
        assert res.after_status == "UP_TO_DATE"

        # Verify pull was called
        mock_run.assert_any_call(Path("/dummy/myrepo"), ["pull", "--ff-only"])


@pytest.mark.unit
@patch.object(GitService, "_run_git")
@patch.object(GitService, "is_git_repository")
def test_get_local_status_behind(mock_is_repo: MagicMock, mock_run: MagicMock, git_service: GitService) -> None:
    with patch("pathlib.Path.exists") as mock_exists:
        mock_exists.return_value = True
        mock_is_repo.return_value = True

        cp_url = MagicMock(returncode=0, stdout="https://github.com/org/repo")
        cp_branch = MagicMock(returncode=0, stdout="main")
        cp_up = MagicMock(returncode=0, stdout="origin/main")
        cp_ab = MagicMock(returncode=0, stdout="0\t3")
        cp_status = MagicMock(returncode=0, stdout="")

        mock_run.side_effect = [cp_url, cp_branch, cp_up, cp_ab, cp_status]

        status, branch, ahead, behind, _ = git_service.get_local_status(Path("/dummy"), "org")
        assert status == "BEHIND"
        assert behind == 3


@pytest.mark.unit
@patch.object(GitService, "_run_git")
@patch.object(GitService, "is_git_repository")
def test_get_local_status_conflict(mock_is_repo: MagicMock, mock_run: MagicMock, git_service: GitService) -> None:
    with patch("pathlib.Path.exists") as mock_exists:
        mock_exists.return_value = True
        mock_is_repo.return_value = True

        cp_url = MagicMock(returncode=0, stdout="https://github.com/org/repo")
        cp_branch = MagicMock(returncode=0, stdout="main")
        cp_up = MagicMock(returncode=0, stdout="origin/main")
        cp_ab = MagicMock(returncode=0, stdout="0\t0")
        # UU indicates a merge conflict (unmerged path)
        cp_status = MagicMock(returncode=0, stdout="UU file.txt\n")

        mock_run.side_effect = [cp_url, cp_branch, cp_up, cp_ab, cp_status]

        status, _, _, _, _ = git_service.get_local_status(Path("/dummy"), "org")
        assert status == "DIRTY"


@pytest.mark.unit
@patch.object(GitService, "_run_git")
@patch.object(GitService, "is_git_repository")
def test_get_local_status_no_upstream(mock_is_repo: MagicMock, mock_run: MagicMock, git_service: GitService) -> None:
    with patch("pathlib.Path.exists") as mock_exists:
        mock_exists.return_value = True
        mock_is_repo.return_value = True

        cp_url = MagicMock(returncode=0, stdout="https://github.com/org/repo")
        cp_branch = MagicMock(returncode=0, stdout="main")
        # rev-parse @{u} fails (no upstream branch configured)
        cp_up = MagicMock(returncode=1, stderr="fatal: no upstream configured")

        mock_run.side_effect = [cp_url, cp_branch, cp_up]

        status, _, _, _, _ = git_service.get_local_status(Path("/dummy"), "org")
        assert status == "NO_UPSTREAM"


@pytest.mark.unit
@patch.object(GitService, "_run_git")
@patch.object(GitService, "is_git_repository")
def test_get_local_status_detached_head(mock_is_repo: MagicMock, mock_run: MagicMock, git_service: GitService) -> None:
    with patch("pathlib.Path.exists") as mock_exists:
        mock_exists.return_value = True
        mock_is_repo.return_value = True

        cp_url = MagicMock(returncode=0, stdout="https://github.com/org/repo")
        # rev-parse --abbrev-ref HEAD returns "HEAD" under detached state
        cp_branch = MagicMock(returncode=0, stdout="HEAD")

        mock_run.side_effect = [cp_url, cp_branch]

        status, branch, _, _, _ = git_service.get_local_status(Path("/dummy"), "org")
        assert status == "DETACHED_HEAD"
        assert branch == "HEAD"


@pytest.mark.unit
@patch.object(GitService, "_run_git")
@patch.object(GitService, "is_git_repository")
def test_get_local_status_wrong_remote(mock_is_repo: MagicMock, mock_run: MagicMock, git_service: GitService) -> None:
    with patch("pathlib.Path.exists") as mock_exists:
        mock_exists.return_value = True
        mock_is_repo.return_value = True

        # remote points to wrong owner or wrong repo name
        cp_url = MagicMock(returncode=0, stdout="https://github.com/anotherowner/repo")
        mock_run.side_effect = [cp_url]

        status, _, _, _, _ = git_service.get_local_status(Path("/dummy"), "org")
        assert status == "WRONG_REMOTE"


@pytest.mark.unit
@patch.object(GitService, "_run_git")
@patch.object(GitService, "is_git_repository")
def test_git_service_exceptions(mock_is_repo: MagicMock, mock_run: MagicMock, git_service: GitService) -> None:
    # Test permission or execution errors when running process runner
    with patch("pathlib.Path.exists") as mock_exists:
        mock_exists.return_value = True
        mock_is_repo.return_value = True
        mock_run.side_effect = PermissionError("Access denied")

        # get_local_status should handle the error and return FAILED status
        status, _, _, _, err_msg = git_service.get_local_status(Path("/dummy"), "org")
        assert status == "FAILED"
        assert err_msg is not None and "Access denied" in err_msg


@pytest.mark.unit
@patch("github_org_sync.utils.process.popen_process")
def test_launch_merge_tool(mock_popen: MagicMock, git_service: GitService) -> None:
    git_service.launch_merge_tool(Path("/dummy"))
    mock_popen.assert_called_once_with(["git", "mergetool"], cwd=Path("/dummy"))


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_get_local_branches(mock_run: MagicMock, git_service: GitService) -> None:
    cp = MagicMock(returncode=0, stdout="master\nmain\nfeature/test\n")
    mock_run.return_value = cp
    branches = git_service.get_local_branches(Path("/dummy"))
    assert branches == ["master", "main", "feature/test"]
    mock_run.assert_called_once_with(Path("/dummy"), ["branch", "--format=%(refname:short)"])


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_checkout_branch(mock_run: MagicMock, git_service: GitService) -> None:
    cp = MagicMock(returncode=0, stdout="Switched to branch 'main'\n", stderr="")
    mock_run.return_value = cp
    ok, out = git_service.checkout_branch(Path("/dummy"), "main")
    assert ok is True
    assert "Switched to branch 'main'" in out
    mock_run.assert_called_once_with(Path("/dummy"), ["checkout", "main"])


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_stage_and_unstage_file(mock_run: MagicMock, git_service: GitService) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    ok, _ = git_service.stage_file(Path("/dummy"), "file.txt")
    assert ok is True
    mock_run.assert_called_with(Path("/dummy"), ["add", "--", "file.txt"])

    ok, _ = git_service.unstage_file(Path("/dummy"), "file.txt")
    assert ok is True
    mock_run.assert_called_with(Path("/dummy"), ["restore", "--staged", "--", "file.txt"])


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_stage_and_unstage_all(mock_run: MagicMock, git_service: GitService) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    ok, _ = git_service.stage_all(Path("/dummy"))
    assert ok is True
    mock_run.assert_called_with(Path("/dummy"), ["add", "-A"])

    ok, _ = git_service.unstage_all(Path("/dummy"))
    assert ok is True
    mock_run.assert_called_with(Path("/dummy"), ["restore", "--staged", "."])


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_commit_changes(mock_run: MagicMock, git_service: GitService) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="[main 1234567] feat: test", stderr="")
    ok, out = git_service.commit_changes(Path("/dummy"), "feat: test")
    assert ok is True
    assert "1234567" in out
    mock_run.assert_called_once_with(Path("/dummy"), ["commit", "-m", "feat: test"])


@pytest.mark.unit
@patch.object(GitService, "get_dirty_files")
def test_get_staged_and_unstaged_files(mock_dirty: MagicMock, git_service: GitService) -> None:
    mock_dirty.return_value = [
        ("M ", "staged.txt"),
        (" M", "unstaged.txt"),
        ("??", "untracked.txt"),
        ("MM", "both.txt"),
    ]
    staged, unstaged = git_service.get_staged_and_unstaged_files(Path("/dummy"))
    assert staged == ["staged.txt", "both.txt"]
    assert unstaged == ["unstaged.txt", "untracked.txt", "both.txt"]


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_get_stash_list_and_show(mock_run: MagicMock, git_service: GitService) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="stash@{0}: WIP on main\nstash@{1}: test stash\n")
    stashes = git_service.get_stash_list(Path("/dummy"))
    assert len(stashes) == 2
    assert stashes[0] == "stash@{0}: WIP on main"

    mock_run.return_value = MagicMock(returncode=0, stdout="file.py | 2 +-")
    show = git_service.get_stash_show(Path("/dummy"), 0)
    assert "file.py" in show


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_stash_push_pop_drop(mock_run: MagicMock, git_service: GitService) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="Saved working directory", stderr="")
    ok, _ = git_service.stash_push(Path("/dummy"), "my stash")
    assert ok is True
    mock_run.assert_called_with(Path("/dummy"), ["stash", "push", "--include-untracked", "-m", "my stash"])

    mock_run.return_value = MagicMock(returncode=0, stdout="Dropped stash@{0}", stderr="")
    ok, _ = git_service.stash_drop(Path("/dummy"), 0)
    assert ok is True
    mock_run.assert_called_with(Path("/dummy"), ["stash", "drop", "stash@{0}"])

    mock_run.return_value = MagicMock(returncode=0, stdout="Applied stash@{0}", stderr="")
    ok, _ = git_service.stash_pop(Path("/dummy"), 0)
    assert ok is True
    mock_run.assert_called_with(Path("/dummy"), ["stash", "pop", "stash@{0}"])


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_prune_remote_branches(mock_run: MagicMock, git_service: GitService) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="Pruning origin\n * [pruned] origin/feat\n", stderr="")
    ok, out = git_service.prune_remote_branches(Path("/dummy"))
    assert ok is True
    assert "[pruned] origin/feat" in out
    mock_run.assert_called_with(Path("/dummy"), ["remote", "prune", "origin"])


@pytest.mark.unit
@patch.object(GitService, "_run_git")
@patch.object(GitService, "get_default_branch")
def test_get_stale_branches(mock_def_branch: MagicMock, mock_run: MagicMock, git_service: GitService) -> None:
    mock_def_branch.return_value = "main"

    cp_head = MagicMock(returncode=0, stdout="main\n")
    cp_merged = MagicMock(returncode=0, stdout="  merged-feat\n* main\n")
    cp_refs = MagicMock(
        returncode=0,
        stdout=(
            "main|origin/main||\n"
            "gone-feat|origin/gone-feat|[gone]|\n"
            "merged-feat|origin/merged-feat||\n"
            "active-feat|origin/active-feat|[ahead 1]|\n"
        ),
    )
    mock_run.side_effect = [cp_head, cp_merged, cp_refs]

    stale = git_service.get_stale_branches(Path("/dummy"))
    assert len(stale) == 2
    assert stale[0] == {"name": "gone-feat", "upstream": "origin/gone-feat", "reason": "gone"}
    assert stale[1] == {"name": "merged-feat", "upstream": "origin/merged-feat", "reason": "merged"}


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_delete_local_branch(mock_run: MagicMock, git_service: GitService) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="Deleted branch old-feat (was 1234567).", stderr="")
    ok, out = git_service.delete_local_branch(Path("/dummy"), "old-feat", force=True)
    assert ok is True
    assert "Deleted branch old-feat" in out
    mock_run.assert_called_with(Path("/dummy"), ["branch", "-D", "old-feat"])


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_get_log_graph(mock_run: MagicMock, git_service: GitService) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="* 1234abc (HEAD -> main) Initial commit\n", stderr="")
    graph = git_service.get_log_graph(Path("/dummy"), limit=10, all_branches=True)
    assert "* 1234abc" in graph
    mock_run.assert_called_with(
        Path("/dummy"),
        ["log", "--graph", "--oneline", "--decorate", "--all", "-n", "10"],
    )
