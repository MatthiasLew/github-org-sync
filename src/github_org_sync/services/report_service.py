import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from github_org_sync.models.sync_result import SyncResult


def _scrub_secrets(text: str) -> str:
    """Redacts potential GitHub CLI tokens from error outputs."""
    import re
    return re.sub(r"gh[op]_[a-zA-Z0-9]+", "[REDACTED_TOKEN]", text)


class ReportService:
    @staticmethod
    def get_app_data_dir() -> Path:
        """
        Returns the cross-platform application data directory.
        Windows: C:\\Users\\<user>\\AppData\\Roaming\\github-org-sync
        Linux/macOS: ~/.config/github-org-sync
        """
        if os.name == "nt":
            appdata = os.environ.get("APPDATA")
            if appdata:
                return Path(appdata) / "github-org-sync"
        return Path.home() / ".config" / "github-org-sync"

    @classmethod
    def get_reports_dir(cls) -> Path:
        """Returns the directory where reports are stored."""
        path = cls.get_app_data_dir() / "reports"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def get_config_path(cls) -> Path:
        """Returns the path to the config file."""
        path = cls.get_app_data_dir()
        path.mkdir(parents=True, exist_ok=True)
        return path / "config.json"

    @classmethod
    def generate_reports(
        cls,
        organization: str,
        workspace: Path,
        auth_user: str,
        protocol: str,
        options: dict[str, Any],
        results: list[SyncResult],
    ) -> tuple[Path, Path]:
        """
        Generates both JSON and Markdown reports and saves them to the reports directory.
        Returns (json_report_path, md_report_path).
        """
        reports_dir = cls.get_reports_dir()
        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y%m%d-%H%M%S")

        json_filename = f"report-{organization}-{timestamp_str}.json"
        md_filename = f"report-{organization}-{timestamp_str}.md"

        json_path = reports_dir / json_filename
        md_path = reports_dir / md_filename

        # Prepare Report Data
        report_data = {
            "timestamp": timestamp.isoformat(),
            "organization": _scrub_secrets(organization),
            "workspace": str(workspace),
            "authenticated_user": _scrub_secrets(auth_user),
            "selected_protocol": protocol,
            "options": options,
            "results": [
                {
                    "repository": r.repo_name,
                    "operation": r.performed_action,
                    "before_status": r.before_status,
                    "after_status": r.after_status,
                    "duration": round(r.duration, 3),
                    "result": _scrub_secrets(r.result or ""),
                    "error": _scrub_secrets(r.error or ""),
                }
                for r in results
            ],
        }

        # 1. Save JSON Report
        with json_path.open("w", encoding="utf-8") as fh:
            json.dump(report_data, fh, indent=2, ensure_ascii=False)

        # 2. Save Markdown Report
        md_lines = [
            f"# Sync Report - {_scrub_secrets(organization)}",
            "",
            f"- **Timestamp:** {timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Organization:** {_scrub_secrets(organization)}",
            f"- **Workspace:** `{workspace}`",
            f"- **Authenticated User:** {_scrub_secrets(auth_user)}",
            f"- **Selected Protocol:** {protocol.upper()}",
            "",
            "## Sync Options",
        ]
        for opt_key, opt_val in options.items():
            md_lines.append(f"- **{opt_key}:** {opt_val}")

        md_lines.extend(
            [
                "",
                "## Repository Details",
                "",
                "| Repository | Operation | Before Status | After Status | Duration (s) | Result |",
                "| :--- | :--- | :--- | :--- | :--- | :--- |",
            ]
        )

        for r in results:
            status_symbol = "✅"
            if r.after_status in ("FAILED", "CONFLICT"):
                status_symbol = "❌"
            elif r.after_status in ("WRONG_REMOTE", "BLOCKED", "DIRTY", "DIVERGED"):
                status_symbol = "⚠️"

            res_msg = _scrub_secrets(r.result or "")
            if r.error:
                res_msg += f" (Error: {_scrub_secrets(r.error)})"

            md_lines.append(
                f"| {r.repo_name} | {r.performed_action} | {r.before_status} | {status_symbol} {r.after_status} | {r.duration:.2f} | {res_msg} |"
            )

        md_content = "\n".join(md_lines)
        with md_path.open("w", encoding="utf-8") as fh:
            fh.write(md_content)

        return json_path, md_path
