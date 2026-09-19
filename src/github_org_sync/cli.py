from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from github_org_sync import __version__
from github_org_sync.models.repository import Repository
from github_org_sync.models.sync_result import SyncResult
from github_org_sync.services.diagnostics_service import DiagnosticsService
from github_org_sync.services.git_service import GitService
from github_org_sync.services.github_service import GitHubService
from github_org_sync.services.planner import SyncPlanner
from github_org_sync.services.report_service import ReportService
from github_org_sync.services.sync_service import SyncService
from github_org_sync.services.validation_service import ValidationService
from github_org_sync.utils.process import set_default_timeout
from github_org_sync.utils.security import scrub_secrets

# Standard CLI Exit Codes
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_ATTENTION = 2
EXIT_USAGE = 3

# Aliases for backwards compatibility
EXIT_OK = EXIT_SUCCESS
EXIT_REPO_STATE = EXIT_ATTENTION


def format_json_envelope(
    command: str,
    status: str,
    exit_code: int,
    data: Any,
    summary: str,
    errors: list[str] | None = None,
) -> str:
    """Renders structured, versioned JSON CLI output envelope."""
    clean_errors = [scrub_secrets(str(err)) for err in (errors or [])]
    envelope = {
        "schema_version": "1.0",
        "tool_version": __version__,
        "command": command,
        "status": status,
        "exit_code": exit_code,
        "summary": scrub_secrets(summary),
        "data": data,
        "errors": clean_errors,
    }
    return json.dumps(envelope, indent=2, ensure_ascii=False)


def print_summary(results: list[SyncResult]) -> int:
    """Prints a terminal summary table of sync results and determines the exit code."""
    print("=" * 60)
    print("Synchronization Summary")
    print("=" * 60)

    counts: dict[str, int] = {}
    for res in results:
        counts[res.after_status] = counts.get(res.after_status, 0) + 1

    for status, count in sorted(counts.items()):
        print(f"{status + ':':<20} {count:>5}")
    print("=" * 60)

    if any(r.after_status == "FAILED" for r in results):
        return EXIT_ERROR
    if any(r.after_status in ("CONFLICT", "DIVERGED", "BLOCKED", "WRONG_REMOTE") for r in results):
        return EXIT_ATTENTION
    return EXIT_SUCCESS


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    # Intercept headless GUI smoke test if passed directly
    if "--smoke-test" in argv:
        try:
            from github_org_sync.app import main as gui_main

            gui_main()
            return EXIT_SUCCESS
        except ImportError:
            print(
                "ERROR: PySide6 is required for GUI smoke test. Install it using: pip install 'github-org-sync[gui]'",
                file=sys.stderr,
            )
            return EXIT_ERROR

    parser = argparse.ArgumentParser(
        prog="github-org-sync",
        description="Safe, CLI-first synchronization tool for GitHub organization repositories",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"github-org-sync {__version__}",
        help="Show version and exit",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="global_json",
        help="Emit output in structured JSON format",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Common argument groups
    org_parser = argparse.ArgumentParser(add_help=False)
    org_parser.add_argument("--org", required=True, help="GitHub organization name or URL")

    workspace_parser = argparse.ArgumentParser(add_help=False)
    workspace_parser.add_argument("--workspace", required=True, help="Local workspace directory path")

    filter_parser = argparse.ArgumentParser(add_help=False)
    filter_parser.add_argument("--include-archived", action="store_true", help="Include archived repositories")
    filter_parser.add_argument(
        "--include-forks", action="store_true", default=True, help="Include forks (default: True)"
    )
    filter_parser.add_argument("--exclude-forks", dest="include_forks", action="store_false", help="Exclude forks")

    json_parser = argparse.ArgumentParser(add_help=False)
    json_parser.add_argument("--json", action="store_true", help="Emit output in structured JSON format")

    # 1. 'doctor'
    doctor_parser = subparsers.add_parser(
        "doctor", parents=[json_parser], help="Inspect environment health, tools, and workspace permissions"
    )
    doctor_parser.add_argument("--workspace", default=None, help="Optional workspace path to verify write/lock access")

    # 2. 'list'
    subparsers.add_parser(
        "list",
        parents=[org_parser, filter_parser, json_parser],
        help="List remote organization repositories on GitHub",
    )

    # 3. 'status'
    subparsers.add_parser(
        "status",
        parents=[org_parser, workspace_parser, filter_parser, json_parser],
        help="Inspect local workspace repositories without mutating files",
    )

    # 4. 'plan'
    plan_parser = subparsers.add_parser(
        "plan",
        parents=[org_parser, workspace_parser, filter_parser, json_parser],
        help="Compute and display deterministic synchronization plan",
    )
    plan_parser.add_argument(
        "--checkout-default",
        action="store_true",
        default=False,
        help="Opt-in: automatically switch to default branch if clean (default: False)",
    )
    plan_parser.add_argument("--no-stash", action="store_true", help="Disable preserving local changes via stash")
    plan_parser.add_argument("--fetch-only", action="store_true", help="Only fetch changes without merging/pulling")
    plan_parser.add_argument("--use-ssh", action="store_true", help="Use SSH protocol for clones")

    # 5. 'sync'
    sync_parser = subparsers.add_parser(
        "sync",
        parents=[org_parser, workspace_parser, filter_parser, json_parser],
        help="Synchronize organization repositories (clone missing, pull clean changes)",
    )
    sync_parser.add_argument(
        "--checkout-default",
        action="store_true",
        default=False,
        help="Opt-in: switch to default branch before pull if clean (default: False)",
    )
    sync_parser.add_argument("--no-stash", action="store_true", help="Disable preserving local changes via stash")
    sync_parser.add_argument("--fetch-only", action="store_true", help="Only fetch changes without merging/pulling")
    sync_parser.add_argument(
        "--dry-run", action="store_true", help="Simulate synchronization using deterministic plan without mutations"
    )
    sync_parser.add_argument("--use-ssh", action="store_true", help="Use SSH protocol for clones")
    sync_parser.add_argument("--timeout", type=float, default=None, help="Command timeout override in seconds")
    sync_parser.add_argument("--jobs", type=int, default=4, help="Parallel worker concurrency (default: 4)")

    # 6. 'gui'
    subparsers.add_parser("gui", help="Launch the graphical user interface (requires PySide6)")

    # 7. 'summary'
    summary_parser = subparsers.add_parser(
        "summary", help="Generate monthly GitHub work summary (commits, PRs, technologies)"
    )
    summary_parser.add_argument("--month", required=True, help="Month as YYYY-MM (e.g. 2026-08)")
    summary_parser.add_argument("--org", default=None, help="Filter to specific GitHub organization")
    summary_parser.add_argument("--user", default=None, help="Override GitHub login (defaults to current user)")
    summary_parser.add_argument("--exclude", default=None, help="Owner login to ignore (e.g. personal account)")
    summary_parser.add_argument("--md", default=None, help="Markdown output file path")
    summary_parser.add_argument("--json", default=None, help="Raw JSON output file path")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return EXIT_SUCCESS

    emit_json = getattr(args, "global_json", False) or getattr(args, "json", False)

    # Apply timeout override if provided
    if hasattr(args, "timeout") and args.timeout:
        set_default_timeout(args.timeout)

    # -------------------------------------------------------------
    # Command: gui
    # -------------------------------------------------------------
    if args.command == "gui":
        try:
            from github_org_sync.app import main as gui_main

            gui_main()
            return EXIT_SUCCESS
        except ImportError as exc:
            msg = (
                "ERROR: PySide6 is required to run the graphical interface.\n"
                "Install GUI dependencies using: pip install 'github-org-sync[gui]'"
            )
            if emit_json:
                print(format_json_envelope("gui", "error", EXIT_ERROR, {}, "Missing GUI dependency", [str(exc), msg]))
            else:
                print(msg, file=sys.stderr)
            return EXIT_ERROR

    # -------------------------------------------------------------
    # Command: doctor
    # -------------------------------------------------------------
    if args.command == "doctor":
        ws = Path(args.workspace) if args.workspace else None
        report = DiagnosticsService.run_doctor(ws)
        status = report["status"]
        exit_code = EXIT_SUCCESS if status == "success" else (EXIT_ATTENTION if status == "warning" else EXIT_ERROR)
        summary = f"Diagnostics {status}: {report['passed_checks']}/{report['total_checks']} checks passed"

        if emit_json:
            print(format_json_envelope("doctor", status, exit_code, report, summary))
            return exit_code

        print("=" * 60)
        print("GitHub Organization Sync - Environment Doctor")
        print("=" * 60)
        for check in report["checks"]:
            mark = "OK" if check["status"] == "ok" else ("WARN" if check["status"] == "warning" else "FAIL")
            req = " (optional)" if not check["required"] else ""
            print(f"[{mark:<4}] {check['label']}{req}: {check['message']}")
        print("=" * 60)
        print(f"Summary: {summary}")
        return exit_code

    # -------------------------------------------------------------
    # Command: summary
    # -------------------------------------------------------------
    if args.command == "summary":
        from github_org_sync.services.work_summary_service import WorkSummaryService

        summary_service = WorkSummaryService()
        if not summary_service.check_gh():
            print("ERROR: GitHub CLI (gh) not found or not installed.", file=sys.stderr)
            return EXIT_ERROR

        try:
            year, month = summary_service.parse_month(args.month)
            user = args.user or summary_service.get_current_user()
            print(f"Generating monthly work summary for {user} ({year}-{month:02d})...")
            summary_result = summary_service.generate_summary(
                login=user,
                year=year,
                month=month,
                excluded_owner=args.exclude,
                target_org=args.org,
            )
            saved_md, saved_json = summary_service.save_reports(
                summary_result,
                md_path=args.md,
                json_path=args.json,
            )
            print(f"Summary saved: MD='{saved_md}', JSON='{saved_json}'")
            return EXIT_SUCCESS
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return EXIT_ERROR

    # -------------------------------------------------------------
    # Common validation for org and workspace commands
    # -------------------------------------------------------------
    gh_service = GitHubService()
    if not gh_service.check_cli_installed():
        msg = "GitHub CLI (gh) is not installed or not in PATH."
        if emit_json:
            print(format_json_envelope(args.command, "error", EXIT_ERROR, {}, msg, [msg]))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return EXIT_ERROR

    auth_status = gh_service.check_auth_status()
    if not auth_status:
        msg = "GitHub CLI is not authenticated. Run 'gh auth login' first."
        if emit_json:
            print(format_json_envelope(args.command, "error", EXIT_ERROR, {}, msg, [msg]))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return EXIT_ERROR

    try:
        org_name = ValidationService.validate_org_name(args.org)
    except ValueError as e:
        msg = f"Invalid organization name: {e}"
        if emit_json:
            print(format_json_envelope(args.command, "error", EXIT_USAGE, {}, msg, [msg]))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return EXIT_USAGE

    if not emit_json:
        print(f"Authenticating as: {auth_status}")
        print(f"Fetching repositories for organization '{org_name}'...")

    try:
        remote_repos = gh_service.list_repositories(org_name)
    except Exception as e:
        msg = f"Failed to list repositories for '{org_name}': {e}"
        if emit_json:
            print(format_json_envelope(args.command, "error", EXIT_ERROR, {}, msg, [msg]))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return EXIT_ERROR

    sync_service = SyncService()
    filtered_repos = sync_service.filter_repositories(
        remote_repos,
        include_archived=args.include_archived,
        include_forks=args.include_forks,
    )

    # -------------------------------------------------------------
    # Command: list
    # -------------------------------------------------------------
    if args.command == "list":
        if emit_json:
            data = [
                {
                    "name": r.name,
                    "url": r.url,
                    "ssh_url": r.ssh_url,
                    "default_branch": r.default_branch,
                    "is_archived": r.is_archived,
                    "is_fork": r.is_fork,
                }
                for r in filtered_repos
            ]
            summary = f"Found {len(filtered_repos)} repositories in organization '{org_name}'"
            print(format_json_envelope("list", "success", EXIT_SUCCESS, data, summary))
            return EXIT_SUCCESS

        print(f"\nFound {len(filtered_repos)} repositories in '{org_name}':")
        print(f"{'Repository':<35} {'Default Branch':<16} {'Archived':<10} {'Fork':<8}")
        print("-" * 75)
        for r in filtered_repos:
            print(f"{r.name:<35} {r.default_branch:<16} {str(r.is_archived):<10} {str(r.is_fork):<8}")
        return EXIT_SUCCESS

    # -------------------------------------------------------------
    # Validate workspace for status, plan, sync
    # -------------------------------------------------------------
    try:
        ws_path = ValidationService.validate_workspace(args.workspace)
    except ValueError as e:
        msg = f"Invalid workspace directory: {e}"
        if emit_json:
            print(format_json_envelope(args.command, "error", EXIT_USAGE, {}, msg, [msg]))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return EXIT_USAGE

    git_service = GitService()

    # -------------------------------------------------------------
    # Command: status
    # -------------------------------------------------------------
    if args.command == "status":
        sync_service.check_local_statuses(filtered_repos, ws_path, org_name)
        states: dict[str, Any] = {}
        has_attention = False

        for r in filtered_repos:
            if r.state:
                states[r.name] = r.state.to_dict()
                if not r.state.is_clean and r.state.exists:
                    has_attention = True
            else:
                states[r.name] = {"primary_status": r.status}
                if r.status not in ("UP_TO_DATE", "MISSING"):
                    has_attention = True

        exit_code = EXIT_ATTENTION if has_attention else EXIT_SUCCESS
        status_label = "warning" if has_attention else "success"
        summary = f"Inspected {len(filtered_repos)} repositories in workspace '{ws_path}'"

        if emit_json:
            print(format_json_envelope("status", status_label, exit_code, states, summary))
            return exit_code

        print(f"{'Repository':<30} {'Status':<18} {'Branch':<15} {'Ahead':<6} {'Behind':<6} {'Details':<20}")
        print("-" * 100)
        for r in filtered_repos:
            branch = r.branch or ""
            ahead = str(r.ahead) if r.ahead is not None else ""
            behind = str(r.behind) if r.behind is not None else ""
            res = r.result or ""
            print(f"{r.name:<30} {r.status:<18} {branch:<15} {ahead:<6} {behind:<6} {res:<20}")
        return exit_code

    # -------------------------------------------------------------
    # Command: plan
    # -------------------------------------------------------------
    if args.command == "plan":
        states = {}
        branches = {}
        for r in filtered_repos:
            r_path = ws_path / r.name
            r.local_path = r_path
            state = git_service.inspect_repo_state(r_path, expected_org=org_name, expected_repo=r.name)
            states[r.name] = state
            branches[r.name] = r.default_branch

        plan_options = {
            "preserve_local_changes": not args.no_stash,
            "fetch_only": args.fetch_only,
            "checkout_default": args.checkout_default,
            "use_ssh": args.use_ssh,
        }
        sync_plan = SyncPlanner.create_plan(
            organization=org_name,
            workspace=str(ws_path),
            states=states,
            options=plan_options,
            default_branches=branches,
        )

        exit_code = EXIT_ATTENTION if sync_plan.requires_attention_count > 0 else EXIT_SUCCESS
        status_label = "warning" if sync_plan.requires_attention_count > 0 else "success"
        summary = (
            f"Sync plan computed for {sync_plan.total_count} repositories "
            f"({sync_plan.requires_attention_count} require attention)"
        )

        if emit_json:
            print(format_json_envelope("plan", status_label, exit_code, sync_plan.to_dict(), summary))
            return exit_code

        print(f"\nPlanned actions for '{org_name}' in '{ws_path}':")
        print(f"{'Repository':<28} {'Current State':<18} {'Planned Action':<26} {'Reason':<30}")
        print("-" * 105)
        for p in sync_plan.plans:
            print(f"{p.repo_name:<28} {p.state.primary_status:<18} {p.action_summary:<26} {p.reason:<30}")
        print("-" * 105)
        print(summary)
        return exit_code

    # -------------------------------------------------------------
    # Command: sync
    # -------------------------------------------------------------
    if args.command == "sync":
        sync_options = {
            "use_ssh": args.use_ssh,
            "preserve_local_changes": not args.no_stash,
            "fetch_only": args.fetch_only,
            "dry_run": args.dry_run,
            "checkout_default": args.checkout_default,
        }

        if not emit_json:
            mode_desc = " (Simulation)" if args.dry_run else ""
            print(f"\nSynchronizing {len(filtered_repos)} repositories to '{ws_path}'{mode_desc}...")

        # Pre-check local status
        def progress_chk(curr: int, tot: int, name: str) -> None:
            if not emit_json:
                print(f"[{curr}/{tot}] Inspecting {name}...", end="\r", flush=True)

        sync_service.check_local_statuses(filtered_repos, ws_path, org_name, progress_callback=progress_chk)
        if not emit_json:
            print("\n")

        # Sync with progress
        def progress_sync(curr: int, tot: int, repo: Repository, res: SyncResult) -> None:
            if not emit_json:
                msg_text = res.result or res.error or ""
                details = f": {msg_text}" if msg_text else ""
                print(f"[{curr}/{tot}] {repo.name} -> {res.after_status}{details}")

        results = sync_service.sync_repositories(
            repositories=filtered_repos,
            workspace=ws_path,
            org_name=org_name,
            options=sync_options,
            progress_callback=progress_sync,
            max_workers=args.jobs,
        )

        # Generate Reports
        auth_user = auth_status.split("account ")[-1].split()[0] if "account " in auth_status else "User"
        protocol = "SSH" if args.use_ssh else "HTTPS"
        json_path, md_path = ReportService.generate_reports(
            organization=org_name,
            workspace=ws_path,
            auth_user=auth_user,
            protocol=protocol,
            options=sync_options,
            results=results,
        )

        # Evaluate exit code
        has_failed = any(r.after_status == "FAILED" for r in results)
        has_attention = any(r.after_status in ("CONFLICT", "DIVERGED", "BLOCKED", "WRONG_REMOTE") for r in results)
        if has_failed:
            exit_code = EXIT_ERROR
            status_label = "error"
        elif has_attention:
            exit_code = EXIT_ATTENTION
            status_label = "warning"
        else:
            exit_code = EXIT_SUCCESS
            status_label = "success"

        prefix = "[DRY-RUN] " if args.dry_run else ""
        summary = f"{prefix}Synchronized {len(results)} repositories. Report: JSON='{json_path}', MD='{md_path}'"

        if emit_json:
            sync_data = {
                "dry_run": args.dry_run,
                "results": [r.to_dict() for r in results],
                "reports": {"json": str(json_path), "markdown": str(md_path)},
            }
            print(format_json_envelope("sync", status_label, exit_code, sync_data, summary))
            return exit_code

        print("\n" + "=" * 60)
        print(f"Reports generated successfully:\nJSON: {json_path}\nMarkdown: {md_path}")
        return print_summary(results)

    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
