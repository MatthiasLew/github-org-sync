import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from github_org_sync.models.sync_result import SyncResult
from github_org_sync.services.report_service import ReportService, _scrub_secrets


@pytest.fixture
def temp_app_data_dir(tmp_path: Path):
    with patch("github_org_sync.services.report_service.ReportService.get_app_data_dir") as mock_dir:
        mock_dir.return_value = tmp_path
        yield tmp_path


@pytest.mark.unit
def test_scrub_secrets() -> None:
    text_with_token = "Error: ghp_12345abcdef for gho_987654321xyz token authentication failed."
    scrubbed = _scrub_secrets(text_with_token)
    assert "[REDACTED_TOKEN]" in scrubbed
    assert "ghp_12345abcdef" not in scrubbed
    assert "gho_987654321xyz" not in scrubbed


@pytest.mark.unit
def test_get_app_data_dir_default() -> None:
    if sys.platform == "win32":
        pytest.skip("Unix-specific test")
    # Test fallback behavior when APPDATA is not present in environment
    with patch.dict("os.environ", {}, clear=True), patch("pathlib.Path.home") as mock_home:
        mock_home.return_value = Path("/home/testuser")
        dir_path = ReportService.get_app_data_dir()
        assert dir_path == Path("/home/testuser/.config/github-org-sync")


@pytest.mark.unit
def test_get_app_data_dir_windows() -> None:
    if sys.platform != "win32":
        pytest.skip("Windows-specific test")
    # Test Windows AppData behavior
    with patch("os.name", "nt"), patch.dict("os.environ", {"APPDATA": "C:\\Users\\testuser\\AppData\\Roaming"}):
        dir_path = ReportService.get_app_data_dir()
        assert dir_path == Path("C:/Users/testuser/AppData/Roaming/github-org-sync")


@pytest.mark.unit
def test_generate_reports(temp_app_data_dir: Path) -> None:
    results = [
        SyncResult(
            repo_name="repo-a",
            requested_action="clone",
            performed_action="clone",
            before_status="MISSING",
            after_status="SYNCED",
            duration=1.234,
            result="Successfully cloned ghp_secrettoken.",
            error=None,
        ),
        SyncResult(
            repo_name="repo-b",
            requested_action="pull",
            performed_action="pull",
            before_status="OUTDATED",
            after_status="FAILED",
            duration=0.567,
            result=None,
            error="Remote checkout failed for gho_anothersecret.",
        ),
    ]

    options = {
        "use_ssh": False,
        "preserve_local_changes": True,
    }

    json_path, md_path = ReportService.generate_reports(
        organization="my-org-ghp_token",
        workspace=Path("/workspace/my-org"),
        auth_user="auth-user-gho_user",
        protocol="https",
        options=options,
        results=results,
    )

    # Verify files created
    assert json_path.exists()
    assert md_path.exists()

    # Verify JSON content (secrets scrubbed)
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["organization"] == "my-org-[REDACTED_TOKEN]"
    assert data["authenticated_user"] == "auth-user-[REDACTED_TOKEN]"
    assert data["results"][0]["result"] == "Successfully cloned [REDACTED_TOKEN]."
    assert data["results"][1]["error"] == "Remote checkout failed for [REDACTED_TOKEN]."

    # Verify Markdown content (secrets scrubbed)
    with md_path.open("r", encoding="utf-8") as f:
        md_text = f.read()

    assert "my-org-[REDACTED_TOKEN]" in md_text
    assert "auth-user-[REDACTED_TOKEN]" in md_text
    assert "Successfully cloned [REDACTED_TOKEN]." in md_text
    assert "Remote checkout failed for [REDACTED_TOKEN]." in md_text
