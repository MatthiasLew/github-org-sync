from __future__ import annotations

import pytest

from github_org_sync.utils.git_url_parser import ParsedGitUrl, parse_git_url


@pytest.mark.unit
def test_parse_git_url_https() -> None:
    url = "https://github.com/my-org/my-repo.git"
    parsed = parse_git_url(url)
    assert parsed is not None
    assert parsed.host == "github.com"
    assert parsed.owner == "my-org"
    assert parsed.repo == "my-repo"
    assert parsed.matches("my-org", "my-repo", "github.com")


@pytest.mark.unit
def test_parse_git_url_trailing_slash_and_git() -> None:
    # url with .git and trailing slash
    url = "https://github.com/my-org/my-repo.git/"
    parsed = parse_git_url(url)
    assert parsed is not None
    assert parsed.repo == "my-repo"
    assert parsed.matches("my-org", "my-repo")

    # url with multiple trailing slashes
    url2 = "https://github.com/my-org/my-repo///"
    parsed2 = parse_git_url(url2)
    assert parsed2 is not None
    assert parsed2.repo == "my-repo"


@pytest.mark.unit
def test_parse_git_url_ssh_protocol() -> None:
    url = "ssh://git@github.com/my-org/my-repo.git"
    parsed = parse_git_url(url)
    assert parsed is not None
    assert parsed.host == "github.com"
    assert parsed.owner == "my-org"
    assert parsed.repo == "my-repo"
    assert parsed.matches("my-org", "my-repo")


@pytest.mark.unit
def test_parse_git_url_scp_syntax() -> None:
    url = "git@github.com:my-org/my-repo.git"
    parsed = parse_git_url(url)
    assert parsed is not None
    assert parsed.host == "github.com"
    assert parsed.owner == "my-org"
    assert parsed.repo == "my-repo"
    assert parsed.matches("my-org", "my-repo")


@pytest.mark.unit
def test_remote_identity_case_insensitivity() -> None:
    url = "HTTPS://GITHUB.COM/My-Org/My-Repo.GIT"
    parsed = parse_git_url(url)
    assert parsed is not None
    assert parsed.matches("my-org", "my-repo", "github.com")
    assert parsed.matches("MY-ORG", "MY-REPO", "GITHUB.COM")


@pytest.mark.unit
def test_remote_identity_good_owner_bad_repo() -> None:
    # Critical regression test: same owner, different repo
    url = "https://github.com/example-org/frontend.git"
    parsed = parse_git_url(url)
    assert parsed is not None
    assert parsed.matches("example-org", "frontend")
    # Must FAIL when expected repo is api-server
    assert not parsed.matches("example-org", "api-server")


@pytest.mark.unit
def test_remote_identity_bad_owner_good_repo() -> None:
    url = "https://github.com/wrong-org/my-repo.git"
    parsed = parse_git_url(url)
    assert parsed is not None
    assert not parsed.matches("my-org", "my-repo")


@pytest.mark.unit
def test_remote_identity_different_host() -> None:
    url = "https://gitlab.com/my-org/my-repo.git"
    parsed = parse_git_url(url)
    assert parsed is not None
    assert not parsed.matches("my-org", "my-repo", expected_host="github.com")
    assert parsed.matches("my-org", "my-repo", expected_host="gitlab.com")


@pytest.mark.unit
def test_parsed_git_url_backward_compatible_dict_access() -> None:
    parsed = ParsedGitUrl(host="github.com", owner="org", repo="repo", original_url="orig")
    assert parsed["host"] == "github.com"
    assert parsed["owner"] == "org"
    assert parsed["repo"] == "repo"
    assert parsed.get("host") == "github.com"
    assert parsed.get("missing", "default") == "default"
