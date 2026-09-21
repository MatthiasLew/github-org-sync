import sys
from pathlib import Path
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


@pytest.mark.unit
def test_timeout_configuration() -> None:
    from github_org_sync.utils.process import DEFAULT_COMMAND_TIMEOUT, get_default_timeout, set_default_timeout

    original = get_default_timeout()
    try:
        set_default_timeout(42.5)
        assert get_default_timeout() == 42.5
        set_default_timeout(None)
        assert get_default_timeout() == DEFAULT_COMMAND_TIMEOUT
    finally:
        set_default_timeout(original)


@pytest.mark.unit
def test_validate_git_policy_edge_cases() -> None:
    from github_org_sync.utils.process import GitSecurityPolicyError, validate_git_policy

    # Empty args
    validate_git_policy([])

    # Non-git command
    validate_git_policy(["python", "-m", "foo"])
    validate_git_policy(["/usr/bin/ls", "-la"])

    # Disallowed subcommand
    with pytest.raises(GitSecurityPolicyError, match="not permitted"):
        validate_git_policy(["git", "fast-export"])

    # Global flags parsing: -c and -C flags
    validate_git_policy(["git", "-C", "/some/path", "status"])
    validate_git_policy(["git", "-c", "core.filemode=false", "fetch"])
    validate_git_policy(["git", "-v", "status"])

    # Force flags
    with pytest.raises(GitSecurityPolicyError, match="Force push is strictly prohibited"):
        validate_git_policy(["git", "push", "--force"])

    with pytest.raises(GitSecurityPolicyError, match="Force push is strictly prohibited"):
        validate_git_policy(["git", "push", "--force-with-lease=main:main"])

    # Reset --hard
    with pytest.raises(GitSecurityPolicyError, match="git reset --hard"):
        validate_git_policy(["git", "reset", "--hard", "HEAD"])

    # Clean
    with pytest.raises(GitSecurityPolicyError, match="not permitted"):
        validate_git_policy(["git", "clean", "-fd"])


@pytest.mark.unit
def test_run_process_scrubs_secrets_in_called_process_error() -> None:
    from subprocess import CalledProcessError

    with patch("subprocess.run") as mock_run:
        err = CalledProcessError(
            1,
            ["whoami"],
            output="error with ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456 in stdout",
            stderr="error with ghp_1234567890abcdefghij12345678901234 in stderr",
        )
        mock_run.side_effect = err

        with pytest.raises(CalledProcessError) as exc_info:
            run_process(["whoami"], check=True)
        assert "[REDACTED_TOKEN]" in exc_info.value.output
        assert "[REDACTED_TOKEN]" in exc_info.value.stderr
        assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in exc_info.value.output


@pytest.mark.unit
def test_run_process_binary_mode() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=b"binary\x00data", stderr=b"")
        res = run_process(["whoami"], text=False)
        assert res.stdout == b"binary\x00data"


@pytest.mark.unit
def test_open_terminal_windows(tmp_path: Path) -> None:
    from github_org_sync.utils.process import open_terminal

    with patch("sys.platform", "win32"), patch("subprocess.Popen") as mock_popen:
        # Case 1: Windows Terminal (wt) exists
        with patch("shutil.which", side_effect=lambda cmd: "/path/to/wt.exe" if cmd == "wt" else None):
            assert open_terminal(tmp_path) is True
            mock_popen.assert_called_with(["/path/to/wt.exe", "-d", str(tmp_path)])

        # Case 2: wt does not exist, powershell exists
        with patch("shutil.which", side_effect=lambda cmd: "/path/powershell.exe" if cmd == "powershell" else None):
            assert open_terminal(tmp_path) is True
            mock_popen.assert_called_with(["cmd.exe", "/c", "start", "powershell.exe"], cwd=tmp_path)

        # Case 3: neither exists
        with patch("shutil.which", return_value=None):
            assert open_terminal(tmp_path) is False


@pytest.mark.unit
def test_open_terminal_unix_and_darwin(tmp_path: Path) -> None:
    from github_org_sync.utils.process import open_terminal

    with patch("subprocess.Popen") as mock_popen:
        # macOS
        with patch("sys.platform", "darwin"):
            assert open_terminal(tmp_path) is True
            mock_popen.assert_called_with(["open", "-a", "Terminal", str(tmp_path)])

        # Linux with terminal available
        with (
            patch("sys.platform", "linux"),
            patch("shutil.which", side_effect=lambda cmd: "/bin/konsole" if cmd == "konsole" else None),
        ):
            assert open_terminal(tmp_path) is True
            mock_popen.assert_called_with(["/bin/konsole"], cwd=tmp_path)

        # Linux with no terminal available
        with patch("sys.platform", "linux"), patch("shutil.which", return_value=None):
            assert open_terminal(tmp_path) is False

        # Exception handled
        with patch("sys.platform", "linux"), patch("shutil.which", side_effect=RuntimeError("disk crash")):
            assert open_terminal(tmp_path) is False
