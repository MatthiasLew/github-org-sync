# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.1] - 2026-07-25

### Added
- **Cross-Platform Release Packages**: Packaged native executables and binaries for Linux (`.tar.gz`) and macOS (`.zip`) along with Windows (`.zip`).
- Cross-platform spec configurations for PyInstaller using forward slash paths.

### Fixed
- Fixed directory zipping path error inside macOS packaging and publishing pipelines.

## [1.3.0] - 2026-07-22

### Added
- **Open Existing Workspace Mode**: Scan and inspect local Git repositories directly without specifying a GitHub organization name.
- **Support for Non-GitHub Repositories**: Safely scan and perform local Git operations (Fetch, Update, Open, etc.) on GitLab, Bitbucket, and other self-hosted/custom Git locations.
- **Detected Organization Auto-fill**: Automatically detects and populates the organization name if all scanned GitHub repositories belong to the same owner.
- **Repository Grouping and Filtering**: Filter repository views by hosting platforms and owners (e.g. `GitHub / my-org`, `GitLab / project`).
- **Workspace-to-Org Verification**: Instantly compare scanned local workspace repositories against any GitHub organization to highlight missing/extra repositories.
- Persistence of the chosen workspace scanner settings and last-used app mode on application exit.

### Fixed
- Fixed subprocess UTF-8 encoding page mismatch on Windows environments to prevent Polish and special character mojibake.
- Resolved unhandled exceptions in the repository resolver for non-GitHub/No-remote repositories.

## [1.2.0] - 2026-07-20

### Added
- Application visual logo (SVG design, generated PNG icons, and Windows executable application icon).
- Interactive Git Sync Wizard: guides the user through resolving non-trivial repository states (DIRTY, AHEAD, BEHIND, DIVERGED) step-by-step.
- Resolution actions per state: create backup branches, stash & pull, push (no force-push allowed, displays manual override instructions instead), soft discard changes, fast-forward pull, and merge conflict checks.
- Comprehensive sync result summary displaying counts for skipped, conflict, failed, updated, and resolved repositories.
- Custom context menu action to trigger the resolution dialog for a specific repository.
- Double-click table row action to automatically open the resolve issue dialog.
- Detailed synchronization reporting with granular, machine-readable sync action statuses (`requested_action`, `performed_action`, `before_status`, `after_status`).

### Fixed
- Fixed unhandled lambda signals on application close by cleaning up worker connections.
- Mypy type annotation issues and platform-specific code structure paths.

## [1.1.0] - 2026-07-20

### Added
- Polish and English interface languages with real-time switching.
- System, Light, and Dark interface themes with automatic system color scheme detection.
- Contextual tooltips for all fields, options, and actions.
- Keyboard shortcuts for primary actions (Ctrl+L, Ctrl+R, Ctrl+Shift+S, Ctrl+F, F1).
- Context menus for opening local directories or GitHub repo links.
- Logs panel with Clear Log action and copy selection capabilities.
- Repository search and Git status filters.
- Dialog Help (Getting Started) and About (displaying version 1.1.0).
- Windows execution parameters to hide subprocess terminal prompt windows silently.
- Type checking markers (py.typed) for full PEP 561 compliance.

### Fixed
- Prevented command prompt console window flashing on Windows during Git and GitHub CLI operations.
- Prevented duplicate background worker threads during workspace directory changes.
- Fixed stale status results display by automatically resetting table items on workspace changes.
- Safe thread cancellation checks during local status inspections.

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
