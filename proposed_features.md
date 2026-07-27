# Proposed Features - github-org-sync

Below is the list of proposed enhancements and feature ideas for the **github-org-sync** application. All of these features are designed to work seamlessly across all three target operating systems: **Windows**, **macOS**, and **Linux**.

---

## Feature List & Status

### 1. Parallel Repository Syncing & Status Inspection
*   **Status**: :white_check_mark: **COMPLETED** (Released in v1.3.5)
*   **Description**: Speeds up organizations with large counts of repositories by running cloning, pulling, and status inspection concurrently using Python's `ThreadPoolExecutor`.

### 2. "Open in Terminal" Row Context Menu Action
*   **Status**: :pause_button: **TODO**
*   **Description**: Adds a right-click option on any repository in the GUI table to open a visible OS terminal directly inside that repository's local folder path.
*   **Cross-platform Support**: Runs PowerShell/cmd.exe on Windows, Terminal.app on macOS, and detects common terminals (`gnome-terminal`, `konsole`, etc.) on Linux.

### 3. Persistent Rotating Application Log Files
*   **Status**: :pause_button: **TODO**
*   **Description**: Configures Python's standard `RotatingFileHandler` to save log statements to disk inside the application data directory.
*   **Cross-platform Support**: Stores logs under `%APPDATA%/github-org-sync/logs` on Windows, `~/Library/Logs/github-org-sync` on macOS, and `~/.config/github-org-sync/logs` on Linux.

### 4. Git & GitHub CLI Authentication Diagnostic Panel
*   **Status**: :pause_button: **TODO**
*   **Description**: Adds a diagnostics checklist tool under the Help menu that verifies the user's environment setup (checking if Git is installed, if GitHub CLI is installed, if the CLI is authenticated, and if SSH connection to GitHub succeeds).
*   **Cross-platform Support**: Executes standard commands in the background to report setup issues cleanly.

### 5. Launch Git Merge Tool from Conflict Resolution Dialog
*   **Status**: :pause_button: **TODO**
*   **Description**: When a synchronization encounters merge conflicts, the resolution dialog will offer a button to directly spawn the system's default merge/diff tool (`git mergetool`) inside the repository folder.
*   **Cross-platform Support**: Opens the user's configured merging app (e.g. VS Code, KDiff3, Meld) on all systems.
