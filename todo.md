# Implementation Guide - todo.md

This guide explains how to implement each of the proposed features in **github-org-sync** ensuring full cross-platform compatibility for Windows, macOS, and Linux.

---

## 1. Persistent Rotating Application Log Files

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
           app_dir = Path(ReportService.get_config_path()).parent
           log_dir = app_dir / "logs"
           log_dir.mkdir(parents=True, exist_ok=True)
           log_file = log_dir / "app.log"

           handler = RotatingFileHandler(log_file, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
           formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
           handler.setFormatter(formatter)

           root_logger = logging.getLogger()
           root_logger.addHandler(handler)
           logging.info("File logger initialized successfully.")
       except Exception as e:
           print(f"Failed to initialize file logger: {e}")
   ```
2. **Initialize on Startup**:
   Call `setup_logging()` inside the entry point of `app.py` before instantiating `QApplication`.

---

## 2. Git & GitHub CLI Authentication Diagnostic Panel

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

## 3. Launch Git Merge Tool from Conflict Resolution Dialog

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

---

## 4. Git Branch Switcher & Checkout Dialog

### Description:
Adds a right-click menu item "Switch Branch..." to switch repository branches inside the GUI.

### Steps:
1. **Git Service Methods**:
   Add to [git_service.py](file:///c:/Users/Praca/fork/MatthiasLew/github-org-sync/src/github_org_sync/services/git_service.py):
   ```python
   def get_local_branches(self, repo_path: Path) -> list[str]:
       """Returns list of local branch names in the repository."""
       res = self.run_process(["git", "branch", "--format=%(refname:short)"], cwd=repo_path)
       return [line.strip() for line in res.stdout.splitlines() if line.strip()]


   def checkout_branch(self, repo_path: Path, branch_name: str) -> tuple[bool, str]:
       """Performs a git checkout to the selected branch."""
       try:
           res = self.run_process(["git", "checkout", branch_name], cwd=repo_path)
           return True, res.stdout or res.stderr
       except Exception as e:
           return False, str(e)
   ```
2. **Checkout UI Dialog**:
   Create a `SwitchBranchDialog(QDialog)` inside [dialogs.py](file:///c:/Users/Praca/fork/MatthiasLew/github-org-sync/src/github_org_sync/ui/dialogs.py) with a `QComboBox` listing local branches.
3. **Table Context Menu Integration**:
   Add "Switch Branch..." to `_show_context_menu` in [repository_table.py](file:///c:/Users/Praca/fork/MatthiasLew/github-org-sync/src/github_org_sync/ui/repository_table.py) and update the table in-place upon successful checkout.

---

## 5. Hosting Provider Badges in Repository Table

### Description:
Draws visual badges or host-specific colored labels in the repository list table to distinguish between GitHub, GitLab, and Bitbucket references.

### Steps:
1. **Define Table Header**:
   In [repository_table.py](file:///c:/Users/Praca/fork/MatthiasLew/github-org-sync/src/github_org_sync/ui/repository_table.py), add a "Host" column or append it to the columns structure.
2. **Populate Host Badges**:
   During `_set_row_data`, read `repo.computed_hosting`. Create a custom colored label:
   * **GitHub**: Blue/black theme label.
   * **GitLab**: Orange theme label.
   * **Bitbucket**: Deep blue theme label.
3. **Draw custom widgets**:
   Insert the custom badge widget using `self.setCellWidget(row, col, badge_widget)`.

---

## 6. Offline Workspace State Cache

### Description:
Caches scanned local repository status metadata to a local file, enabling instantaneous UI startup in offline mode without disk rescans.

### Steps:
1. **Cache Loading & Saving**:
   In [config.py](file:///c:/Users/Praca/fork/MatthiasLew/github-org-sync/src/github_org_sync/config.py):
   ```python
   def save_workspace_cache(self, org_name: str, repos: list[Repository]) -> None:
       cache_path = Path(self.config_path).parent / f"cache_{org_name}.json"
       data = [
           {
               "name": r.name,
               "status": r.status,
               "branch": r.branch,
               "ahead": r.ahead,
               "behind": r.behind,
               "result": r.result,
           }
           for r in repos
       ]
       cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


   def load_workspace_cache(self, org_name: str) -> list[dict[str, Any]]:
       cache_path = Path(self.config_path).parent / f"cache_{org_name}.json"
       if not cache_path.exists():
           return []
       return json.loads(cache_path.read_text(encoding="utf-8"))
   ```
2. **Main Window Wiring**:
   In [main_window.py](file:///c:/Users/Praca/fork/MatthiasLew/github-org-sync/src/github_org_sync/ui/main_window.py), load the cache upon typing/selecting an organization, pre-populating the table immediately, and save the cache after every successful scan.
