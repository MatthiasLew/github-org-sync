import re
import shutil
import subprocess
import time
from datetime import datetime
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

    def add_remote(self, path: Path, name: str, url: str) -> None:
        """Adds a remote to the git repository."""
        cp = self._run_git(path, ["remote", "add", name, url])
        if cp.returncode != 0:
            raise RuntimeError(cp.stderr.strip() or f"git remote add failed with exit code {cp.returncode}")

    def is_wrong_remote(self, remote_url: str, org_name: str) -> bool:
        """Checks if origin URL belongs to another owner/organization."""
        if not org_name:
            return False
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
                requested_action="CLONE",
                performed_action="NO_CHANGE",
                before_status="MISSING",
                after_status="MISSING",
                result=f"[DRY-RUN] Would clone {url} to {dest_path}",
                duration=0.0,
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
                    requested_action="CLONE",
                    performed_action="FAILED",
                    before_status="MISSING",
                    after_status="MISSING",
                    duration=duration,
                    error=err_msg,
                    result=f"Clone failed: {err_msg}",
                )

            return SyncResult(
                repo_name=repo.name,
                requested_action="CLONE",
                performed_action="CLONED",
                before_status="MISSING",
                after_status="UP_TO_DATE",
                duration=duration,
                result="Successfully cloned repository",
            )
        except Exception as e:
            return SyncResult(
                repo_name=repo.name,
                requested_action="CLONE",
                performed_action="FAILED",
                before_status="MISSING",
                after_status="MISSING",
                duration=time.time() - start_time,
                error=str(e),
                result=f"Exception during clone: {e}",
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
                requested_action="FETCH" if fetch_only else "SYNC",
                performed_action="FAILED",
                before_status="MISSING",
                after_status="MISSING",
                duration=0.0,
                error="Local path does not exist",
                result="Local path does not exist",
            )

        # 1. Assess initial status
        status, init_branch, ahead, behind, init_msg = self.get_local_status(path, org_name)
        if status in ("NOT_A_REPOSITORY", "WRONG_REMOTE", "FAILED"):
            return SyncResult(
                repo_name=repo.name,
                requested_action="FETCH" if fetch_only else "SYNC",
                performed_action="FAILED",
                before_status=status,
                after_status=status,
                duration=0.0,
                error=init_msg,
                result=init_msg,
            )

        # Fetch count of dirty files
        dirty_files = self.get_dirty_files(path)
        dirty_count = len(dirty_files)

        if dry_run:
            duration = time.time() - start_time
            return SyncResult(
                repo_name=repo.name,
                requested_action="FETCH" if fetch_only else "SYNC",
                performed_action="NO_CHANGE",
                before_status=status,
                after_status=status,
                duration=duration,
                local_branch=init_branch,
                ahead=ahead,
                behind=behind,
                dirty_file_count=dirty_count,
                result=f"[DRY-RUN] Would fetch and update (fetch_only={fetch_only})",
            )

        # 2. Fetch changes
        cp_fetch = self._run_git(path, ["fetch", "--prune"])
        if cp_fetch.returncode != 0:
            duration = time.time() - start_time
            err_msg = (cp_fetch.stderr or cp_fetch.stdout).strip()
            return SyncResult(
                repo_name=repo.name,
                requested_action="FETCH" if fetch_only else "SYNC",
                performed_action="FAILED",
                before_status=status,
                after_status=status,
                duration=duration,
                local_branch=init_branch,
                ahead=ahead,
                behind=behind,
                dirty_file_count=dirty_count,
                error=err_msg,
                result=f"Fetch failed: {err_msg}",
            )

        # Recheck status after fetch to get accurate ahead/behind
        post_status, post_branch, post_ahead, post_behind, post_msg = self.get_local_status(path, org_name)

        if fetch_only:
            duration = time.time() - start_time
            return SyncResult(
                repo_name=repo.name,
                requested_action="FETCH",
                performed_action="FETCHED",
                before_status=status,
                after_status=post_status,
                duration=duration,
                local_branch=post_branch,
                ahead=post_ahead,
                behind=post_behind,
                dirty_file_count=dirty_count,
                result=f"Fetched remote changes. Post status: {post_status}.",
            )

        # 3. Handle checkout default branch if required
        current_b = init_branch
        if checkout_default:
            default_b = self.get_default_branch(path) or repo.default_branch
            if current_b != default_b:
                # Check if we can checkout safely (is dirty?)
                if dirty_count > 0:
                    duration = time.time() - start_time
                    return SyncResult(
                        repo_name=repo.name,
                        requested_action="SYNC",
                        performed_action="BLOCKED",
                        before_status=status,
                        after_status=status,
                        duration=duration,
                        local_branch=init_branch,
                        ahead=ahead,
                        behind=behind,
                        dirty_file_count=dirty_count,
                        error="Local changes present. Checkout default branch blocked.",
                        result="Checkout default branch blocked: repository is dirty.",
                    )
                cp_co = self._run_git(path, ["checkout", default_b])
                if cp_co.returncode != 0:
                    duration = time.time() - start_time
                    err_msg = (cp_co.stderr or cp_co.stdout).strip()
                    return SyncResult(
                        repo_name=repo.name,
                        requested_action="SYNC",
                        performed_action="FAILED",
                        before_status=status,
                        after_status=status,
                        duration=duration,
                        local_branch=init_branch,
                        ahead=ahead,
                        behind=behind,
                        dirty_file_count=dirty_count,
                        error=err_msg,
                        result=f"Checkout {default_b} failed: {err_msg}",
                    )
                current_b = default_b

        # 4. Check status again to get up-to-date ahead/behind and dirty
        status_mid, current_b, ahead_mid, behind_mid, msg_mid = self.get_local_status(path, org_name)
        if status_mid in ("DIVERGED", "AHEAD"):
            duration = time.time() - start_time
            return SyncResult(
                repo_name=repo.name,
                requested_action="SYNC",
                performed_action="SKIPPED",
                before_status=status,
                after_status=status_mid,
                duration=duration,
                local_branch=current_b,
                ahead=ahead_mid,
                behind=behind_mid,
                dirty_file_count=dirty_count,
                result=f"Skipping pull: repository is {status_mid}.",
            )

        if status_mid == "UP_TO_DATE":
            duration = time.time() - start_time
            return SyncResult(
                repo_name=repo.name,
                requested_action="SYNC",
                performed_action="NO_CHANGE",
                before_status=status,
                after_status="UP_TO_DATE",
                duration=duration,
                local_branch=current_b,
                ahead=0,
                behind=0,
                dirty_file_count=dirty_count,
                result="Repository was already up to date.",
            )

        # 5. Stashing if dirty
        stashed = False
        if status_mid == "DIRTY":
            if not preserve_local_changes:
                duration = time.time() - start_time
                return SyncResult(
                    repo_name=repo.name,
                    requested_action="SYNC",
                    performed_action="BLOCKED",
                    before_status=status,
                    after_status="DIRTY",
                    duration=duration,
                    local_branch=current_b,
                    ahead=ahead_mid,
                    behind=behind_mid,
                    dirty_file_count=dirty_count,
                    error="Local changes exist and preserve changes is disabled",
                    result="Sync skipped: repository is dirty and auto-stash is disabled.",
                )

            # Perform git stash push
            cp_stash = self._run_git(path, ["stash", "push", "--include-untracked", "-m", "github-org-sync autostash"])
            if cp_stash.returncode != 0:
                duration = time.time() - start_time
                err_msg = (cp_stash.stderr or cp_stash.stdout).strip()
                return SyncResult(
                    repo_name=repo.name,
                    requested_action="SYNC",
                    performed_action="FAILED",
                    before_status=status,
                    after_status="DIRTY",
                    duration=duration,
                    local_branch=current_b,
                    ahead=ahead_mid,
                    behind=behind_mid,
                    dirty_file_count=dirty_count,
                    error=err_msg,
                    result=f"Autostash failed: {err_msg}",
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
                requested_action="SYNC",
                performed_action="FAILED",
                before_status=status,
                after_status="DIRTY" if stashed else "FAILED",
                duration=duration,
                local_branch=current_b,
                ahead=ahead_mid,
                behind=behind_mid,
                dirty_file_count=dirty_count,
                error=pull_err,
                result=f"Pull fast-forward failed: {pull_err}",
            )

        if pop_conflict:
            conf_files = self.get_conflict_files(path)
            return SyncResult(
                repo_name=repo.name,
                requested_action="SYNC",
                performed_action="CONFLICT",
                before_status=status,
                after_status="CONFLICT",
                duration=duration,
                local_branch=current_b,
                ahead=ahead_mid,
                behind=behind_mid,
                dirty_file_count=dirty_count,
                conflict_files=conf_files,
                error=pop_err,
                result="Stash pop conflict. Resolve files manually, then run 'git stash drop' after verifying.",
            )

        # Recheck final status
        final_status, _, final_ahead, final_behind, _ = self.get_local_status(path, org_name)
        res_msg = "Successfully updated repository"
        if stashed:
            res_msg = (
                "Remote branch was updated successfully. Local uncommitted changes were restored and remain present."
            )
        return SyncResult(
            repo_name=repo.name,
            requested_action="SYNC",
            performed_action="UPDATED",
            before_status=status,
            after_status=final_status,
            duration=duration,
            local_branch=current_b,
            ahead=final_ahead,
            behind=final_behind,
            dirty_file_count=dirty_count,
            result=res_msg,
        )

    def get_dirty_files(self, path: Path) -> list[tuple[str, str]]:
        try:
            cp = self._run_git(path, ["status", "--porcelain"])
            if cp.returncode != 0:
                return []
            files = []
            for line in cp.stdout.splitlines():
                if len(line) >= 4:
                    status_code = line[:2]
                    file_path = line[3:].strip().strip('"')
                    files.append((status_code, file_path))
            return files
        except Exception:
            return []

    def get_conflict_files(self, path: Path) -> list[str]:
        try:
            cp = self._run_git(path, ["diff", "--name-only", "--diff-filter=U"])
            if cp.returncode == 0:
                return [line.strip() for line in cp.stdout.splitlines() if line.strip()]
            return []
        except Exception:
            return []

    def get_unpushed_commits(self, path: Path, branch: str, upstream: str) -> list[dict[str, str]]:
        try:
            cp = self._run_git(path, ["log", f"{upstream}..{branch}", "--format=%H|%an|%ad|%s"])
            if cp.returncode != 0:
                return []
            commits = []
            for line in cp.stdout.splitlines():
                parts = line.split("|", 3)
                if len(parts) >= 4:
                    commits.append({"sha": parts[0], "author": parts[1], "date": parts[2], "subject": parts[3]})
            return commits
        except Exception:
            return []

    def get_diverged_commits(
        self, path: Path, branch: str, upstream: str
    ) -> tuple[list[dict[str, str]], list[dict[str, str]], str]:
        try:
            local_commits = self.get_unpushed_commits(path, branch, upstream)
            cp_remote = self._run_git(path, ["log", f"{branch}..{upstream}", "--format=%H|%an|%ad|%s"])
            remote_commits = []
            if cp_remote.returncode == 0:
                for line in cp_remote.stdout.splitlines():
                    parts = line.split("|", 3)
                    if len(parts) >= 4:
                        remote_commits.append(
                            {"sha": parts[0], "author": parts[1], "date": parts[2], "subject": parts[3]}
                        )
            cp_base = self._run_git(path, ["merge-base", branch, upstream])
            merge_base = cp_base.stdout.strip() if cp_base.returncode == 0 else ""
            return local_commits, remote_commits, merge_base
        except Exception:
            return [], [], ""

    def backup_repository(self, path: Path, org_name: str, repo_name: str) -> Path | None:
        """Creates a zip backup of the repository directory (excluding .git) inside AppData/backups/."""
        try:
            from github_org_sync.services.report_service import ReportService

            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_root = ReportService.get_app_data_dir() / "backups" / timestamp / org_name / repo_name
            backup_root.mkdir(parents=True, exist_ok=True)
            zip_path = backup_root / "backup.zip"

            import os
            import zipfile

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(path):
                    if ".git" in dirs:
                        dirs.remove(".git")
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(path)
                        zf.write(file_path, arcname)
            return zip_path
        except Exception as e:
            print(f"Backup failed: {e}")
            return None

    def discard_changes(self, path: Path) -> bool:
        """Discards local changes via git reset --hard and git clean -fd."""
        try:
            cp_reset = self._run_git(path, ["reset", "--hard", "HEAD"])
            cp_clean = self._run_git(path, ["clean", "-fd"])
            return cp_reset.returncode == 0 and cp_clean.returncode == 0
        except Exception:
            return False

    def push_commits(self, path: Path, branch: str) -> subprocess.CompletedProcess[str]:
        """Pushes current branch to origin. Never uses force."""
        return self._run_git(path, ["push", "origin", branch])

    def merge_branch(self, path: Path, upstream: str) -> subprocess.CompletedProcess[str]:
        """Merges remote upstream branch into local HEAD."""
        return self._run_git(path, ["merge", upstream])

    def rebase_branch(self, path: Path, upstream: str) -> subprocess.CompletedProcess[str]:
        """Rebases current branch onto remote upstream branch."""
        return self._run_git(path, ["rebase", upstream])

    def abort_merge(self, path: Path) -> subprocess.CompletedProcess[str]:
        return self._run_git(path, ["merge", "--abort"])

    def abort_rebase(self, path: Path) -> subprocess.CompletedProcess[str]:
        return self._run_git(path, ["rebase", "--abort"])

    def create_branch(self, path: Path, branch_name: str) -> subprocess.CompletedProcess[str]:
        return self._run_git(path, ["checkout", "-b", branch_name])

    def set_upstream_branch(
        self, path: Path, local_branch: str, remote_branch: str
    ) -> subprocess.CompletedProcess[str]:
        return self._run_git(path, ["branch", f"--set-upstream-to=origin/{remote_branch}", local_branch])

    def push_set_upstream(self, path: Path, local_branch: str) -> subprocess.CompletedProcess[str]:
        return self._run_git(path, ["push", "-u", "origin", local_branch])

    def get_file_diff(self, path: Path, file_path: str) -> str:
        """Runs git diff HEAD -- file_path to show both staged and unstaged changes."""
        try:
            cp = self._run_git(path, ["diff", "HEAD", "--", file_path])
            return cp.stdout if cp.returncode == 0 else (cp.stderr or "")
        except Exception as e:
            return str(e)

    def get_commit_show(self, path: Path, sha: str) -> str:
        """Runs git show --stat sha to show commit statistics and patch details."""
        try:
            cp = self._run_git(path, ["show", "--stat", sha])
            return cp.stdout if cp.returncode == 0 else (cp.stderr or "")
        except Exception as e:
            return str(e)
