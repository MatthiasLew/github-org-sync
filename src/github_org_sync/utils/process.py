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
    if sys.platform == "win32":
        flags = kwargs.get("creationflags", 0)
        flags |= 0x08000000
        kwargs["creationflags"] = flags

    return subprocess.Popen(args, cwd=cwd, text=True, **kwargs)
