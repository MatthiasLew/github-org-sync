from __future__ import annotations

from pathlib import Path

import pytest

from github_org_sync.utils.lock import (
    WorkspaceLock,
    WorkspaceLockedError,
    get_process_create_time,
    is_process_active,
    is_process_running,
    workspace_lock,
)


@pytest.mark.unit
def test_workspace_lock_acquire_and_release(tmp_path: Path) -> None:
    lock = WorkspaceLock(tmp_path, command="test:sync", timeout=1.0)
    lock.acquire()
    assert lock.lock_path.exists()
    assert lock.info_path.exists()
    lock.release()
    assert not lock.info_path.exists()


@pytest.mark.unit
def test_workspace_lock_context_manager(tmp_path: Path) -> None:
    with workspace_lock(tmp_path, command="context:test", timeout=1.0):
        lock_info = tmp_path / ".github-org-sync.lock.info"
        assert lock_info.exists()
        assert "context:test" in lock_info.read_text(encoding="utf-8")
    assert not (tmp_path / ".github-org-sync.lock.info").exists()


@pytest.mark.unit
def test_workspace_lock_concurrency_rejected(tmp_path: Path) -> None:
    lock1 = WorkspaceLock(tmp_path, command="cli:sync", timeout=1.0)
    lock1.acquire()
    try:
        # Second lock attempt must fail and raise WorkspaceLockedError
        lock2 = WorkspaceLock(tmp_path, command="gui:sync", timeout=0.2)
        with pytest.raises(WorkspaceLockedError) as exc_info:
            lock2.acquire()
        assert "is locked by another running process" in str(exc_info.value)
        assert "cli:sync" in str(exc_info.value)
    finally:
        lock1.release()


@pytest.mark.unit
def test_is_process_running() -> None:
    import os

    current_pid = os.getpid()
    assert is_process_running(current_pid) is True
    # Non-existent high PID
    assert is_process_running(999999) is False
    assert is_process_running(-1) is False


@pytest.mark.unit
def test_get_process_create_time() -> None:
    import os

    current_pid = os.getpid()
    ctime = get_process_create_time(current_pid)
    # On Windows or Linux, should be a positive integer
    if ctime is not None:
        assert isinstance(ctime, int)
        assert ctime > 0
    assert get_process_create_time(-1) is None


@pytest.mark.unit
def test_is_process_active_pid_recycling() -> None:
    import os
    import socket

    current_pid = os.getpid()
    actual_ctime = get_process_create_time(current_pid)
    my_host = socket.gethostname()

    # Active when matched
    assert is_process_active(current_pid, expected_create_time=actual_ctime, expected_hostname=my_host) is True

    # Stale when create_time differs (PID recycled)
    if actual_ctime is not None:
        assert (
            is_process_active(current_pid, expected_create_time=actual_ctime + 9999, expected_hostname=my_host) is False
        )

    # Fails closed (returns True) if hostname differs
    assert is_process_active(current_pid, expected_hostname="foreign-server-01") is True

    # Inactive if PID is dead
    assert is_process_active(999999, expected_hostname=my_host) is False


@pytest.mark.unit
def test_workspace_lock_holder_info_pid_recycled(tmp_path: Path) -> None:
    import json
    import os
    import socket

    lock = WorkspaceLock(tmp_path, command="test:info")
    # Simulate a stale holder info file with recycled create_time
    info_file = tmp_path / ".github-org-sync.lock.info"
    stale_info = {
        "pid": os.getpid(),
        "create_time": 12345678,  # Different from real process create_time
        "hostname": socket.gethostname(),
        "command": "old:sync",
        "timestamp": "2026-01-01T00:00:00Z",
    }
    info_file.write_text(json.dumps(stale_info), encoding="utf-8")

    info_str = lock._read_holder_info()
    if get_process_create_time(os.getpid()) is not None:
        assert "stale (PID terminated or recycled)" in info_str


@pytest.mark.unit
def test_workspace_lock_holder_info_corrupt_or_missing_pid(tmp_path: Path) -> None:
    lock = WorkspaceLock(tmp_path, command="test:corrupt")
    info_file = tmp_path / ".github-org-sync.lock.info"

    # Corrupt non-JSON
    info_file.write_text("NOT_JSON_DATA", encoding="utf-8")
    assert lock._read_holder_info() == "Unknown process holding lock"

    # JSON without PID
    info_file.write_text('{"command": "orphan"}', encoding="utf-8")
    info_str = lock._read_holder_info()
    assert "status=unknown" in info_str
