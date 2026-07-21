# Testing Guide

This document describes the testing architecture, pytest marker configuration, and manual/automated execution procedures for `github-org-sync`.

## Testing Architecture & Markers

The test suite is structured into unit, integration, and security checks. Pytest markers are strictly enforced (configured in `pyproject.toml` with `--strict-markers`).

### Registered Markers
*   `unit`: Fast isolated unit tests.
*   `integration`: Complex integration test flows.
*   `git`: Tests executing real Git commands on temporary local repositories.
*   `gui`: PySide6 graphical user interface tests (requiring display/Xvfb).
*   `slow`: Long-running scenarios.
*   `security`: Security rules and static vulnerability audits.
*   `smoke`: Fast GUI/app boot check verification.
*   `windows` / `linux` / `macos`: OS-specific assertions.

## Execution Commands

### Run all tests
```bash
pytest
```

### Run only unit tests
```bash
pytest -m unit
```

### Run Git integration scenarios
```bash
pytest -m git
```

### Run GUI tests
*   **Windows & macOS:**
    ```bash
    pytest -m gui
    ```
*   **Linux (Headless/CI):**
    ```bash
    xvfb-run pytest -m gui
    ```

## Application Smoke Test Mode

A dedicated CLI mode is provided to verify window creation, translations, styles, and basic widgets boot cleanly without starting threads or prompting dialogs.

Run the smoke test:
```bash
python -m github_org_sync --smoke-test
```
Or on compiled Windows binary:
```bash
github-org-sync.exe --smoke-test
```

## Security Rules Enforcement

1.  **Direct Subprocess Ban**: Direct calls to `subprocess.run` or `subprocess.Popen` are strictly banned outside the central `github_org_sync.utils.process` runner (verified by AST checks in `test_security_rules.py`).
2.  **Force Push Block**: Any Git command args containing `--force` or `--force-with-lease` will raise a `ValueError` inside the process runner, failing immediately and safely.
