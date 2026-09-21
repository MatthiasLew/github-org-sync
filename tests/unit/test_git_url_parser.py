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


@pytest.mark.unit
def test_parsed_git_url_methods_and_edge_cases() -> None:
    u1 = parse_git_url("https://github.com/owner/repo.git/")
    assert u1 is not None
    assert u1.host == "github.com"
    assert u1.owner == "owner"
    assert u1.repo == "repo"

    u2 = parse_git_url("git@github.com:owner/repo")
    assert u2 is not None
    assert u1 == u2
    assert u1 == {"host": "github.com", "owner": "owner", "repo": "repo"}
    assert (u1 == "not a git url") is False

    # Hash
    assert hash(u1) == hash(u2)

    # __getitem__ and get
    assert u1["host"] == "github.com"
    assert u1["owner"] == "owner"
    assert u1["repo"] == "repo"
    with pytest.raises(KeyError):
        _ = u1["nonexistent"]
    assert u1.get("host") == "github.com"
    assert u1.get("invalid", "default_val") == "default_val"

    # matches
    assert u1.matches(expected_owner="owner", expected_repo="repo", expected_host="github.com") is True
    assert u1.matches(expected_owner="owner", expected_repo=None) is True
    assert u1.matches(expected_owner="wrong_owner") is False
    assert u1.matches(expected_owner="owner", expected_repo="wrong_repo") is False
    assert u1.matches(expected_owner="owner", expected_host="gitlab.com") is False

    # Incomplete paths (len(parts) < 2)
    assert parse_git_url("https://github.com/onepart") is None
    assert parse_git_url("ssh://git@github.com/onepart") is None
    assert parse_git_url("git@github.com:onepart") is None
