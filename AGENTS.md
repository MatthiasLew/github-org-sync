# Agent Guidelines - github-org-sync

This file contains rules and guidelines for AI agents working on this project.

## Code Quality and Style
- Use Python 3.11+ syntax and type hints for all public functions and classes.
- Follow Ruff conventions and maintain clean code that passes `ruff check` and `ruff format`.
- Ensure all types are verified with `mypy src`.

## Design Constraints
- Separate GUI layout from business logic (Git operations, GitHub API operations).
- Do not store or log credentials or tokens.
- Execute Git and GitHub commands asynchronously using PySide6 threads/workers (`QThread` or `QRunnable`) to prevent freezing the GUI.
- Implement dry run modes safely: they must never make network mutation requests or change files.
