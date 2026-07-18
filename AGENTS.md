# Agent Guidelines - github-org-sync

This file contains rules and guidelines for AI agents working on this project.

## Code Quality and Style
- Use Python 3.11+ syntax and type hints for all public functions and classes.
- Follow Ruff conventions and maintain clean code that passes `ruff check` and `ruff format`.
- Ensure all types are verified with `mypy src`. Use `src/github_org_sync/py.typed` to enable type annotations check.

## Subprocess Execution Rules
- Do NOT run subprocesses directly using `subprocess.run` or `subprocess.Popen` in GUI or services layers.
- Always use the wrappers `run_process` and `popen_process` from `github_org_sync.utils.process`.
- This ensures that on Windows, command prompt windows are hidden automatically (`CREATE_NO_WINDOW`) and do not flash on the screen.
- Do NOT pass `shell=True`.

## Internationalization & Localization
- Never hardcode user-visible texts directly inside UI classes.
- Retrieve all UI texts, buttons, placeholders, dialogs, warnings, and statuses using `_t(key)` from `github_org_sync.i18n`.
- Keep Polish (`pl`) and English (`en`) dictionary keys synchronized in `src/github_org_sync/i18n/translations.py`.

## Lifecycle & State Control
- Enforce the GUI State Machine constraints in `MainWindow._set_app_state(state)` to avoid concurrent executions.
- Before starting any worker thread, call `_cancel_active_worker()` to safely cancel and clean up any running `QThread`.
- Changing the workspace path must instantly stop active inspections and invalidate table statuses to prevent race conditions or writing stale results.
