from __future__ import annotations

import datetime
import json
import os
import socket
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout


class WorkspaceLockedError(RuntimeError):
    """Raised when an operation cannot acquire the exclusive lock on a workspace."""


def get_process_create_time(pid: int) -> int | None:
    """Returns a platform-specific integer timestamp of process creation or None."""
    if pid <= 0:
        return None
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class _FILETIME(ctypes.Structure):
                _fields_ = [
                    ("dwLowDateTime", wintypes.DWORD),
                    ("dwHighDateTime", wintypes.DWORD),
                ]

            kernel32 = ctypes.windll.kernel32
            # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return None
            try:
                creation = _FILETIME()
                exit_time = _FILETIME()
                kernel = _FILETIME()
                user = _FILETIME()
                if kernel32.GetProcessTimes(
                    handle,
                    ctypes.byref(creation),
                    ctypes.byref(exit_time),
                    ctypes.byref(kernel),
                    ctypes.byref(user),
                ):
                    return int((creation.dwHighDateTime << 32) | creation.dwLowDateTime)
                return None
            finally:
                kernel32.CloseHandle(handle)
        elif sys.platform.startswith("linux"):
            stat_path = Path(f"/proc/{pid}/stat")
            if stat_path.exists():
                content = stat_path.read_text()
                r_paren = content.rfind(")")
                if r_paren != -1:
                    fields = content[r_paren + 2 :].split()
                    return int(fields[19])
    except Exception:
        pass
    return None


def is_process_running(pid: int) -> bool:
    """Checks if a process with the given PID is currently active in the OS."""
    if pid <= 0:
        return False
    try:
        if sys.platform == "win32":
            import ctypes

            # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        else:  # noqa: RET505
            # Unix platforms
            os.kill(pid, 0)
            return True
    except (OSError, PermissionError):
        return False


def is_process_active(
    pid: int,
    expected_create_time: int | None = None,
    expected_hostname: str | None = None,
) -> bool:
    """
    Checks if a process is running and matches the recorded start identity.
    Guards against PID recycling and cross-host lock misinterpretations.
    Fails closed (returns True) if identity cannot be verified safely.
    """
    if expected_hostname and expected_hostname.lower() != socket.gethostname().lower():
        # Cross-host lock: cannot verify remote PID locally. Fail closed to prevent data corruption.
        return True

    if not is_process_running(pid):
        return False

    if expected_create_time is not None:
        actual_create_time = get_process_create_time(pid)
        if actual_create_time is not None:
            return actual_create_time == expected_create_time
        # If create_time cannot be queried (e.g. permission restriction), fail closed.
        return True

    return True


class WorkspaceLock:
    """
    Cross-platform workspace concurrency lock.
    Serializes CLI and GUI access to a workspace directory, writing holder metadata
    and preventing race conditions without permanently locking after crashes.
    """

    def __init__(self, workspace: Path | str, command: str = "sync", timeout: float = 3.0) -> None:
        self.workspace = Path(workspace).resolve()
        self.command = command
        self.timeout = timeout
        self.lock_path = self.workspace / ".github-org-sync.lock"
        self.info_path = self.workspace / ".github-org-sync.lock.info"
        self._file_lock = FileLock(str(self.lock_path), timeout=timeout)
        self._is_locked = False

    def acquire(self) -> None:
        """Acquires exclusive lock or raises WorkspaceLockedError with details."""
        self.workspace.mkdir(parents=True, exist_ok=True)
        try:
            self._file_lock.acquire(timeout=self.timeout)
            self._is_locked = True
            self._write_holder_info()
        except Timeout as exc:
            holder_details = self._read_holder_info()
            msg = (
                f"Workspace '{self.workspace}' is locked by another running process "
                f"({holder_details}). Concurrent operations on the same workspace are prohibited."
            )
            raise WorkspaceLockedError(msg) from exc

    def release(self) -> None:
        """Releases the lock and removes holder info metadata."""
        if self._is_locked:
            self._clear_holder_info()
            try:
                self._file_lock.release()
            finally:
                self._is_locked = False

    def __enter__(self) -> WorkspaceLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()

    def _write_holder_info(self) -> None:
        try:
            info = {
                "pid": os.getpid(),
                "create_time": get_process_create_time(os.getpid()),
                "hostname": socket.gethostname(),
                "command": self.command,
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            }
            self.info_path.write_text(json.dumps(info), encoding="utf-8")
        except OSError:
            pass

    def _clear_holder_info(self) -> None:
        try:
            if self.info_path.exists():
                self.info_path.unlink()
        except OSError:
            pass

    def _read_holder_info(self) -> str:
        try:
            if self.info_path.exists():
                data = json.loads(self.info_path.read_text(encoding="utf-8"))
                pid = data.get("pid")
                create_time = data.get("create_time")
                hostname = data.get("hostname", "unknown")
                cmd = data.get("command", "unknown")
                ts = data.get("timestamp", "unknown time")
                if pid is not None:
                    active = is_process_active(
                        int(pid),
                        expected_create_time=create_time,
                        expected_hostname=hostname,
                    )
                    status_str = "active" if active else "stale (PID terminated or recycled)"
                else:
                    status_str = "unknown"
                return f"PID {pid} on '{hostname}', command='{cmd}', started={ts}, status={status_str}"
        except Exception:
            pass
        return "Unknown process holding lock"


@contextmanager
def workspace_lock(workspace: Path | str, command: str = "sync", timeout: float = 3.0) -> Iterator[WorkspaceLock]:
    """Context manager for acquiring an exclusive workspace lock."""
    lock = WorkspaceLock(workspace, command=command, timeout=timeout)
    lock.acquire()
    try:
        yield lock
    finally:
        lock.release()
