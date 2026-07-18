import re
import shutil
import subprocess
import time
from pathlib import Path

from github_org_sync.models.repository import Repository
from github_org_sync.models.sync_result import SyncResult
from github_org_sync.utils.process import run_process


class GitService:
    def __init__(self) -> None:
        self.git_path = shutil.which("git")

    def _run_git(self, cwd: Path | None, args: list[str]) -> subprocess.CompletedProcess[str]:
        if not self.git_path:
            raise FileNotFoundError("Git is not installed or not in system PATH.")
        return run_process([self.git_path, *args], cwd=cwd)

    def is_git_repository(self, path: Path) -> bool:
        """Checks if the path is a git repository."""
        if not path.is_dir():
            return False
        if (path / ".git").exists():
            return True
        try:
            cp = self._run_git(path, ["rev-parse", "--show-toplevel"])
            if cp.returncode == 0:
                toplevel = Path(cp.stdout.strip()).resolve()
                return toplevel == path.resolve()
            return False
        except Exception:
            return False

    def is_wrong_remote(self, remote_url: str, org_name: str) -> bool:
        """Checks if origin URL belongs to another owner/organization."""
        if not remote_url:
            return True
        # Match github.com/org_name or github.com:org_name or ssh://git@github.com/org_name
        pattern = r"github\.com[:/]" + re.escape(org_name.lower()) + r"(/|$)"
        return not bool(re.search(pattern, remote_url.lower()))

    def get_local_status(self, path: Path, org_name: str) -> tuple[str, str | None, int | None, int | None, str | None]:
        """
        Inspects local path and returns (status, branch, ahead, behind, message/error).
        """
        if not path.exists():
            return "MISSING", None, None, None, None

        if not self.is_git_repository(path):
            return "NOT_A_REPOSITORY", None, None, None, "Folder exists but is not a git repository"

        try:
            # 1. Remote Origin URL
            cp_url = self._run_git(path, ["remote", "get-url", "origin"])
            if cp_url.returncode != 0:
                return "NO_UPSTREAM", None, None, None, "Missing origin remote"
            remote_url = cp_url.stdout.strip()

            if self.is_wrong_remote(remote_url, org_name):
                return "WRONG_REMOTE", None, None, None, f"Remote origin is wrong: {remote_url}"

            # 2. Current branch
            cp_branch = self._run_git(path, ["rev-parse", "--abbrev-ref", "HEAD"])
            branch = cp_branch.stdout.strip() if cp_branch.returncode == 0 else None
            if branch == "HEAD":
                return "DETACHED_HEAD", "HEAD", None, None, "Detached HEAD"

            # 3. Upstream branch
            if branch:
                cp_up = self._run_git(path, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
                if cp_up.returncode != 0:
                    return "NO_UPSTREAM", branch, None, None, "No tracking upstream branch"
                upstream = cp_up.stdout.strip()

                # 4. Ahead / Behind
                cp_ab = self._run_git(path, ["rev-list", "--left-right", "--count", f"HEAD...{upstream}"])
                if cp_ab.returncode == 0:
                    parts = cp_ab.stdout.strip().split()
                    ahead = int(parts[0]) if len(parts) > 0 else 0
                    behind = int(parts[1]) if len(parts) > 1 else 0
                else:
                    ahead, behind = 0, 0
            else:
                ahead, behind = None, None

            # 5. Dirty check
            cp_status = self._run_git(path, ["status", "--porcelain"])
            is_dirty = bool(cp_status.stdout.strip())

            if is_dirty:
                return "DIRTY", branch, ahead, behind, "Local changes present"

            if ahead is not None and behind is not None:
                if ahead > 0 and behind > 0:
                    return "DIVERGED", branch, ahead, behind, "Local and remote have diverged"
                if ahead > 0:
                    return "AHEAD", branch, ahead, behind, "Local commits not pushed"
                if behind > 0:
                    return "BEHIND", branch, ahead, behind, "Remote commits can be pulled"

            return "UP_TO_DATE", branch, ahead, behind, None

        except Exception as e:
            return "FAILED", None, None, None, str(e)

    def clone(self, repo: Repository, dest_path: Path, use_ssh: bool, dry_run: bool) -> SyncResult:
        """Clones a remote repository."""
        start_time = time.time()
        url = repo.ssh_url if use_ssh else repo.url

        if dry_run:
            return SyncResult(
                repo_name=repo.name,
                status="READY_TO_CLONE",
                before_status="MISSING",
                after_status="MISSING",
                duration=0.0,
                operation="clone",
                message=f"[DRY-RUN] Would clone {url} to {dest_path}",
            )

        try:
            # Create destination's parent directories if needed
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            cp = self._run_git(None, ["clone", url, str(dest_path)])
            duration = time.time() - start_time

            if cp.returncode != 0:
                err_msg = (cp.stderr or cp.stdout).strip()
                return SyncResult(
                    repo_name=repo.name,
                    status="FAILED",
                    before_status="MISSING",
                    after_status="MISSING",
                    duration=duration,
                    operation="clone",
                    error=err_msg,
                    message=f"Clone failed: {err_msg}",
                )

            return SyncResult(
                repo_name=repo.name,
                status="CLONED",
                before_status="MISSING",
                after_status="UP_TO_DATE",
                duration=duration,
                operation="clone",
                message="Successfully cloned repository",
            )
        except Exception as e:
            return SyncResult(
                repo_name=repo.name,
                status="FAILED",
                before_status="MISSING",
                after_status="MISSING",
                duration=time.time() - start_time,
                operation="clone",
                error=str(e),
                message=f"Exception during clone: {e}",
            )

    def get_default_branch(self, path: Path) -> str | None:
        """Attempts to find default remote branch name."""
        # Try asking remote
        self._run_git(path, ["remote", "set-head", "origin", "-a"])
        cp = self._run_git(path, ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"])
        if cp.returncode == 0 and "/" in cp.stdout:
            return cp.stdout.strip().split("/", 1)[1]

        # Fallback to local branch checking
        for candidate in ("main", "master"):
            cp = self._run_git(path, ["rev-parse", "--verify", f"origin/{candidate}"])
            if cp.returncode == 0:
                return candidate
        return None

    def sync(
        self,
        repo: Repository,
        org_name: str,
        preserve_local_changes: bool = True,
        fetch_only: bool = False,
        checkout_default: bool = False,
        dry_run: bool = False,
    ) -> SyncResult:
        """
        Updates an existing local repository.
        """
        start_time = time.time()
        path = repo.local_path
        if not path or not path.exists():
            return SyncResult(
                repo_name=repo.name,
                status="FAILED",
                before_status="MISSING",
                after_status="MISSING",
                duration=0.0,
                operation="sync",
                error="Local path does not exist",
                message="Local path does not exist",
            )

        # 1. Assess initial status
        status, init_branch, ahead, behind, init_msg = self.get_local_status(path, org_name)
        if status in ("NOT_A_REPOSITORY", "WRONG_REMOTE", "FAILED"):
            return SyncResult(
                repo_name=repo.name,
                status=status,
                before_status=status,
                after_status=status,
                duration=0.0,
                operation="sync",
                error=init_msg,
                message=init_msg,
            )

        if dry_run:
            duration = time.time() - start_time
            return SyncResult(
                repo_name=repo.name,
                status=status,
                before_status=status,
                after_status=status,
                duration=duration,
                operation="sync",
                message=f"[DRY-RUN] Would fetch and update (fetch_only={fetch_only})",
            )

        # 2. Fetch changes
        cp_fetch = self._run_git(path, ["fetch", "--prune"])
        if cp_fetch.returncode != 0:
            duration = time.time() - start_time
            err_msg = (cp_fetch.stderr or cp_fetch.stdout).strip()
            return SyncResult(
                repo_name=repo.name,
                status="FAILED",
                before_status=status,
                after_status=status,
                duration=duration,
                operation="sync",
                error=err_msg,
                message=f"Fetch failed: {err_msg}",
            )

        if fetch_only:
            # Recheck status after fetch
            post_status, post_branch, post_ahead, post_behind, post_msg = self.get_local_status(path, org_name)
            duration = time.time() - start_time
            return SyncResult(
                repo_name=repo.name,
                status="FETCHED",
                before_status=status,
                after_status=post_status,
                duration=duration,
                operation="sync",
                message=f"Fetched remote changes. Post status: {post_status}.",
            )

        # 3. Handle checkout default branch if required
        current_b = init_branch
        if checkout_default:
            default_b = self.get_default_branch(path) or repo.default_branch
            if current_b != default_b:
                # Check if we can checkout safely (is dirty?)
                cp_dirty = self._run_git(path, ["status", "--porcelain"])
                if cp_dirty.stdout.strip():
                    duration = time.time() - start_time
                    return SyncResult(
                        repo_name=repo.name,
                        status="BLOCKED",
                        before_status=status,
                        after_status=status,
                        duration=duration,
                        operation="sync",
                        error="Local changes present. Checkout default branch blocked.",
                        message="Checkout default branch blocked: repository is dirty.",
                    )
                cp_co = self._run_git(path, ["checkout", default_b])
                if cp_co.returncode != 0:
                    duration = time.time() - start_time
                    err_msg = (cp_co.stderr or cp_co.stdout).strip()
                    return SyncResult(
                        repo_name=repo.name,
                        status="FAILED",
                        before_status=status,
                        after_status=status,
                        duration=duration,
                        operation="sync",
                        error=err_msg,
                        message=f"Checkout {default_b} failed: {err_msg}",
                    )
                current_b = default_b

        # 4. Check status again to get up-to-date ahead/behind and dirty
        status_mid, current_b, ahead_mid, behind_mid, msg_mid = self.get_local_status(path, org_name)
        if status_mid in ("DIVERGED", "AHEAD"):
            duration = time.time() - start_time
            return SyncResult(
                repo_name=repo.name,
                status=status_mid,
                before_status=status,
                after_status=status_mid,
                duration=duration,
                operation="sync",
                message=f"Skipping pull: repository is {status_mid}.",
            )

        if status_mid == "UP_TO_DATE":
            duration = time.time() - start_time
            return SyncResult(
                repo_name=repo.name,
                status="UP_TO_DATE",
                before_status=status,
                after_status="UP_TO_DATE",
                duration=duration,
                operation="sync",
                message="Repository is already up to date.",
            )

        # 5. Stashing if dirty
        stashed = False
        if status_mid == "DIRTY":
            if not preserve_local_changes:
                duration = time.time() - start_time
                return SyncResult(
                    repo_name=repo.name,
                    status="DIRTY",
                    before_status=status,
                    after_status="DIRTY",
                    duration=duration,
                    operation="sync",
                    error="Local changes exist and preserve changes is disabled",
                    message="Sync skipped: repository is dirty and auto-stash is disabled.",
                )

            # Perform git stash push
            cp_stash = self._run_git(path, ["stash", "push", "--include-untracked", "-m", "github-org-sync autostash"])
            if cp_stash.returncode != 0:
                duration = time.time() - start_time
                err_msg = (cp_stash.stderr or cp_stash.stdout).strip()
                return SyncResult(
                    repo_name=repo.name,
                    status="FAILED",
                    before_status=status,
                    after_status="DIRTY",
                    duration=duration,
                    operation="sync",
                    error=err_msg,
                    message=f"Autostash failed: {err_msg}",
                )
            # Only count as stashed if changes were actually pushed
            stashed = "No local changes" not in cp_stash.stdout

        # 6. Pull --ff-only
        cp_pull = self._run_git(path, ["pull", "--ff-only"])
        pull_failed = cp_pull.returncode != 0
        pull_err = (cp_pull.stderr or cp_pull.stdout).strip() if pull_failed else None

        # 7. Pop stash if we stashed
        pop_conflict = False
        pop_err = None
        if stashed:
            cp_pop = self._run_git(path, ["stash", "pop"])
            if cp_pop.returncode != 0:
                pop_conflict = True
                pop_err = (cp_pop.stderr or cp_pop.stdout).strip()

        duration = time.time() - start_time

        if pull_failed:
            return SyncResult(
                repo_name=repo.name,
                status="FAILED",
                before_status=status,
                after_status="DIRTY" if stashed else "FAILED",
                duration=duration,
                operation="sync",
                error=pull_err,
                message=f"Pull fast-forward failed: {pull_err}",
            )

        if pop_conflict:
            return SyncResult(
                repo_name=repo.name,
                status="CONFLICT",
                before_status=status,
                after_status="CONFLICT",
                duration=duration,
                operation="sync",
                error=pop_err,
                message="Stash pop conflict. Resolve files manually, then run 'git stash drop' after verifying.",
            )

        # Recheck final status
        final_status, _, _, _, _ = self.get_local_status(path, org_name)
        return SyncResult(
            repo_name=repo.name,
            status="UPDATED",
            before_status=status,
            after_status=final_status,
            duration=duration,
            operation="sync",
            message="Successfully updated repository",
        )
