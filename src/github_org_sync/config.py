import json
from typing import Any

from github_org_sync.services.report_service import ReportService


class ConfigManager:
    DEFAULT_CONFIG = {
        "last_organization": "",
        "last_workspace": "",
        "use_ssh": False,
        "preserve_local_changes": True,
        "fetch_only": False,
        "dry_run": False,
        "include_archived": False,
        "include_forks": True,
        "window_width": 1000,
        "window_height": 700,
        "window_x": -1,
        "window_y": -1,
        "language": "pl",
        "theme": "System",
        "column_widths": [],
        "max_workers": 4,
    }

    def __init__(self) -> None:
        self.config_path = ReportService.get_config_path()

    def load(self) -> dict[str, Any]:
        """Loads config from file, or returns defaults if missing/corrupt."""
        if not self.config_path.exists():
            return self.DEFAULT_CONFIG.copy()

        try:
            with self.config_path.open(encoding="utf-8") as fh:
                data = json.load(fh)
                # Merge with defaults to ensure all keys are present
                config = self.DEFAULT_CONFIG.copy()
                config.update(data)
                return config
        except Exception:
            return self.DEFAULT_CONFIG.copy()

    def save(self, config: dict[str, Any]) -> None:
        """Saves current config back to disk."""
        try:
            # First load existing or start with empty
            current = self.load()
            current.update(config)

            with self.config_path.open("w", encoding="utf-8") as fh:
                json.dump(current, fh, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def save_workspace_cache(self, org_name: str, repos: list[Any]) -> None:
        """Saves current repository status metadata to a local JSON cache file."""
        from pathlib import Path

        if not org_name:
            return

        try:
            cache_path = Path(self.config_path).parent / f"cache_{org_name}.json"
            data = [
                {
                    "name": r.name,
                    "url": r.url,
                    "visibility": r.visibility,
                    "is_archived": r.is_archived,
                    "status": r.status,
                    "branch": r.branch,
                    "ahead": r.ahead,
                    "behind": r.behind,
                    "result": r.result,
                    "computed_hosting": getattr(r, "computed_hosting", "GitHub"),
                    "computed_owner": getattr(r, "computed_owner", ""),
                }
                for r in repos
            ]
            cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def load_workspace_cache(self, org_name: str) -> list[dict[str, Any]]:
        """Loads cached repository status metadata for the organization."""
        from pathlib import Path

        if not org_name:
            return []

        cache_path = Path(self.config_path).parent / f"cache_{org_name}.json"
        if not cache_path.exists():
            return []
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            return []
        except Exception:
            return []

