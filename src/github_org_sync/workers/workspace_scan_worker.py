import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

from github_org_sync.services.git_service import GitService
from github_org_sync.utils.git_url_parser import parse_git_url


class WorkspaceScanWorker(QThread):
    # Signals
    progress_updated = Signal(int, int, str)  # current, total, repo_path
    log_emitted = Signal(str)  # log messages
    finished = Signal(list, bool)  # results, was_cancelled
    error_occurred = Signal(str)

    def __init__(self, workspace_path: Path, recursive: bool, parent: Any = None) -> None:
        super().__init__(parent)
        self.workspace_path: Path = workspace_path
        self.recursive: bool = recursive
        self.git_service: GitService = GitService()
        self._is_cancelled: bool = False

    def cancel(self) -> None:
        self._is_cancelled = True
        self.log_emitted.emit("Cancellation requested. Stopping scan...")

    def run(self) -> None:
        try:
            self.log_emitted.emit(f"Scanning directory: {self.workspace_path}")
            candidate_dirs = self._find_candidate_directories()

            if getattr(self, "_is_cancelled"):  # noqa: B009
                self.finished.emit([], True)
                return

            self.log_emitted.emit(f"Found {len(candidate_dirs)} candidate directories. Inspecting Git properties...")

            results = []
            total = len(candidate_dirs)

            # Use ThreadPoolExecutor to run check processes concurrently (max 4)
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(self._inspect_repo, p): p for p in candidate_dirs}

                for completed, future in enumerate(futures, start=1):
                    if getattr(self, "_is_cancelled"):  # noqa: B009
                        break

                    try:
                        res = future.result()
                        if res:
                            results.append(res)
                    except Exception as e:
                        self.log_emitted.emit(f"Error inspecting {futures[future]}: {e}")

                    self.progress_updated.emit(completed, total, str(futures[future]))

            if getattr(self, "_is_cancelled"):  # noqa: B009
                self.log_emitted.emit("Workspace scan cancelled by user.")
                self.finished.emit([], True)
            else:
                self.log_emitted.emit(f"Workspace scan complete. Detected {len(results)} Git repositories.")
                self.finished.emit(results, False)

        except Exception as e:
            self.error_occurred.emit(str(e))

    def _find_candidate_directories(self) -> list[Path]:
        results = []
        visited = set()

        stack = [(self.workspace_path, 0)]
        visited.add(self.workspace_path.resolve())

        exclude_names = {
            ".git",
            ".venv",
            "node_modules",
            "dist",
            "build",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".cache",
        }
        max_depth = 3

        while stack:
            if getattr(self, "_is_cancelled"):  # noqa: B009
                break

            curr, depth = stack.pop()

            # If the current folder is a git repository, stop traversing inside it
            is_git = (curr / ".git").exists() or self.git_service.is_git_repository(curr)
            if is_git and curr != self.workspace_path:
                results.append(curr)
                continue

            # Stop if not recursive and we are beyond root level subdirs
            if not getattr(self, "recursive") and depth > 0:  # noqa: B009
                continue

            if depth >= max_depth:
                continue

            try:
                # Use os.scandir for highly efficient directory listings
                with os.scandir(curr) as it:
                    for entry in it:
                        if getattr(self, "_is_cancelled"):  # noqa: B009
                            break
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name in exclude_names:
                                continue

                            child_path = Path(entry.path)
                            resolved = child_path.resolve()
                            if resolved in visited:
                                continue
                            visited.add(resolved)

                            stack.append((child_path, depth + 1))
            except PermissionError:
                pass

        return results

    def _inspect_repo(self, path: Path) -> dict[str, Any] | None:
        if self._is_cancelled:
            return None

        if not self.git_service.is_git_repository(path):
            return None

        try:
            # 1. Remote Origin URL
            cp_url = self.git_service._run_git(path, ["remote", "get-url", "origin"])
            origin_url = cp_url.stdout.strip() if cp_url.returncode == 0 else None

            # 2. Current branch
            cp_branch = self.git_service._run_git(path, ["rev-parse", "--abbrev-ref", "HEAD"])
            branch = cp_branch.stdout.strip() if cp_branch.returncode == 0 else None
            detached_head = branch == "HEAD"

            # 3. Upstream branch
            upstream = None
            ahead = None
            behind = None
            if branch and not detached_head:
                cp_up = self.git_service._run_git(path, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
                if cp_up.returncode == 0:
                    upstream = cp_up.stdout.strip()

                    # 4. Ahead / Behind
                    cp_ab = self.git_service._run_git(
                        path, ["rev-list", "--left-right", "--count", f"HEAD...{upstream}"]
                    )
                    if cp_ab.returncode == 0:
                        parts = cp_ab.stdout.strip().split()
                        ahead = int(parts[0]) if len(parts) > 0 else 0
                        behind = int(parts[1]) if len(parts) > 1 else 0

            # 5. Dirty check
            cp_status = self.git_service._run_git(path, ["status", "--porcelain"])
            is_dirty = bool(cp_status.stdout.strip())

            # Determine local status
            if not origin_url:
                status = "NO_REMOTE"
                msg = "No remote origin configured"
            elif detached_head:
                status = "DETACHED_HEAD"
                msg = "HEAD is detached"
            elif not upstream:
                status = "NO_UPSTREAM"
                msg = "No tracking upstream branch"
            elif is_dirty:
                status = "DIRTY"
                msg = "Local changes present"
            elif ahead is not None and behind is not None:
                if ahead > 0 and behind > 0:
                    status = "DIVERGED"
                    msg = "Local and remote have diverged"
                elif ahead > 0:
                    status = "AHEAD"
                    msg = "Local commits not pushed"
                elif behind > 0:
                    status = "BEHIND"
                    msg = "Remote commits not pulled"
                else:
                    status = "UP_TO_DATE"
                    msg = "Up to date"
            else:
                status = "UP_TO_DATE"
                msg = "Up to date"

            # Parse Remote
            hosting = "No remote"
            owner = "No remote"
            repo_name = path.name

            if origin_url:
                parsed = parse_git_url(origin_url)
                if parsed:
                    host = parsed["host"]
                    owner = parsed["owner"]
                    repo_name = parsed["repo"]
                    if "github.com" in host.lower():
                        hosting = "GitHub"
                    elif "gitlab.com" in host.lower():
                        hosting = "GitLab"
                    elif "bitbucket.org" in host.lower():
                        hosting = "Bitbucket"
                    else:
                        hosting = host
                else:
                    hosting = "Custom"
                    owner = "Unknown"
                    repo_name = path.name

            return {
                "path": path,
                "name": path.name,
                "is_git": True,
                "branch": branch,
                "upstream": upstream,
                "origin_url": origin_url,
                "hosting": hosting,
                "owner": owner,
                "repo_name": repo_name,
                "status": status,
                "ahead": ahead,
                "behind": behind,
                "is_dirty": is_dirty,
                "message": msg,
            }

        except Exception as e:
            # Fallback for failed/broken repos
            return {
                "path": path,
                "name": path.name,
                "is_git": True,
                "branch": None,
                "upstream": None,
                "origin_url": None,
                "hosting": "Unknown",
                "owner": "Unknown",
                "repo_name": path.name,
                "status": "FAILED",
                "ahead": None,
                "behind": None,
                "is_dirty": False,
                "message": f"Failed to inspect git repository: {e}",
            }
