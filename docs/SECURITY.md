# Security Policy & Safety Architecture

`github-org-sync` is designed to protect local work and fail closed when an operation cannot be proven safe. When synchronizing codebases across an organization, developer work must never be silently discarded, overwritten, or corrupted.

---

## 1. Fail-Closed Safety Principles

1. **Strict Prohibition of Force Operations**:
   - The application enforces a central Git policy validator (`validate_git_policy` in `src/github_org_sync/utils/process.py`).
   - Any attempt to run destructive commands—including `git push --force`, `git push --force-with-lease`, `git reset --hard`, or `git clean`—immediately raises a `GitSecurityPolicyError` and halts execution.

2. **Non-Interactive Process Environment**:
   - All Git and GitHub CLI processes run with interactive prompts completely disabled:
     - `GIT_TERMINAL_PROMPT=0`
     - `GH_PROMPT_DISABLED=1`
     - `GIT_SSH_COMMAND=ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new`
   - Prevents hangs when waiting for credentials or host key confirmations.

3. **Subprocess Timeouts**:
   - Subprocess commands are bounded by default timeouts (45s for standard operations, 180s for network operations like clone/fetch).
   - Prevents indefinite thread starvation in automation environments.

4. **Windows Flash Prevention**:
   - Under Windows, all subprocesses are spawned with the `CREATE_NO_WINDOW` flag (`0x08000000`) and `shell=False`.
   - Command prompt windows never flash or steal focus from active windows.

---

## 2. Remote Identity Verification

To prevent syncing against incorrect remotes or mismatched forks, every repository is verified using exact URL parsing (`ParsedGitUrl`):
- Exact domain matching (case-insensitive `github.com` or custom enterprise host).
- Exact organization / owner matching (case-insensitive).
- Exact repository name matching (case-insensitive, ignoring trailing `.git` and slashes).
- Repositories pointing to unexpected owners or repositories are flagged as `WRONG_REMOTE` and blocked from sync.

---

## 3. Workspace Concurrency Locking

To prevent race conditions between simultaneous CLI and GUI processes operating on the same workspace:
- Uses `WorkspaceLock` based on file locking (`.sync.lock`).
- Records lock holder metadata (`.sync.lock.info`):
  - Operating system PID
  - Executed command
  - ISO-8601 UTC timestamp
- **Stale Lock Detection**: Automatically inspects whether the recording PID is still alive using cross-platform checks (Windows `OpenProcess` / Unix `os.kill(pid, 0)`). Orphaned locks left behind after machine crashes are safely broken.

---

## 4. Atomic Cloning

Partially cloned repositories caused by network drops or process interruptions can leave unusable working copies.
- `github-org-sync` clones new repositories into an isolated temporary folder:
  `workspace/.github-org-sync-tmp/<repo>-<uuid>`
- Once the clone finishes:
  1. Validates repository integrity (`is_git_repository`).
  2. Validates remote URL identity.
  3. Atomically replaces/moves the temporary folder to the final workspace destination (`os.replace` / `Path.replace`).
- On failure, temporary folders are purged, leaving the user's workspace untouched.

---

## 5. Secure Updater Hardening

The built-in self-updater (`UpdateService`) downloads official release assets from GitHub Releases and validates security constraints:
1. **SHA-256 Checksum Verification**:
   - Computes the SHA-256 hash of downloaded assets in 64KB blocks.
   - Compares the calculated hash against `checksums.txt` published with the release before executing or extracting files.
2. **Zip Slip / Path Traversal Prevention**:
   - Archives are extracted using `safe_extract_zip` and `safe_extract_tar`.
   - Every archive member is inspected using `Path.resolve()` to ensure its destination falls strictly inside the extraction directory. Any path containing `../` or absolute destination targets is rejected with an error.
