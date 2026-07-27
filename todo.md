# Implementation Guide - todo.md

This guide explains how to implement each of the proposed features in **github-org-sync** ensuring full cross-platform compatibility for Windows, macOS, and Linux.

---

## 1. "Open in Terminal" Row Context Menu Action

### Description:
Adds a context menu item allowing the user to right-click a repository row and open the command prompt/terminal directly at that repository path.

### Steps:
1. **Translations**:
   Add `menu_open_in_terminal` translations to [translations.py](file:///c:/Users/Praca/fork/MatthiasLew/github-org-sync/src/github_org_sync/i18n/translations.py):
   ```python
   # Polish
   "menu_open_in_terminal": "Otwórz w terminalu",
   # English
   "menu_open_in_terminal": "Open in Terminal",
   ```
2. **Context Menu Setup**:
   Modify [repository_table.py](file:///c:/Users/Praca/fork/MatthiasLew/github-org-sync/src/github_org_sync/ui/repository_table.py). Under `contextMenuEvent`:
   ```python
   # Import utility
   from github_org_sync.utils.process import open_terminal

   # Inside context menu population:
   action_terminal = menu.addAction(_t("menu_open_in_terminal"))
   action_terminal.setEnabled(repo.status != "MISSING" and repo.local_path is not None)

   # In action handling:
   selected_action = menu.exec(event.globalPos())
   if selected_action == action_terminal:
       if repo.local_path:
           open_terminal(repo.local_path)
   ```

---

## 2. Persistent Rotating Application Log Files

### Description:
Enables writing logs to disk in a dedicated `logs` directory inside the platform's AppData directory, keeping the last few runs for troubleshooting.

### Steps:
1. **Configure Logger**:
   Modify [app.py](file:///c:/Users/Praca/fork/MatthiasLew/github-org-sync/src/github_org_sync/app.py) or create a `logging_setup.py` module:
   ```python
   import logging
   from logging.handlers import RotatingFileHandler
   from pathlib import Path
   from github_org_sync.services.report_service import ReportService

   def setup_logging() -> None:
       try:
           # ReportService.get_config_path() returns the config file path,
           # we can extract its parent directory.
           app_dir = Path(ReportService.get_config_path()).parent
           log_dir = app_dir / "logs"
           log_dir.mkdir(parents=True, exist_ok=True)
           log_file = log_dir / "app.log"

           # Rotating log file, max 2MB, keeping 3 old copies
           handler = RotatingFileHandler(
               log_file, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
           )
           formatter = logging.Formatter(
               "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
           )
           handler.setFormatter(formatter)

           # Add to root logger
           root_logger = logging.getLogger()
           root_logger.addHandler(handler)
           logging.info("File logger initialized successfully.")
       except Exception as e:
           print(f"Failed to initialize file logger: {e}")
   ```
2. **Initialize on Startup**:
   Call `setup_logging()` inside the entry point of `app.py` before instantiating `QApplication`.

---

## 3. Git & GitHub CLI Authentication Diagnostic Panel

### Description:
Adds a dialog under **Help -> Run Diagnostics** that checks the user's environment setup and credentials.

### Steps:
1. **Create Diagnostics Service**:
   Create `src/github_org_sync/services/diagnostics_service.py` checking:
   * **Git**: Run `run_process(["git", "--version"])`
   * **GitHub CLI**: Run `run_process(["gh", "--version"])`
   * **Auth Status**: Run `run_process(["gh", "auth", "status"])`
   * **SSH Connectivity**: Run `run_process(["ssh", "-T", "git@github.com"], timeout=5)` (Note: exit code is usually 1, but we parse stderr for "successfully authenticated" string).
2. **Diagnostics Dialog**:
   Create `src/github_org_sync/ui/diagnostics_dialog.py` with a simple table/list showing green checks (:green_circle:) or red crosses (:red_circle:) for each test, along with troubleshooting instructions for failures.
3. **Menu Action**:
   In [main_window.py](file:///c:/Users/Praca/fork/MatthiasLew/github-org-sync/src/github_org_sync/ui/main_window.py), add "Diagnostics Checklist" to the Help menu.

---

## 4. Launch Git Merge Tool from Conflict Resolution Dialog

### Description:
Adds a button to launch `git mergetool` directly from the conflict resolution dialog to easily merge divergent branches.

### Steps:
1. **Git Service Method**:
   Add to `GitService` in [git_service.py](file:///c:/Users/Praca/fork/MatthiasLew/github-org-sync/src/github_org_sync/services/git_service.py):
   ```python
   def launch_merge_tool(self, repo_path: Path) -> None:
       """Launches the configured git mergetool asynchronously."""
       from github_org_sync.utils.process import popen_process
       # Spawns the tool detached so the GUI does not freeze
       popen_process(["git", "mergetool"], cwd=repo_path)
   ```
2. **UI Integration**:
   Locate conflict resolution dialog inside [dialogs.py](file:///c:/Users/Praca/fork/MatthiasLew/github-org-sync/src/github_org_sync/ui/dialogs.py). Add a `btn_launch_mergetool` button next to resolution actions that triggers `git_service.launch_merge_tool`.
