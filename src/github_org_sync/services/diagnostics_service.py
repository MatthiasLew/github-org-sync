import subprocess

from github_org_sync.utils.process import run_process


class DiagnosticsResult:
    def __init__(self, key: str, label: str, success: bool, message: str) -> None:
        self.key = key
        self.label = label
        self.success = success
        self.message = message


class DiagnosticsService:
    @staticmethod
    def run_all_checks() -> list[DiagnosticsResult]:
        results = []

        # 1. Git installation check
        try:
            res_git = run_process(["git", "--version"], check=True)
            git_ver = res_git.stdout.strip()
            results.append(DiagnosticsResult("git", "Git Installation", True, git_ver))
        except Exception as e:
            results.append(
                DiagnosticsResult("git", "Git Installation", False, f"Git not found or failed to execute: {e}")
            )

        # 2. GitHub CLI installation check
        try:
            res_gh = run_process(["gh", "--version"], check=True)
            gh_ver = res_gh.stdout.splitlines()[0].strip() if res_gh.stdout else "gh CLI"
            results.append(DiagnosticsResult("gh", "GitHub CLI Installation", True, gh_ver))
        except Exception as e:
            results.append(
                DiagnosticsResult(
                    "gh",
                    "GitHub CLI Installation",
                    False,
                    f"GitHub CLI (gh) not found or failed to execute: {e}",
                )
            )

        # 3. GitHub CLI Auth check
        try:
            res_auth = run_process(["gh", "auth", "status"], check=True)
            auth_msg = (res_auth.stdout + res_auth.stderr).strip()
            if "Logged in to github.com" in auth_msg or "Logged in to" in auth_msg:
                results.append(
                    DiagnosticsResult(
                        "auth", "GitHub CLI Authentication", True, "Successfully authenticated with GitHub CLI."
                    )
                )
            else:
                results.append(
                    DiagnosticsResult(
                        "auth", "GitHub CLI Authentication", False, f"Not logged in via gh CLI:\n{auth_msg}"
                    )
                )
        except Exception as e:
            # Check if it was a subprocess.CalledProcessError
            if isinstance(e, subprocess.CalledProcessError):
                auth_msg = (e.stdout or "") + (e.stderr or "")
                auth_msg = auth_msg.strip()
                results.append(
                    DiagnosticsResult(
                        "auth", "GitHub CLI Authentication", False, f"Not logged in via gh CLI:\n{auth_msg}"
                    )
                )
            else:
                results.append(
                    DiagnosticsResult(
                        "auth", "GitHub CLI Authentication", False, f"Authentication status check failed:\n{e}"
                    )
                )

        # 4. SSH Connectivity check
        try:
            # ssh -T returns code 1 on successful authentication, let's catch CalledProcessError or output parsing
            res_ssh = run_process(["ssh", "-T", "git@github.com"], timeout=5)
            ssh_msg = (res_ssh.stdout + res_ssh.stderr).strip()
        except subprocess.TimeoutExpired:
            ssh_msg = "Connection timed out (5s)."
        except subprocess.CalledProcessError as e:
            ssh_msg = (e.stdout or "") + (e.stderr or "")
            ssh_msg = ssh_msg.strip()
        except Exception as e:
            ssh_msg = str(e)

        if "successfully authenticated" in ssh_msg.lower():
            results.append(
                DiagnosticsResult(
                    "ssh",
                    "SSH Connectivity to GitHub",
                    True,
                    f"SSH connection successful and authenticated:\n{ssh_msg}",
                )
            )
        else:
            results.append(
                DiagnosticsResult(
                    "ssh",
                    "SSH Connectivity to GitHub",
                    False,
                    f"SSH handshake succeeded but failed authentication or returned unexpected message:\n{ssh_msg}",
                )
            )

        return results
