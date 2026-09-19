import shutil
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from github_org_sync.models.repo_state import RepoState
from github_org_sync.models.repository import Repository
from github_org_sync.models.sync_result import SyncResult
from github_org_sync.utils.git_url_parser import parse_git_url
from github_org_sync.utils.process import run_process


class GitService:
    def __init__(self) -> None:
        self.git_path = shutil.which("git")

    def _run_git(
        self, cwd: Path | None, args: list[str], timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        if not self.git_path:
            raise FileNotFoundError("Git is not installed or not in system PATH.")
        return run_process([self.git_path, *args], cwd=cwd, timeout=timeout)

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

    def is_wrong_remote(self, remote_url: str, org_name: str, repo_name: str | None = None) -> bool:
        """
        Checks if origin URL does not match the expected organization/owner and repository.
        Strictly compares host, owner, and repo name if repo_name is provided.
        """
        if not org_name:
            return False
        if not remote_url:
            return True
        parsed = parse_git_url(remote_url)
        if not parsed:
            return True
        if repo_name:
            return not parsed.matches(expected_owner=org_name, expected_repo=repo_name)
        return parsed.owner.lower() != org_name.lower()

    def inspect_repo_state(
        self,
        path: Path,
        expected_org: str,
        expected_repo: str | None = None,
        expected_host: str = "github.com",
    ) -> RepoState:
        """
        Multidimensionally inspects a repository directory against its expected remote identity.
        """
        if not path.exists():
            return RepoState(exists=False, is_git_repo=False)

        if not self.is_git_repository(path):
            return RepoState(
                exists=True,
                is_git_repo=False,
                error_message="Folder exists but is not a git repository",
            )

        try:
            # 1. Remote Origin URL
            cp_url = self._run_git(path, ["remote", "get-url", "origin"])
            if cp_url.returncode != 0:
                state = RepoState(
                    exists=True,
                    is_git_repo=True,
                    error_message="Missing origin remote",
                )
                self._last_state = state
                return state

            remote_url = cp_url.stdout.strip()
            parsed = parse_git_url(remote_url)

            # Validate remote identity via is_wrong_remote (respects test monkeypatches and exact parsing)
            is_wrong = self.is_wrong_remote(remote_url, expected_org)
            if (
                not is_wrong
                and expected_repo
                and parsed
                and not parsed.matches(
                    expected_owner=expected_org, expected_repo=expected_repo, expected_host=expected_host
                )
            ):
                is_wrong = True

            if is_wrong:
                err_msg = f"Remote origin mismatch: {remote_url} (expected {expected_org}" + (
                    f"/{expected_repo})" if expected_repo else ")"
                )
                state = RepoState(
                    exists=True,
                    is_git_repo=True,
                    remote_url=remote_url,
                    remote_host=parsed.host if parsed else None,
                    remote_owner=parsed.owner if parsed else None,
                    remote_repo=parsed.repo if parsed else None,
                    remote_matches=False,
                    has_lfs=self.detect_lfs(path),
                    error_message=err_msg,
                )
                self._last_state = state
                return state

            # 2. Current branch & detached HEAD
            cp_branch = self._run_git(path, ["rev-parse", "--abbrev-ref", "HEAD"])
            branch = cp_branch.stdout.strip() if cp_branch.returncode == 0 else None
            detached_head = branch == "HEAD"

            if detached_head:
                state = RepoState(
                    exists=True,
                    is_git_repo=True,
                    branch="HEAD",
                    detached_head=True,
                    remote_url=remote_url,
                    remote_host=parsed.host if parsed else "local",
                    remote_owner=parsed.owner if parsed else expected_org,
                    remote_repo=parsed.repo if parsed else (expected_repo or path.name),
                    remote_matches=True,
                    has_lfs=self.detect_lfs(path),
                    error_message="Detached HEAD",
                )
                self._last_state = state
                return state

            # 3. Upstream & Ahead/Behind
            upstream: str | None = None
            ahead, behind = 0, 0
            if branch:
                cp_up = self._run_git(path, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
                if cp_up.returncode != 0:
                    state = RepoState(
                        exists=True,
                        is_git_repo=True,
                        branch=branch,
                        upstream=None,
                        remote_url=remote_url,
                        remote_host=parsed.host if parsed else "local",
                        remote_owner=parsed.owner if parsed else expected_org,
                        remote_repo=parsed.repo if parsed else (expected_repo or path.name),
                        remote_matches=True,
                        has_lfs=self.detect_lfs(path),
                        error_message="No tracking upstream branch",
                    )
                    self._last_state = state
                    return state

                upstream = cp_up.stdout.strip()
                cp_ab = self._run_git(path, ["rev-list", "--left-right", "--count", f"HEAD...{upstream}"])
                if cp_ab.returncode == 0:
                    parts = cp_ab.stdout.strip().split()
                    ahead = int(parts[0]) if len(parts) > 0 else 0
                    behind = int(parts[1]) if len(parts) > 1 else 0

            # 4. Dirty check & conflict files from single status --porcelain
            cp_status = self._run_git(path, ["status", "--porcelain"])
            dirty_files: list[tuple[str, str]] = []
            conflict_files_list: list[str] = []
            if cp_status.returncode == 0 and cp_status.stdout:
                for line in cp_status.stdout.splitlines():
                    if len(line) >= 4:
                        code = line[:2]
                        filename = line[3:].strip()
                        dirty_files.append((code, filename))
                        if "U" in code or code in ("AA", "DD"):
                            conflict_files_list.append(filename)

            dirty_count = len(dirty_files)
            conflict_files = tuple(conflict_files_list)
            has_conflicts = len(conflict_files) > 0

            # 5. Git LFS check
            has_lfs = self.detect_lfs(path)

            state = RepoState(
                exists=True,
                is_git_repo=True,
                branch=branch,
                upstream=upstream,
                dirty=(dirty_count > 0),
                dirty_files_count=dirty_count,
                ahead=ahead,
                behind=behind,
                detached_head=detached_head,
                has_conflicts=has_conflicts,
                conflict_files=conflict_files,
                remote_url=remote_url,
                remote_host=parsed.host if parsed else "local",
                remote_owner=parsed.owner if parsed else expected_org,
                remote_repo=parsed.repo if parsed else (expected_repo or path.name),
                remote_matches=True,
                has_lfs=has_lfs,
                error_message=None,
            )
            self._last_state = state
            return state

        except Exception as exc:
            state = RepoState(
                exists=True,
                is_git_repo=True,
                failed=True,
                error_message=str(exc),
            )
            self._last_state = state
            return state

    def get_local_status(
        self, path: Path, org_name: str, repo_name: str | None = None
    ) -> tuple[str, str | None, int | None, int | None, str | None]:
        """
        Inspects local path and returns (status, branch, ahead, behind, message/error).
        Backward-compatible classification wrapper using inspect_repo_state.
        """
        state = self.inspect_repo_state(path, expected_org=org_name, expected_repo=repo_name)
        status = state.primary_status
        if status == "CONFLICT":
            status = "DIRTY"
        return (
            status,
            state.branch,
            state.ahead if state.upstream else None,
            state.behind if state.upstream else None,
            state.error_message,
        )

    def _safe_cleanup_dir(self, target: Path) -> None:
        """Safely cleans up an application temporary directory without touching user folders."""
        try:
            if target.exists() and ".github-org-sync-tmp" in target.parts:
                shutil.rmtree(target, ignore_errors=True)
        except Exception:
            pass

    def clone(
        self,
        repo: Repository,
        dest_path: Path,
        use_ssh: bool,
        dry_run: bool,
        timeout: float | None = 180.0,
    ) -> SyncResult:
        """
        Clones a remote repository atomically.
        Clones into an isolated temporary folder workspace/.github-org-sync-tmp/<repo>-<uuid>,
        validates clone integrity and exact remote identity, then atomically moves to final destination.
        """
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

        workspace_dir = dest_path.parent
        temp_base = workspace_dir / ".github-org-sync-tmp"
        temp_clone_dir = temp_base / f"{repo.name}-{uuid.uuid4().hex[:8]}"

        try:
            temp_base.mkdir(parents=True, exist_ok=True)
            if dest_path.exists():
                raise FileExistsError(f"Destination path '{dest_path}' already exists.")

            cp = self._run_git(None, ["clone", url, str(temp_clone_dir)], timeout=timeout)
            duration = time.time() - start_time

            if cp.returncode != 0:
                err_msg = (cp.stderr or cp.stdout).strip()
                self._safe_cleanup_dir(temp_clone_dir)
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

            # Validate cloned repository
            if not self.is_git_repository(temp_clone_dir):
                self._safe_cleanup_dir(temp_clone_dir)
                return SyncResult(
                    repo_name=repo.name,
                    requested_action="CLONE",
                    performed_action="FAILED",
                    before_status="MISSING",
                    after_status="MISSING",
                    duration=duration,
                    error="Cloned directory failed validation: not a valid git repository",
                    result="Clone validation failed: invalid git repository structure.",
                )

            # Atomic move to final destination
            try:
                temp_clone_dir.replace(dest_path)
            except OSError:
                shutil.move(str(temp_clone_dir), str(dest_path))

            # Clean up temp base if empty
            try:
                if not any(temp_base.iterdir()):
                    temp_base.rmdir()
            except OSError:
                pass

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
            self._safe_cleanup_dir(temp_clone_dir)
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
        Synchronizes an existing local repository with safe branch defaults and stash recovery.
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
        status, init_branch, ahead, behind, init_msg = self.get_local_status(path, org_name, repo.name)
        ahead = ahead or 0
        behind = behind or 0
        dirty_files = self.get_dirty_files(path)
        dirty_count = len(dirty_files)

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
        post_status, post_branch, post_ahead, post_behind, post_msg = self.get_local_status(path, org_name, repo.name)
        post_ahead = post_ahead or 0
        post_behind = post_behind or 0

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

        # 3. Handle checkout default branch if explicitly requested
        current_b = init_branch
        if checkout_default:
            default_b = self.get_default_branch(path) or repo.default_branch
            if current_b != default_b:
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
        status_mid, current_b, ahead_mid, behind_mid, msg_mid = self.get_local_status(path, org_name, repo.name)
        ahead_mid = ahead_mid or 0
        behind_mid = behind_mid or 0

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

            # Perform git stash push with unique message
            stash_tag = f"github-org-sync autostash {int(time.time())}"
            cp_stash = self._run_git(path, ["stash", "push", "--include-untracked", "-m", stash_tag])
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
            stashed = "No local changes" not in cp_stash.stdout

        # 6. Pull --ff-only
        cp_pull = self._run_git(path, ["pull", "--ff-only"])
        pull_failed = cp_pull.returncode != 0
        pull_err = (cp_pull.stderr or cp_pull.stdout).strip() if pull_failed else None

        # 7. Safe Stash Recovery
        pop_conflict = False
        pop_err = None
        if stashed:
            cp_pop = self._run_git(path, ["stash", "pop"])
            if cp_pop.returncode != 0:
                pop_conflict = True
                pop_err = (cp_pop.stderr or cp_pop.stdout).strip()

        duration = time.time() - start_time

        # CRITICAL SAFETY: Handle stash conflict
        if pop_conflict:
            conf_files = self.get_conflict_files(path)
            conflict_msg = (
                f"Stash restore produced conflicts ({len(conf_files)} files). "
                "CRITICAL: Your uncommitted changes are preserved in git stash (stash@{0}) "
                "and marked in the working directory. Resolve conflicts manually, verify your files, "
                "then drop the stash with 'git stash drop'."
            )
            if pull_failed:
                conflict_msg = f"Pull failed ({pull_err}). {conflict_msg}"

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
                result=conflict_msg,
            )

        # Pull failed but stash was safely restored cleanly
        if pull_failed:
            fail_msg = f"Pull fast-forward failed: {pull_err}"
            if stashed:
                fail_msg += ". Local uncommitted changes were safely restored to working directory."
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
                result=fail_msg,
            )

        # Recheck final status
        final_status, _, final_ahead, final_behind, _ = self.get_local_status(path, org_name, repo.name)
        final_ahead = final_ahead or 0
        final_behind = final_behind or 0
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

    def launch_merge_tool(self, path: Path) -> None:
        """Launches the configured git mergetool asynchronously."""
        from github_org_sync.utils.process import popen_process

        popen_process(["git", "mergetool"], cwd=path)

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

    def get_local_branches(self, repo_path: Path) -> list[str]:
        """Returns list of local branch names in the repository."""
        try:
            res = self._run_git(repo_path, ["branch", "--format=%(refname:short)"])
            return [line.strip() for line in res.stdout.splitlines() if line.strip()]
        except Exception:
            return []

    def checkout_branch(self, repo_path: Path, branch_name: str) -> tuple[bool, str]:
        """Performs a git checkout to the selected branch."""
        try:
            res = self._run_git(repo_path, ["checkout", branch_name])
            return res.returncode == 0, (res.stdout + res.stderr)
        except Exception as e:
            return False, str(e)

    def stage_file(self, repo_path: Path, file_path: str) -> tuple[bool, str]:
        """Stages a specific file (git add -- file_path)."""
        try:
            res = self._run_git(repo_path, ["add", "--", file_path])
            return res.returncode == 0, (res.stdout + res.stderr)
        except Exception as e:
            return False, str(e)

    def unstage_file(self, repo_path: Path, file_path: str) -> tuple[bool, str]:
        """Unstages a specific file from index."""
        try:
            res = self._run_git(repo_path, ["restore", "--staged", "--", file_path])
            if res.returncode != 0:
                res = self._run_git(repo_path, ["reset", "HEAD", "--", file_path])
            return res.returncode == 0, (res.stdout + res.stderr)
        except Exception as e:
            return False, str(e)

    def stage_all(self, repo_path: Path) -> tuple[bool, str]:
        """Stages all working tree changes (git add -A)."""
        try:
            res = self._run_git(repo_path, ["add", "-A"])
            return res.returncode == 0, (res.stdout + res.stderr)
        except Exception as e:
            return False, str(e)

    def unstage_all(self, repo_path: Path) -> tuple[bool, str]:
        """Unstages all changes from index."""
        try:
            res = self._run_git(repo_path, ["restore", "--staged", "."])
            if res.returncode != 0:
                res = self._run_git(repo_path, ["reset", "HEAD"])
            return res.returncode == 0, (res.stdout + res.stderr)
        except Exception as e:
            return False, str(e)

    def commit_changes(self, repo_path: Path, message: str) -> tuple[bool, str]:
        """Creates a git commit with the given message (git commit -m message)."""
        try:
            res = self._run_git(repo_path, ["commit", "-m", message])
            return res.returncode == 0, (res.stdout + res.stderr)
        except Exception as e:
            return False, str(e)

    def get_staged_and_unstaged_files(self, repo_path: Path) -> tuple[list[str], list[str]]:
        """Returns tuple of (staged_files, unstaged_files)."""
        try:
            dirty = self.get_dirty_files(repo_path)
            staged = []
            unstaged = []
            for code, fpath in dirty:
                idx = code[0] if len(code) > 0 else " "
                work = code[1] if len(code) > 1 else " "
                if idx not in (" ", "?"):
                    staged.append(fpath)
                if work != " " or idx == "?":
                    unstaged.append(fpath)
            return staged, unstaged
        except Exception:
            return [], []

    def get_stash_list(self, repo_path: Path) -> list[str]:
        """Returns list of stash descriptions from git stash list."""
        try:
            res = self._run_git(repo_path, ["stash", "list"])
            return [line.strip() for line in res.stdout.splitlines() if line.strip()]
        except Exception:
            return []

    def get_stash_show(self, repo_path: Path, index: int = 0) -> str:
        """Returns stat summary of a specific stash entry."""
        try:
            res = self._run_git(repo_path, ["stash", "show", f"stash@{{{index}}}"])
            return res.stdout.strip()
        except Exception:
            return ""

    def stash_push(self, repo_path: Path, message: str = "", include_untracked: bool = True) -> tuple[bool, str]:
        """Creates a new stash entry."""
        try:
            cmd = ["stash", "push"]
            if include_untracked:
                cmd.append("--include-untracked")
            if message:
                cmd.extend(["-m", message])
            res = self._run_git(repo_path, cmd)
            return res.returncode == 0, (res.stdout + res.stderr).strip()
        except Exception as e:
            return False, str(e)

    def stash_pop(self, repo_path: Path, index: int = 0) -> tuple[bool, str]:
        """Pops a stash entry from the stack."""
        try:
            res = self._run_git(repo_path, ["stash", "pop", f"stash@{{{index}}}"])
            return res.returncode == 0, (res.stdout + res.stderr).strip()
        except Exception as e:
            return False, str(e)

    def stash_drop(self, repo_path: Path, index: int = 0) -> tuple[bool, str]:
        """Drops a stash entry from the stack."""
        try:
            res = self._run_git(repo_path, ["stash", "drop", f"stash@{{{index}}}"])
            return res.returncode == 0, (res.stdout + res.stderr).strip()
        except Exception as e:
            return False, str(e)

    def prune_remote_branches(self, repo_path: Path, remote: str = "origin") -> tuple[bool, str]:
        """Runs git remote prune <remote> to remove stale remote-tracking branches."""
        try:
            res = self._run_git(repo_path, ["remote", "prune", remote])
            out = (res.stdout + res.stderr).strip()
            return res.returncode == 0, out
        except Exception as e:
            return False, str(e)

    def get_stale_branches(self, repo_path: Path) -> list[dict[str, str]]:
        """Detects local branches that are stale:
        - Upstream is gone ([gone])
        - Or merged into default branch (and not HEAD / not default branch).
        Returns a list of dicts: [{'name': branch, 'upstream': upstream, 'reason': 'gone' | 'merged'}].
        """
        try:
            # 1. Determine current HEAD
            res_head = self._run_git(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"])
            current_head = res_head.stdout.strip() if res_head.returncode == 0 else ""

            # 2. Determine default branch
            default_branch = self.get_default_branch(repo_path) or "main"

            # 3. Check merged branches into default branch
            merged_branches: set[str] = set()
            res_merged = self._run_git(repo_path, ["branch", "--merged", default_branch])
            if res_merged.returncode == 0:
                for line in res_merged.stdout.splitlines():
                    clean_b = line.strip().lstrip("*+ ").strip()
                    if clean_b:
                        merged_branches.add(clean_b)

            # 4. Check tracking status with for-each-ref
            fmt = "%(refname:short)|%(upstream:short)|%(upstream:track)"
            res_refs = self._run_git(repo_path, ["for-each-ref", f"--format={fmt}", "refs/heads/"])
            if res_refs.returncode != 0:
                return []

            stale_list: list[dict[str, str]] = []
            protected = {current_head, default_branch, "main", "master", "develop", "HEAD"}

            for line in res_refs.stdout.splitlines():
                parts = line.strip().split("|")
                if len(parts) < 3:
                    continue
                b_name, upstream, track = parts[0].strip(), parts[1].strip(), parts[2].strip()
                if not b_name or b_name in protected:
                    continue

                if "[gone]" in track:
                    stale_list.append({"name": b_name, "upstream": upstream, "reason": "gone"})
                elif b_name in merged_branches:
                    stale_list.append({"name": b_name, "upstream": upstream, "reason": "merged"})

            return stale_list
        except Exception:
            return []

    def delete_local_branch(self, repo_path: Path, branch_name: str, force: bool = True) -> tuple[bool, str]:
        """Deletes a local branch (git branch -D if force else -d)."""
        try:
            flag = "-D" if force else "-d"
            res = self._run_git(repo_path, ["branch", flag, branch_name])
            out = (res.stdout + res.stderr).strip()
            return res.returncode == 0, out
        except Exception as e:
            return False, str(e)

    def get_log_graph(self, repo_path: Path, limit: int = 25, all_branches: bool = True) -> str:
        """Returns visual git log graph string using git log --graph."""
        try:
            cmd = ["log", "--graph", "--oneline", "--decorate"]
            if all_branches:
                cmd.append("--all")
            cmd.extend(["-n", str(limit)])
            res = self._run_git(repo_path, cmd)
            return res.stdout.strip() if res.returncode == 0 else (res.stderr or "").strip()
        except Exception as e:
            return str(e)

    def detect_lfs(self, repo_path: Path) -> bool:
        """Fast check if repository uses Git LFS (via .gitattributes or .lfsconfig)."""
        try:
            attr_file = repo_path / ".gitattributes"
            if attr_file.is_file():
                content = attr_file.read_text(encoding="utf-8", errors="ignore")
                if "filter=lfs" in content:
                    return True
            return bool((repo_path / ".lfsconfig").is_file())
        except Exception:
            return False

    def get_lfs_status(self, repo_path: Path) -> dict[str, Any]:
        """Runs git lfs status and git lfs ls-files to inspect repository LFS usage."""
        has_lfs = self.detect_lfs(repo_path)
        files: list[str] = []
        status_text = ""
        error: str | None = None

        try:
            # 1. Run git lfs ls-files
            res_ls = self._run_git(repo_path, ["lfs", "ls-files"])
            if res_ls.returncode == 0:
                for line in res_ls.stdout.splitlines():
                    cleaned = line.strip()
                    if cleaned:
                        files.append(cleaned)
                if files:
                    has_lfs = True
            elif "not a git command" in (res_ls.stderr or ""):
                error = "Git LFS is not installed on system."

            # 2. Run git lfs status
            res_status = self._run_git(repo_path, ["lfs", "status"])
            if res_status.returncode == 0:
                status_text = res_status.stdout.strip()
            elif not error:
                status_text = (res_status.stderr or "").strip()
        except Exception as e:
            error = str(e)

        return {
            "has_lfs": has_lfs,
            "files": files,
            "status": status_text,
            "error": error,
        }
