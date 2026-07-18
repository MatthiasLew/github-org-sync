# User Guide - GitHub Organization Sync

This guide provides instructions on how to use the GitHub Organization Sync application to discover, clone, and update repositories.

---

## Prerequisites

Before running the application, make sure the following software is installed on your system:

1. **Git**: Required to clone and update source code repositories. Verify with `git --version`.
2. **GitHub CLI (`gh`)**: Required to securely connect to your GitHub account and load organization repositories. Verify with `gh --version`.

### Authenticating GitHub CLI
Before using the synchronizer, you must be logged into GitHub CLI. Open a command terminal (e.g., PowerShell on Windows, Terminal on Linux/macOS) and execute:
```bash
gh auth login
```
Follow the interactive steps to sign in. To verify status:
```bash
gh auth status
```

---

## Using the Desktop Application

### 1. Starting the Application
Double-click `github-org-sync.exe` inside your extracted directory (or run `python -m github_org_sync` if running from source).

*Note on Windows:* All commands are executed silently behind the scenes. You will not experience flashing command prompt windows when the application runs Git or GitHub CLI actions.

### 2. Basic Configuration
- **GitHub Organization**: Type the name or full URL of the target organization (e.g., `subactor` or `https://github.com/subactor`).
- **Load Repositories**: Click this button (or press `Ctrl+L`) to pull the list of organization repositories from GitHub.
- **Workspace Folder**: Click **Choose Folder** to select where the repositories will be saved on your computer.

### 3. Localization and Styling
- **Language**: Switch between **Polski** and **English** on the fly under `Settings -> Language` (or `Ustawienia -> Język`). UI texts, headers, tooltips, and log columns will retranslate instantly.
- **Themes**: Switch between **System** (follows OS appearance), **Light**, or **Dark** themes under `Settings -> Theme` (or `Ustawienia -> Motyw`). Your choice is remembered between runs.

### 4. Interactive Table Features
- **Search & Filters**: Type in the search box to filter repositories by name (or press `Ctrl+F`). Use the dropdown next to the search box to filter by specific Git statuses (Missing, Up to date, Local changes, Behind, Ahead, Diverged, Errors).
- **Sorting**: Click any column header to sort the list (e.g. by repository name or status).
- **Double-click Action**: Double-clicking any repository row in the table opens its local folder in your file manager (if it exists).
- **Context Menu**: Right-click any row to open its local folder or go directly to the GitHub page in your browser. Right-clicking the logs panel allows you to copy message lines.
- **Tooltip Help**: Hover over any button, checkbox, input, or table header to see a detailed explanation of its function.

### 5. Running Synchronization
- Select repositories by checking individual boxes, or use the quick buttons (**Select All**, **Select None**, **Select Missing**, **Select Outdated**).
- Customize options:
  - *Preserve local changes (stash)*: Auto-stashes modified files before updating, then restores them.
  - *Dry run*: Simulates the synchronization without changing files.
  - *Use SSH*: Use SSH keys instead of HTTPS to connect.
  - *Fetch only*: Downloads metadata from GitHub without modifying files.
- Click **Sync Selected** (or press `Ctrl+Shift+S`). If running in write mode (not dry run), a confirmation summary will show.
- You can stop the synchronization at any time by clicking **Cancel** (or pressing `Esc`). The worker thread will safely terminate after finishing the current repository.
- If you close the application during active synchronization, a warning popup will ask for confirmation before terminating background workers.

### 6. Local Status Refresh
If you want to re-examine the local directories without downloading the entire list from GitHub again, click **Refresh Status** (or press `Ctrl+R`). Changing your workspace directory will also automatically reset statuses in the table to prevent showing stale results.
