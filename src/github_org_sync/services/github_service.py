import json
import shutil
import subprocess
from typing import Any
from github_org_sync.models.repository import Repository

class GitHubServiceError(Exception):
    pass

class GitHubCLIMissingError(GitHubServiceError):
    pass

class GitHubAuthError(GitHubServiceError):
    pass

class OrganizationNotFoundError(GitHubServiceError):
    pass

class GitHubService:
    def __init__(self) -> None:
        self.gh_path = shutil.which("gh")

    def check_cli_installed(self) -> str:
        """
        Checks if gh CLI is installed and returns its version.
        Raises GitHubCLIMissingError if not installed.
        """
        if not self.gh_path:
            raise GitHubCLIMissingError("GitHub CLI (gh) is not installed or not in system PATH.")
            
        try:
            cp = subprocess.run([self.gh_path, "--version"], text=True, capture_output=True, check=True)
            # The first line usually contains the version, e.g. "gh version 2.30.0"
            first_line = cp.stdout.splitlines()[0] if cp.stdout else "gh version unknown"
            return first_line
        except (subprocess.SubprocessError, IndexError) as e:
            raise GitHubCLIMissingError(f"Failed to check GitHub CLI version: {e}") from e

    def check_auth_status(self) -> str:
        """
        Checks gh CLI authentication status.
        Raises GitHubAuthError if not authenticated.
        Returns logged-in user name/details.
        """
        if not self.gh_path:
            raise GitHubCLIMissingError("GitHub CLI (gh) is not installed.")
            
        try:
            # gh auth status can exit with code 1 if not logged in
            cp = subprocess.run([self.gh_path, "auth", "status"], text=True, capture_output=True)
            output = (cp.stdout or "") + (cp.stderr or "")
            
            if cp.returncode != 0:
                raise GitHubAuthError(f"GitHub CLI authentication check failed (exit code {cp.returncode}):\n{output}")
                
            # Parse user name from output if possible
            # e.g., "Logged in to github.com account MatthiasLew"
            return output.strip()
        except subprocess.SubprocessError as e:
            raise GitHubAuthError(f"Subprocess error checking GitHub CLI auth status: {e}") from e

    def list_repositories(self, org_name: str) -> list[Repository]:
        """
        Lists all repositories for the given organization name.
        """
        if not self.gh_path:
            raise GitHubCLIMissingError("GitHub CLI (gh) is not installed.")
            
        try:
            # Fetch repos.
            # visibility is supported in gh CLI repo list json fields
            cmd = [
                self.gh_path,
                "repo",
                "list",
                org_name,
                "--limit",
                "1000",
                "--json",
                "name,url,sshUrl,isArchived,isFork,defaultBranchRef,visibility",
            ]
            cp = subprocess.run(cmd, text=True, capture_output=True)
            
            if cp.returncode != 0:
                stderr_lower = cp.stderr.lower()
                if "could not resolve to an organization" in stderr_lower or "not found" in stderr_lower:
                    raise OrganizationNotFoundError(f"Organization '{org_name}' not found on GitHub.")
                if "authentication" in stderr_lower or "login" in stderr_lower:
                    raise GitHubAuthError("Authentication required or token expired. Run `gh auth login`.")
                raise GitHubServiceError(f"GitHub CLI failed to list repositories:\n{cp.stderr}")
                
            data = json.loads(cp.stdout or "[]")
            repos = []
            for item in data:
                # visibility might not be returned in some versions or structures, fallback to private/public
                visibility = item.get("visibility", "private").lower()
                
                # defaultBranchRef is an object: {"name": "main"}
                default_branch_ref = item.get("defaultBranchRef") or {}
                default_branch = default_branch_ref.get("name", "main")
                
                repos.append(
                    Repository(
                        name=item["name"],
                        url=item.get("url", ""),
                        ssh_url=item.get("sshUrl", ""),
                        is_archived=item.get("isArchived", False),
                        is_fork=item.get("isFork", False),
                        default_branch=default_branch,
                        visibility=visibility,
                    )
                )
            return repos
            
        except subprocess.SubprocessError as e:
            raise GitHubServiceError(f"Subprocess error listing repositories: {e}") from e
        except json.JSONDecodeError as e:
            raise GitHubServiceError(f"Failed to parse GitHub CLI response: {e}") from e
