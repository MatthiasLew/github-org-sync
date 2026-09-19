from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from github_org_sync.models.repository import Repository
from github_org_sync.services.git_service import GitService


@pytest.mark.unit
def test_atomic_clone_dry_run(tmp_path: Path) -> None:
    service = GitService()
    repo = Repository("api-repo", "https://github.com/myorg/api-repo.git", "git@github.com:myorg/api-repo.git")
    dest = tmp_path / "api-repo"

    res = service.clone(repo, dest, use_ssh=False, dry_run=True)
    assert res.performed_action == "NO_CHANGE"
    assert not dest.exists()


@pytest.mark.unit
def test_atomic_clone_success(tmp_path: Path) -> None:
    service = GitService()
    repo = Repository("api-repo", "https://github.com/myorg/api-repo.git", "git@github.com:myorg/api-repo.git")
    dest = tmp_path / "api-repo"

    def mock_run_process(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        # Emulate git clone by creating the directory structure in target clone dir
        target_dir = Path(args[3])
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / ".git").mkdir()
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="Cloning into...", stderr="")

    with (
        patch("github_org_sync.services.git_service.run_process", side_effect=mock_run_process),
        patch.object(service, "is_git_repository", return_value=True),
    ):
        res = service.clone(repo, dest, use_ssh=False, dry_run=False)

    assert res.performed_action == "CLONED"
    assert res.after_status == "UP_TO_DATE"
    assert dest.exists()
    assert (dest / ".git").exists()
    # Temp base directory should be cleaned up
    assert not (tmp_path / ".github-org-sync-tmp").exists() or not any((tmp_path / ".github-org-sync-tmp").iterdir())


@pytest.mark.unit
def test_atomic_clone_failure_cleans_up_and_leaves_no_dest(tmp_path: Path) -> None:
    service = GitService()
    repo = Repository("broken-repo", "https://github.com/myorg/broken-repo.git", "git@github.com:myorg/broken-repo.git")
    dest = tmp_path / "broken-repo"

    def mock_failed_clone(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        # Emulate partial write in temp dir before failing
        target_dir = Path(args[3])
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "partial_file.txt").write_text("corrupt", encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=128, stdout="", stderr="fatal: repository not found")

    with patch("github_org_sync.services.git_service.run_process", side_effect=mock_failed_clone):
        res = service.clone(repo, dest, use_ssh=False, dry_run=False)

    assert res.performed_action == "FAILED"
    # CRITICAL: Destination directory must NOT exist and must NOT look like a cloned repo
    assert not dest.exists()
    # Temp directory must be cleaned up
    temp_dirs = list((tmp_path / ".github-org-sync-tmp").glob("broken-repo-*"))
    assert len(temp_dirs) == 0


@pytest.mark.unit
def test_atomic_clone_invalid_git_structure_rejected(tmp_path: Path) -> None:
    service = GitService()
    repo = Repository(
        "corrupt-repo", "https://github.com/myorg/corrupt-repo.git", "git@github.com:myorg/corrupt-repo.git"
    )
    dest = tmp_path / "corrupt-repo"

    def mock_clone_no_git(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        target_dir = Path(args[3])
        target_dir.mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    with (
        patch("github_org_sync.services.git_service.run_process", side_effect=mock_clone_no_git),
        patch.object(service, "is_git_repository", return_value=False),
    ):
        res = service.clone(repo, dest, use_ssh=False, dry_run=False)

    assert res.performed_action == "FAILED"
    assert "validation" in (res.error or "").lower()
    assert not dest.exists()
