import pytest

from github_org_sync.utils.git_url_parser import parse_git_url


@pytest.mark.unit
def test_parse_git_url_https_github() -> None:
    res = parse_git_url("https://github.com/OWNER/REPOSITORY.git")
    assert res == {"host": "github.com", "owner": "OWNER", "repo": "REPOSITORY"}


@pytest.mark.unit
def test_parse_git_url_ssh_github() -> None:
    res = parse_git_url("git@github.com:OWNER/REPOSITORY.git")
    assert res == {"host": "github.com", "owner": "OWNER", "repo": "REPOSITORY"}


@pytest.mark.unit
def test_parse_git_url_ssh_url() -> None:
    res = parse_git_url("ssh://git@github.com/OWNER/REPOSITORY.git")
    assert res == {"host": "github.com", "owner": "OWNER", "repo": "REPOSITORY"}


@pytest.mark.unit
def test_parse_git_url_gitlab() -> None:
    res = parse_git_url("https://gitlab.com/group/subgroup/repo.git")
    assert res == {"host": "gitlab.com", "owner": "group/subgroup", "repo": "repo"}


@pytest.mark.unit
def test_parse_git_url_bitbucket() -> None:
    res = parse_git_url("git@bitbucket.org:owner/repo.git")
    assert res == {"host": "bitbucket.org", "owner": "owner", "repo": "repo"}


@pytest.mark.unit
def test_parse_git_url_custom_host() -> None:
    res = parse_git_url("https://mycustomgit.com/owner/repo")
    assert res == {"host": "mycustomgit.com", "owner": "owner", "repo": "repo"}


@pytest.mark.unit
def test_parse_git_url_no_git_suffix() -> None:
    res = parse_git_url("https://github.com/OWNER/REPOSITORY")
    assert res == {"host": "github.com", "owner": "OWNER", "repo": "REPOSITORY"}


@pytest.mark.unit
def test_parse_git_url_invalid_remote() -> None:
    res = parse_git_url("not_a_url")
    assert res is None


@pytest.mark.unit
def test_parse_git_url_empty() -> None:
    assert parse_git_url("") is None
    assert parse_git_url("   ") is None


@pytest.mark.unit
def test_parse_git_url_unicode() -> None:
    res = parse_git_url("https://github.com/zażółć/gęślą-jaźń.git")
    assert res == {"host": "github.com", "owner": "zażółć", "repo": "gęślą-jaźń"}


@pytest.mark.unit
def test_parse_git_url_unusual_name() -> None:
    res = parse_git_url("git@github.com:owner-name/repo_name.with-dots.git")
    assert res == {"host": "github.com", "owner": "owner-name", "repo": "repo_name.with-dots"}
