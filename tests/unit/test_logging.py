import logging
from pathlib import Path

import pytest

from github_org_sync.app import setup_logging


@pytest.mark.unit
def test_setup_logging_creates_file(tmp_path: Path) -> None:
    # Set up logging to temporary directory
    setup_logging(app_data_dir=tmp_path)

    # Verify directory and file created
    log_file = tmp_path / "logs" / "app.log"
    assert log_file.parent.exists()
    assert log_file.exists()

    # Log something to verify it writes
    test_logger = logging.getLogger("test_logger")
    test_logger.info("Hello diagnostic test log")

    # Read log file and assert message is inside
    content = log_file.read_text(encoding="utf-8")
    assert "Hello diagnostic test log" in content
