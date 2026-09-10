"""Unit tests for summary_analyzer module."""

from github_org_sync.services.summary_analyzer import (
    _extract_terms,
    _is_excluded,
    analyze_contributions,
)


def test_is_excluded() -> None:
    assert _is_excluded("MatthiasLew", "MatthiasLew")
    assert _is_excluded("matthiaslew", "MatthiasLew")
    assert not _is_excluded("other-org", "MatthiasLew")
    assert not _is_excluded("other-org", None)


def test_extract_terms() -> None:
    texts = [
        "Add authentication token support",
        "Fix authentication bypass vulnerability",
        "Refactor token parser and validator",
    ]
    terms = _extract_terms(texts, top_n=3)
    assert "token" in terms or "authentication" in terms
    assert "and" not in terms


def test_analyze_contributions_filtering() -> None:
    raw_data = {
        "user": "test-user",
        "month": "2026-08",
        "commit_contributions_by_repo": [
            {
                "name_with_owner": "org1/repo1",
                "owner": "org1",
                "primary_language": "Python",
                "commit_count": 10,
            },
            {
                "name_with_owner": "personal/repo2",
                "owner": "personal",
                "primary_language": "Rust",
                "commit_count": 5,
            },
        ],
        "pr_contributions_by_repo": [
            {
                "name_with_owner": "org1/repo1",
                "owner": "org1",
                "primary_language": "Python",
                "pr_count": 2,
            },
        ],
        "commits": [],
        "pull_requests": [
            {
                "repo_name_with_owner": "org1/repo1",
                "owner": "org1",
                "title": "Add async pipeline",
            },
        ],
    }

    # Case 1: Exclude 'personal'
    res = analyze_contributions(raw_data, excluded_owner="personal")
    assert res["total_commits"] == 10
    assert res["total_prs"] == 2
    assert "personal/repo2" not in res["repositories"]
    assert "org1/repo1" in res["repositories"]
    assert len(res["projects"]) == 1
    assert res["projects"][0]["name"] == "org1/repo1"

    # Case 2: Target org 'org1'
    res_org = analyze_contributions(raw_data, target_org="org1")
    assert res_org["total_commits"] == 10
    assert "org1/repo1" in res_org["repositories"]

    # Case 3: Target org 'non-existent'
    res_none = analyze_contributions(raw_data, target_org="other")
    assert res_none["total_commits"] == 0
    assert len(res_none["repositories"]) == 0
