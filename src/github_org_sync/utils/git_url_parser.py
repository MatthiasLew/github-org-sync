import re


def parse_git_url(url: str) -> dict | None:
    """
    Parses a Git remote URL and extracts hosting domain, owner/organization, and repository name.
    Handles HTTPS, SSH, SCP-like, and custom git URLs.
    """
    if not url:
        return None
    url = url.strip()

    # Remove trailing slashes and .git suffix
    cleaned_url = url
    if cleaned_url.endswith("/"):
        cleaned_url = cleaned_url[:-1]
    if cleaned_url.endswith(".git"):
        cleaned_url = cleaned_url[:-4]

    # 1. HTTP/HTTPS protocols: http[s]://[user@][host][:port]/[owner]/[repo]
    http_match = re.match(r"^https?://(?:[^@]+@)?([^/:]+)(?::\d+)?/(.+)$", cleaned_url)
    if http_match:
        host = http_match.group(1)
        path = http_match.group(2)
        parts = path.split("/")
        if len(parts) >= 2:
            owner = "/".join(parts[:-1])
            repo = parts[-1]
            return {"host": host, "owner": owner, "repo": repo}

    # 2. SSH Protocol URL: ssh://[git@][host][:port]/[owner]/[repo]
    ssh_proto_match = re.match(r"^ssh://(?:[^@]+@)?([^/:]+)(?::\d+)?/(.+)$", cleaned_url)
    if ssh_proto_match:
        host = ssh_proto_match.group(1)
        path = ssh_proto_match.group(2)
        parts = path.split("/")
        if len(parts) >= 2:
            owner = "/".join(parts[:-1])
            repo = parts[-1]
            return {"host": host, "owner": owner, "repo": repo}

    # 3. SCP-like SSH: [git@][host]:[owner]/[repo]
    scp_match = re.match(r"^(?:[^@]+@)?([^/:]+):(.+)$", cleaned_url)
    if scp_match:
        host = scp_match.group(1)
        path = scp_match.group(2)
        parts = path.split("/")
        if len(parts) >= 2:
            owner = "/".join(parts[:-1])
            repo = parts[-1]
            return {"host": host, "owner": owner, "repo": repo}

    return None
