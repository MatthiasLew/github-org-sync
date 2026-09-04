# Proposed Features - github-org-sync

Below is the list of new proposed enhancements and feature ideas for the **github-org-sync** application. All of these features are designed to work seamlessly across Windows, macOS, and Linux.

---

## Feature List & Status

### 1. GUI Commit & Staging Manager
*   **Status**: :white_check_mark: **DONE**
*   **Description**: Enables developers to stage/unstage individual files inside dirty repositories and commit changes directly from the GUI using a text field for the commit message.
*   **Cross-platform Support**: Runs standard `git add`, `git reset`, and `git commit` commands using safe subprocess execution.

### 2. Git Stash Drawer / Visual Manager
*   **Status**: :white_check_mark: **DONE**
*   **Description**: Exposes a stash panel displaying the repository's stash stack (`git stash list`) and provides buttons to manually push (stash changes), pop, or drop stashes.
*   **Cross-platform Support**: Implements Git stash commands uniformly across all operating systems.

### 3. Prune Stale Local & Remote Tracking Branches
*   **Status**: :pause_button: **TODO**
*   **Description**: Cleans up local branch lists by identifying and pruning local branches whose remote tracking branches have already been deleted on the server (calls `git remote prune origin` and filters merged branches).
*   **Cross-platform Support**: Resolves tracking branch references cleanly without modifying any active work trees.

### 4. Visual History Log Graph (git log --graph)
*   **Status**: :pause_button: **TODO**
*   **Description**: Renders a readable monospaced layout displaying a visual representation of the branch graph and commit log history (`git log --graph --oneline --decorate --all -n 25`) inside a repository detail drawer.
*   **Cross-platform Support**: Renders standard ANSI text formatting in a monospaced text block natively on all platforms.

### 5. Git LFS Status Monitor
*   **Status**: :pause_button: **TODO**
*   **Description**: Checks if a repository uses Git Large File Storage (LFS), displays LFS track configuration, and alerts users if files are missing or if LFS binaries are not installed.
*   **Cross-platform Support**: Checks LFS presence using generic CLI command queries.
