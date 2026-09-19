from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from github_org_sync.services.update_service import (
    ChecksumMismatchError,
    InvalidArchiveStructureError,
    MaliciousArchiveError,
    UpdateSecurityError,
    UpdateService,
)


@pytest.mark.unit
def test_calculate_and_verify_sha256(tmp_path: Path) -> None:
    test_file = tmp_path / "sample.bin"
    test_file.write_bytes(b"hello github-org-sync security")

    calculated = UpdateService.calculate_sha256(test_file)
    assert len(calculated) == 64

    service = UpdateService()
    # Correct checksum succeeds
    service.verify_archive_integrity(test_file, calculated)
    # Incorrect checksum raises ChecksumMismatchError
    with pytest.raises(ChecksumMismatchError):
        service.verify_archive_integrity(test_file, "0" * 64)


@pytest.mark.unit
def test_safe_extract_zip_rejects_path_traversal(tmp_path: Path) -> None:
    zip_path = tmp_path / "malicious.zip"
    extract_dir = tmp_path / "extracted"
    extract_dir.mkdir()

    # Create malicious zip with Zip Slip
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../../evil.txt", "pwned")

    with pytest.raises(MaliciousArchiveError) as exc_info:
        UpdateService.safe_extract_zip(zip_path, extract_dir)
    assert "Unsafe file path" in str(exc_info.value) or "Path traversal" in str(exc_info.value)
    # Target should not have evil.txt outside
    assert not (tmp_path / "evil.txt").exists()


@pytest.mark.unit
def test_safe_extract_zip_rejects_absolute_paths(tmp_path: Path) -> None:
    zip_path = tmp_path / "absolute.zip"
    extract_dir = tmp_path / "extracted"
    extract_dir.mkdir()

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("/root/pwned.txt", "data")

    with pytest.raises(MaliciousArchiveError):
        UpdateService.safe_extract_zip(zip_path, extract_dir)


@pytest.mark.unit
def test_safe_extract_tar_rejects_path_traversal(tmp_path: Path) -> None:
    tar_path = tmp_path / "malicious.tar.gz"
    extract_dir = tmp_path / "extracted_tar"
    extract_dir.mkdir()

    with tarfile.open(tar_path, "w:gz") as tf:
        tarinfo = tarfile.TarInfo(name="../escape.txt")
        data = b"escape"
        tarinfo.size = len(data)
        tf.addfile(tarinfo, io.BytesIO(data))

    with pytest.raises(MaliciousArchiveError):
        UpdateService.safe_extract_tar(tar_path, extract_dir)
    assert not (tmp_path / "escape.txt").exists()


@pytest.mark.unit
def test_safe_extract_valid_archive(tmp_path: Path) -> None:
    zip_path = tmp_path / "valid.zip"
    extract_dir = tmp_path / "extracted_valid"
    extract_dir.mkdir()

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("github-org-sync/README.md", "# Valid App")
        zf.writestr("github-org-sync/github-org-sync.exe", "binary")
        zf.writestr("github-org-sync/github-org-sync", "binary")

    UpdateService.safe_extract_archive(zip_path, extract_dir)
    assert (extract_dir / "github-org-sync" / "README.md").exists()

    validated_dir = UpdateService.validate_extracted_structure(extract_dir)
    assert validated_dir.exists()


@pytest.mark.unit
def test_validate_extracted_structure_missing_binary(tmp_path: Path) -> None:
    extract_dir = tmp_path / "empty_extracted"
    extract_dir.mkdir()
    (extract_dir / "random_file.txt").write_text("not app", encoding="utf-8")

    with pytest.raises(InvalidArchiveStructureError):
        UpdateService.validate_extracted_structure(extract_dir)


@pytest.mark.unit
def test_verify_archive_integrity_malformed_hash(tmp_path: Path) -> None:
    test_file = tmp_path / "test.bin"
    test_file.write_bytes(b"data")
    service = UpdateService()
    # Non-hex characters
    with pytest.raises(UpdateSecurityError) as exc_info:
        service.verify_archive_integrity(test_file, "not-a-valid-hex-hash!" + "0" * 44)
    assert "malformed" in str(exc_info.value).lower()

    # Wrong length
    with pytest.raises(UpdateSecurityError) as exc_info:
        service.verify_archive_integrity(test_file, "abc123")
    assert "malformed" in str(exc_info.value).lower()


@pytest.mark.unit
def test_safe_extract_zip_rejects_duplicate_members(tmp_path: Path) -> None:
    zip_path = tmp_path / "duplicate.zip"
    extract_dir = tmp_path / "extracted_dup"
    extract_dir.mkdir()

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("app/config.json", '{"version": 1}')
        zf.writestr("app/config.json", '{"version": 2}')

    with pytest.raises(MaliciousArchiveError) as exc_info:
        UpdateService.safe_extract_zip(zip_path, extract_dir)
    assert "Duplicate member" in str(exc_info.value)


@pytest.mark.unit
def test_safe_extract_tar_rejects_duplicate_members(tmp_path: Path) -> None:
    tar_path = tmp_path / "duplicate.tar.gz"
    extract_dir = tmp_path / "extracted_tar_dup"
    extract_dir.mkdir()

    with tarfile.open(tar_path, "w:gz") as tf:
        t1 = tarfile.TarInfo(name="app/config.json")
        t1.size = 5
        tf.addfile(t1, io.BytesIO(b"data1"))
        t2 = tarfile.TarInfo(name="app/config.json")
        t2.size = 5
        tf.addfile(t2, io.BytesIO(b"data2"))

    with pytest.raises(MaliciousArchiveError) as exc_info:
        UpdateService.safe_extract_tar(tar_path, extract_dir)
    assert "Duplicate member" in str(exc_info.value)


@pytest.mark.unit
def test_safe_extract_tar_rejects_symlinks(tmp_path: Path) -> None:
    tar_path = tmp_path / "symlink.tar.gz"
    extract_dir = tmp_path / "extracted_tar_sym"
    extract_dir.mkdir()

    with tarfile.open(tar_path, "w:gz") as tf:
        t_sym = tarfile.TarInfo(name="app/evil_symlink")
        t_sym.type = tarfile.SYMTYPE
        t_sym.linkname = "/etc/passwd"
        tf.addfile(t_sym)

    with pytest.raises(MaliciousArchiveError) as exc_info:
        UpdateService.safe_extract_tar(tar_path, extract_dir)
    assert "Symlinks and hardlinks are prohibited" in str(exc_info.value)
