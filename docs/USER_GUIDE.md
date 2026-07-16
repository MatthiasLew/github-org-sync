# User Guide - GitHub Organization Sync

This guide provides instructions on how to use the GitHub Organization Sync application to clone and update repositories.

---

## Prerequisites

Before running the application, please make sure the following software is installed on your computer:

1. **Git**: Used to clone and update source code repositories.
2. **GitHub CLI (`gh`)**: Used to securely connect to your GitHub account and search for organization repositories.

### Logging In
Open your command terminal (Command Prompt or PowerShell on Windows, Terminal on Linux) and type:
```bash
gh auth login
```
Follow the interactive prompt to sign in with your GitHub account.

---

## Using the Desktop Application

### 1. Starting the Application
Double-click the executable (`github-org-sync.exe` inside the `dist` folder) or launch it from the command line:
```bash
python -m github_org_sync
```

### 2. Specifying the Organization
At the top, enter the GitHub organization you want to synchronize. You can enter:
- Just the name: `subactor`
- The full website URL: `https://github.com/subactor`

Click **Load Repositories**. The application will list all repositories belonging to that organization.

### 3. Choosing a Workspace Folder
Click **Choose Folder** to select a directory on your computer where the repositories should be saved. 
- *Note: Repositories will be downloaded directly into this directory (e.g. `C:\Users\Praca\fork\subactor\my-repo`).*

### 4. Customizing Sync Options
- **Include Archived**: Check this if you also want to download old, archived repositories.
- **Include Forks**: Check this to download copies of other repositories that your organization has forked.
- **Use SSH**: Check this if you connect to GitHub using SSH keys instead of HTTPS.
- **Preserve Changes (Stash)**: Recommended. If you have unsaved changes in a repository, the application will temporarily hide them (stash), update the repository, and then restore your changes.
- **Fetch Only**: Only downloads metadata updates from GitHub without altering local branch files.
- **Dry Run**: Simulates the sync process without making any changes to files or downloading anything.

### 5. Selecting Repositories to Sync
Use the checkboxes in the table to choose which repositories to synchronize. You can use the helper buttons:
- **Select All** / **Select None**
- **Select Missing**: Selects only repositories that are not yet downloaded.
- **Select Outdated**: Selects repositories that have newer commits on GitHub.

### 6. Starting Synchronization
Click **Sync Selected**. The progress bar and console log at the bottom will display the actions in real time. 
You can stop the execution safely at any time by clicking **Cancel**.

### 7. Reviewing Reports
Once finished, click **Open Report** to review a Markdown log of the operation. Reports are saved inside your system's Application Data folder under `github-org-sync/reports/`.
To view your files immediately, click **Open Workspace**.

---

## Troubleshooting Status Messages

- **MISSING**: The repository is not downloaded locally yet. Ready to clone.
- **UP_TO_DATE**: The local repository matches the branch on GitHub.
- **DIRTY**: You have unsaved changes in your local directory. The sync will stash them before updating if option is checked.
- **WRONG_REMOTE**: The local directory points to a different owner or organization. The sync is skipped to prevent overwriting files.
- **CONFLICT**: Autostash restore encountered a conflict. You must open that folder and resolve git conflicts manually.
