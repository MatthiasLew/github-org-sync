import urllib.parse
from pathlib import Path
from unittest.mock import patch

import pytest

from github_org_sync.ui.crash_dialog import CrashReportDialog, sanitize_error_text


@pytest.mark.unit
def test_sanitize_error_text_secrets() -> None:
    text = "Failed with ghp_secretToken123 and gho_oauthToken456."
    sanitized = sanitize_error_text(text)
    assert "[REDACTED_TOKEN]" in sanitized
    assert "ghp_secretToken123" not in sanitized
    assert "gho_oauthToken456" not in sanitized


@pytest.mark.unit
def test_sanitize_error_text_home_dir() -> None:
    fake_home = str(Path.home())
    text = f"File not found in {fake_home}/documents/config.json"
    sanitized = sanitize_error_text(text)
    assert "[USER_HOME]" in sanitized
    assert fake_home not in sanitized


@pytest.mark.gui
def test_crash_dialog_url_generation(qtbot) -> None:
    # We use qtbot to safely run GUI code in unit tests without actual windows popping up
    error_type = "ValueError"
    error_msg = "Something went wrong with ghp_token"
    traceback_text = 'Traceback (most recent call last):\n  File "app.py", line 10, in main'

    dialog = CrashReportDialog(error_type, error_msg, traceback_text)

    # Verify attributes were correctly sanitized
    assert "[REDACTED_TOKEN]" in dialog.error_msg
    assert "ghp_token" not in dialog.error_msg

    # We patch webbrowser.open to check if the correct URL is generated
    with patch("webbrowser.open") as mock_open:
        dialog.report_on_github()

        mock_open.assert_called_once()
        called_url = mock_open.call_args[0][0]

        assert "https://github.com/MatthiasLew/github-org-sync/issues/new" in called_url
        parsed_url = urllib.parse.urlparse(called_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)

        assert "title" in query_params
        assert "body" in query_params

        # Title should contain the error type and sanitized message
        title_val = query_params["title"][0]
        assert "ValueError" in title_val
        assert "[REDACTED_TOKEN]" in title_val

        # Body should contain the formatted error traceback and details
        body_val = query_params["body"][0]
        assert "Application Version" in body_val
        assert "ValueError" in body_val
        assert "[REDACTED_TOKEN]" in body_val
