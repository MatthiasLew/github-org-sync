# CLI Contract Specification & Reference

`github-org-sync` provides a deterministic, CLI-first interface designed for scripting, CI/CD automation, AI agent tool calls, and desktop workflows.

---

## 1. Exit Codes

All CLI subcommands return consistent, machine-readable exit codes:

| Code | Constant | Meaning | Description |
| :---: | :--- | :--- | :--- |
| **0** | `EXIT_SUCCESS` | Clean success | All operations completed with clean status; repository is clean or synced without conflicts. |
| **1** | `EXIT_ATTENTION` | Attention required | Operation succeeded, but repositories require human review (e.g., uncommitted changes, diverged branches, conflicts). |
| **2** | `EXIT_USAGE` | Usage error | Missing arguments, invalid organization name, non-existent workspace, or syntax errors. |
| **3** | `EXIT_ERROR` | System / Git error | Network failure, GitHub CLI authentication error, process timeout, or unhandled exception. |

---

## 2. Standard Structured JSON Envelope (`--json`)

When `--json` is supplied to any command, output written to `stdout` is formatted as a single, valid JSON object following this envelope schema:

```json
{
  "schema_version": "1.0",
  "tool_version": "1.10.0",
  "command": "sync",
  "status": "success",
  "exit_code": 0,
  "summary": "Synchronized 10 repositories.",
  "data": {},
  "errors": []
}
```

### Envelope Fields
- `schema_version` *(string)*: Contract schema version (e.g. `"1.0"`).
- `tool_version` *(string)*: Version of `github-org-sync` (e.g. `"1.10.0"`).
- `command` *(string)*: Name of the executed subcommand (`doctor`, `list`, `status`, `plan`, `sync`, `summary`, `gui`).
- `status` *(string)*: One of `"success"`, `"warning"`, or `"error"`.
- `exit_code` *(integer)*: Corresponding numerical exit code (0, 1, 2, or 3).
- `summary` *(string)*: Human-readable single-line summary suitable for logging or notifications.
- `data` *(object | array)*: Command-specific payload.
- `errors` *(array of strings)*: List of error details or diagnostic messages if an error occurred.

---

## 3. Command Reference

### `doctor`
Performs environment diagnostics, checking Python runtime, Git installation, GitHub CLI (`gh`), authentication state, SSH connectivity, Git LFS extension, workspace permissions, and concurrency file locking.

```bash
github-org-sync doctor [--workspace PATH] [--json]
```

**JSON Payload (`data`):**
```json
{
  "status": "success",
  "passed_checks": 7,
  "total_checks": 7,
  "checks": [
    {
      "key": "python",
      "label": "Python Runtime",
      "status": "ok",
      "message": "Python 3.11.8 (C:\\...\\python.exe)",
      "required": true
    },
    {
      "key": "git",
      "label": "Git Tooling",
      "status": "ok",
      "message": "git version 2.40.1.windows.1",
      "required": true
    }
  ]
}
```

---

### `list`
Discovers and lists all repositories belonging to the specified GitHub organization.

```bash
github-org-sync list --org <NAME> [--include-archived] [--include-forks] [--json]
```

**JSON Payload (`data`):**
```json
[
  {
    "name": "backend-api",
    "url": "https://github.com/myorg/backend-api",
    "ssh_url": "git@github.com:myorg/backend-api.git",
    "default_branch": "main",
    "is_archived": false,
    "is_fork": false
  }
]
```

---

### `status`
Inspects local workspace repositories against GitHub organization identity and reports branch, tracking, uncommitted files, and ahead/behind counts.

```bash
github-org-sync status --org <NAME> --workspace <DIR> [--json]
```

**Exit codes:**
- `0`: All inspected repositories exist and are `UP_TO_DATE`.
- `1`: One or more repositories are `DIRTY`, `AHEAD`, `BEHIND`, `DIVERGED`, or `CONFLICT`.

---

### `plan`
Generates a pure, deterministic execution plan (`SyncPlan`) detailing the exact Git steps that would be performed, without making any modifications.

```bash
github-org-sync plan --org <NAME> --workspace <DIR> [--no-stash] [--fetch-only] [--checkout-default] [--use-ssh] [--json]
```

**Planned Action Types (`action`):**
- `NONE`: Repository is already up-to-date.
- `CLONE`: Repository directory is missing locally; atomic clone required.
- `FAST_FORWARD`: Clean working directory; pull fast-forward.
- `STASH_FF_RESTORE`: Uncommitted changes present; autostash, fast-forward, and restore uncommitted changes.
- `FETCH`: Remote fetch only (`--fetch-only`).
- `BLOCKED`: Operation unsafe (e.g. uncommitted changes with `--no-stash`, or branch diverged).
- `SKIPPED`: Branch is ahead of remote; skipping to avoid overwriting unpushed work.

---

### `sync`
Executes repository synchronization (cloning missing repositories, fetching remote commits, and pulling fast-forward changes).

```bash
github-org-sync sync --org <NAME> --workspace <DIR> [OPTIONS]
```

**Options:**
- `--dry-run`: Simulates the execution without modifying any files or branches.
- `--no-stash`: Disables automatic stashing of uncommitted changes (dirty repositories are safely blocked).
- `--fetch-only`: Fetches remote tracking branches without merging or checking out.
- `--checkout-default`: Safely switches clean repositories to their remote default branch before updating.
- `--use-ssh`: Clones using SSH URLs (`git@github.com:...`) rather than HTTPS.
- `--jobs N`: Number of concurrent workers for parallel cloning/fetching (default: 4).
- `--timeout SEC`: Command timeout in seconds for Git operations (default: 45s, 180s for network).
- `--json`: Formats output as structured JSON envelope.

---

### `summary`
Queries GitHub GraphQL API to generate monthly activity and contribution reports (commits, PRs, technologies).

```bash
github-org-sync summary --month YYYY-MM [--org <NAME>] [--md report.md] [--json report.json]
```

---

### `gui`
Launches the optional desktop GUI application (requires `github-org-sync[gui]` extra with PySide6).

```bash
github-org-sync gui
# Or directly:
github-org-sync-gui
```
