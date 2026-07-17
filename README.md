# GitHub Organization Repository Synchronizer

`github-org-sync` is a cross-platform desktop and command-line application built with Python 3.11+, PySide6, and the GitHub CLI. It provides a visual and automated way to discover, clone, and update all repositories belonging to any GitHub organization.

![GUI Mockup Place Holder](docs/images/gui_screenshot.png)

## Features
- **Organization Repository Discovery**: Fetch all repositories of any organization you have access to.
- **Git State Assessment**: Identifies local status (up-to-date, missing, modified/dirty, ahead, behind, diverged, wrong remote).
- **Safe Git Operations**: Auto-stash changes when updating, fast-forward pulls only, avoids destructive actions (like hard resets).
- **Asynchronous Execution**: PySide6 thread worker prevents GUI freeze during operations.
- **Dynamic Operations Log**: Live output scroll showing exactly what the sync worker is executing.
- **JSON & Markdown Reports**: Generates details reports stored locally in application data paths.

## Windows Release

To run the application on Windows without installing Python or setting up virtual environments:

1. Download `github-org-sync-v1.0.0-windows-x64.zip` from the [Releases](https://github.com/MatthiasLew/github-org-sync/releases) page.
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

## Requirements
- Python 3.11+
- [Git](https://git-scm.com/) installed and on PATH.
- [GitHub CLI (gh)](https://cli.github.com/) installed and authenticated.

## Installation
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
3. Install dependencies:
   ```bash
   pip install -e .[dev]
   ```

## Running the Application
### GUI Mode
Run the desktop GUI via:
```bash
python -m github_org_sync
```
or
```bash
python -m github_org_sync.app
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

## GitHub CLI Authentication
Ensure you are authenticated:
```bash
gh auth status
```
If not logged in, run:
```bash
gh auth login
```
*Note: Make sure your credentials have scopes to read the organization's repositories.*

## Safety Constraints
- Only updates repositories if the local `origin` URL matches the target organization (`github.com/org-name/repo-name`). If it doesn't, status is marked as `WRONG_REMOTE` and sync is skipped.
- Does not run `git reset --hard` or `git clean`.
- Stores configurations and execution reports in `<user-app-data>/github-org-sync/`.

## Running Tests
Run tests using:
```bash
python -m pytest -q
```

## Packaging
To build a standalone executable on Windows:
```powershell
.\scripts\build_windows.ps1
```
The output executable will be placed in the `dist/` directory.

## Limitations & Roadmap
- Git operations require local Git and GitHub CLI.
- No direct multi-threaded parallel cloning to avoid disk/network bottlenecks and GitHub API rate limits.
