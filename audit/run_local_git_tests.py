import shutil
import subprocess
from pathlib import Path

from github_org_sync.models.repository import Repository
from github_org_sync.services.git_service import GitService


def run_git(cwd: Path | None, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)


def setup_repo(path: Path, bare: bool = False) -> None:
    path.mkdir(parents=True, exist_ok=True)
    run_git(path, ["init", "-b", "main"] + (["--bare"] if bare else []))
    if not bare:
        run_git(path, ["config", "user.name", "Audit Tester"])
        run_git(path, ["config", "user.email", "audit@test.com"])


def main() -> None:
    # Patch is_wrong_remote to bypass check for temp folders
    original_is_wrong_remote = GitService.is_wrong_remote

    def patched_is_wrong_remote(self, remote_url: str, org_name: str) -> bool:
        if "github-org-sync-audit" in remote_url or "Zażółć gęślą" in remote_url:
            return False
        return original_is_wrong_remote(self, remote_url, org_name)

    GitService.is_wrong_remote = patched_is_wrong_remote

    temp_dir = Path("C:/Users/Praca/AppData/Local/Temp/github-org-sync-audit")
    if temp_dir.exists():
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            # Try running command if blocked
            subprocess.run(["rmdir", "/s", "/q", str(temp_dir)], shell=True)

    temp_dir.mkdir(parents=True, exist_ok=True)

    git_service = GitService()
    org_name = "testorg"

    print("=== Running Local Git Integration Audits ===")

    # ----------------------------------------------------
    # Scenario A: Missing & Clone
    # ----------------------------------------------------
    print("\n[Scenario A] Missing & Clone...")
    remote_a = temp_dir / "repo_a_remote"
    setup_repo(remote_a, bare=True)

    # Create initial commit on remote_a
    helper_a = temp_dir / "helper_a"
    setup_repo(helper_a)
    run_git(helper_a, ["remote", "add", "origin", str(remote_a)])
    (helper_a / "file.txt").write_text("Hello A")
    run_git(helper_a, ["add", "file.txt"])
    run_git(helper_a, ["commit", "-m", "initial"])
    run_git(helper_a, ["push", "-u", "origin", "main"])

    dest_a = temp_dir / "workspace" / "repo_a"
    repo_a = Repository("repo_a", str(remote_a), f"git@github.com:{org_name}/repo_a.git")

    status, _, _, _, _ = git_service.get_local_status(dest_a, org_name)
    assert status == "MISSING", f"Expected MISSING, got {status}"

    res = git_service.clone(repo_a, dest_a, use_ssh=False, dry_run=False)
    assert res.status == "CLONED", f"Expected CLONED, got {res.status}"
    assert (dest_a / "file.txt").read_text() == "Hello A"

    # Configure clone
    run_git(dest_a, ["config", "user.name", "Audit Tester"])
    run_git(dest_a, ["config", "user.email", "audit@test.com"])

    # ----------------------------------------------------
    # Scenario B: Up to Date
    # ----------------------------------------------------
    print("\n[Scenario B] Up to Date...")
    status, branch, ahead, behind, msg = git_service.get_local_status(dest_a, org_name)
    print(f"Status: {status}, branch={branch}, ahead={ahead}, behind={behind}")
    assert status == "UP_TO_DATE"
    assert branch == "main"
    assert ahead == 0
    assert behind == 0

    # ----------------------------------------------------
    # Scenario C: Behind & Sync
    # ----------------------------------------------------
    print("\n[Scenario C] Behind & Sync...")
    # Add a commit to remote using helper
    (helper_a / "file.txt").write_text("Hello A modified")
    run_git(helper_a, ["add", "file.txt"])
    run_git(helper_a, ["commit", "-m", "second commit"])
    run_git(helper_a, ["push"])

    # Check status (should be BEHIND after fetch, or BEHIND if fetch not run? get_local_status doesn't run fetch)
    # So we should run sync or fetch to verify behind. Let's run fetch prune first.
    run_git(dest_a, ["fetch", "--prune"])
    status, _, _, behind, _ = git_service.get_local_status(dest_a, org_name)
    assert status == "BEHIND", f"Expected BEHIND, got {status}"
    assert behind == 1

    # Perform sync
    repo_a.local_path = dest_a
    res = git_service.sync(repo_a, org_name, preserve_local_changes=True)
    assert res.status == "UPDATED", f"Expected UPDATED, got {res.status}"
    assert (dest_a / "file.txt").read_text() == "Hello A modified"

    # ----------------------------------------------------
    # Scenario D: Ahead
    # ----------------------------------------------------
    print("\n[Scenario D] Ahead...")
    (dest_a / "file.txt").write_text("Hello A local change commit")
    run_git(dest_a, ["add", "file.txt"])
    run_git(dest_a, ["commit", "-m", "local commit"])

    status, _, ahead, behind, _ = git_service.get_local_status(dest_a, org_name)
    assert status == "AHEAD", f"Expected AHEAD, got {status}"
    assert ahead == 1

    # Sync should skip updating and not destroy
    res = git_service.sync(repo_a, org_name)
    assert res.status == "AHEAD"
    assert (dest_a / "file.txt").read_text() == "Hello A local change commit"

    # ----------------------------------------------------
    # Scenario E: Diverged
    # ----------------------------------------------------
    print("\n[Scenario E] Diverged...")
    # Reset local to be aligned first, then create diverged commit
    run_git(dest_a, ["reset", "--hard", "origin/main"])

    # Commit local
    (dest_a / "file.txt").write_text("Local edit")
    run_git(dest_a, ["add", "file.txt"])
    run_git(dest_a, ["commit", "-m", "diverged local"])

    # Commit remote using helper
    run_git(helper_a, ["reset", "--hard", "origin/main"])
    (helper_a / "file.txt").write_text("Remote edit")
    run_git(helper_a, ["add", "file.txt"])
    run_git(helper_a, ["commit", "-m", "diverged remote"])
    run_git(helper_a, ["push"])

    run_git(dest_a, ["fetch", "--prune"])
    status, _, ahead, behind, _ = git_service.get_local_status(dest_a, org_name)
    assert status == "DIVERGED", f"Expected DIVERGED, got {status}"
    assert ahead == 1
    assert behind == 1

    # Sync should skip
    res = git_service.sync(repo_a, org_name)
    assert res.status == "DIVERGED"
    # Reset local back to origin
    run_git(dest_a, ["reset", "--hard", "origin/main"])

    # ----------------------------------------------------
    # Scenario F: Dirty + Autostash
    # ----------------------------------------------------
    print("\n[Scenario F] Dirty + Autostash...")
    # Add a tracked file change
    (dest_a / "file.txt").write_text("Tracked local edit")
    # Add an untracked file
    (dest_a / "untracked.txt").write_text("Untracked content")

    # Commit remote using helper
    run_git(helper_a, ["reset", "--hard", "origin/main"])
    (helper_a / "newfile.txt").write_text("New remote file")
    run_git(helper_a, ["add", "newfile.txt"])
    run_git(helper_a, ["commit", "-m", "remote edit"])
    run_git(helper_a, ["push"])

    # Sync
    res = git_service.sync(repo_a, org_name, preserve_local_changes=True)
    assert res.status == "UPDATED", f"Expected UPDATED, got {res.status}"

    # Check that remote file exists
    assert (dest_a / "newfile.txt").exists()
    # Check that tracked local edit returned
    assert (dest_a / "file.txt").read_text() == "Tracked local edit"
    # Check that untracked file remains
    assert (dest_a / "untracked.txt").read_text() == "Untracked content"

    # Clear untracked and reset
    (dest_a / "untracked.txt").unlink()
    run_git(dest_a, ["reset", "--hard", "origin/main"])

    # ----------------------------------------------------
    # Scenario G: Conflict on pop
    # ----------------------------------------------------
    print("\n[Scenario G] Conflict on pop...")
    # Setup same line modification
    (dest_a / "file.txt").write_text("Local conflict line")

    run_git(helper_a, ["reset", "--hard", "origin/main"])
    (helper_a / "file.txt").write_text("Remote conflict line")
    run_git(helper_a, ["add", "file.txt"])
    run_git(helper_a, ["commit", "-m", "remote conflict"])
    run_git(helper_a, ["push"])

    # Sync (autostash) should encounter conflict on pop
    res = git_service.sync(repo_a, org_name, preserve_local_changes=True)
    print(f"Sync status on conflict: {res.status}, message: {res.message}")
    assert res.status == "CONFLICT"
    assert "conflict" in res.message.lower()

    # Abort/clean the conflict
    run_git(dest_a, ["merge", "--abort"])
    run_git(dest_a, ["reset", "--hard", "origin/main"])
    # Clean stash
    run_git(dest_a, ["stash", "clear"])

    # ----------------------------------------------------
    # Scenario H: WRONG_REMOTE
    # ----------------------------------------------------
    print("\n[Scenario H] Wrong remote...")
    # Change remote url to something else
    run_git(dest_a, ["remote", "set-url", "origin", "https://github.com/anotherowner/repo_a.git"])

    # Temporarily restore original is_wrong_remote to test it
    GitService.is_wrong_remote = original_is_wrong_remote
    status, _, _, _, msg = git_service.get_local_status(dest_a, org_name)
    print(f"Wrong remote status: {status}, msg={msg}")
    assert status == "WRONG_REMOTE"

    # Re-apply patch
    GitService.is_wrong_remote = patched_is_wrong_remote
    # Restore original URL
    run_git(dest_a, ["remote", "set-url", "origin", str(remote_a)])

    # ----------------------------------------------------
    # Scenario I: NO_UPSTREAM
    # ----------------------------------------------------
    print("\n[Scenario I] No upstream...")
    run_git(dest_a, ["checkout", "-b", "noupstream_branch"])
    status, branch, _, _, msg = git_service.get_local_status(dest_a, org_name)
    print(f"No upstream status: {status}, branch={branch}, msg={msg}")
    assert status == "NO_UPSTREAM"
    assert branch == "noupstream_branch"

    # Checkout main
    run_git(dest_a, ["checkout", "main"])

    # ----------------------------------------------------
    # Scenario J: DETACHED_HEAD
    # ----------------------------------------------------
    print("\n[Scenario J] Detached HEAD...")
    # Get last commit hash
    cp_hash = run_git(dest_a, ["rev-parse", "HEAD"])
    commit_hash = cp_hash.stdout.strip()

    # Checkout commit directly
    run_git(dest_a, ["checkout", commit_hash])
    status, branch, _, _, msg = git_service.get_local_status(dest_a, org_name)
    print(f"Detached HEAD status: {status}, branch={branch}, msg={msg}")
    assert status == "DETACHED_HEAD"
    assert branch == "HEAD"

    # Restore main
    run_git(dest_a, ["checkout", "main"])

    # ----------------------------------------------------
    # Scenario K: NOT_A_REPOSITORY
    # ----------------------------------------------------
    print("\n[Scenario K] Not a repository...")
    not_repo_path = temp_dir / "workspace" / "repo_k"
    not_repo_path.mkdir(parents=True, exist_ok=True)
    (not_repo_path / "dummy.txt").write_text("Not git")

    status, _, _, _, msg = git_service.get_local_status(not_repo_path, org_name)
    print(f"Not a repository status: {status}, msg={msg}")
    assert status == "NOT_A_REPOSITORY"

    # ----------------------------------------------------
    # Scenario L: Path with spaces and Unicode
    # ----------------------------------------------------
    print("\n[Scenario L] Path with spaces and Unicode...")
    space_path = temp_dir / "GitHub Org Sync Test" / "Zażółć gęślą" / "repo_l"
    remote_l = temp_dir / "repo_l_remote"
    setup_repo(remote_l, bare=True)

    # Create initial commit on remote_l
    helper_l = temp_dir / "helper_l"
    setup_repo(helper_l)
    run_git(helper_l, ["remote", "add", "origin", str(remote_l)])
    (helper_l / "file.txt").write_text("Hello Unicode")
    run_git(helper_l, ["add", "file.txt"])
    run_git(helper_l, ["commit", "-m", "initial"])
    run_git(helper_l, ["push", "-u", "origin", "main"])

    repo_l = Repository("repo_l", str(remote_l), f"git@github.com:{org_name}/repo_l.git")

    res = git_service.clone(repo_l, space_path, use_ssh=False, dry_run=False)
    print(f"Clone in unicode path: {res.status}")
    assert res.status == "CLONED"
    assert (space_path / "file.txt").exists()

    # Clean up temp audit directory
    print("\nCleaning up temp directories...")
    import contextlib

    with contextlib.suppress(Exception):
        shutil.rmtree(temp_dir)

    print("\n=== ALL LOCAL GIT AUDITS PASSED SUCCESSFULLY ===")


if __name__ == "__main__":
    main()
