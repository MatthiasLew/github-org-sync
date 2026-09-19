from collections.abc import Callable
from pathlib import Path
from typing import Any

from github_org_sync.models.repo_state import RepoState
from github_org_sync.models.repository import Repository
from github_org_sync.models.sync_result import SyncResult
from github_org_sync.services.git_service import GitService


class SyncService:
    def __init__(self, git_service: GitService | None = None) -> None:
        self.git_service = git_service or GitService()

    def filter_repositories(
        self,
        repositories: list[Repository],
        include_archived: bool,
        include_forks: bool,
    ) -> list[Repository]:
        """
        Filters a list of repositories based on archive and fork options.
        """
        filtered = []
        for repo in repositories:
            if repo.is_archived and not include_archived:
                continue
            if repo.is_fork and not include_forks:
                continue
            filtered.append(repo)
        return filtered

    def check_local_statuses(
        self,
        repositories: list[Repository],
        workspace: Path,
        org_name: str,
        progress_callback: Callable[[int, int, str], None] | None = None,
        is_cancelled_callback: Callable[[], bool] | None = None,
        max_workers: int = 4,
    ) -> list[Repository]:
        """
        Inspects the local directory for each repository in parallel and updates their status.
        """
        import concurrent.futures
        from threading import Lock

        total = len(repositories)
        completed_lock = Lock()
        completed_count = 0

        def inspect_single(repo: Repository) -> None:
            nonlocal completed_count
            if is_cancelled_callback and is_cancelled_callback():
                return

            repo_path = workspace / repo.name
            repo.local_path = repo_path

            status, branch, ahead, behind, err = self.git_service.get_local_status(repo_path, org_name)
            repo.status = status
            repo.branch = branch
            repo.ahead = ahead or 0
            repo.behind = behind or 0
            repo.error_message = err

            last_state = getattr(self.git_service, "_last_state", None)
            if isinstance(last_state, RepoState) and (
                last_state.primary_status == status or (last_state.has_conflicts and status == "DIRTY")
            ):
                repo.state = last_state
            else:
                repo.state = RepoState(
                    exists=(status != "MISSING"),
                    is_git_repo=(status not in ("MISSING", "NOT_A_REPOSITORY")),
                    branch=branch,
                    upstream=f"origin/{branch}"
                    if branch and status not in ("NO_UPSTREAM", "MISSING", "NOT_A_REPOSITORY")
                    else None,
                    dirty=(status == "DIRTY"),
                    ahead=ahead or 0,
                    behind=behind or 0,
                    has_conflicts=(status == "CONFLICT"),
                    remote_matches=(status != "WRONG_REMOTE"),
                    error_message=err,
                )
            repo.requested_action = None
            repo.performed_action = None

            with completed_lock:
                completed_count += 1
                current_completed = completed_count

            if progress_callback:
                progress_callback(current_completed, total, repo.name)

        # Run checks in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(inspect_single, repo) for repo in repositories]
            for _future in concurrent.futures.as_completed(futures):
                if is_cancelled_callback and is_cancelled_callback():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

        return repositories

    def sync_repositories(
        self,
        repositories: list[Repository],
        workspace: Path,
        org_name: str,
        options: dict[str, Any],
        progress_callback: Callable[[int, int, Repository, SyncResult], None] | None = None,
        is_cancelled_callback: Callable[[], bool] | None = None,
        max_workers: int = 4,
    ) -> list[SyncResult]:
        """
        Synchronizes (clones or updates) selected repositories in parallel.
        Protected by workspace locking to prevent concurrent modifications.
        """
        import concurrent.futures
        from threading import Lock

        from github_org_sync.utils.lock import workspace_lock

        dry_run = options.get("dry_run", False)

        def _do_sync() -> list[SyncResult]:
            use_ssh = options.get("use_ssh", False)
            preserve_local_changes = options.get("preserve_local_changes", True)
            fetch_only = options.get("fetch_only", False)
            checkout_default = options.get("checkout_default", False)

            results = [
                SyncResult(
                    repo_name=repo.name,
                    requested_action="FETCH" if fetch_only else "SYNC",
                    performed_action="CANCELLED",
                    before_status=repo.status,
                    after_status=repo.status,
                    duration=0.0,
                    result="Sync cancelled by user.",
                )
                for repo in repositories
            ]
            total = len(repositories)

            results_lock = Lock()
            completed_count = 0

            def sync_single(idx: int, repo: Repository) -> None:
                nonlocal completed_count
                if is_cancelled_callback and is_cancelled_callback():
                    with results_lock:
                        completed_count += 1
                        current_completed = completed_count
                    if progress_callback:
                        progress_callback(current_completed, total, repo, results[idx])
                    return

                repo_path = workspace / repo.name
                repo.local_path = repo_path
                before_status = repo.status

                if before_status == "MISSING":
                    res = self.git_service.clone(repo, repo_path, use_ssh=use_ssh, dry_run=dry_run)
                elif before_status in ("NOT_A_REPOSITORY", "WRONG_REMOTE", "FAILED"):
                    res = SyncResult(
                        repo_name=repo.name,
                        requested_action="FETCH" if fetch_only else "SYNC",
                        performed_action="SKIPPED",
                        before_status=before_status,
                        after_status=before_status,
                        duration=0.0,
                        result=f"Skipped due to status: {before_status}",
                    )
                else:
                    res = self.git_service.sync(
                        repo=repo,
                        org_name=org_name,
                        preserve_local_changes=preserve_local_changes,
                        fetch_only=fetch_only,
                        checkout_default=checkout_default,
                        dry_run=dry_run,
                    )

                repo.status = res.after_status
                repo.result = res.result or res.error
                repo.requested_action = res.requested_action
                repo.performed_action = res.performed_action
                if res.local_branch:
                    repo.branch = res.local_branch
                if res.ahead is not None:
                    repo.ahead = res.ahead
                if res.behind is not None:
                    repo.behind = res.behind
                repo.has_lfs = self.git_service.detect_lfs(repo_path)

                with results_lock:
                    results[idx] = res
                    completed_count += 1
                    current_completed = completed_count

                if progress_callback:
                    progress_callback(current_completed, total, repo, res)

            # Run synchronization in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(sync_single, idx, repo) for idx, repo in enumerate(repositories)]
                for _future in concurrent.futures.as_completed(futures):
                    if is_cancelled_callback and is_cancelled_callback():
                        executor.shutdown(wait=False, cancel_futures=True)
                        break

            return results

        if dry_run:
            return _do_sync()

        with workspace_lock(workspace, command="sync"):
            return _do_sync()
