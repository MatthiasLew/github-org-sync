import subprocess
import sys
from pathlib import Path
from typing import Any


def run_process(
    args: list[str],
    cwd: Path | str | None = None,
    check: bool = False,
    capture_output: bool = True,
    text: bool = True,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """
    Central helper to run subprocesses.
    On Windows, sets creationflags=subprocess.CREATE_NO_WINDOW to avoid flashing CMD windows.
    """
    if args:
        cmd_name = Path(args[0]).name.lower()
        if cmd_name in ("git", "git.exe"):
            for arg in args:
                if arg == "--force" or arg == "--force-with-lease" or arg.startswith("--force="):
                    raise ValueError("Force push is strictly prohibited in github-org-sync.")

    if sys.platform == "win32":
        flags = kwargs.get("creationflags", 0)
        # 0x08000000 is CREATE_NO_WINDOW
        flags |= 0x08000000
        kwargs["creationflags"] = flags

    return subprocess.run(args, cwd=cwd, check=check, capture_output=capture_output, text=text, **kwargs)


def popen_process(args: list[str], cwd: Path | str | None = None, **kwargs: Any) -> subprocess.Popen[str]:
    """
    Central helper to start subprocesses asynchronously.
    On Windows, sets creationflags=subprocess.CREATE_NO_WINDOW to avoid flashing CMD windows.
    """
    if args:
        cmd_name = Path(args[0]).name.lower()
        if cmd_name in ("git", "git.exe"):
            for arg in args:
                if arg == "--force" or arg == "--force-with-lease" or arg.startswith("--force="):
                    raise ValueError("Force push is strictly prohibited in github-org-sync.")

    if sys.platform == "win32":
        flags = kwargs.get("creationflags", 0)
        flags |= 0x08000000
        kwargs["creationflags"] = flags

    return subprocess.Popen(args, cwd=cwd, text=True, **kwargs)


def open_terminal(path: Path) -> bool:
    """
    Opens a visible OS terminal in the specified directory.
    This is an interactive action initiated by the user, so the terminal is visible.
    """
    import shutil

    try:
        if sys.platform == "win32":
            # Prefer Windows Terminal if available
            wt_path = shutil.which("wt")
            if wt_path:
                subprocess.Popen([wt_path, "-d", str(path)])
                return True
            # Fallback to PowerShell
            powershell_path = shutil.which("powershell")
            if powershell_path:
                # To open a new visible PowerShell window on Windows, we start it via cmd's start
                subprocess.Popen(["cmd.exe", "/c", "start", "powershell.exe"], cwd=path)
                return True
            return False
        elif sys.platform == "darwin":  # noqa: RET505
            subprocess.Popen(["open", "-a", "Terminal", str(path)])
            return True
        else:  # noqa: RET505
            # Linux: try common terminal emulators
            for term in ("gnome-terminal", "konsole", "xfce4-terminal", "xterm"):
                term_path = shutil.which(term)
                if term_path:
                    subprocess.Popen([term_path], cwd=path)
                    return True
            return False
    except Exception:
        return False
