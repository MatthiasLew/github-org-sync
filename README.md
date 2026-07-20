# GitHub Organization Repository Synchronizer

`github-org-sync` is a cross-platform desktop and command-line application built with Python 3.11+, PySide6, and the GitHub CLI. It provides a visual and automated way to discover, clone, and update all repositories belonging to any GitHub organization.

![GUI Screenshot Placeholder](docs/images/gui_screenshot.png)

## New in Version 1.2.0
- **Interactive Git Sync Wizard**: Guides you step-by-step through resolving non-trivial repository states (DIRTY, AHEAD, BEHIND, DIVERGED).
- **Comprehensive Conflict Resolution**: Choose to stash & pull, force push, create backup branches, soft discard local edits, fast-forward pull, or do deep merges directly from dialog interfaces.
- **Double-Click Resolution Dialog**: Double-click any repository row or select "Resolve Issue" from the custom context menu to invoke the Git Resolve dialog.
- **Application Logo**: Beautiful vector SVG logo, generated multi-size icons, and embedded executable application icon.
- **Summary Count Report**: Shows sync success, failure, updated, conflict, and skipped totals.
- **Detailed Sync Statusing**: Richer status information in synchronization report files (`requested_action`, `performed_action`, `before_status`, `after_status`).

## Windows Release Installation

To run the application on Windows without installing Python:

1. Download the release package (`github-org-sync-v1.2.0-windows-x64.zip`) from the [Releases](https://github.com/MatthiasLew/github-org-sync/releases) page.
2. Extract the complete archive to a directory of your choice.
3. Run `github-org-sync.exe` inside the extracted folder.

*Important:* The application still requires external command-line tools to interact with Git and GitHub. Make sure you have installed:
* [Git](https://git-scm.com/) (verify with `git --version`)
* [GitHub CLI (gh)](https://cli.github.com/) (verify with `gh --version`)

Before synchronizing private repositories, log in via the GitHub CLI:
```powershell
gh auth login
gh auth status
```

## Developer Guide & Requirements
- Python 3.11+
- [Git](https://git-scm.com/) installed and on PATH.
- [GitHub CLI (gh)](https://cli.github.com/) installed and authenticated.

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/MatthiasLew/github-org-sync.git
   cd github-org-sync
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # On Windows:
   .venv\Scripts\activate
   # On Linux/macOS:
   source .venv/bin/activate
   ```
3. Install dependencies and the package:
   ```bash
   pip install -e .[dev]
   ```

## Running the Application
### GUI Mode
Run the desktop GUI via:
```bash
python -m github_org_sync
```

### CLI Mode
Show status of repositories:
```bash
python -m github_org_sync.cli status --org subactor --workspace C:\Users\Praca\fork\subactor
```
Sync (clone and update) repositories:
```bash
python -m github_org_sync.cli sync --org subactor --workspace C:\Users\Praca\fork\subactor
```
Add `--dry-run` to run without performing any local modifications.

## Running Tests
Run the test suite using:
```bash
python -m pytest -q
```

## Packaging
To build a standalone executable on Windows:
```powershell
.\scripts\build_windows.ps1
```
The output executable will be placed in the `dist/` directory.
