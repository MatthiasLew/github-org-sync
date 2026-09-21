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


@patch.object(GitService, "is_git_repository", return_value=True)
@patch.object(GitService, "_run_git")
def test_clone_success(mock_run: MagicMock, mock_is_git: MagicMock, git_service: GitService) -> None:
    mock_run.return_value = MagicMock(returncode=0)
    repo = Repository(name="myrepo", url="https://github.com/org/myrepo", ssh_url="git@github.com:org/myrepo.git")

    with patch("pathlib.Path.mkdir"), patch("pathlib.Path.replace"), patch("pathlib.Path.exists", return_value=False):
        res = git_service.clone(repo, Path("/dummy/myrepo"), use_ssh=False, dry_run=False)
        assert res.performed_action == "CLONED"
        assert res.requested_action == "CLONE"
        mock_run.assert_called_once()
        assert mock_run.call_args[0][1][:2] == ["clone", "https://github.com/org/myrepo"]


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


@pytest.mark.unit
def test_detect_lfs(tmp_path: Path, git_service: GitService) -> None:
    assert git_service.detect_lfs(tmp_path) is False

    (tmp_path / ".gitattributes").write_text("*.psd filter=lfs diff=lfs merge=lfs -text\n", encoding="utf-8")
    assert git_service.detect_lfs(tmp_path) is True


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_get_lfs_status(mock_run: MagicMock, tmp_path: Path, git_service: GitService) -> None:
    (tmp_path / ".gitattributes").write_text("*.bin filter=lfs\n", encoding="utf-8")
    cp_ls = MagicMock(returncode=0, stdout="d123456789 * asset.bin\n", stderr="")
    cp_status = MagicMock(returncode=0, stdout="Objects to be committed:\n\tasset.bin (Git LFS: 100%)\n", stderr="")
    mock_run.side_effect = [cp_ls, cp_status]

    info = git_service.get_lfs_status(tmp_path)
    assert info["has_lfs"] is True
    assert len(info["files"]) == 1
    assert "asset.bin" in info["files"][0]
    assert "Objects to be committed" in info["status"]


@pytest.mark.unit
def test_git_service_missing_git_path() -> None:
    service = GitService()
    service.git_path = None
    with pytest.raises(FileNotFoundError, match="Git is not installed"):
        service._run_git(Path("/dummy"), ["status"])


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_is_git_repository_detailed_branches(mock_run: MagicMock, tmp_path: Path, git_service: GitService) -> None:
    non_dir = tmp_path / "a_file.txt"
    non_dir.write_text("not a dir", encoding="utf-8")
    assert git_service.is_git_repository(non_dir) is False

    repo_dir = tmp_path / "repo_dir"
    repo_dir.mkdir()
    # Rev-parse returns toplevel matching
    mock_run.return_value = MagicMock(returncode=0, stdout=str(repo_dir) + "\n")
    assert git_service.is_git_repository(repo_dir) is True

    # Rev-parse returns toplevel mismatch
    mock_run.return_value = MagicMock(returncode=0, stdout=str(tmp_path / "other") + "\n")
    assert git_service.is_git_repository(repo_dir) is False

    # Rev-parse raises exception
    mock_run.side_effect = RuntimeError("git exploded")
    assert git_service.is_git_repository(repo_dir) is False


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_add_remote_branches(mock_run: MagicMock, git_service: GitService) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    git_service.add_remote(Path("/dummy"), "origin", "https://github.com/org/repo.git")

    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="remote origin already exists")
    with pytest.raises(RuntimeError, match="remote origin already exists"):
        git_service.add_remote(Path("/dummy"), "origin", "https://github.com/org/repo.git")


@pytest.mark.unit
def test_is_wrong_remote_edge_branches(git_service: GitService) -> None:
    assert git_service.is_wrong_remote("https://github.com/org/repo.git", "") is False
    assert git_service.is_wrong_remote("", "org") is True
    assert git_service.is_wrong_remote("not a git url", "org") is True
    assert git_service.is_wrong_remote("https://github.com/org/repo.git", "org", repo_name="repo") is False
    assert git_service.is_wrong_remote("https://github.com/org/repo.git", "org", repo_name="wrong_repo") is True


@pytest.mark.unit
@patch.object(GitService, "is_git_repository")
@patch.object(GitService, "_run_git")
def test_inspect_repo_state_missing_origin_and_repo_mismatch(
    mock_run: MagicMock, mock_is_repo: MagicMock, tmp_path: Path, git_service: GitService
) -> None:
    mock_is_repo.return_value = True
    # Missing origin remote
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error: No such remote 'origin'")
    state = git_service.inspect_repo_state(tmp_path, expected_org="myorg")
    assert state.exists is True
    assert state.is_git_repo is True
    assert state.error_message == "Missing origin remote"

    # Expected repo mismatch
    mock_run.return_value = MagicMock(returncode=0, stdout="https://github.com/myorg/other-repo.git", stderr="")
    state2 = git_service.inspect_repo_state(tmp_path, expected_org="myorg", expected_repo="target-repo")
    assert state2.remote_matches is False
    assert "Remote origin mismatch" in (state2.error_message or "")


@pytest.mark.unit
def test_clone_destination_already_exists(tmp_path: Path, git_service: GitService) -> None:
    existing_dest = tmp_path / "existing-repo"
    existing_dest.mkdir()
    repo = Repository(
        "existing-repo", "https://github.com/org/existing-repo.git", "git@github.com:org/existing-repo.git"
    )
    res = git_service.clone(repo, existing_dest, use_ssh=False, dry_run=False)
    assert res.performed_action == "FAILED"
    assert "already exists" in (res.result or "")


@pytest.mark.unit
@patch.object(GitService, "is_git_repository")
@patch.object(GitService, "_run_git")
@patch("shutil.move")
def test_clone_fallback_to_shutil_move(
    mock_shutil_move: MagicMock,
    mock_run: MagicMock,
    mock_is_repo: MagicMock,
    tmp_path: Path,
    git_service: GitService,
) -> None:
    dest_path = tmp_path / "dest-repo"
    repo = Repository("dest-repo", "https://github.com/org/dest-repo.git", "git@github.com:org/dest-repo.git")
    mock_run.return_value = MagicMock(returncode=0, stdout="Cloned successfully", stderr="")
    mock_is_repo.return_value = True

    with patch("pathlib.Path.replace", side_effect=OSError("Cross-device link")):
        res = git_service.clone(repo, dest_path, use_ssh=False, dry_run=False)
    assert res.performed_action == "CLONED"
    mock_shutil_move.assert_called_once()


@pytest.mark.unit
@patch.object(GitService, "is_git_repository")
@patch.object(GitService, "_run_git")
def test_clone_invalid_git_structure(
    mock_run: MagicMock, mock_is_repo: MagicMock, tmp_path: Path, git_service: GitService
) -> None:
    dest_path = tmp_path / "invalid-repo"
    repo = Repository("invalid-repo", "https://github.com/org/invalid-repo.git", "git@github.com:org/invalid-repo.git")
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    mock_is_repo.return_value = False

    res = git_service.clone(repo, dest_path, use_ssh=False, dry_run=False)
    assert res.performed_action == "FAILED"
    assert "failed validation" in (res.error or "")


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_get_default_branch_fallbacks(mock_run: MagicMock, git_service: GitService) -> None:
    # 1. symbolic-ref fails, origin/main fails, origin/master succeeds
    cp_sethead = MagicMock(returncode=0)
    cp_sym = MagicMock(returncode=1, stdout="")
    cp_main = MagicMock(returncode=1, stdout="")
    cp_master = MagicMock(returncode=0, stdout="sha123")
    mock_run.side_effect = [cp_sethead, cp_sym, cp_main, cp_master]
    assert git_service.get_default_branch(Path("/dummy")) == "master"

    # 2. Both candidates fail -> None
    mock_run.side_effect = [
        MagicMock(returncode=0),
        MagicMock(returncode=1),
        MagicMock(returncode=1),
        MagicMock(returncode=1),
    ]
    assert git_service.get_default_branch(Path("/dummy")) is None


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_get_conflict_files(mock_run: MagicMock, git_service: GitService) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="file1.txt\nfile2.py\n")
    assert git_service.get_conflict_files(Path("/dummy")) == ["file1.txt", "file2.py"]

    mock_run.return_value = MagicMock(returncode=1, stdout="")
    assert git_service.get_conflict_files(Path("/dummy")) == []

    mock_run.side_effect = RuntimeError("git error")
    assert git_service.get_conflict_files(Path("/dummy")) == []


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_get_unpushed_commits(mock_run: MagicMock, git_service: GitService) -> None:
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="aaa|Author|2026-01-01|Fix bug\ninvalidline\nbbb|Author2|2026-01-02|Add feature\n",
    )
    commits = git_service.get_unpushed_commits(Path("/dummy"), "main", "origin/main")
    assert len(commits) == 2
    assert commits[0]["sha"] == "aaa"
    assert commits[1]["sha"] == "bbb"

    mock_run.return_value = MagicMock(returncode=1, stdout="")
    assert git_service.get_unpushed_commits(Path("/dummy"), "main", "origin/main") == []

    mock_run.side_effect = RuntimeError("fail")
    assert git_service.get_unpushed_commits(Path("/dummy"), "main", "origin/main") == []


@pytest.mark.unit
@patch.object(GitService, "_run_git")
@patch.object(GitService, "get_unpushed_commits")
def test_get_diverged_commits(mock_unpushed: MagicMock, mock_run: MagicMock, git_service: GitService) -> None:
    mock_unpushed.return_value = [{"sha": "loc1", "author": "me", "date": "today", "subject": "local"}]
    cp_remote = MagicMock(returncode=0, stdout="rem1|them|yesterday|remote commit\ninvalid\n")
    cp_base = MagicMock(returncode=0, stdout="base123\n")
    mock_run.side_effect = [cp_remote, cp_base]

    local, remote, base = git_service.get_diverged_commits(Path("/dummy"), "main", "origin/main")
    assert len(local) == 1
    assert len(remote) == 1
    assert remote[0]["sha"] == "rem1"
    assert base == "base123"

    mock_run.side_effect = RuntimeError("failure")
    l_err, r_err, b_err = git_service.get_diverged_commits(Path("/dummy"), "main", "origin/main")
    assert l_err == []
    assert r_err == []
    assert b_err == ""


@pytest.mark.unit
def test_backup_repository(tmp_path: Path, git_service: GitService) -> None:
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    (repo_dir / "code.py").write_text("print('hello')", encoding="utf-8")
    git_dir = repo_dir / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("git internal", encoding="utf-8")

    with patch("github_org_sync.services.report_service.ReportService.get_app_data_dir", return_value=tmp_path):
        backup_zip = git_service.backup_repository(repo_dir, "myorg", "test_repo")
        assert backup_zip is not None
        assert backup_zip.is_file()

        # Check that .git was excluded
        import zipfile

        with zipfile.ZipFile(backup_zip, "r") as zf:
            namelist = zf.namelist()
            assert "code.py" in namelist
            assert not any(".git" in n for n in namelist)

        # Exception branch returns None
        with patch("pathlib.Path.mkdir", side_effect=PermissionError("no write")):
            assert git_service.backup_repository(repo_dir, "myorg", "test_repo") is None


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_discard_changes(mock_run: MagicMock, git_service: GitService) -> None:
    # Both succeed
    mock_run.side_effect = [MagicMock(returncode=0), MagicMock(returncode=0)]
    assert git_service.discard_changes(Path("/dummy")) is True

    # Clean fails
    mock_run.side_effect = [MagicMock(returncode=0), MagicMock(returncode=1)]
    assert git_service.discard_changes(Path("/dummy")) is False

    # Exception
    mock_run.side_effect = RuntimeError("git died")
    assert git_service.discard_changes(Path("/dummy")) is False


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_branch_and_sync_operations(mock_run: MagicMock, git_service: GitService) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

    git_service.push_commits(Path("/dummy"), "feature")
    mock_run.assert_called_with(Path("/dummy"), ["push", "origin", "feature"])

    git_service.merge_branch(Path("/dummy"), "origin/main")
    mock_run.assert_called_with(Path("/dummy"), ["merge", "origin/main"])

    git_service.rebase_branch(Path("/dummy"), "origin/main")
    mock_run.assert_called_with(Path("/dummy"), ["rebase", "origin/main"])

    git_service.abort_merge(Path("/dummy"))
    mock_run.assert_called_with(Path("/dummy"), ["merge", "--abort"])

    git_service.abort_rebase(Path("/dummy"))
    mock_run.assert_called_with(Path("/dummy"), ["rebase", "--abort"])

    git_service.create_branch(Path("/dummy"), "new-branch")
    mock_run.assert_called_with(Path("/dummy"), ["checkout", "-b", "new-branch"])

    git_service.set_upstream_branch(Path("/dummy"), "local-b", "remote-b")
    mock_run.assert_called_with(Path("/dummy"), ["branch", "--set-upstream-to=origin/remote-b", "local-b"])

    git_service.push_set_upstream(Path("/dummy"), "local-b")
    mock_run.assert_called_with(Path("/dummy"), ["push", "-u", "origin", "local-b"])


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_get_file_diff_and_commit_show(mock_run: MagicMock, git_service: GitService) -> None:
    # Diff success
    mock_run.return_value = MagicMock(returncode=0, stdout="diff content", stderr="")
    assert git_service.get_file_diff(Path("/dummy"), "file.txt") == "diff content"

    # Diff failure returns stderr
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="diff error")
    assert git_service.get_file_diff(Path("/dummy"), "file.txt") == "diff error"

    # Diff exception
    mock_run.side_effect = RuntimeError("diff crashed")
    assert "diff crashed" in git_service.get_file_diff(Path("/dummy"), "file.txt")

    # Show success
    mock_run.side_effect = None
    mock_run.return_value = MagicMock(returncode=0, stdout="show content", stderr="")
    assert git_service.get_commit_show(Path("/dummy"), "sha1") == "show content"

    # Show failure returns stderr
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="show error")
    assert git_service.get_commit_show(Path("/dummy"), "sha1") == "show error"

    # Show exception
    mock_run.side_effect = RuntimeError("show crashed")
    assert "show crashed" in git_service.get_commit_show(Path("/dummy"), "sha1")


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_get_local_branches_and_checkout(mock_run: MagicMock, git_service: GitService) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="main\nfeature-x\n", stderr="")
    assert git_service.get_local_branches(Path("/dummy")) == ["main", "feature-x"]

    mock_run.side_effect = RuntimeError("branch crashed")
    assert git_service.get_local_branches(Path("/dummy")) == []

    # Checkout success
    mock_run.side_effect = None
    mock_run.return_value = MagicMock(returncode=0, stdout="Switched branch", stderr="")
    ok, out = git_service.checkout_branch(Path("/dummy"), "main")
    assert ok is True
    assert "Switched branch" in out

    # Checkout error
    mock_run.side_effect = RuntimeError("checkout error")
    ok, out = git_service.checkout_branch(Path("/dummy"), "main")
    assert ok is False
    assert "checkout error" in out


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_staging_and_commit_operations(mock_run: MagicMock, git_service: GitService) -> None:
    # stage_file
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    ok, _ = git_service.stage_file(Path("/dummy"), "test.py")
    assert ok is True

    mock_run.side_effect = RuntimeError("stage fail")
    ok, err = git_service.stage_file(Path("/dummy"), "test.py")
    assert ok is False
    assert "stage fail" in err

    # unstage_file: restore succeeds
    mock_run.side_effect = None
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    ok, _ = git_service.unstage_file(Path("/dummy"), "test.py")
    assert ok is True

    # unstage_file: restore fails, reset succeeds
    mock_run.side_effect = [
        MagicMock(returncode=1, stdout="", stderr="restore failed"),
        MagicMock(returncode=0, stdout="Unstaged changes", stderr=""),
    ]
    ok, out = git_service.unstage_file(Path("/dummy"), "test.py")
    assert ok is True
    assert "Unstaged changes" in out

    # stage_all
    mock_run.side_effect = None
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    ok, _ = git_service.stage_all(Path("/dummy"))
    assert ok is True

    mock_run.side_effect = RuntimeError("stage_all error")
    ok, _ = git_service.stage_all(Path("/dummy"))
    assert ok is False

    # unstage_all: restore succeeds
    mock_run.side_effect = None
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    ok, _ = git_service.unstage_all(Path("/dummy"))
    assert ok is True

    # unstage_all: restore fails, reset succeeds
    mock_run.side_effect = [
        MagicMock(returncode=1, stdout="", stderr="restore err"),
        MagicMock(returncode=0, stdout="reset done", stderr=""),
    ]
    ok, _ = git_service.unstage_all(Path("/dummy"))
    assert ok is True

    # commit_changes
    mock_run.side_effect = None
    mock_run.return_value = MagicMock(returncode=0, stdout="[main 1234] commit", stderr="")
    ok, out = git_service.commit_changes(Path("/dummy"), "test message")
    assert ok is True
    assert "commit" in out

    mock_run.side_effect = RuntimeError("commit error")
    ok, _ = git_service.commit_changes(Path("/dummy"), "test message")
    assert ok is False


@pytest.mark.unit
@patch.object(GitService, "get_dirty_files")
def test_get_staged_and_unstaged_files_error_and_edge_cases(mock_dirty: MagicMock, git_service: GitService) -> None:
    mock_dirty.return_value = [
        ("M ", "staged_file.txt"),
        (" M", "unstaged_file.txt"),
        ("MM", "both_file.txt"),
        ("??", "untracked_file.txt"),
    ]
    staged, unstaged = git_service.get_staged_and_unstaged_files(Path("/dummy"))
    assert "staged_file.txt" in staged
    assert "both_file.txt" in staged
    assert "unstaged_file.txt" in unstaged
    assert "both_file.txt" in unstaged
    assert "untracked_file.txt" in unstaged

    mock_dirty.side_effect = RuntimeError("dirty error")
    assert git_service.get_staged_and_unstaged_files(Path("/dummy")) == ([], [])


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_stash_methods(mock_run: MagicMock, git_service: GitService) -> None:
    # get_stash_list
    mock_run.return_value = MagicMock(returncode=0, stdout="stash@{0}: WIP on main\nstash@{1}: WIP\n", stderr="")
    assert len(git_service.get_stash_list(Path("/dummy"))) == 2

    mock_run.side_effect = RuntimeError("stash list err")
    assert git_service.get_stash_list(Path("/dummy")) == []

    # get_stash_show
    mock_run.side_effect = None
    mock_run.return_value = MagicMock(returncode=0, stdout=" 1 file changed\n", stderr="")
    assert git_service.get_stash_show(Path("/dummy"), 0) == "1 file changed"

    mock_run.side_effect = RuntimeError("show err")
    assert git_service.get_stash_show(Path("/dummy"), 0) == ""

    # stash_push
    mock_run.side_effect = None
    mock_run.return_value = MagicMock(returncode=0, stdout="Saved WIP\n", stderr="")
    ok, out = git_service.stash_push(Path("/dummy"), message="my save", include_untracked=True)
    assert ok is True
    assert "Saved WIP" in out
    mock_run.assert_called_with(Path("/dummy"), ["stash", "push", "--include-untracked", "-m", "my save"])

    ok, _ = git_service.stash_push(Path("/dummy"), message="", include_untracked=False)
    assert ok is True
    mock_run.assert_called_with(Path("/dummy"), ["stash", "push"])

    mock_run.side_effect = RuntimeError("stash push failed")
    ok, err = git_service.stash_push(Path("/dummy"))
    assert ok is False
    assert "failed" in err

    # stash_drop
    mock_run.side_effect = None
    mock_run.return_value = MagicMock(returncode=0, stdout="Dropped stash@{0}\n", stderr="")
    ok, out = git_service.stash_drop(Path("/dummy"), 0)
    assert ok is True
    assert "Dropped" in out

    mock_run.side_effect = RuntimeError("drop err")
    ok, _ = git_service.stash_drop(Path("/dummy"), 0)
    assert ok is False


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_prune_and_stale_branches_edges(mock_run: MagicMock, git_service: GitService) -> None:
    # prune exception
    mock_run.side_effect = RuntimeError("prune crashed")
    ok, err = git_service.prune_remote_branches(Path("/dummy"))
    assert ok is False
    assert "prune crashed" in err

    # get_stale_branches refs failure
    mock_run.side_effect = None
    cp_head = MagicMock(returncode=0, stdout="main\n")
    cp_merged = MagicMock(returncode=0, stdout="")
    cp_refs = MagicMock(returncode=1, stdout="")
    mock_run.side_effect = [cp_head, cp_merged, cp_refs]
    with patch.object(git_service, "get_default_branch", return_value="main"):
        assert git_service.get_stale_branches(Path("/dummy")) == []

    # get_stale_branches exception
    mock_run.side_effect = RuntimeError("crash")
    assert git_service.get_stale_branches(Path("/dummy")) == []


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_delete_branch_non_force_and_log_graph(mock_run: MagicMock, git_service: GitService) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="Deleted branch feat.", stderr="")
    ok, out = git_service.delete_local_branch(Path("/dummy"), "feat", force=False)
    assert ok is True
    mock_run.assert_called_with(Path("/dummy"), ["branch", "-d", "feat"])

    mock_run.side_effect = RuntimeError("del fail")
    ok, _ = git_service.delete_local_branch(Path("/dummy"), "feat")
    assert ok is False

    # get_log_graph non-all-branches and errors
    mock_run.side_effect = None
    mock_run.return_value = MagicMock(returncode=0, stdout="* log graph", stderr="")
    graph = git_service.get_log_graph(Path("/dummy"), limit=5, all_branches=False)
    assert "* log graph" in graph
    mock_run.assert_called_with(Path("/dummy"), ["log", "--graph", "--oneline", "--decorate", "-n", "5"])

    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="log error")
    assert git_service.get_log_graph(Path("/dummy")) == "log error"

    mock_run.side_effect = RuntimeError("graph error")
    assert "graph error" in git_service.get_log_graph(Path("/dummy"))


@pytest.mark.unit
@patch.object(GitService, "_run_git")
def test_lfs_detailed_branches(mock_run: MagicMock, tmp_path: Path, git_service: GitService) -> None:
    # .lfsconfig detection
    assert git_service.detect_lfs(tmp_path) is False
    (tmp_path / ".lfsconfig").write_text("[lfs]\n", encoding="utf-8")
    assert git_service.detect_lfs(tmp_path) is True

    # detect_lfs exception
    with patch("pathlib.Path.is_file", side_effect=PermissionError("no access")):
        assert git_service.detect_lfs(tmp_path) is False

    # get_lfs_status when lfs is not installed on system
    (tmp_path / ".lfsconfig").unlink(missing_ok=True)
    cp_ls = MagicMock(returncode=1, stdout="", stderr="git: 'lfs' is not a git command. See 'git --help'.")
    cp_status = MagicMock(returncode=1, stdout="", stderr="")
    mock_run.side_effect = [cp_ls, cp_status]

    info = git_service.get_lfs_status(tmp_path)
    assert info["error"] == "Git LFS is not installed on system."

    # get_lfs_status exception
    mock_run.side_effect = RuntimeError("lfs crashed")
    info2 = git_service.get_lfs_status(tmp_path)
    assert "lfs crashed" in (info2["error"] or "")


@pytest.mark.unit
def test_git_service_sync_branches(tmp_path: Path, git_service: GitService) -> None:
    repo = Repository("repo1", "https://github.com/myorg/repo1.git", "git@github.com:myorg/repo1.git")

    # 1. Local path does not exist
    repo.local_path = tmp_path / "nonexistent"
    res_missing = git_service.sync(repo, "myorg")
    assert res_missing.performed_action == "FAILED"
    assert "does not exist" in (res_missing.error or "")

    # 2. Local path exists but status in ("NOT_A_REPOSITORY", "WRONG_REMOTE", "FAILED")
    real_path = tmp_path / "repo1"
    real_path.mkdir()
    repo.local_path = real_path

    with (
        patch.object(git_service, "get_local_status", return_value=("NOT_A_REPOSITORY", None, 0, 0, "not a repo")),
        patch.object(git_service, "get_dirty_files", return_value=[]),
    ):
        res_not_repo = git_service.sync(repo, "myorg")
        assert res_not_repo.performed_action == "FAILED"
        assert res_not_repo.error == "not a repo"

    # 3. Dry-run
    with (
        patch.object(git_service, "get_local_status", return_value=("UP_TO_DATE", "main", 0, 0, None)),
        patch.object(git_service, "get_dirty_files", return_value=[]),
    ):
        res_dry = git_service.sync(repo, "myorg", dry_run=True)
        assert res_dry.performed_action == "NO_CHANGE"
        assert "[DRY-RUN]" in (res_dry.result or "")

    # 4. Fetch failure
    with (
        patch.object(git_service, "get_local_status", return_value=("UP_TO_DATE", "main", 0, 0, None)),
        patch.object(git_service, "get_dirty_files", return_value=[]),
        patch.object(git_service, "_run_git", return_value=MagicMock(returncode=1, stdout="", stderr="network error")),
    ):
        res_fetch_err = git_service.sync(repo, "myorg")
        assert res_fetch_err.performed_action == "FAILED"
        assert "Fetch failed" in (res_fetch_err.result or "")

    # 5. Fetch-only success
    with (
        patch.object(
            git_service,
            "get_local_status",
            side_effect=[
                ("UP_TO_DATE", "main", 0, 0, None),
                ("UP_TO_DATE", "main", 0, 0, None),
            ],
        ),
        patch.object(git_service, "get_dirty_files", return_value=[]),
        patch.object(git_service, "_run_git", return_value=MagicMock(returncode=0, stdout="", stderr="")),
    ):
        res_fetch_only = git_service.sync(repo, "myorg", fetch_only=True)
        assert res_fetch_only.performed_action == "FETCHED"

    # 6. Checkout default blocked when dirty
    with (
        patch.object(git_service, "get_local_status", return_value=("BEHIND", "feature", 0, 1, None)),
        patch.object(git_service, "get_dirty_files", return_value=[(" M", "file.txt")]),
        patch.object(git_service, "_run_git", return_value=MagicMock(returncode=0, stdout="", stderr="")),
        patch.object(git_service, "get_default_branch", return_value="main"),
    ):
        res_blocked = git_service.sync(repo, "myorg", checkout_default=True)
        assert res_blocked.performed_action == "BLOCKED"
        assert "dirty" in (res_blocked.result or "")

    # 7. Checkout default fails
    with (
        patch.object(git_service, "get_local_status", return_value=("BEHIND", "feature", 0, 1, None)),
        patch.object(git_service, "get_dirty_files", return_value=[]),
        patch.object(
            git_service,
            "_run_git",
            side_effect=[
                MagicMock(returncode=0),  # fetch
                MagicMock(returncode=1, stdout="", stderr="error: pathspec 'main' did not match"),  # checkout
            ],
        ),
        patch.object(git_service, "get_default_branch", return_value="main"),
    ):
        res_co_fail = git_service.sync(repo, "myorg", checkout_default=True)
        assert res_co_fail.performed_action == "FAILED"
        assert "Checkout main failed" in (res_co_fail.result or "")


@pytest.mark.unit
def test_get_default_branch_variations(git_service: GitService) -> None:
    # 1. symbolic-ref returns origin/develop
    with patch.object(git_service, "_run_git") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=0),  # set-head
            MagicMock(returncode=0, stdout="origin/develop\n", stderr=""),  # symbolic-ref
        ]
        assert git_service.get_default_branch(Path("/dummy")) == "develop"

    # 2. symbolic-ref fails, origin/main fails, origin/master succeeds
    with patch.object(git_service, "_run_git") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=1),  # set-head
            MagicMock(returncode=1, stdout="", stderr="error"),  # symbolic-ref
            MagicMock(returncode=1),  # rev-parse origin/main
            MagicMock(returncode=0),  # rev-parse origin/master
        ]
        assert git_service.get_default_branch(Path("/dummy")) == "master"

    # 3. all fail -> returns None
    with patch.object(git_service, "_run_git") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=1),
            MagicMock(returncode=1),
            MagicMock(returncode=1),
            MagicMock(returncode=1),
        ]
        assert git_service.get_default_branch(Path("/dummy")) is None


@pytest.mark.unit
def test_sync_dirty_auto_stash_failure_and_up_to_date(git_service: GitService, tmp_path: Path) -> None:
    repo = Repository(name="test-repo", url="https://example.com/repo.git", ssh_url="git@example.com:repo.git")
    repo_dir = tmp_path / "test-repo"
    repo_dir.mkdir()
    repo.local_path = repo_dir
    git_service.workspace_path = tmp_path

    # 1. status_mid is UP_TO_DATE -> returns NO_CHANGE
    with (
        patch.object(
            git_service,
            "get_local_status",
            side_effect=[
                ("BEHIND", "main", 0, 1, None),
                ("UP_TO_DATE", "main", 0, 0, None),
                ("UP_TO_DATE", "main", 0, 0, None),
            ],
        ),
        patch.object(git_service, "get_dirty_files", return_value=[]),
        patch.object(git_service, "_run_git", return_value=MagicMock(returncode=0, stdout="", stderr="")),
    ):
        res = git_service.sync(repo, "myorg")
        assert res.performed_action == "NO_CHANGE"
        assert res.after_status == "UP_TO_DATE"

    # 2. status_mid is DIRTY and auto-stash fails (returncode != 0)
    with (
        patch.object(
            git_service,
            "get_local_status",
            side_effect=[
                ("BEHIND", "main", 0, 1, None),
                ("BEHIND", "main", 0, 1, None),
                ("DIRTY", "main", 0, 1, None),
            ],
        ),
        patch.object(git_service, "get_dirty_files", return_value=[(" M", "dirty.py")]),
        patch.object(
            git_service,
            "_run_git",
            side_effect=[
                MagicMock(returncode=0),  # fetch
                MagicMock(returncode=1, stdout="", stderr="stash failed: cannot create stash"),  # stash push
            ],
        ),
    ):
        res_stash_fail = git_service.sync(repo, "myorg", preserve_local_changes=True)
        assert res_stash_fail.performed_action == "FAILED"
        assert res_stash_fail.after_status == "DIRTY"
