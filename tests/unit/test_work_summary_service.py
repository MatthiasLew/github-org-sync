"""Unit tests for work_summary_service module."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from github_org_sync.services.work_summary_service import (
    GHNotInstalledError,
    WorkSummaryService,
)


def test_parse_month() -> None:
    year, month = WorkSummaryService.parse_month("2026-08")
    assert year == 2026
    assert month == 8

    with pytest.raises(ValueError):
        WorkSummaryService.parse_month("invalid-month")

    with pytest.raises(ValueError):
        WorkSummaryService.parse_month("2026-13")


def test_month_bounds() -> None:
    start, end = WorkSummaryService.month_bounds(2026, 8)
    assert start == "2026-08-01T00:00:00+00:00"
    assert end == "2026-08-31T23:59:59+00:00"

    start_dec, end_dec = WorkSummaryService.month_bounds(2026, 12)
    assert start_dec == "2026-12-01T00:00:00+00:00"
    assert end_dec == "2026-12-31T23:59:59+00:00"


def test_service_without_gh() -> None:
    service = WorkSummaryService(gh_path=None)
    assert not service.check_gh()
    with pytest.raises(GHNotInstalledError):
        service._run_gh(["version"])


def test_fetch_contributions_success() -> None:
    service = WorkSummaryService(gh_path="/usr/bin/gh")
    mock_payload = {
        "data": {
            "user": {
                "contributionsCollection": {
                    "totalCommitContributions": 15,
                    "totalPullRequestContributions": 3,
                    "commitContributionsByRepository": [
                        {
                            "repository": {
                                "nameWithOwner": "org/repo-a",
                                "owner": {"login": "org"},
                                "primaryLanguage": {"name": "Python"},
                            },
                            "contributions": {"nodes": [{"commitCount": 15}]},
                        }
                    ],
                    "pullRequestContributionsByRepository": [
                        {
                            "repository": {
                                "nameWithOwner": "org/repo-a",
                                "owner": {"login": "org"},
                                "primaryLanguage": {"name": "Python"},
                            },
                            "contributions": {
                                "nodes": [{"pullRequest": {"title": "PR 1", "url": "url1"}}],
                                "totalCount": 1,
                            },
                        }
                    ],
                    "pullRequestContributions": {
                        "nodes": [
                            {
                                "occurredAt": "2026-08-10T10:00:00Z",
                                "pullRequest": {
                                    "title": "PR 1",
                                    "body": "Body",
                                    "url": "url1",
                                    "repository": {"nameWithOwner": "org/repo-a", "owner": {"login": "org"}},
                                },
                            }
                        ]
                    },
                }
            }
        }
    }

    with patch.object(service, "_run_gh", return_value=json.dumps(mock_payload)):
        res = service.fetch_contributions("test-user", 2026, 8)
        assert res["user"] == "test-user"
        assert res["month"] == "2026-08"
        assert len(res["commit_contributions_by_repo"]) == 1
        assert res["commit_contributions_by_repo"][0]["commit_count"] == 15
        assert len(res["pull_requests"]) == 1
        assert res["pull_requests"][0]["title"] == "PR 1"


def test_generate_and_save_reports(tmp_path: Path) -> None:
    service = WorkSummaryService(gh_path="/mock/gh")
    report = {
        "user": "test-user",
        "month": "2026-08",
        "repositories": ["org/repo-a"],
        "total_commits": 12,
        "total_prs": 4,
        "projects": [{"name": "org/repo-a", "commits": 12, "prs": 4, "language": "Python"}],
        "main_areas": ["Python", "automation"],
        "top_work": ["- [org/repo-a] Implemented report pipeline"],
        "what_learned": ["- Python 3.11"],
    }

    md = service.generate_markdown(report)
    assert "# Miesięczne podsumowanie pracy — 2026-08" in md
    assert "Commity:** 12" in md

    js = service.generate_json(report)
    assert '"total_commits": 12' in js

    md_file = tmp_path / "out.md"
    json_file = tmp_path / "out.json"
    saved_md, saved_json = service.save_reports(report, md_path=md_file, json_path=json_file)

    assert saved_md is not None and saved_md.exists()
    assert saved_json is not None and saved_json.exists()
    assert md_file.read_text(encoding="utf-8") == md
