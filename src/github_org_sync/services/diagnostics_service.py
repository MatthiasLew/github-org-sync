from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from github_org_sync.utils.lock import WorkspaceLock
from github_org_sync.utils.process import run_process


class DiagnosticsResult:
    def __init__(self, key: str, label: str, success: bool, message: str, required: bool = True) -> None:
        self.key = key
        self.label = label
        self.success = success
        self.message = message
        self.required = required

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "status": "ok" if self.success else ("warning" if not self.required else "error"),
            "message": self.message,
            "required": self.required,
        }


class DiagnosticsService:
    @staticmethod
    def run_all_checks() -> list[DiagnosticsResult]:
        results: list[DiagnosticsResult] = []

        # 1. Git installation check
        try:
            res_git = run_process(["git", "--version"], check=True)
            git_ver = res_git.stdout.strip()
            results.append(DiagnosticsResult("git", "Git Tooling", True, git_ver, required=True))
        except Exception as e:
            results.append(
                DiagnosticsResult(
                    "git", "Git Tooling", False, f"Git not found or failed to execute: {e}", required=True
                )
            )

        # 3. GitHub CLI installation check
        try:
            res_gh = run_process(["gh", "--version"], check=True)
            gh_ver = res_gh.stdout.splitlines()[0].strip() if res_gh.stdout else "gh CLI"
            results.append(DiagnosticsResult("gh", "GitHub CLI", True, gh_ver, required=True))
        except Exception as e:
            results.append(
                DiagnosticsResult(
                    "gh",
                    "GitHub CLI",
                    False,
                    f"GitHub CLI (gh) not found or failed to execute: {e}",
                    required=True,
                )
            )

        # 4. GitHub CLI Auth check
        try:
            res_auth = run_process(["gh", "auth", "status"], check=True)
            auth_msg = (res_auth.stdout + res_auth.stderr).strip()
            if "Logged in to github.com" in auth_msg or "Logged in to" in auth_msg:
                results.append(
                    DiagnosticsResult(
                        "auth",
                        "GitHub CLI Authentication",
                        True,
                        "Successfully authenticated with GitHub CLI.",
                        required=True,
                    )
                )
            else:
                results.append(
                    DiagnosticsResult(
                        "auth",
                        "GitHub CLI Authentication",
                        False,
                        f"Not logged in via gh CLI:\n{auth_msg}",
                        required=True,
                    )
                )
        except Exception as e:
            if isinstance(e, subprocess.CalledProcessError):
                auth_msg = ((e.stdout or "") + (e.stderr or "")).strip()
                results.append(
                    DiagnosticsResult(
                        "auth",
                        "GitHub CLI Authentication",
                        False,
                        f"Not logged in via gh CLI:\n{auth_msg}",
                        required=True,
                    )
                )
            else:
                results.append(
                    DiagnosticsResult(
                        "auth", "GitHub CLI Authentication", False, f"Authentication check failed:\n{e}", required=True
                    )
                )

        # 5. SSH Connectivity check
        try:
            res_ssh = run_process(["ssh", "-T", "git@github.com"], timeout=5)
            ssh_msg = (res_ssh.stdout + res_ssh.stderr).strip()
        except subprocess.TimeoutExpired:
            ssh_msg = "Connection timed out (5s)."
        except subprocess.CalledProcessError as e:
            ssh_msg = ((e.stdout or "") + (e.stderr or "")).strip()
        except Exception as e:
            ssh_msg = str(e)

        if "successfully authenticated" in ssh_msg.lower():
            results.append(
                DiagnosticsResult(
                    "ssh",
                    "SSH Connectivity to GitHub",
                    True,
                    f"Authenticated: {ssh_msg}",
                    required=False,
                )
            )
        else:
            results.append(
                DiagnosticsResult(
                    "ssh",
                    "SSH Connectivity to GitHub",
                    False,
                    f"SSH unavailable or unauthenticated: {ssh_msg}",
                    required=False,
                )
            )

        # 6. Git LFS installation check
        try:
            res_lfs = run_process(["git", "lfs", "version"], check=True)
            lfs_ver = res_lfs.stdout.splitlines()[0].strip() if res_lfs.stdout else "Git LFS"
            results.append(DiagnosticsResult("lfs", "Git LFS Extension", True, lfs_ver, required=False))
        except Exception as e:
            results.append(
                DiagnosticsResult(
                    "lfs",
                    "Git LFS Extension",
                    False,
                    f"Git LFS is not installed (optional): {e}",
                    required=False,
                )
            )

        return results

    @classmethod
    def run_doctor(cls, workspace: Path | None = None) -> dict[str, Any]:
        """Runs complete diagnostics including workspace permissions and lock verification."""
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        py_ok = sys.version_info >= (3, 11)
        results: list[DiagnosticsResult] = [
            DiagnosticsResult(
                "python",
                "Python Runtime",
                py_ok,
                f"Python {py_ver} ({sys.executable})" if py_ok else f"Python {py_ver} < 3.11",
                required=True,
            )
        ]
        results.extend(cls.run_all_checks())

        if workspace:
            ws_path = Path(workspace).resolve()
            # Check directory permissions
            try:
                ws_path.mkdir(parents=True, exist_ok=True)
                test_file = ws_path / f".write-test-{os.getpid()}.tmp"
                test_file.write_text("ok", encoding="utf-8")
                test_file.unlink()
                results.append(
                    DiagnosticsResult(
                        "workspace",
                        "Workspace Permissions",
                        True,
                        f"Read/write access verified: {ws_path}",
                        required=True,
                    )
                )
            except Exception as exc:
                results.append(
                    DiagnosticsResult(
                        "workspace",
                        "Workspace Permissions",
                        False,
                        f"Workspace access failure at '{ws_path}': {exc}",
                        required=True,
                    )
                )

            # Check locking capability
            try:
                lock = WorkspaceLock(ws_path, command="doctor:test", timeout=0.5)
                lock.acquire()
                lock.release()
                results.append(
                    DiagnosticsResult(
                        "locking",
                        "Workspace Locking",
                        True,
                        "File lock acquisition and release verified successfully.",
                        required=True,
                    )
                )
            except Exception as exc:
                results.append(
                    DiagnosticsResult(
                        "locking",
                        "Workspace Locking",
                        False,
                        f"Lock check failed on '{ws_path}': {exc}",
                        required=True,
                    )
                )

        has_required_error = any(not r.success and r.required for r in results)
        has_optional_warning = any(not r.success and not r.required for r in results)

        if has_required_error:
            status = "error"
        elif has_optional_warning:
            status = "warning"
        else:
            status = "success"

        passed = sum(1 for r in results if r.success)
        total = len(results)

        return {
            "status": status,
            "passed_checks": passed,
            "total_checks": total,
            "checks": [r.to_dict() for r in results],
        }
