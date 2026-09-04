# Implementation Guide - todo.md

This document outlines the step-by-step guides for implementing the proposed features.

---

## 1. GUI Commit & Staging Manager [COMPLETED]

### Description
Enables developers to stage/unstage individual files inside dirty repositories and commit changes directly from the GUI.

### Steps
1. **Git Service Methods**:
   Add `stage_file(self, path: Path, file_path: str)`, `unstage_file(self, path: Path, file_path: str)`, and `commit_changes(self, path: Path, message: str)` to `git_service.py`.
2. **Staging Interface**:
   Create a new staging/commit panel inside [ResolveIssueDialog](file:///c:/Users/Praca/fork/MatthiasLew/github-org-sync/src/github_org_sync/ui/dialogs.py#L164) shown when status is `DIRTY`.
3. **Commit Action**:
   Add a text edit field for the commit message and a "Commit" button that triggers the commit and refreshes local status.
4. **Localization**:
   Register localization keys for commit fields, success prompts, and warnings.

---

## 2. Git Stash Drawer / Visual Manager

### Description
Displays the repository's stash stack and provides push/pop/drop actions.

### Steps
1. **Git Service Methods**:
   Add `get_stash_list(self, path: Path) -> list[str]`, `stash_push(self, path: Path, message: str)`, `stash_pop(self, path: Path, index: int)`, and `stash_drop(self, path: Path, index: int)` to `git_service.py`.
2. **Stash Drawer UI**:
   Build `src/github_org_sync/ui/stash_dialog.py` showing the stash stack with pop/drop actions.
3. **Menu/Context Integration**:
   Add "Manage Stash Stack..." to the context menu in [repository_table.py](file:///c:/Users/Praca/fork/MatthiasLew/github-org-sync/src/github_org_sync/ui/repository_table.py#L559).
4. **Translations**:
   Register localized strings for stash lists, empty states, and push/pop actions.

---

## 3. Prune Stale Local & Remote Tracking Branches

### Description
Cleans up local branch lists by identifying and pruning local branches whose remote branches have been deleted on the server.

### Steps
1. **Git Service Command**:
   Add `prune_branches(self, path: Path) -> tuple[int, list[str]]` to `git_service.py` to run `git remote prune origin` and identify merged branches.
2. **Prune Action UI**:
   Add a right-click action "Prune Stale Branches..." to the repository table.
3. **Execution & Feedback**:
   Execute the pruning asynchronously, displaying a success summary showing branches deleted/pruned.
4. **Unit Tests**:
   Create tests covering branch detection and mock output verification.

---

## 4. Visual History Log Graph (git log --graph)

### Description
Renders a readable monospaced layout displaying a visual representation of the branch graph and commit log history.

### Steps
1. **Git Service Method**:
   Add `get_log_graph(self, path: Path, limit: int = 25) -> str` to `git_service.py` using `git log --graph --oneline --decorate --all -n <limit>`.
2. **Logs Display Tab**:
   Add a sub-tab or side panel in the UI showing the visual history output for the selected repository.
3. **Auto-refresh**:
   Refresh the graph automatically on workspace changes or after branch checkouts.
4. **Tests**:
   Test graph string formatting parsing.

---

## 5. Git LFS Status Monitor

### Description
Checks if a repository uses Git Large File Storage (LFS) and reports missing files or LFS tracking status.

### Steps
1. **LFS Checker Utility**:
   Add `get_lfs_status(self, path: Path) -> dict[str, Any]` to `git_service.py` checking `git lfs status` and `git lfs ls-files`.
2. **Table Badge or Status Column**:
   Render a small "LFS" badge or label in the repository table status column if a repo uses LFS.
3. **Diagnostics Warning**:
   Add LFS presence checks to the Environment Diagnostics checklist.
4. **Localization**:
   Register LFS translations.
