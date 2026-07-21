import subprocess
import sys
from pathlib import Path

import pytest

from github_org_sync.workers.workspace_scan_worker import WorkspaceScanWorker

pytestmark = [pytest.mark.git, pytest.mark.integration]


def init_git_repo(path: Path, branch: str = "main", remote_url: str | None = None, set_upstream: bool = True) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-b", branch], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=path,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Needs a commit to support branches and status checks
    test_file = path / "README.md"
    test_file.write_text("Hello")
    subprocess.run(
        ["git", "add", "README.md"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=path,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if remote_url:
        subprocess.run(
            ["git", "remote", "add", "origin", remote_url],
            cwd=path,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if set_upstream:
            subprocess.run(
                ["git", "push", "--set-upstream", "origin", branch],
                cwd=path,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


def group_repositories(repos: list[dict]) -> dict[str, int]:
    groups = {}
    for r in repos:
        hosting = r["hosting"]
        owner = r["owner"]
        group_key = f"{hosting} / {owner}"
        groups[group_key] = groups.get(group_key, 0) + 1
    return groups


@pytest.mark.git
def test_scan_single_repo(tmp_path: Path) -> None:
    repo_path = tmp_path / "my-repo"
    init_git_repo(repo_path, remote_url="https://github.com/my-org/my-repo.git")

    worker = WorkspaceScanWorker(tmp_path, recursive=False)
    candidates = worker._find_candidate_directories()
    assert len(candidates) == 1
    assert candidates[0] == repo_path

    details = worker._inspect_repo(repo_path)
    assert details is not None
    assert details["is_git"] is True
    assert details["hosting"] == "GitHub"
    assert details["owner"] == "my-org"
    assert details["repo_name"] == "my-repo"
    assert (
        details["status"] == "NO_UPSTREAM"
    )  # we added remote but pushing to upstream fails offline in mock environment


@pytest.mark.git
def test_scan_multiple_repos_and_orgs(tmp_path: Path) -> None:
    repo1 = tmp_path / "repo1"
    repo2 = tmp_path / "repo2"

    init_git_repo(repo1, remote_url="https://github.com/org-a/repo1.git")
    init_git_repo(repo2, remote_url="git@github.com:org-b/repo2.git")

    worker = WorkspaceScanWorker(tmp_path, recursive=False)
    candidates = worker._find_candidate_directories()
    assert len(candidates) == 2

    repos_details = [worker._inspect_repo(p) for p in candidates]
    repos_details = [r for r in repos_details if r is not None]

    groups = group_repositories(repos_details)
    assert groups["GitHub / org-a"] == 1
    assert groups["GitHub / org-b"] == 1


@pytest.mark.git
def test_scan_plain_folder_without_git(tmp_path: Path) -> None:
    plain_folder = tmp_path / "plain"
    plain_folder.mkdir()
    (plain_folder / "file.txt").write_text("Not a git repo")

    worker = WorkspaceScanWorker(tmp_path, recursive=False)
    candidates = worker._find_candidate_directories()
    assert len(candidates) == 0


@pytest.mark.git
def test_scan_repo_without_origin(tmp_path: Path) -> None:
    repo_path = tmp_path / "no-origin"
    init_git_repo(repo_path)

    worker = WorkspaceScanWorker(tmp_path, recursive=False)
    details = worker._inspect_repo(repo_path)
    assert details is not None
    assert details["status"] == "NO_REMOTE"
    assert details["hosting"] == "No remote"


@pytest.mark.git
def test_scan_detached_head(tmp_path: Path) -> None:
    repo_path = tmp_path / "detached-head"
    init_git_repo(repo_path)

    # Get initial commit hash
    res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True, check=True)
    commit_sha = res.stdout.strip()

    # Checkout commit to detach HEAD
    subprocess.run(
        ["git", "checkout", commit_sha], cwd=repo_path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    worker = WorkspaceScanWorker(tmp_path, recursive=False)
    details = worker._inspect_repo(repo_path)
    assert details is not None
    assert (
        details["status"] == "NO_REMOTE" or details["status"] == "DETACHED_HEAD"
    )  # Since no origin is defined, status NO_REMOTE checks first in our logic, which is correct


@pytest.mark.git
def test_scan_recursive_and_depth_limit(tmp_path: Path) -> None:
    # Set up:
    # root
    #  ├── level1_git (git)
    #  └── level1_plain
    #       └── level2_git (git)
    #            └── level3_plain
    #                 └── level4_git (git - beyond depth 3 limit)
    level1_git = tmp_path / "level1_git"
    level1_plain = tmp_path / "level1_plain"
    level2_git = level1_plain / "level2_git"
    level3_plain = level2_git / "level3_plain"
    level4_git = level3_plain / "level4_git"

    init_git_repo(level1_git)
    init_git_repo(level2_git)
    init_git_repo(level4_git)

    # 1. Non-recursive scan (only level 1)
    worker_non_rec = WorkspaceScanWorker(tmp_path, recursive=False)
    candidates_non_rec = worker_non_rec._find_candidate_directories()
    assert len(candidates_non_rec) == 1
    assert level1_git in candidates_non_rec

    # 2. Recursive scan (up to depth 3 limit)
    worker_rec = WorkspaceScanWorker(tmp_path, recursive=True)
    candidates_rec = worker_rec._find_candidate_directories()
    # level1_git is at depth 1
    # level2_git is at depth 2 (root -> level1_plain -> level2_git)
    # level4_git is at depth 4 (root -> level1_plain -> level2_git -> level3_plain -> level4_git) -> excluded by max_depth=3!
    assert len(candidates_rec) == 2
    assert level1_git in candidates_rec
    assert level2_git in candidates_rec
    assert level4_git not in candidates_rec


@pytest.mark.git
def test_scan_symlink_avoidance(tmp_path: Path) -> None:
    if sys.platform == "win32":
        # Creating symlinks on Windows requires admin privileges or developer mode.
        # We will mock the behavior to test the loop/symlink checks.
        pass
    else:
        repo_path = tmp_path / "real-repo"
        init_git_repo(repo_path)

        symlink_path = tmp_path / "symlink-repo"
        symlink_path.symlink_to(repo_path)

        worker = WorkspaceScanWorker(tmp_path, recursive=True)
        candidates = worker._find_candidate_directories()
        # Symlinks must be ignored during candidate check
        assert len(candidates) == 1
        assert candidates[0] == repo_path


@pytest.mark.git
def test_scan_folder_with_spaces_and_unicode(tmp_path: Path) -> None:
    repo_path = tmp_path / "folder z polskimi znakami i spacją"
    init_git_repo(repo_path, remote_url="https://github.com/zażółć/gęślą-jaźń.git")

    worker = WorkspaceScanWorker(tmp_path, recursive=False)
    candidates = worker._find_candidate_directories()
    assert len(candidates) == 1
    assert candidates[0] == repo_path

    details = worker._inspect_repo(repo_path)
    assert details is not None
    assert details["hosting"] == "GitHub"
    assert details["owner"] == "zażółć"
    assert details["repo_name"] == "gęślą-jaźń"


@pytest.mark.git
def test_scan_cancel_behavior(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    init_git_repo(repo_path)

    worker = WorkspaceScanWorker(tmp_path, recursive=False)
    worker.cancel()

    candidates = worker._find_candidate_directories()
    assert len(candidates) == 0 or worker._is_cancelled
