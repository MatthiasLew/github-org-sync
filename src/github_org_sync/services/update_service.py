import contextlib
import json
import logging
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from github_org_sync import __version__

logger = logging.getLogger(__name__)


class UpdateService:
    API_URL = "https://api.github.com/repos/MatthiasLew/github-org-sync/releases/latest"

    def __init__(self, current_version: str = __version__) -> None:
        self.current_version = current_version.lstrip("v")

    def check_for_updates(self) -> dict[str, Any] | None:
        """
        Queries the GitHub API to check if a newer version is available.
        Returns a dict with version info if update is available, or None otherwise.
        """
        try:
            req = urllib.request.Request(
                self.API_URL,
                headers={"User-Agent": f"github-org-sync-updater/{self.current_version}"},
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status != 200:
                    logger.error(f"GitHub API returned status code {response.status}")
                    return None
                data = json.loads(response.read().decode("utf-8"))

            latest_tag = data.get("tag_name", "").lstrip("v")
            if not latest_tag:
                logger.error("No tag_name found in GitHub Release payload")
                return None

            if self._is_newer(latest_tag, self.current_version):
                assets = data.get("assets", [])
                download_url = self._get_matching_asset_url(assets)
                return {
                    "version": latest_tag,
                    "release_notes": data.get("body", ""),
                    "download_url": download_url,
                }
        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            return None

        return None

    def _is_newer(self, latest: str, current: str) -> bool:
        """Compares two semantic version strings."""
        try:
            latest_parts = [int(x) for x in latest.split(".") if x.isdigit()]
            current_parts = [int(x) for x in current.split(".") if x.isdigit()]
            return latest_parts > current_parts
        except Exception:
            return False

    def _get_matching_asset_url(self, assets: list[dict[str, Any]]) -> str | None:
        """Finds the download URL of the asset matching the current operating system."""
        if sys.platform == "win32":
            suffix = "windows-x64.zip"
        elif sys.platform == "darwin":
            suffix = "macos-x64.zip"
        else:
            suffix = "linux-x64.tar.gz"

        for asset in assets:
            name = asset.get("name", "")
            if name.endswith(suffix):
                return asset.get("browser_download_url")

        return None

    def download_update(
        self, url: str, dest_path: Path, progress_callback: Callable[[int, int], None] | None = None
    ) -> None:
        """Downloads the update archive from the specified URL, reporting progress chunks."""
        req = urllib.request.Request(
            url,
            headers={"User-Agent": f"github-org-sync-updater/{self.current_version}"},
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            block_size = 8192
            downloaded = 0

            with dest_path.open("wb") as f:
                while True:
                    buffer = response.read(block_size)
                    if not buffer:
                        break
                    f.write(buffer)
                    downloaded += len(buffer)
                    if progress_callback:
                        progress_callback(downloaded, total_size)

    def apply_update(self, archive_path: Path, install_dir: Path) -> None:
        """
        Extracts the download archive and applies the update.
        On Windows, spawns a detached updater script since running binary files are locked.
        On macOS and Linux, overrides binaries inline and prepares to restart.
        """
        temp_extract_dir = Path(tempfile.mkdtemp(prefix="github-org-sync-update-"))

        try:
            # Extract archive
            if archive_path.name.endswith(".zip"):
                with zipfile.ZipFile(archive_path, "r") as zip_ref:
                    zip_ref.extractall(temp_extract_dir)
            else:
                with tarfile.open(archive_path, "r:gz") as tar_ref:
                    tar_ref.extractall(temp_extract_dir)

            # Inside the archive there should be a directory named 'github-org-sync'
            extracted_app_dir = temp_extract_dir / "github-org-sync"
            if not extracted_app_dir.exists():
                # Fallback to searching for the directory or using the first child directory
                dirs = [p for p in temp_extract_dir.iterdir() if p.is_dir()]
                extracted_app_dir = dirs[0] if dirs else temp_extract_dir

            if sys.platform == "win32":
                self._apply_windows(extracted_app_dir, install_dir)
            else:
                self._apply_unix(extracted_app_dir, install_dir)
        finally:
            # Note: temporary directory cleanup on Windows is handled by the batch script
            if sys.platform != "win32":
                shutil.rmtree(temp_extract_dir, ignore_errors=True)

    def _apply_windows(self, src_dir: Path, dest_dir: Path) -> None:
        """Creates a batch file to wait for exit, copy files, restart, and spawns it."""
        from github_org_sync.utils.process import popen_process

        bat_path = Path(tempfile.gettempdir()) / "github_org_sync_update.bat"

        # Generate batch file content
        # Note: xcopy options: /Y (suppress prompt to overwrite), /S /E (copy subdirectories), /I (assume destination is directory)
        bat_content = f"""@echo off
timeout /t 2 /nobreak > nul
xcopy /Y /S /E /I "{src_dir}" "{dest_dir}"
start "" "{dest_dir / "github-org-sync.exe"}"
del "%~f0"
exit
"""
        with bat_path.open("w", encoding="utf-8") as f:
            f.write(bat_content)

        # Launch the batch script detached
        popen_process([str(bat_path)], cwd=dest_dir)
        sys.exit(0)

    def _apply_unix(self, src_dir: Path, dest_dir: Path) -> None:
        """Directly overwrites files inline and replaces the process image to restart."""
        # Overwrite destination directory files inline
        for root, _, files in os.walk(src_dir):
            root_path = Path(root)
            rel_path = root_path.relative_to(src_dir)
            dest_root = dest_dir / rel_path
            dest_root.mkdir(parents=True, exist_ok=True)

            for file in files:
                src_file = root_path / file
                dest_file = dest_root / file
                # If target exists and is currently locked, we unlink it first (Unix allows unlinking open files)
                if dest_file.exists():
                    with contextlib.suppress(Exception):
                        dest_file.unlink()
                shutil.copy2(src_file, dest_file)

        # Re-exec the current process image to restart
        os.execv(sys.executable, sys.argv)
