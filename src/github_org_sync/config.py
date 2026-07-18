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
