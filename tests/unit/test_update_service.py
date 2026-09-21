import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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


@patch("github_org_sync.services.update_service.sys.exit")
@patch("github_org_sync.utils.process.popen_process")
@patch("pathlib.Path.open")
def test_apply_windows(mock_open: MagicMock, mock_popen: MagicMock, mock_exit: MagicMock) -> None:
    from pathlib import Path

    mock_file = MagicMock()
    mock_open.return_value.__enter__.return_value = mock_file

    service = UpdateService()
    src = Path("C:/src")
    dest = Path("C:/dest")

    with patch("sys.platform", "win32"), patch("sys.executable", "C:/dest/github-org-sync.exe"):
        service._apply_windows(src, dest)

    mock_open.assert_called_once()
    written_data = "".join(call[0][0] for call in mock_file.write.call_args_list)
    assert "robocopy" in written_data
    assert "tasklist" in written_data
    assert "github-org-sync.exe" in written_data

    mock_popen.assert_called_once()
    mock_exit.assert_called_once_with(0)


@patch("urllib.request.urlopen")
def test_check_for_updates_failure_paths(mock_urlopen: MagicMock) -> None:
    service = UpdateService(current_version="1.3.1")

    # 1. Non-200 status code
    mock_resp = MagicMock(status=404)
    mock_urlopen.return_value.__enter__.return_value = mock_resp
    assert service.check_for_updates() is None

    # 2. Missing tag_name
    mock_resp = MagicMock(status=200)
    mock_resp.read.return_value = b'{"body": "no tag"}'
    mock_urlopen.return_value.__enter__.return_value = mock_resp
    assert service.check_for_updates() is None

    # 3. Newer version but no matching assets
    mock_resp.read.return_value = b'{"tag_name": "v2.0.0", "assets": [{"name": "random.txt"}]}'
    mock_urlopen.return_value.__enter__.return_value = mock_resp
    with patch("sys.platform", "win32"):
        assert service.check_for_updates() is None

    # 4. Exception in urlopen
    mock_urlopen.side_effect = RuntimeError("network down")
    assert service.check_for_updates() is None


@patch("urllib.request.urlopen")
def test_check_for_updates_with_checksum_asset(mock_urlopen: MagicMock) -> None:
    mock_resp = MagicMock(status=200)
    payload = {
        "tag_name": "v1.4.0",
        "body": "Release v1.4.0",
        "assets": [
            {"name": "github-org-sync-windows-x64.zip", "browser_download_url": "http://pkg.zip"},
            {"name": "github-org-sync-windows-x64.zip.sha256", "browser_download_url": "http://pkg.sha256"},
        ],
    }
    mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_resp
    mock_urlopen.side_effect = None

    service = UpdateService(current_version="1.3.1")
    with patch("sys.platform", "win32"):
        res = service.check_for_updates()
    assert res is not None
    assert res["download_url"] == "http://pkg.zip"
    assert res["checksum_url"] == "http://pkg.sha256"


@patch("urllib.request.urlopen")
def test_fetch_expected_sha256(mock_urlopen: MagicMock) -> None:
    from github_org_sync.services.update_service import UpdateSecurityError

    service = UpdateService()

    # Valid SHA256 in file: "hash  filename"
    valid_hash = "a" * 64
    mock_resp = MagicMock()
    mock_resp.read.return_value = f"{valid_hash}  pkg.zip\n".encode()
    mock_urlopen.return_value.__enter__.return_value = mock_resp
    assert service.fetch_expected_sha256("http://example.com/pkg.sha256") == valid_hash

    # Empty file
    mock_resp.read.return_value = b"   \n"
    with pytest.raises(UpdateSecurityError, match="empty"):
        service.fetch_expected_sha256("http://example.com/pkg.sha256")

    # Malformed hash
    mock_resp.read.return_value = b"short_hash\n"
    with pytest.raises(UpdateSecurityError, match="Malformed SHA-256"):
        service.fetch_expected_sha256("http://example.com/pkg.sha256")


def test_safe_extract_archive_dispatch(tmp_path: Path) -> None:
    from github_org_sync.services.update_service import UpdateSecurityError

    zip_file = tmp_path / "update.zip"
    tar_file = tmp_path / "update.tar.gz"
    bad_file = tmp_path / "update.msi"

    dest = tmp_path / "dest"
    dest.mkdir()

    with (
        patch.object(UpdateService, "safe_extract_zip") as mock_zip,
        patch.object(UpdateService, "safe_extract_tar") as mock_tar,
    ):
        UpdateService.safe_extract_archive(zip_file, dest)
        mock_zip.assert_called_once_with(zip_file, dest)

        UpdateService.safe_extract_archive(tar_file, dest)
        mock_tar.assert_called_once_with(tar_file, dest)

        with pytest.raises(UpdateSecurityError, match="Unsupported archive format"):
            UpdateService.safe_extract_archive(bad_file, dest)


def test_validate_extracted_structure(tmp_path: Path) -> None:
    from github_org_sync.services.update_service import InvalidArchiveStructureError

    # Subdir structure with binary
    app_dir = tmp_path / "github-org-sync"
    app_dir.mkdir()
    binary_name = "github-org-sync.exe" if sys.platform == "win32" else "github-org-sync"
    (app_dir / binary_name).write_text("bin", encoding="utf-8")

    assert UpdateService.validate_extracted_structure(tmp_path) == app_dir

    # Missing binary raises InvalidArchiveStructureError
    (app_dir / binary_name).unlink()
    with pytest.raises(InvalidArchiveStructureError, match="does not contain expected executable"):
        UpdateService.validate_extracted_structure(tmp_path)

    # Direct in root
    (tmp_path / binary_name).write_text("bin", encoding="utf-8")
    assert UpdateService.validate_extracted_structure(tmp_path) == tmp_path


@patch("urllib.request.urlopen")
def test_download_update_progress_and_error(mock_urlopen: MagicMock, tmp_path: Path) -> None:
    from github_org_sync.services.update_service import UpdateSecurityError

    dest = tmp_path / "archive.zip"
    service = UpdateService()

    # Success with progress
    mock_resp = MagicMock()
    mock_resp.headers.get.return_value = "8"
    mock_resp.read.side_effect = [b"1234", b"5678", b""]
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    progress_calls = []
    service.download_update("http://dl", dest, progress_callback=lambda d, t: progress_calls.append((d, t)))
    assert dest.is_file()
    assert dest.read_bytes() == b"12345678"
    assert len(progress_calls) == 2

    # Incomplete download error
    mock_resp.headers.get.return_value = "20"
    mock_resp.read.side_effect = [b"1234", b""]
    with pytest.raises(UpdateSecurityError, match="Incomplete download"):
        service.download_update("http://dl", dest)
    assert not (dest.with_suffix(".zip.part")).exists()


def test_apply_unix(tmp_path: Path) -> None:
    service = UpdateService()
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.sh").write_text("#!/bin/sh", encoding="utf-8")
    (src / "sub").mkdir()
    (src / "sub" / "file.txt").write_text("sub content", encoding="utf-8")

    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "old.txt").write_text("old", encoding="utf-8")

    service._apply_unix(src, dest)
    assert (dest / "app.sh").is_file()
    assert (dest / "sub" / "file.txt").is_file()


def test_apply_update_linux(tmp_path: Path) -> None:
    import zipfile

    service = UpdateService()
    zip_path = tmp_path / "update.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("github-org-sync/github-org-sync", "binary data")

    sha = service.calculate_sha256(zip_path)
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    (install_dir / "old_file").write_text("old", encoding="utf-8")

    with patch("sys.platform", "linux"):
        service.apply_update(zip_path, install_dir, expected_sha256=sha)
    assert (install_dir / "github-org-sync").is_file()


def test_safe_extract_tar_valid(tmp_path: Path) -> None:
    import io
    import tarfile

    tar_path = tmp_path / "valid.tar.gz"
    extract_dir = tmp_path / "extracted_tar"
    extract_dir.mkdir()

    with tarfile.open(tar_path, "w:gz") as tf:
        t_dir = tarfile.TarInfo(name="app")
        t_dir.type = tarfile.DIRTYPE
        tf.addfile(t_dir)
        t_file = tarfile.TarInfo(name="app/file.txt")
        t_file.size = 4
        tf.addfile(t_file, io.BytesIO(b"test"))

    UpdateService.safe_extract_tar(tar_path, extract_dir)
    assert (extract_dir / "app" / "file.txt").is_file()
