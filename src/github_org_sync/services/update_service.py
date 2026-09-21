from __future__ import annotations

import contextlib
import hashlib
import inspect
import json
import logging
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


class UpdateSecurityError(RuntimeError):
    """Raised when an update fails integrity or security verification."""


class ChecksumMismatchError(UpdateSecurityError):
    """Raised when the calculated checksum does not match the expected release hash."""


class MaliciousArchiveError(UpdateSecurityError):
    """Raised when an archive contains path traversal or unsafe file entries."""


class InvalidArchiveStructureError(UpdateSecurityError):
    """Raised when an extracted archive does not contain expected application binaries."""


class UpdateService:
    API_URL = "https://api.github.com/repos/MatthiasLew/github-org-sync/releases/latest"

    def __init__(self, current_version: str = __version__) -> None:
        self.current_version = current_version.lstrip("v")

    def check_for_updates(self) -> dict[str, Any] | None:
        """
        Queries the GitHub API to check if a newer version is available.
        Returns a dict with version info, asset URL, and checksum URL if available.
        """
        try:
            req = urllib.request.Request(
                self.API_URL,
                headers={"User-Agent": f"github-org-sync-updater/{self.current_version}"},
            )
            with urllib.request.urlopen(req, timeout=10) as response:  # nosec B310
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
                asset, checksum_asset = self._get_matching_assets(assets)
                if not asset:
                    return None

                return {
                    "version": latest_tag,
                    "release_notes": data.get("body", ""),
                    "download_url": asset.get("browser_download_url"),
                    "checksum_url": checksum_asset.get("browser_download_url") if checksum_asset else None,
                    "asset_name": asset.get("name"),
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

    def _get_matching_assets(self, assets: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Finds both the archive asset and its corresponding .sha256 checksum asset."""
        if sys.platform == "win32":
            suffix = "windows-x64.zip"
        elif sys.platform == "darwin":
            suffix = "macos-x64.zip"
        else:
            suffix = "linux-x64.tar.gz"

        matching_asset: dict[str, Any] | None = None
        for asset in assets:
            name = asset.get("name", "")
            if name.endswith(suffix):
                matching_asset = asset
                break

        if not matching_asset:
            return None, None

        checksum_name = f"{matching_asset.get('name')}.sha256"
        matching_checksum: dict[str, Any] | None = None
        for asset in assets:
            if asset.get("name") == checksum_name:
                matching_checksum = asset
                break

        return matching_asset, matching_checksum

    def _get_matching_asset_url(self, assets: list[dict[str, Any]]) -> str | None:
        """Backwards compatibility helper returning only the download URL."""
        asset, _ = self._get_matching_assets(assets)
        return asset.get("browser_download_url") if asset else None

    def fetch_expected_sha256(self, checksum_url: str) -> str:
        """Downloads and parses the expected SHA-256 hash from release metadata."""
        req = urllib.request.Request(
            checksum_url,
            headers={"User-Agent": f"github-org-sync-updater/{self.current_version}"},
        )
        with urllib.request.urlopen(req, timeout=15) as response:  # nosec B310
            content = response.read().decode("utf-8").strip()
            # Checksum files format: "<hash>  <filename>" or just "<hash>"
            parts = content.split()
            if not parts:
                raise UpdateSecurityError("Downloaded checksum file is empty.")
            expected_hash = str(parts[0].strip().lower())
            if len(expected_hash) != 64 or not all(c in "0123456789abcdef" for c in expected_hash):
                raise UpdateSecurityError(f"Malformed SHA-256 hash in checksum file: '{expected_hash}'")
            return expected_hash

    @staticmethod
    def calculate_sha256(path: Path) -> str:
        """Calculates the SHA-256 digest of a local file in 64KB chunks."""
        hasher = hashlib.sha256()
        with path.open("rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest().lower()

    def verify_archive_integrity(self, archive_path: Path, expected_sha256: str) -> None:
        """Verifies that the downloaded archive exactly matches the expected SHA-256 hash."""
        expected = expected_sha256.strip().lower()
        if len(expected) != 64 or not all(c in "0123456789abcdef" for c in expected):
            raise UpdateSecurityError(f"Expected SHA-256 hash is malformed: '{expected_sha256}'")
        calculated = self.calculate_sha256(archive_path)
        if calculated != expected:
            raise ChecksumMismatchError(
                f"SHA-256 verification failed for {archive_path.name}: expected '{expected}', got '{calculated}'."
            )

    @staticmethod
    def safe_extract_zip(archive_path: Path, dest_dir: Path) -> None:
        """
        Safely extracts a ZIP archive preventing Zip Slip / path traversal attacks.
        Rejects duplicate members, '..', absolute paths, drive letters, and symlinks.
        """
        dest_resolved = dest_dir.resolve()
        dest_resolved.mkdir(parents=True, exist_ok=True)
        seen_members: set[str] = set()

        with zipfile.ZipFile(archive_path, "r") as zf:
            for member in zf.infolist():
                name = member.filename
                norm_name = Path(name).as_posix().lstrip("/")
                if norm_name:
                    if norm_name in seen_members:
                        raise MaliciousArchiveError(f"Duplicate member detected in ZIP archive: '{name}'")
                    seen_members.add(norm_name)

                # Check for absolute paths, path traversal tokens, drive letters, or null bytes
                if name.startswith(("/", "\\")) or ".." in Path(name).parts or ":" in name or "\0" in name:
                    raise MaliciousArchiveError(f"Unsafe file path detected in ZIP archive: '{name}'")

                target_path = (dest_dir / name).resolve()
                if not target_path.is_relative_to(dest_resolved):
                    raise MaliciousArchiveError(f"Path traversal detected in ZIP: '{name}' escapes target directory")

                # Prevent dangerous symlinks
                is_symlink = (member.external_attr >> 16) & 0o120000 == 0o120000
                if is_symlink:
                    raise MaliciousArchiveError(f"Symlinks are prohibited in update archive: '{name}'")

                zf.extract(member, dest_dir)

    @staticmethod
    def safe_extract_tar(archive_path: Path, dest_dir: Path) -> None:
        """
        Safely extracts a TAR archive preventing path traversal attacks.
        Rejects duplicate members, symlinks/hardlinks, and traversal escaping targets.
        """
        dest_resolved = dest_dir.resolve()
        dest_resolved.mkdir(parents=True, exist_ok=True)
        seen_members: set[str] = set()

        with tarfile.open(archive_path, "r:*") as tf:
            for member in tf.getmembers():
                name = member.name
                norm_name = Path(name).as_posix().lstrip("/")
                if norm_name:
                    if norm_name in seen_members:
                        raise MaliciousArchiveError(f"Duplicate member detected in TAR archive: '{name}'")
                    seen_members.add(norm_name)

                if name.startswith(("/", "\\")) or ".." in Path(name).parts or ":" in name or "\0" in name:
                    raise MaliciousArchiveError(f"Unsafe file path detected in TAR archive: '{name}'")

                target_path = (dest_dir / name).resolve()
                if not target_path.is_relative_to(dest_resolved):
                    raise MaliciousArchiveError(f"Path traversal detected in TAR: '{name}' escapes target directory")

                if member.issym() or member.islnk():
                    raise MaliciousArchiveError(
                        f"Symlinks and hardlinks are prohibited in update archive: '{name}' -> '{member.linkname}'"
                    )

                if "filter" in inspect.signature(tf.extract).parameters:
                    tf.extract(member, dest_dir, filter="data")
                else:
                    tf.extract(member, dest_dir)

    @classmethod
    def safe_extract_archive(cls, archive_path: Path, dest_dir: Path) -> None:
        """Extracts either a ZIP or TAR archive safely."""
        name = archive_path.name.lower()
        if name.endswith(".zip"):
            cls.safe_extract_zip(archive_path, dest_dir)
        elif name.endswith((".tar.gz", ".tgz", ".tar")):
            cls.safe_extract_tar(archive_path, dest_dir)
        else:
            raise UpdateSecurityError(f"Unsupported archive format: {archive_path.name}")

    @staticmethod
    def validate_extracted_structure(extracted_root: Path) -> Path:
        """
        Validates that the extracted directory contains expected application components.
        Returns the directory path containing the application files.
        """
        app_dir = extracted_root / "github-org-sync"
        if not app_dir.exists():
            candidates = [p for p in extracted_root.iterdir() if p.is_dir()]
            app_dir = candidates[0] if candidates else extracted_root

        expected_binary = "github-org-sync.exe" if sys.platform == "win32" else "github-org-sync"
        bin_path = app_dir / expected_binary
        if not bin_path.exists():
            # Check direct extracted_root
            if (extracted_root / expected_binary).exists():
                return extracted_root
            raise InvalidArchiveStructureError(
                f"Extracted update archive does not contain expected executable '{expected_binary}'."
            )
        return app_dir

    def download_update(
        self, url: str, dest_path: Path, progress_callback: Callable[[int, int], None] | None = None
    ) -> None:
        """Downloads the update archive atomically reporting progress chunks."""
        req = urllib.request.Request(
            url,
            headers={"User-Agent": f"github-org-sync-updater/{self.current_version}"},
        )
        temp_dest = dest_path.with_suffix(dest_path.suffix + ".part")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:  # nosec B310
                total_size = int(response.headers.get("Content-Length", 0))
                block_size = 8192
                downloaded = 0

                with temp_dest.open("wb") as f:
                    while True:
                        buffer = response.read(block_size)
                        if not buffer:
                            break
                        f.write(buffer)
                        downloaded += len(buffer)
                        if progress_callback:
                            progress_callback(downloaded, total_size)

                if total_size > 0 and downloaded < total_size:
                    raise UpdateSecurityError(
                        f"Incomplete download: received {downloaded} bytes, expected {total_size} bytes."
                    )
            temp_dest.replace(dest_path)
        except Exception:
            if temp_dest.exists():
                temp_dest.unlink()
            raise

    def apply_update(
        self,
        archive_path: Path,
        install_dir: Path,
        expected_sha256: str | None = None,
    ) -> None:
        """
        Full verified update flow:
        1. Verify SHA-256 if provided.
        2. Safely extract archive to temporary folder with path traversal checks.
        3. Validate archive structure.
        4. Apply update to installation directory.
        """
        if expected_sha256:
            self.verify_archive_integrity(archive_path, expected_sha256)

        temp_extract_dir = Path(tempfile.mkdtemp(prefix="github-org-sync-update-"))

        try:
            self.safe_extract_archive(archive_path, temp_extract_dir)
            validated_app_dir = self.validate_extracted_structure(temp_extract_dir)

            if sys.platform == "win32":
                self._apply_windows(validated_app_dir, install_dir)
            else:
                self._apply_unix(validated_app_dir, install_dir)
        finally:
            if sys.platform != "win32":
                shutil.rmtree(temp_extract_dir, ignore_errors=True)

    def _apply_windows(self, src_dir: Path, dest_dir: Path) -> None:
        """Creates a batch file to wait for exit, copy files, restart, and spawns it."""
        from github_org_sync.utils.process import popen_process

        bat_path = Path(tempfile.gettempdir()) / "github_org_sync_update.bat"
        exe_name = Path(sys.executable).name
        dest_exe = dest_dir / exe_name

        bat_content = f"""@echo off
setlocal enabledelayedexpansion

set "PID_CHECK={exe_name}"
for /L %%i in (1,1,10) do (
    tasklist /FI "IMAGENAME eq !PID_CHECK!" 2>NUL | find /I "!PID_CHECK!" >NUL
    if !ERRORLEVEL! EQU 0 (
        timeout /t 1 /nobreak > nul
    ) else (
        goto :DO_COPY
    )
)

:DO_COPY
robocopy "{src_dir}" "{dest_dir}" /MIR /R:2 /W:1 /NP /NFL /NDO
if %ERRORLEVEL% GEQ 8 (
    xcopy "{src_dir}\\*" "{dest_dir}\\" /E /Y /I /Q
)

if exist "{src_dir}" (
    rmdir /S /Q "{src_dir.parent}"
)

if exist "{dest_exe}" (
    start "" "{dest_exe}"
)

del "%~f0"
exit /b 0
"""
        bat_path.write_text(bat_content, encoding="utf-8")
        popen_process(["cmd.exe", "/c", str(bat_path)])
        sys.exit(0)

    def _apply_unix(self, src_dir: Path, dest_dir: Path) -> None:
        """Inline atomic update for macOS and Linux."""
        for item in src_dir.iterdir():
            target = dest_dir / item.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
                with contextlib.suppress(Exception):
                    target.chmod(0o755)
