import sys
from unittest.mock import MagicMock, patch

import pytest

from github_org_sync.utils.process import popen_process, run_process


@pytest.mark.unit
def test_process_runner_windows_flags() -> None:
    # We patch subprocess.run to verify the flags passed to it
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="test", stderr="")

        # Trigger run_process
        with patch("sys.platform", "win32"):
            run_process(["whoami"])

        # Check creationflags
        args, kwargs = mock_run.call_args
        assert "creationflags" in kwargs
        assert kwargs["creationflags"] & 0x08000000 == 0x08000000


@pytest.mark.unit
def test_process_runner_non_windows_flags() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="test", stderr="")

        with patch("sys.platform", "linux"):
            run_process(["whoami"])

        args, kwargs = mock_run.call_args
        # Should not set CREATE_NO_WINDOW on linux
        if "creationflags" in kwargs:
            assert not (kwargs["creationflags"] & 0x08000000)


@pytest.mark.unit
def test_popen_process_windows_flags() -> None:
    with patch("subprocess.Popen") as mock_popen:
        # Trigger popen_process
        with patch("sys.platform", "win32"):
            popen_process(["whoami"])

        args, kwargs = mock_popen.call_args
        assert "creationflags" in kwargs
        assert kwargs["creationflags"] & 0x08000000 == 0x08000000


@pytest.mark.unit
def test_run_process_execution() -> None:
    # Run a simple check command synchronously
    cp = run_process([sys.executable, "--version"])
    assert cp.returncode == 0
    assert "Python" in cp.stdout
