"""GitHub user contribution fetching and summary report generation service."""

import json
import re
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from github_org_sync.services.summary_analyzer import analyze_contributions
from github_org_sync.utils.process import run_process
from github_org_sync.utils.security import scrub_secrets

_scrub_secrets = scrub_secrets


class WorkSummaryError(Exception):
    """Base error for work summary operations."""


class GHNotInstalledError(WorkSummaryError):
    """gh CLI is missing."""


class GHNotAuthorizedError(WorkSummaryError):
    """gh CLI is not logged in."""


GRAPHQL_QUERY = """
query($login:String!,$from:DateTime!,$to:DateTime!){
  user(login:$login){
    contributionsCollection(from:$from,to:$to){
      totalCommitContributions
      totalPullRequestContributions
      commitContributionsByRepository(maxRepositories:100){
        repository{nameWithOwner owner{login} primaryLanguage{name}}
        contributions(first:100){
          nodes{
            commitCount
            isRestricted
            occurredAt
          }
          totalCount
        }
      }
      pullRequestContributionsByRepository(maxRepositories:100){
        repository{nameWithOwner owner{login} primaryLanguage{name}}
        contributions(first:100){
          nodes{
            pullRequest{title url}
            occurredAt
          }
          totalCount
        }
      }
      pullRequestContributions(first:100){
        nodes{
          occurredAt
          pullRequest{title body url repository{nameWithOwner owner{login}}}
        }
        pageInfo{hasNextPage endCursor}
      }
    }
  }
}
"""


_SENTINEL = object()


class WorkSummaryService:
    """Service to fetch monthly contributions and build summaries."""

    def __init__(self, gh_path: str | None | object = _SENTINEL) -> None:
        if gh_path is _SENTINEL:
            self.gh_path = shutil.which("gh")
        else:
            self.gh_path = gh_path if isinstance(gh_path, str) else None

    def check_gh(self) -> bool:
        """Check if gh CLI is installed."""
        return bool(self.gh_path)

    def _run_gh(self, args: list[str]) -> str:
        """Run a gh command with run_process and return stdout."""
        if not self.gh_path:
            raise GHNotInstalledError("GitHub CLI (gh) not found. Install and run `gh auth login`.")
        try:
            cp = run_process([self.gh_path, *args])
            if cp.returncode != 0:
                err = cp.stderr or ""
                lowered = err.lower()
                if "unauthorized" in lowered or "not logged" in lowered or "authentication" in lowered:
                    raise GHNotAuthorizedError(f"gh not authorized: {_scrub_secrets(err)}")
                raise WorkSummaryError(f"gh command failed: {_scrub_secrets(err)}")
            return cp.stdout or ""
        except (subprocess.SubprocessError, OSError) as exc:
            raise WorkSummaryError(f"Failed to execute gh CLI: {_scrub_secrets(str(exc))}") from exc

    def get_current_user(self) -> str:
        """Return the login of the currently authenticated GitHub user."""
        out = self._run_gh(["api", "user", "--jq", ".login"])
        return out.strip()

    @staticmethod
    def parse_month(month_str: str) -> tuple[int, int]:
        """Parse YYYY-MM string to (year, month)."""
        if not re.fullmatch(r"\d{4}-\d{2}", month_str):
            raise ValueError(f"Month must be YYYY-MM, got {month_str!r}")
        year, month = map(int, month_str.split("-"))
        if not 1 <= month <= 12:
            raise ValueError(f"Invalid month: {month_str!r}")
        return year, month

    @staticmethod
    def month_bounds(year: int, month: int) -> tuple[str, str]:
        """Return ISO DateTime bounds for a month in UTC."""
        start = datetime(year, month, 1, 0, 0, 0, tzinfo=UTC)
        if month == 12:
            end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=UTC)
        else:
            end = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=UTC)
        end_inclusive = end - timedelta(seconds=1)
        return start.isoformat(), end_inclusive.isoformat()

    def fetch_contributions(self, login: str, year: int, month: int) -> dict[str, Any]:
        """Fetch raw commit and PR contributions for a month via GraphQL."""
        from_dt, to_dt = self.month_bounds(year, month)
        out = self._run_gh(
            [
                "api",
                "graphql",
                "-f",
                f"query={GRAPHQL_QUERY}",
                "-f",
                f"login={login}",
                "-f",
                f"from={from_dt}",
                "-f",
                f"to={to_dt}",
            ]
        )
        try:
            data = json.loads(out)
        except json.JSONDecodeError as exc:
            raise WorkSummaryError(f"Invalid JSON from gh: {_scrub_secrets(str(exc))}") from exc

        if data.get("errors"):
            raise WorkSummaryError(f"GitHub GraphQL errors: {_scrub_secrets(str(data['errors']))}")
        if not data.get("data", {}).get("user"):
            raise WorkSummaryError("No user data returned from GitHub.")

        collection = data["data"]["user"]["contributionsCollection"]
        month_str = f"{year:04d}-{month:02d}"
        result: dict[str, Any] = {
            "user": login,
            "month": month_str,
            "from": from_dt,
            "to": to_dt,
            "commit_contributions_by_repo": [],
            "pr_contributions_by_repo": [],
            "commits": [],
            "pull_requests": [],
        }

        for item in collection.get("commitContributionsByRepository", []):
            repo = item.get("repository", {})
            commit_sum = sum(n.get("commitCount", 0) for n in item.get("contributions", {}).get("nodes", []))
            result["commit_contributions_by_repo"].append(
                {
                    "name_with_owner": repo.get("nameWithOwner", ""),
                    "owner": repo.get("owner", {}).get("login", ""),
                    "primary_language": (repo.get("primaryLanguage") or {}).get("name"),
                    "commit_count": commit_sum,
                }
            )

        for item in collection.get("pullRequestContributionsByRepository", []):
            repo = item.get("repository", {})
            pr_nodes = item.get("contributions", {}).get("nodes", [])
            result["pr_contributions_by_repo"].append(
                {
                    "name_with_owner": repo.get("nameWithOwner", ""),
                    "owner": repo.get("owner", {}).get("login", ""),
                    "primary_language": (repo.get("primaryLanguage") or {}).get("name"),
                    "pr_count": item.get("contributions", {}).get("totalCount", len(pr_nodes)),
                }
            )

        for node in collection.get("pullRequestContributions", {}).get("nodes", []):
            pr = node.get("pullRequest") or {}
            repo = pr.get("repository") or {}
            result["pull_requests"].append(
                {
                    "repo_name_with_owner": repo.get("nameWithOwner", ""),
                    "owner": repo.get("owner", {}).get("login", ""),
                    "title": pr.get("title", ""),
                    "body": pr.get("body", ""),
                    "url": pr.get("url", ""),
                    "occurred_at": node.get("occurredAt", ""),
                }
            )

        return result

    def generate_summary(
        self,
        login: str,
        year: int,
        month: int,
        excluded_owner: str | None = None,
        target_org: str | None = None,
    ) -> dict[str, Any]:
        """Fetch and analyze contributions in one go."""
        raw_data = self.fetch_contributions(login, year, month)
        return analyze_contributions(
            raw_data,
            excluded_owner=excluded_owner,
            target_org=target_org,
        )

    @staticmethod
    def generate_markdown(report: dict[str, Any]) -> str:
        """Return a formatted Markdown report."""
        month = report.get("month", "")
        user = report.get("user", "")
        projects = report.get("projects", [])
        main = report.get("main_areas", [])
        work = report.get("top_work", [])
        learned = report.get("what_learned", [])

        lines = [
            f"# Miesięczne podsumowanie pracy — {month}",
            "",
            f"**Konto GitHub:** {user}",
            f"**Okres:** {month}",
            "",
            "## Krótkie statystyki",
            "",
            f"- **Repozytoria:** {len(report.get('repositories', []))}",
            f"- **Commity:** {report.get('total_commits', 0)}",
            f"- **PR-y:** {report.get('total_prs', 0)}",
            "",
            "## Projekty",
            "",
        ]

        for p in projects:
            lang = f" ({p['language']})" if p.get("language") else ""
            lines.append(f"- **{p['name']}**{lang} — commity: {p['commits']}, PR-y: {p['prs']}")

        lines.extend(["", "## Główne obszary zmian", ""])
        for item in main:
            lines.append(f"- {item}")

        lines.extend(["", "## Najważniejsze wykonane prace", ""])
        for item in work:
            lines.append(item)

        lines.extend(["", "## Czego się nauczyłem / Kluczowe technologie", ""])
        for item in learned:
            lines.append(item)

        return "\n".join(lines)

    @staticmethod
    def generate_json(report: dict[str, Any]) -> str:
        """Return raw data used by the report as formatted JSON."""
        return json.dumps(report, indent=2, ensure_ascii=False)

    def save_reports(
        self,
        report: dict[str, Any],
        md_path: Path | str | None = None,
        json_path: Path | str | None = None,
    ) -> tuple[Path | None, Path | None]:
        """Save Markdown and/or JSON reports to disk."""
        saved_md: Path | None = None
        saved_json: Path | None = None

        if md_path:
            p_md = Path(md_path)
            p_md.parent.mkdir(parents=True, exist_ok=True)
            p_md.write_text(self.generate_markdown(report), encoding="utf-8")
            saved_md = p_md

        if json_path:
            p_json = Path(json_path)
            p_json.parent.mkdir(parents=True, exist_ok=True)
            p_json.write_text(self.generate_json(report), encoding="utf-8")
            saved_json = p_json

        return saved_md, saved_json
