# GitHub Organization Repository Synchronizer

[![CI](https://github.com/MatthiasLew/github-org-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/MatthiasLew/github-org-sync/actions/workflows/ci.yml)
[![Release](https://github.com/MatthiasLew/github-org-sync/actions/workflows/release.yml/badge.svg)](https://github.com/MatthiasLew/github-org-sync/actions/workflows/release.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A hardened, **CLI-first** tool and optional desktop application for automated discovery, atomic cloning, deterministic planning, and safe synchronization of all repositories belonging to a GitHub organization.

Designed to protect local work and fail closed when an operation cannot be proven safe. Your local uncommitted work and diverged branches are never overwritten or silently discarded.

---

## Key Highlights

- **CLI-First Architecture**: Lightweight base package without mandatory GUI dependencies (`pip install github-org-sync`). PySide6 is completely isolated in the optional `[gui]` extra.
- **Deterministic Planning (`plan`)**: Computes a pure, deterministic `SyncPlan` showing every Git command before touching the disk.
- **Structured JSON Envelopes (`--json`)**: Uniform, machine-readable JSON payloads and standardized exit codes (`0`, `1`, `2`, `3`) for CI/CD pipelines and AI agent workflows ([docs/CLI_CONTRACT.md](docs/CLI_CONTRACT.md)).
- **Fail-Closed Safety Policy**: Designed to protect local work and fail closed when an operation cannot be proven safe. Force pushes (`push --force`), hard resets (`reset --hard`), and working tree wipes (`clean`) are strictly blocked at the process wrapper level ([docs/SECURITY.md](docs/SECURITY.md)).
- **Safe Stash Recovery**: Automatic stashes (`preserve_local_changes`) are **never** dropped if restoring produces a merge conflict ([docs/RECOVERY.md](docs/RECOVERY.md)).
- **Atomic Cloning**: Clones to an isolated temporary folder within the filesystem and performs an atomic rename upon integrity validation, preventing corrupt half-cloned directories.
- **Workspace Concurrency Locking**: Prevents concurrent CLI/GUI processes from writing to the same workspace simultaneously, with automatic dead-PID stale lock recovery.
- **Environment Doctor (`doctor`)**: Verifies Python runtime, Git, GitHub CLI authentication, SSH connectivity, Git LFS, workspace permissions, and locking capabilities.
- **Monthly Contribution Analytics (`summary`)**: Aggregates commits, PRs, technologies, and project statistics via GitHub GraphQL API into Markdown and JSON reports.
- **Optional Desktop GUI**: Modern PySide6 graphical interface with repository status monitor, Git LFS inspector, commit drawer, and visual commit graphs.

---

## Installation

### 1. Base CLI (Recommended for CI/CD, Scripts & Servers)
```bash
pip install github-org-sync
```

### 2. Full Installation with GUI
```bash
pip install "github-org-sync[gui]"
```

### Prerequisites
- Python 3.11+
- [Git](https://git-scm.com/) installed and on PATH.
- [GitHub CLI (gh)](https://cli.github.com/) installed and authenticated (`gh auth login`).

---

## CLI Quickstart

### Verify Environment
```bash
github-org-sync doctor --workspace /path/to/workspace
```

### Discover Repositories
```bash
github-org-sync list --org my-org
```

### Inspect Workspace Status
```bash
github-org-sync status --org my-org --workspace /path/to/workspace
```

### Generate Dry-Run Plan
```bash
github-org-sync plan --org my-org --workspace /path/to/workspace
```

### Synchronize Repositories
```bash
# Simulation without disk modifications
github-org-sync sync --org my-org --workspace /path/to/workspace --dry-run

# Full synchronization with parallel workers
github-org-sync sync --org my-org --workspace /path/to/workspace --jobs 4
```

### Structured JSON Output
Append `--json` to any command for machine-readable JSON envelopes:
```bash
github-org-sync plan --org my-org --workspace /path/to/workspace --json
```

### Monthly Work Summary
```bash
github-org-sync summary --month 2026-08 --org my-org --md summary.md --json summary.json
```

### Launch GUI
```bash
github-org-sync gui
# Or:
github-org-sync-gui
```

---

## Standard Exit Codes

| Code | Status | Description |
| :---: | :--- | :--- |
| **0** | `SUCCESS` | Clean success; all operations completed cleanly. |
| **1** | `ATTENTION` | Human attention required (uncommitted files, diverged branches, conflicts). |
| **2** | `USAGE` | Invalid CLI arguments, organization name, or workspace path. |
| **3** | `ERROR` | Git error, network timeout, or execution failure. |

---

## Documentation

- [CLI Contract & JSON Schema](docs/CLI_CONTRACT.md)
- [Security Policy & Safety Architecture](docs/SECURITY.md)
- [Safe Recovery & Conflict Resolution Guide](docs/RECOVERY.md)
- [Architecture & State Machine](docs/ARCHITECTURE.md)
- [Testing & Quality Assurance](docs/TESTING.md)
- [Release Process](docs/RELEASING.md)

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
