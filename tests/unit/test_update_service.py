from unittest.mock import MagicMock, patch

from github_org_sync.services.update_service import UpdateService


def test_is_newer() -> None:
    service = UpdateService(current_version="1.3.1")
    assert service._is_newer("1.3.2", "1.3.1") is True
    assert service._is_newer("1.4.0", "1.3.1") is True
    assert service._is_newer("2.0.0", "1.3.1") is True
    assert service._is_newer("1.3.1", "1.3.1") is False
    assert service._is_newer("1.3.0", "1.3.1") is False
    assert service._is_newer("invalid", "1.3.1") is False


def test_get_matching_asset_url() -> None:
    service = UpdateService(current_version="1.3.1")
    assets = [
        {"name": "github-org-sync-v1.3.2-windows-x64.zip", "browser_download_url": "http://win"},
        {"name": "github-org-sync-v1.3.2-macos-x64.zip", "browser_download_url": "http://mac"},
        {"name": "github-org-sync-v1.3.2-linux-x64.tar.gz", "browser_download_url": "http://linux"},
    ]

    with patch("sys.platform", "win32"):
        assert service._get_matching_asset_url(assets) == "http://win"

    with patch("sys.platform", "darwin"):
        assert service._get_matching_asset_url(assets) == "http://mac"

    with patch("sys.platform", "linux"):
        assert service._get_matching_asset_url(assets) == "http://linux"


@patch("urllib.request.urlopen")
def test_check_for_updates_available(mock_urlopen: MagicMock) -> None:
    # Set up mock response
    mock_response = MagicMock()
    mock_response.status = 200
    mock_payload = {
        "tag_name": "v1.3.2",
        "body": "Release notes for 1.3.2",
        "assets": [
            {"name": "github-org-sync-v1.3.2-windows-x64.zip", "browser_download_url": "http://win"},
        ],
    }
    mock_response.read.return_value = bytes(str(mock_payload).replace("'", '"'), "utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_response

    service = UpdateService(current_version="1.3.1")
    with patch("sys.platform", "win32"):
        result = service.check_for_updates()

    assert result is not None
    assert result["version"] == "1.3.2"
    assert result["release_notes"] == "Release notes for 1.3.2"
    assert result["download_url"] == "http://win"


@patch("urllib.request.urlopen")
def test_check_for_updates_none(mock_urlopen: MagicMock) -> None:
    mock_response = MagicMock()
    mock_response.status = 200
    mock_payload = {
        "tag_name": "v1.3.1",
        "body": "Release notes",
        "assets": [],
    }
    mock_response.read.return_value = bytes(str(mock_payload).replace("'", '"'), "utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_response

    service = UpdateService(current_version="1.3.1")
    result = service.check_for_updates()
    assert result is None
