from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParsedGitUrl:
    """Represents the parsed identity of a Git remote URL."""

    host: str
    owner: str
    repo: str
    original_url: str

    def matches(self, expected_owner: str, expected_repo: str | None = None, expected_host: str = "github.com") -> bool:
        """Compares host, owner, and optional repository name strictly with case-insensitivity."""
        host_ok = self.host.lower() == expected_host.lower()
        owner_ok = self.owner.lower() == expected_owner.lower()
        repo_ok = (expected_repo is None) or (self.repo.lower() == expected_repo.lower())
        return host_ok and owner_ok and repo_ok

    def to_dict(self) -> dict[str, str]:
        return {"host": self.host, "owner": self.owner, "repo": self.repo}

    def __eq__(self, other: object) -> bool:
        if isinstance(other, dict):
            return self.to_dict() == other
        if isinstance(other, ParsedGitUrl):
            return (self.host, self.owner, self.repo) == (other.host, other.owner, other.repo)
        return False

    def __hash__(self) -> int:
        return hash((self.host.lower(), self.owner, self.repo))

    def __getitem__(self, key: str) -> str:
        if key == "host":
            return self.host
        if key == "owner":
            return self.owner
        if key == "repo":
            return self.repo
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


def parse_git_url(url: str) -> ParsedGitUrl | None:
    """
    Parses a Git remote URL and extracts hosting domain, owner/organization, and repository name.
    Handles HTTPS, SSH, SCP-like, and custom git URLs.
    """
    if not url:
        return None
    raw_url = url.strip()

    # Normalize: strip trailing slashes and .git suffix repeatedly to handle .git/
    cleaned_url = raw_url
    while cleaned_url.endswith("/") or cleaned_url.lower().endswith(".git"):
        if cleaned_url.endswith("/"):
            cleaned_url = cleaned_url[:-1]
        elif cleaned_url.lower().endswith(".git"):
            cleaned_url = cleaned_url[:-4]

    # 1. HTTP/HTTPS protocols: http[s]://[user@][host][:port]/[owner]/[repo]
    http_match = re.match(r"^https?://(?:[^@]+@)?([^/:]+)(?::\d+)?/(.+)$", cleaned_url, re.IGNORECASE)
    if http_match:
        host = http_match.group(1).lower()
        path = http_match.group(2).strip("/")
        parts = path.split("/")
        if len(parts) >= 2:
            owner = "/".join(parts[:-1])
            repo = parts[-1]
            return ParsedGitUrl(host=host, owner=owner, repo=repo, original_url=raw_url)

    # 2. SSH Protocol URL: ssh://[git@][host][:port]/[owner]/[repo]
    ssh_proto_match = re.match(r"^ssh://(?:[^@]+@)?([^/:]+)(?::\d+)?/(.+)$", cleaned_url, re.IGNORECASE)
    if ssh_proto_match:
        host = ssh_proto_match.group(1).lower()
        path = ssh_proto_match.group(2).strip("/")
        parts = path.split("/")
        if len(parts) >= 2:
            owner = "/".join(parts[:-1])
            repo = parts[-1]
            return ParsedGitUrl(host=host, owner=owner, repo=repo, original_url=raw_url)

    # 3. SCP-like SSH: [git@][host]:[owner]/[repo]
    if "://" not in cleaned_url:
        scp_match = re.match(r"^(?:[^@]+@)?([^/:]+):(.+)$", cleaned_url)
        if scp_match:
            host = scp_match.group(1).lower()
            path = scp_match.group(2).strip("/")
            parts = path.split("/")
            if len(parts) >= 2:
                owner = "/".join(parts[:-1])
                repo = parts[-1]
                return ParsedGitUrl(host=host, owner=owner, repo=repo, original_url=raw_url)

    return None
