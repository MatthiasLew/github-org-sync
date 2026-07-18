import os
import subprocess
import sys
from pathlib import Path

import pytest

from github_org_sync.models.repository import Repository
from github_org_sync.services.git_service import GitService
from github_org_sync.ui.main_window import MainWindow


def run_git(cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=True)


def setup_repo(path: Path, bare: bool = False) -> None:
    path.mkdir(parents=True, exist_ok=True)
    run_git(path, ["init", "-b", "main"] + (["--bare"] if bare else []))
    if not bare:
        run_git(path, ["config", "user.name", "Audit Tester"])
        run_git(path, ["config", "user.email", "audit@test.com"])


@pytest.fixture(autouse=True)
def mock_is_wrong_remote(monkeypatch):
    original = GitService.is_wrong_remote

    def patched(self, remote_url, org_name):
        if not remote_url:
            return True
        if "testorg" in remote_url or "temp" in remote_url.lower() or "/" in remote_url or "\\" in remote_url:
            return False
        return original(self, remote_url, org_name)

    monkeypatch.setattr(GitService, "is_wrong_remote", patched)


# Scenarios A & B
def test_git_scenario_a_and_b(tmp_path):
    git_service = GitService()
    org_name = "testorg"

    remote_path = tmp_path / "repo_a_remote"
    setup_repo(remote_path, bare=True)

    helper = tmp_path / "helper"
    setup_repo(helper)
    run_git(helper, ["remote", "add", "origin", str(remote_path)])
    (helper / "file.txt").write_text("Hello A")
    run_git(helper, ["add", "file.txt"])
    run_git(helper, ["commit", "-m", "initial"])
    run_git(helper, ["push", "-u", "origin", "main"])

    dest_path = tmp_path / "workspace" / "repo_a"
    repo_model = Repository("repo_a", str(remote_path), f"git@github.com:{org_name}/repo_a.git")

    # Check MISSING
    status, _, _, _, _ = git_service.get_local_status(dest_path, org_name)
    assert status == "MISSING"

    # Clone
    res = git_service.clone(repo_model, dest_path, use_ssh=False, dry_run=False)
    assert res.status == "CLONED"
    assert (dest_path / "file.txt").read_text() == "Hello A"

    # Set user details on cloned repo
    run_git(dest_path, ["config", "user.name", "Audit Tester"])
    run_git(dest_path, ["config", "user.email", "audit@test.com"])

    # Check UP_TO_DATE
    status, branch, ahead, behind, _ = git_service.get_local_status(dest_path, org_name)
    assert status == "UP_TO_DATE"
    assert branch == "main"
    assert ahead == 0
    assert behind == 0


# Scenario C
def test_git_scenario_c_behind(tmp_path):
    git_service = GitService()
    org_name = "testorg"

    remote_path = tmp_path / "repo_c_remote"
    setup_repo(remote_path, bare=True)

    helper = tmp_path / "helper"
    setup_repo(helper)
    run_git(helper, ["remote", "add", "origin", str(remote_path)])
    (helper / "file.txt").write_text("Hello C")
    run_git(helper, ["add", "file.txt"])
    run_git(helper, ["commit", "-m", "initial"])
    run_git(helper, ["push", "-u", "origin", "main"])

    dest_path = tmp_path / "workspace" / "repo_c"
    repo_model = Repository("repo_c", str(remote_path), f"git@github.com:{org_name}/repo_c.git")

    # Clone
    git_service.clone(repo_model, dest_path, use_ssh=False, dry_run=False)
    run_git(dest_path, ["config", "user.name", "Audit Tester"])
    run_git(dest_path, ["config", "user.email", "audit@test.com"])

    # Push second commit to remote
    (helper / "file.txt").write_text("Hello C modified")
    run_git(helper, ["add", "file.txt"])
    run_git(helper, ["commit", "-m", "second commit"])
    run_git(helper, ["push"])

    # Fetch
    run_git(dest_path, ["fetch", "--prune"])

    # Status behind
    status, _, _, behind, _ = git_service.get_local_status(dest_path, org_name)
    assert status == "BEHIND"
    assert behind == 1

    # Sync
    repo_model.local_path = dest_path
    res = git_service.sync(repo_model, org_name)
    assert res.status == "UPDATED"
    assert (dest_path / "file.txt").read_text() == "Hello C modified"


# Scenario D
def test_git_scenario_d_ahead(tmp_path):
    git_service = GitService()
    org_name = "testorg"

    remote_path = tmp_path / "repo_d_remote"
    setup_repo(remote_path, bare=True)

    helper = tmp_path / "helper"
    setup_repo(helper)
    run_git(helper, ["remote", "add", "origin", str(remote_path)])
    (helper / "file.txt").write_text("Hello D")
    run_git(helper, ["add", "file.txt"])
    run_git(helper, ["commit", "-m", "initial"])
    run_git(helper, ["push", "-u", "origin", "main"])

    dest_path = tmp_path / "workspace" / "repo_d"
    repo_model = Repository("repo_d", str(remote_path), f"git@github.com:{org_name}/repo_d.git")

    git_service.clone(repo_model, dest_path, use_ssh=False, dry_run=False)
    run_git(dest_path, ["config", "user.name", "Audit Tester"])
    run_git(dest_path, ["config", "user.email", "audit@test.com"])

    # Add ahead commit locally
    (dest_path / "file.txt").write_text("Hello D ahead")
    run_git(dest_path, ["add", "file.txt"])
    run_git(dest_path, ["commit", "-m", "local ahead"])

    status, _, ahead, behind, _ = git_service.get_local_status(dest_path, org_name)
    assert status == "AHEAD"
    assert ahead == 1

    # Sync should keep local changes and report AHEAD without errors
    repo_model.local_path = dest_path
    res = git_service.sync(repo_model, org_name)
    assert res.status == "AHEAD"
    assert (dest_path / "file.txt").read_text() == "Hello D ahead"


# Scenario E
def test_git_scenario_e_diverged(tmp_path):
    git_service = GitService()
    org_name = "testorg"

    remote_path = tmp_path / "repo_e_remote"
    setup_repo(remote_path, bare=True)

    helper = tmp_path / "helper"
    setup_repo(helper)
    run_git(helper, ["remote", "add", "origin", str(remote_path)])
    (helper / "file.txt").write_text("Hello E")
    run_git(helper, ["add", "file.txt"])
    run_git(helper, ["commit", "-m", "initial"])
    run_git(helper, ["push", "-u", "origin", "main"])

    dest_path = tmp_path / "workspace" / "repo_e"
    repo_model = Repository("repo_e", str(remote_path), f"git@github.com:{org_name}/repo_e.git")

    git_service.clone(repo_model, dest_path, use_ssh=False, dry_run=False)
    run_git(dest_path, ["config", "user.name", "Audit Tester"])
    run_git(dest_path, ["config", "user.email", "audit@test.com"])

    # Local commit
    (dest_path / "file.txt").write_text("Local E edit")
    run_git(dest_path, ["add", "file.txt"])
    run_git(dest_path, ["commit", "-m", "local diverged"])

    # Remote commit
    (helper / "file.txt").write_text("Remote E edit")
    run_git(helper, ["add", "file.txt"])
    run_git(helper, ["commit", "-m", "remote diverged"])
    run_git(helper, ["push"])

    # Fetch
    run_git(dest_path, ["fetch", "--prune"])

    status, _, ahead, behind, _ = git_service.get_local_status(dest_path, org_name)
    assert status == "DIVERGED"
    assert ahead == 1
    assert behind == 1

    # Sync diverged
    repo_model.local_path = dest_path
    res = git_service.sync(repo_model, org_name)
    assert res.status == "DIVERGED"


# Scenario F
def test_git_scenario_f_dirty_autostash(tmp_path):
    git_service = GitService()
    org_name = "testorg"

    remote_path = tmp_path / "repo_f_remote"
    setup_repo(remote_path, bare=True)

    helper = tmp_path / "helper"
    setup_repo(helper)
    run_git(helper, ["remote", "add", "origin", str(remote_path)])
    (helper / "file.txt").write_text("Hello F")
    run_git(helper, ["add", "file.txt"])
    run_git(helper, ["commit", "-m", "initial"])
    run_git(helper, ["push", "-u", "origin", "main"])

    dest_path = tmp_path / "workspace" / "repo_f"
    repo_model = Repository("repo_f", str(remote_path), f"git@github.com:{org_name}/repo_f.git")

    git_service.clone(repo_model, dest_path, use_ssh=False, dry_run=False)
    run_git(dest_path, ["config", "user.name", "Audit Tester"])
    run_git(dest_path, ["config", "user.email", "audit@test.com"])

    # Tracked file edit (dirty)
    (dest_path / "file.txt").write_text("Local F dirty edit")
    # Untracked file
    (dest_path / "untracked.txt").write_text("Untracked content")

    # Remote edit
    (helper / "new_file.txt").write_text("Hello F remote")
    run_git(helper, ["add", "new_file.txt"])
    run_git(helper, ["commit", "-m", "remote update"])
    run_git(helper, ["push"])

    # Sync with autostash enabled
    repo_model.local_path = dest_path
    res = git_service.sync(repo_model, org_name, preserve_local_changes=True)
    assert res.status == "UPDATED"

    # Remote file pulled successfully
    assert (dest_path / "new_file.txt").read_text() == "Hello F remote"
    # Local dirty modification returned
    assert (dest_path / "file.txt").read_text() == "Local F dirty edit"
    # Untracked file stays intact
    assert (dest_path / "untracked.txt").read_text() == "Untracked content"


# Scenario G
def test_git_scenario_g_stash_conflict(tmp_path):
    git_service = GitService()
    org_name = "testorg"

    remote_path = tmp_path / "repo_g_remote"
    setup_repo(remote_path, bare=True)

    helper = tmp_path / "helper"
    setup_repo(helper)
    run_git(helper, ["remote", "add", "origin", str(remote_path)])
    (helper / "file.txt").write_text("Hello G line 1")
    run_git(helper, ["add", "file.txt"])
    run_git(helper, ["commit", "-m", "initial"])
    run_git(helper, ["push", "-u", "origin", "main"])

    dest_path = tmp_path / "workspace" / "repo_g"
    repo_model = Repository("repo_g", str(remote_path), f"git@github.com:{org_name}/repo_g.git")

    git_service.clone(repo_model, dest_path, use_ssh=False, dry_run=False)
    run_git(dest_path, ["config", "user.name", "Audit Tester"])
    run_git(dest_path, ["config", "user.email", "audit@test.com"])

    # Modify line locally
    (dest_path / "file.txt").write_text("Local edit G conflict")

    # Modify same line remotely
    (helper / "file.txt").write_text("Remote edit G conflict")
    run_git(helper, ["add", "file.txt"])
    run_git(helper, ["commit", "-m", "remote conflicting edit"])
    run_git(helper, ["push"])

    # Sync should fail with CONFLICT
    repo_model.local_path = dest_path
    res = git_service.sync(repo_model, org_name, preserve_local_changes=True)
    assert res.status == "CONFLICT"
    assert res.message is not None
    assert "conflict" in res.message.lower()


# Scenario H
def test_git_scenario_h_wrong_remote(tmp_path, monkeypatch):
    git_service = GitService()
    org_name = "testorg"

    dest_path = tmp_path / "workspace" / "repo_h"
    setup_repo(dest_path)
    run_git(dest_path, ["remote", "add", "origin", "https://github.com/anotherowner/repo_h.git"])

    # Re-enable original check (remove monkeypatch for this specific test)
    monkeypatch.undo()

    status, _, _, _, _ = git_service.get_local_status(dest_path, org_name)
    assert status == "WRONG_REMOTE"


# Scenario I
def test_git_scenario_i_no_upstream(tmp_path):
    git_service = GitService()
    org_name = "testorg"

    dest_path = tmp_path / "workspace" / "repo_i"
    setup_repo(dest_path)
    run_git(dest_path, ["remote", "add", "origin", "https://github.com/testorg/repo_i.git"])

    # Create commit first
    (dest_path / "file.txt").write_text("Hello I")
    run_git(dest_path, ["add", "file.txt"])
    run_git(dest_path, ["commit", "-m", "initial"])

    # Create local branch with no upstream
    run_git(dest_path, ["checkout", "-b", "local-branch-only"])

    status, branch, _, _, _ = git_service.get_local_status(dest_path, org_name)
    assert status == "NO_UPSTREAM"
    assert branch == "local-branch-only"


# Scenario J
def test_git_scenario_j_detached_head(tmp_path):
    git_service = GitService()
    org_name = "testorg"

    dest_path = tmp_path / "workspace" / "repo_j"
    setup_repo(dest_path)
    run_git(dest_path, ["remote", "add", "origin", "https://github.com/testorg/repo_j.git"])

    # Create commit
    (dest_path / "file.txt").write_text("Hello J")
    run_git(dest_path, ["add", "file.txt"])
    run_git(dest_path, ["commit", "-m", "initial"])

    cp_hash = run_git(dest_path, ["rev-parse", "HEAD"])
    commit_hash = cp_hash.stdout.strip()

    # Checkout commit directly
    run_git(dest_path, ["checkout", commit_hash])

    status, branch, _, _, _ = git_service.get_local_status(dest_path, org_name)
    assert status == "DETACHED_HEAD"
    assert branch == "HEAD"


# Scenario K
def test_git_scenario_k_not_a_repository(tmp_path):
    git_service = GitService()
    org_name = "testorg"

    dest_path = tmp_path / "workspace" / "repo_k"
    dest_path.mkdir(parents=True, exist_ok=True)
    (dest_path / "file.txt").write_text("Hello K")

    status, _, _, _, _ = git_service.get_local_status(dest_path, org_name)
    assert status == "NOT_A_REPOSITORY"


# Scenario L
def test_git_scenario_l_unicode_and_spaces(tmp_path):
    git_service = GitService()
    org_name = "testorg"

    remote_path = tmp_path / "repo_l_remote"
    setup_repo(remote_path, bare=True)

    helper = tmp_path / "helper"
    setup_repo(helper)
    run_git(helper, ["remote", "add", "origin", str(remote_path)])
    (helper / "file.txt").write_text("Hello L")
    run_git(helper, ["add", "file.txt"])
    run_git(helper, ["commit", "-m", "initial"])
    run_git(helper, ["push", "-u", "origin", "main"])

    unicode_dest = tmp_path / "spaced path" / "Zażółć gęślą" / "repo_l"
    repo_model = Repository("repo_l", str(remote_path), f"git@github.com:{org_name}/repo_l.git")

    res = git_service.clone(repo_model, unicode_dest, use_ssh=False, dry_run=False)
    assert res.status == "CLONED"
    assert (unicode_dest / "file.txt").exists()
    assert (unicode_dest / "file.txt").read_text() == "Hello L"


# Step 9 Tests: Platform startfile coverage
def test_startfile_platform_handling(monkeypatch, qtbot):
    last_report_calls = []
    workspace_calls = []

    def mock_run(args, **kwargs):
        last_report_calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", mock_run)

    import shutil

    monkeypatch.setattr(shutil, "which", lambda cmd, mode=os.F_OK: "/usr/bin/gh")

    # 1. Test Windows branch
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(os, "startfile", lambda path: workspace_calls.append(path), raising=False)

    app = MainWindow()
    app.last_md_report = Path("test_report.md")
    app.last_md_report.touch(exist_ok=True)

    app.open_last_report()
    assert workspace_calls == [app.last_md_report]

    # 2. Test macOS branch
    monkeypatch.setattr(sys, "platform", "darwin")
    if hasattr(os, "startfile"):
        monkeypatch.delattr(os, "startfile")

    last_report_calls.clear()
    app.open_last_report()
    assert last_report_calls == [["open", "test_report.md"]]

    # Clean up test file
    if app.last_md_report.exists():
        app.last_md_report.unlink()
