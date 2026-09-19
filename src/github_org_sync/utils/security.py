from __future__ import annotations

import re

# Comprehensive patterns for secret tokens, credentials in URLs, and Authorization headers
_GITHUB_TOKEN_PATTERN = re.compile(r"gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+")
_URL_CREDENTIALS_PATTERN = re.compile(r"(https?://)([^:/@\s]+):([^/@\s]+)@")
_AUTHORIZATION_HEADER_PATTERN = re.compile(r"(?i)\b(bearer|token)\s+([A-Za-z0-9_\-\.]{12,})\b")


def scrub_secrets(text: str) -> str:
    """
    Central redaction scrubber that masks sensitive credentials in log messages,
    exception payloads, CLI output, and error reports.

    Redacts:
    - GitHub Personal Access Tokens (classic: ghp_, fine-grained: github_pat_)
    - GitHub OAuth and App tokens (gho_, ghu_, ghs_, ghr_)
    - HTTP basic auth credentials in Git and web URLs (https://user:token@github.com)
    - Authorization Bearer and token headers (Bearer <secret>)
    """
    if not text:
        return text

    # Redact GitHub API tokens
    redacted = _GITHUB_TOKEN_PATTERN.sub("[REDACTED_TOKEN]", text)

    # Redact embedded URL credentials
    redacted = _URL_CREDENTIALS_PATTERN.sub(r"\1\2:[REDACTED]@", redacted)

    # Redact Bearer / Authorization headers
    return _AUTHORIZATION_HEADER_PATTERN.sub(r"\1 [REDACTED_TOKEN]", redacted)


# Backwards compatibility alias
redact_secrets = scrub_secrets
