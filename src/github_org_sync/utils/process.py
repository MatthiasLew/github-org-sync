from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from github_org_sync.utils.security import scrub_secrets

# Default subprocess timeout in seconds
DEFAULT_COMMAND_TIMEOUT: float = 45.0
DEFAULT_NETWORK_TIMEOUT: float = 180.0

_active_global_timeout: float | None = None

ALLOWED_GIT_SUBCOMMANDS: frozenset[str] = frozenset(
    {
        "status",
        "rev-parse",
        "rev-list",
        "symbolic-ref",
        "remote",
        "fetch",
        "pull",
        "clone",
        "checkout",
        "stash",
        "diff",
        "log",
        "branch",
        "mergetool",
        "config",
        "lfs",
        "add",
        "commit",
        "reset",
        "push",
        "version",
    }
)

FORBIDDEN_GIT_FLAGS: frozenset[str] = frozenset(
    {
        "-f",
        "--force",
        "--force-with-lease",
        "--force-if-includes",
    }
)


class GitSecurityPolicyError(ValueError):
    """Raised when a git command violates the central safety policy."""


def set_default_timeout(timeout: float | None) -> None:
    """Sets a global timeout override for all subprocess commands."""
    global _active_global_timeout
    _active_global_timeout = timeout


def get_default_timeout() -> float:
    """Returns the currently active default timeout in seconds."""
    if _active_global_timeout is not None:
        return _active_global_timeout
    return DEFAULT_COMMAND_TIMEOUT


def validate_git_policy(args: list[str]) -> None:
    """
    Enforces the central Git security policy:
    1. Prohibits any force operations (-f, --force, --force-with-lease).
    2. Prohibits destructive commands (reset --hard, clean -f).
    3. Restricts execution strictly to allowed non-destructive git subcommands.
    """
    if not args:
        return

    cmd_name = Path(args[0]).name.lower()
    if cmd_name not in ("git", "git.exe"):
        return

    # Check for forbidden destructive / force flags first
    for arg in args[1:]:
        lower_arg = arg.lower()
        if (
            lower_arg in FORBIDDEN_GIT_FLAGS
            or any(lower_arg.startswith(f"{flag}=") for flag in FORBIDDEN_GIT_FLAGS)
            or lower_arg.startswith("--force")
        ):
            raise GitSecurityPolicyError("Force push is strictly prohibited in github-org-sync.")

    # Extract git subcommand, ignoring global flags like -c, -C, etc.
    subcmd: str | None = None
    i = 1
    while i < len(args):
        arg = args[i]
        if arg.startswith("-"):
            if arg in ("-c", "-C") and i + 1 < len(args):
                i += 2
                continue
            i += 1
            continue
        subcmd = arg.lower()
        break

    if subcmd is not None and subcmd not in ALLOWED_GIT_SUBCOMMANDS:
        raise GitSecurityPolicyError(f"Git subcommand '{subcmd}' is not permitted by github-org-sync security policy.")

    # Specific dangerous combinations
    if subcmd == "reset" and any(a.lower() == "--hard" for a in args):
        raise GitSecurityPolicyError("Command 'git reset --hard' is prohibited to prevent data loss.")
    if subcmd == "clean":
        raise GitSecurityPolicyError("Command 'git clean' is prohibited to prevent data loss.")


def _build_subprocess_env(custom_env: dict[str, str] | None = None) -> dict[str, str]:
    """Prepares child process environment with non-interactive headless flags."""
    env = dict(os.environ) if custom_env is None else dict(custom_env)
    # Prevent git/ssh/gh from popping interactive credential or passphrase prompts
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    return env


def run_process(
    args: list[str],
    cwd: Path | str | None = None,
    check: bool = False,
    capture_output: bool = True,
    text: bool = True,
    encoding: str = "utf-8",
    timeout: float | None = None,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """
    Central helper to run subprocesses synchronously.
    - Enforces Git security allowlist policy and blocks force/destructive arguments.
    - Prevents interactive credential hangs using headless environment flags.
    - Applies configurable timeout.
    - On Windows, sets creationflags=0x08000000 (CREATE_NO_WINDOW) to hide flashing console windows.
    - NEVER uses shell=True.
    """
    validate_git_policy(args)

    if sys.platform == "win32":
        flags = kwargs.get("creationflags", 0)
        flags |= 0x08000000  # CREATE_NO_WINDOW
        kwargs["creationflags"] = flags

    kwargs["env"] = _build_subprocess_env(kwargs.get("env"))

    effective_timeout = timeout if timeout is not None else get_default_timeout()

    try:
        res = subprocess.run(
            args,
            cwd=cwd,
            check=check,
            capture_output=capture_output,
            text=text,
            encoding=encoding,
            timeout=effective_timeout,
            **kwargs,
        )
        if text and capture_output:
            if isinstance(res.stdout, str):
                res.stdout = scrub_secrets(res.stdout)
            if isinstance(res.stderr, str):
                res.stderr = scrub_secrets(res.stderr)
        return res
    except subprocess.CalledProcessError as exc:
        if text:
            if isinstance(exc.stdout, str):
                exc.stdout = scrub_secrets(exc.stdout)
            if isinstance(exc.stderr, str):
                exc.stderr = scrub_secrets(exc.stderr)
        raise exc


def popen_process(
    args: list[str],
    cwd: Path | str | None = None,
    encoding: str = "utf-8",
    **kwargs: Any,
) -> subprocess.Popen[str]:
    """
    Central helper to start subprocesses asynchronously.
    - Enforces Git security allowlist policy.
    - Sets headless environment flags and CREATE_NO_WINDOW on Windows.
    """
    validate_git_policy(args)

    if sys.platform == "win32":
        flags = kwargs.get("creationflags", 0)
        flags |= 0x08000000  # CREATE_NO_WINDOW
        kwargs["creationflags"] = flags

    kwargs["env"] = _build_subprocess_env(kwargs.get("env"))

    return subprocess.Popen(args, cwd=cwd, text=True, encoding=encoding, **kwargs)


def open_terminal(path: Path) -> bool:
    """
    Opens a visible OS terminal in the specified directory.
    This is an interactive action initiated by the user, so the terminal is visible.
    """
    import shutil

    try:
        if sys.platform == "win32":
            wt_path = shutil.which("wt")
            if wt_path:
                subprocess.Popen([wt_path, "-d", str(path)])
                return True
            powershell_path = shutil.which("powershell")
            if powershell_path:
                subprocess.Popen(["cmd.exe", "/c", "start", "powershell.exe"], cwd=path)
                return True
            return False
        elif sys.platform == "darwin":  # noqa: RET505
            subprocess.Popen(["open", "-a", "Terminal", str(path)])
            return True
        else:  # noqa: RET505
            for term in ("gnome-terminal", "konsole", "xfce4-terminal", "xterm"):
                term_path = shutil.which(term)
                if term_path:
                    subprocess.Popen([term_path], cwd=path)
                    return True
            return False
    except Exception:
        return False
