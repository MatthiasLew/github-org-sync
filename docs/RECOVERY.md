# Safe Recovery & Conflict Resolution Guide

This guide explains how `github-org-sync` protects your code during uncommitted changes, merge conflicts, or unexpected interruptions, and details step-by-step recovery actions.

---

## 1. Safe Stash Recovery Protocol

When `preserve_local_changes` (enabled by default) is active, `github-org-sync` performs an automatic stash before pulling remote updates:

```text
Working Tree (Dirty) ─► git stash push -m "autostash <timestamp>" ─► git pull --ff-only ─► git stash pop
```

### What Happens If Stash Pop Conflicts?

If incoming remote commits touch the same lines as your local uncommitted changes:
1. `git stash pop` reports a merge conflict.
2. **CRITICAL SAFETY RULE**: `github-org-sync` **NEVER** drops the stash when a conflict occurs.
3. Your uncommitted work remains safely stored in `git stash` (typically `stash@{0}`), while conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) are placed in the working tree.
4. The synchronization report flags the repository with status `CONFLICT`.

### Recovery Steps:
1. Open the conflicting repository in your terminal or editor:
   ```bash
   cd <workspace>/<repo-name>
   ```
2. Inspect the conflicted files:
   ```bash
   git status
   ```
3. Resolve the conflict markers in the affected files or use a visual merge tool:
   ```bash
   git mergetool
   ```
4. Verify your files and stage resolved changes:
   ```bash
   git add <resolved-file>
   ```
5. Once your working tree is correct, drop the preserved stash entry:
   ```bash
   git stash drop stash@{0}
   ```

---

## 2. Diverged Branch Recovery (`DIVERGED`)

If a local branch has commits that have not been pushed, and the remote branch has also advanced with new commits:
- `github-org-sync` **refuses** to pull or fast-forward to prevent overwriting your local commits.
- The repository is marked as `DIVERGED` (or `BLOCKED` in `plan`).

### Recovery Steps:
1. Navigate to the repository:
   ```bash
   cd <workspace>/<repo-name>
   ```
2. Rebase or merge remote updates explicitly:
   ```bash
   git fetch origin
   git rebase origin/main
   # Or: git merge origin/main
   ```
3. Once linear history or merge commit is established, push your local commits:
   ```bash
   git push origin main
   ```

---

## 3. Stale Workspace Lock Recovery

If an execution was forcibly terminated (e.g., hard system reboot, power failure), a lock file `.sync.lock` and its metadata `.sync.lock.info` might remain in the workspace directory.

`github-org-sync` automatically checks whether the PID in `.sync.lock.info` is currently running:
- If the PID is dead, the stale lock is automatically released.
- If for any reason the lock prevents execution:
  ```bash
  github-org-sync doctor --workspace <PATH>
  ```
  Or manually delete the lock files:
  ```bash
  rm <workspace>/.sync.lock
  rm <workspace>/.sync.lock.info
  ```

---

## 4. Partial Clone Cleanup

If a clone is interrupted halfway (e.g., laptop closed, WiFi lost):
- The destination folder in your workspace was never created.
- The partial data was written to `workspace/.github-org-sync-tmp/`.
- The temporary folder is cleaned up automatically on the next run or can be safely deleted without risk to existing repositories:
  ```bash
  rm -rf <workspace>/.github-org-sync-tmp
  ```
