# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-07-17

### Added
- Desktop GUI for loading and synchronizing repositories from GitHub organizations.
- GitHub CLI authentication and organization repository discovery.
- Safe clone, fetch, and fast-forward update operations.
- Detection of repository states such as dirty, ahead, behind, diverged, and wrong remote.
- Dry-run mode and cooperative cancellation.
- JSON and Markdown synchronization reports.
- Command-line interface with `--version` option.
- Windows executable distribution and build script.
- Headless Docker validation matrix for Windows and Linux environments.
- Comprehensive Git offline integration tests covering all 12 operational scenarios.

### Fixed
- Fixed cross-platform type compatibility and path execution for opening reports/folders on macOS (using `open`) and Linux (using `xdg-open`).
- Resolved missing runtime dependencies required to test PySide6 within headless CI runners.

### Security
- Repository synchronization blocks destructive Git operations (no hard resets or forced changes).
- Existing repositories with mismatched remotes (wrong owner/name) are protected and not modified.
- GitHub credentials and tokens are never stored by the application (delegated to standard GitHub CLI auth).

## [0.1.0] - 2026-07-16

### Added
- Created private GitHub repository `MatthiasLew/github-org-sync`.
- Initialized local repository and set up `.gitignore`, `pyproject.toml`, `LICENSE`, `AGENTS.md`.
- Implemented core database models (`Repository`, `SyncResult`, `Organization`).
- Implemented `GitHubService` to discover organization repositories via GitHub CLI.
- Implemented `GitService` to query repository status (checking branches, tracking upstream ahead/behind values, wrong remote validation) and run safe updates (fetch, ff-only pull, autostash, stash pop).
- Implemented `SyncService` queue manager orchestrating safe clones and updates.
- Implemented `ReportService` to record execution metrics in JSON and Markdown files under user appdata paths.
- Implemented `ConfigManager` to persist user options and main window positions.
- Developed PySide6 Desktop GUI (styled dark-theme UI layout, customized QTableWidget for status styling, asynchronous worker threads for non-blocking execution, live log console).
- Developed CLI interface with subcommands `list`, `status`, and `sync`.
- Created comprehensive architecture documentation (`docs/ARCHITECTURE.md`) and user manual (`docs/USER_GUIDE.md`).
- Added robust test coverage: 30 unit and integration tests (covering Git logic, CLI commands, and PySide6 GUI interactions).
