# GitHub Organization Repository Synchronizer

`github-org-sync` is a cross-platform desktop and command-line application built with Python 3.11+, PySide6, and the GitHub CLI. It provides a visual and automated way to discover, clone, and update all repositories belonging to any GitHub organization.

![GUI Screenshot Placeholder](docs/images/gui_screenshot.png)

## New in Version 1.1.0
- **Multi-language Interface**: Switch between **Polski** and **English** in real-time under `Settings -> Language` (or `Ustawienia -> Język`). Language choices are persisted.
- **Theme Selection**: Choose between **System**, **Light**, or **Dark** themes under `Settings -> Theme` (or `Ustawienia -> Motyw`). System theme matches OS settings automatically.
- **Context Menus**: Right-click any repository row to open its local folder or view its homepage on GitHub. Copy console messages to your clipboard with a right-click on the log panel.
- **Improved Workspace Lifecycle**: Invalidate local status instantly when changing workspace paths, stopping background workers safely to avoid race conditions.
- **Table Search & Status Filters**: Filter by repository name or status (Missing, Up to date, Local changes, Behind, Ahead, Diverged, Errors).
- **Column Sorting & Width Persistence**: Sort columns by clicking headers. Custom column widths, window size, and positions are remembered.
- **Silent execution on Windows**: All Git and GitHub CLI subprocesses are executed without flashing command prompt windows (`CREATE_NO_WINDOW`).
- **Data Validation & Pre-Sync Summaries**: Validates organization inputs and workspace folders, displaying a settings summary dialog before starting synchronization.
- **Shortcuts support**:
  - `Ctrl+L` - Load repositories
  - `Ctrl+R` - Refresh status
  - `Ctrl+Shift+S` - Sync selected
  - `Ctrl+F` - Focus search input
  - `F1` - Getting Started Guide
- **Getting Started Guide & About Dialog**: Instantly accessible guides available under the `Help` menu.

## Windows Release Installation

To run the application on Windows without installing Python:

1. Download the release package (`github-org-sync-v1.1.0-windows-x64.zip`) from the [Releases](https://github.com/MatthiasLew/github-org-sync/releases) page.
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
