from collections.abc import Callable
from pathlib import Path
from typing import Any

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
    ) -> list[Repository]:
        """
        Inspects the local directory for each repository and updates their status/branch/ahead/behind.
        """
        total = len(repositories)
        for idx, repo in enumerate(repositories):
            repo_path = workspace / repo.name
            repo.local_path = repo_path

            if progress_callback:
                progress_callback(idx + 1, total, repo.name)

            status, branch, ahead, behind, msg = self.git_service.get_local_status(repo_path, org_name)

            repo.status = status
            repo.branch = branch
            repo.ahead = ahead
            repo.behind = behind
            repo.result = msg

        return repositories

    def sync_repositories(
        self,
        repositories: list[Repository],
        workspace: Path,
        org_name: str,
        options: dict[str, Any],
        progress_callback: Callable[[int, int, Repository, SyncResult], None] | None = None,
        is_cancelled_callback: Callable[[], bool] | None = None,
    ) -> list[SyncResult]:
        """
        Synchronizes (clones or updates) a list of selected repositories.
        """
        use_ssh = options.get("use_ssh", False)
        preserve_local_changes = options.get("preserve_local_changes", True)
        fetch_only = options.get("fetch_only", False)
        dry_run = options.get("dry_run", False)
        checkout_default = options.get("checkout_default", False)

        results: list[SyncResult] = []
        total = len(repositories)

        for idx, repo in enumerate(repositories):
            if is_cancelled_callback and is_cancelled_callback():
                # Mark remaining as cancelled
                for remaining_repo in repositories[idx:]:
                    res = SyncResult(
                        repo_name=remaining_repo.name,
                        status="CANCELLED",
                        before_status=remaining_repo.status,
                        after_status=remaining_repo.status,
                        duration=0.0,
                        operation="sync",
                        message="Sync cancelled by user.",
                    )
                    results.append(res)
                    if progress_callback:
                        progress_callback(len(results), total, remaining_repo, res)
                break

            repo_path = workspace / repo.name
            repo.local_path = repo_path
            before_status = repo.status

            if before_status == "MISSING":
                # Clone
                res = self.git_service.clone(repo, repo_path, use_ssh=use_ssh, dry_run=dry_run)
            elif before_status in ("NOT_A_REPOSITORY", "WRONG_REMOTE", "FAILED"):
                # Non-updatable states, skip
                res = SyncResult(
                    repo_name=repo.name,
                    status=before_status,
                    before_status=before_status,
                    after_status=before_status,
                    duration=0.0,
                    operation="skip",
                    message=f"Skipped due to status: {before_status}",
                )
            else:
                # Sync / Update
                res = self.git_service.sync(
                    repo=repo,
                    org_name=org_name,
                    preserve_local_changes=preserve_local_changes,
                    fetch_only=fetch_only,
                    checkout_default=checkout_default,
                    dry_run=dry_run,
                )

            # Update repository state in-place based on sync results
            repo.status = res.status
            repo.result = res.message or res.error
            results.append(res)

            if progress_callback:
                progress_callback(idx + 1, total, repo, res)

        return results
