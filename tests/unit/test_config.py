from pathlib import Path
from unittest.mock import patch

import pytest

from github_org_sync.config import ConfigManager


@pytest.fixture
def mock_config_path(tmp_path: Path):
    path = tmp_path / "config.json"
    with patch("github_org_sync.services.report_service.ReportService.get_config_path") as mock_path:
        mock_path.return_value = path
        yield path


@pytest.mark.unit
def test_load_default_config_if_missing(mock_config_path: Path) -> None:
    manager = ConfigManager()
    config = manager.load()
    assert config["language"] == "pl"
    assert config["theme"] == "System"
    assert config["last_organization"] == ""
    assert not mock_config_path.exists()


@pytest.mark.unit
def test_save_and_load_config(mock_config_path: Path) -> None:
    manager = ConfigManager()
    test_config = {
        "language": "en",
        "theme": "Dark",
        "last_organization": "test-org",
    }
    manager.save(test_config)

    assert mock_config_path.exists()

    # Load again with a new manager instance
    new_manager = ConfigManager()
    loaded_config = new_manager.load()

    assert loaded_config["language"] == "en"
    assert loaded_config["theme"] == "Dark"
    assert loaded_config["last_organization"] == "test-org"
    # Ensure default keys not specified in test_config are still present
    assert loaded_config["window_width"] == 1000


@pytest.mark.unit
def test_load_corrupt_config_returns_defaults(mock_config_path: Path) -> None:
    # Write invalid JSON content
    with mock_config_path.open("w", encoding="utf-8") as f:
        f.write("{invalid_json:")

    manager = ConfigManager()
    config = manager.load()
    assert config == ConfigManager.DEFAULT_CONFIG
