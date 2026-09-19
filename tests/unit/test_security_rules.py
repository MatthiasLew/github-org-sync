import ast
from pathlib import Path

import pytest

from github_org_sync.utils.process import popen_process, run_process


@pytest.mark.unit
@pytest.mark.security
def test_force_push_block_run_process() -> None:
    # Test run_process blocks force push variants
    with pytest.raises(ValueError, match="Force push is strictly prohibited"):
        run_process(["git", "push", "--force"])

    with pytest.raises(ValueError, match="Force push is strictly prohibited"):
        run_process(["git", "push", "--force-with-lease"])

    with pytest.raises(ValueError, match="Force push is strictly prohibited"):
        run_process(["git", "push", "--force=true"])

    # Verify standard git push is allowed
    # Note: we use mock command or a non-existent git path to avoid executing anything real here
    # but the parser checks it before any execution, so we expect it to try to execute (and maybe fail with FileNotFoundError or mock it)
    # Actually, we can check that it doesn't raise ValueError!
    with pytest.raises((FileNotFoundError, PermissionError, OSError)):
        run_process(["git-non-existent-executable", "push"])


@pytest.mark.unit
@pytest.mark.security
def test_force_push_block_popen_process() -> None:
    # Test popen_process blocks force push variants
    with pytest.raises(ValueError, match="Force push is strictly prohibited"):
        popen_process(["git", "push", "--force"])

    with pytest.raises(ValueError, match="Force push is strictly prohibited"):
        popen_process(["git", "push", "--force-with-lease"])

    with pytest.raises(ValueError, match="Force push is strictly prohibited"):
        popen_process(["git", "push", "--force=true"])


@pytest.mark.unit
@pytest.mark.security
def test_no_direct_subprocess_calls() -> None:
    # Scan the src folder statically using AST
    src_dir = Path(__file__).parent.parent.parent / "src"
    assert src_dir.exists(), f"Source dir {src_dir} does not exist"

    violations = []
    for path in src_dir.rglob("*.py"):
        # Skip process.py itself
        if path.name == "process.py":
            continue

        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(path))

        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "subprocess"
                and node.attr in ("run", "Popen")
            ):
                violations.append(f"{path.relative_to(src_dir)}: subprocess.{node.attr}")
            elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
                for name in node.names:
                    if name.name in ("run", "Popen"):
                        violations.append(f"{path.relative_to(src_dir)}: import {name.name} from subprocess")

    assert not violations, f"Direct subprocess calls found in source files: {violations}"


@pytest.mark.unit
@pytest.mark.security
def test_scrub_secrets_all_token_types() -> None:
    from github_org_sync.utils.security import scrub_secrets

    # 1. Classic personal access token (ghp_)
    raw1 = "Error during push with token: ghp_1234567890abcdef1234567890abcdef1234"
    assert scrub_secrets(raw1) == "Error during push with token: [REDACTED_TOKEN]"

    # 2. OAuth token (gho_)
    raw2 = "gho_abcdef1234567890abcdef1234567890"
    assert scrub_secrets(raw2) == "[REDACTED_TOKEN]"

    # 3. User-to-server token (ghu_)
    raw3 = "ghu_userToken12345678901234567890"
    assert scrub_secrets(raw3) == "[REDACTED_TOKEN]"

    # 4. Server-to-server token (ghs_)
    raw4 = "ghs_serverToken123456789012345678"
    assert scrub_secrets(raw4) == "[REDACTED_TOKEN]"

    # 5. Refresh token (ghr_)
    raw5 = "ghr_refreshToken12345678901234567"
    assert scrub_secrets(raw5) == "[REDACTED_TOKEN]"

    # 6. Fine-grained PAT (github_pat_)
    raw6 = "github_pat_11ABCD_1234567890abcdefghijklmnopqrstuvwxyz"
    assert scrub_secrets(raw6) == "[REDACTED_TOKEN]"

    # 7. Embedded URL credentials
    raw7 = "fatal: repository 'https://x-access-token:ghs_secret123456789@github.com/org/repo.git' not found"
    clean7 = scrub_secrets(raw7)
    assert "ghs_secret" not in clean7
    assert "https://x-access-token:[REDACTED]@github.com/org/repo.git" in clean7

    # 8. Authorization Bearer header
    raw8 = "Authorization: Bearer mySecretToken12345678"
    assert scrub_secrets(raw8) == "Authorization: Bearer [REDACTED_TOKEN]"

    # 9. None or empty
    assert scrub_secrets("") == ""
