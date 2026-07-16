import argparse
import sys

from github_org_sync.models.repository import Repository
from github_org_sync.models.sync_result import SyncResult
from github_org_sync.services.git_service import GitService
from github_org_sync.services.github_service import GitHubService
from github_org_sync.services.report_service import ReportService
from github_org_sync.services.sync_service import SyncService
from github_org_sync.services.validation_service import ValidationService

# Exit Codes
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REPO_STATE = 2


def print_summary(results: list[SyncResult]) -> int:
    print("=" * 60)
    print("Synchronization Summary")
    print("=" * 60)

    counts: dict[str, int] = {}
    for res in results:
        counts[res.status] = counts.get(res.status, 0) + 1

    for status, count in sorted(counts.items()):
        print(f"{status + ':':<20} {count:>5}")
    print("=" * 60)

    # Check for failures or conflicts
    if any(r.status in ("FAILED") for r in results):
        return EXIT_ERROR
    if any(r.status in ("CONFLICT", "DIVERGED", "BLOCKED", "WRONG_REMOTE") for r in results):
        return EXIT_REPO_STATE
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(description="github-org-sync Command Line Interface")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Common arguments
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

    # 1. 'list' command
    subparsers.add_parser("list", parents=[org_parser, filter_parser], help="List organization repositories on GitHub")

    # 2. 'status' command
    subparsers.add_parser(
        "status", parents=[org_parser, workspace_parser, filter_parser], help="Check status of local repositories"
    )

    # 3. 'sync' command
    sync_parser = subparsers.add_parser(
        "sync",
        parents=[org_parser, workspace_parser, filter_parser],
        help="Synchronize (clone & update) organization repositories",
    )
    sync_parser.add_argument("--use-ssh", action="store_true", help="Use SSH protocol for clones")
    sync_parser.add_argument("--no-stash", action="store_true", help="Disable preserving local changes via stash")
    sync_parser.add_argument("--fetch-only", action="store_true", help="Only fetch changes without merging/pulling")
    sync_parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without changing local files")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return EXIT_OK

    gh_service = GitHubService()
    git_service = GitService()
    sync_service = SyncService(git_service=git_service)

    try:
        # Validate and normalize organization
        org_name = ValidationService.normalize_org_name(args.org)

        # Check CLI requirements
        gh_service.check_cli_installed()
        auth_info = gh_service.check_auth_status()
        auth_user = "unknown"
        for line in auth_info.splitlines():
            if "logged in" in line.lower():
                parts = line.split()
                if parts:
                    auth_user = parts[-1]

        # List remote repositories
        print(f"Fetching repositories for '{org_name}' from GitHub...")
        repos = gh_service.list_repositories(org_name)

        # Filter
        repos = sync_service.filter_repositories(
            repos, include_archived=args.include_archived, include_forks=args.include_forks
        )

        if args.command == "list":
            print(f"\nDiscovered {len(repos)} repositories:")
            for r in repos:
                arch_tag = " [ARCHIVED]" if r.is_archived else ""
                fork_tag = " [FORK]" if r.is_fork else ""
                print(f"- {r.name}{arch_tag}{fork_tag} ({r.visibility})")
            return EXIT_OK

        # Commands requiring workspace validation
        ws_path = ValidationService.validate_workspace(args.workspace)

        if args.command == "status":
            print(f"\nChecking local statuses in '{ws_path}'...")

            def progress(curr: int, tot: int, name: str) -> None:
                print(f"[{curr}/{tot}] Inspecting {name}...", end="\r", flush=True)

            sync_service.check_local_statuses(repos, ws_path, org_name, progress_callback=progress)
            print("\n")

            print(f"{'Repository':<30} {'Status':<18} {'Branch':<15} {'Ahead':<6} {'Behind':<6} {'Details':<20}")
            print("-" * 100)
            for r in repos:
                branch = r.branch or ""
                ahead = str(r.ahead) if r.ahead is not None else ""
                behind = str(r.behind) if r.behind is not None else ""
                result = r.result or ""
                print(f"{r.name:<30} {r.status:<18} {branch:<15} {ahead:<6} {behind:<6} {result:<20}")
            return EXIT_OK

        if args.command == "sync":
            print(f"\nSynchronizing {len(repos)} repositories to '{ws_path}'...")

            # Setup options
            options = {
                "use_ssh": args.use_ssh,
                "preserve_local_changes": not args.no_stash,
                "fetch_only": args.fetch_only,
                "dry_run": args.dry_run,
                "checkout_default": True,
            }

            # Pre-check local status
            def progress_chk(curr: int, tot: int, name: str) -> None:
                print(f"[{curr}/{tot}] Checking {name}...", end="\r", flush=True)

            sync_service.check_local_statuses(repos, ws_path, org_name, progress_callback=progress_chk)
            print("\n")

            # Sync
            def progress_sync(curr: int, tot: int, repo: Repository, res: SyncResult) -> None:
                status_text = res.status
                msg_text = res.message or res.error or ""
                details = f": {msg_text}" if msg_text else ""
                print(f"[{curr}/{tot}] {repo.name} -> {status_text}{details}")

            results = sync_service.sync_repositories(
                repositories=repos,
                workspace=ws_path,
                org_name=org_name,
                options=options,
                progress_callback=progress_sync,
            )

            # Generate Reports
            try:
                json_path, md_path = ReportService.generate_reports(
                    organization=org_name,
                    workspace=ws_path,
                    auth_user=auth_user,
                    protocol="ssh" if args.use_ssh else "https",
                    options=options,
                    results=results,
                )
                print("\nGenerated report files:")
                print(f"- JSON: {json_path}")
                print(f"- MD:   {md_path}")
            except Exception as e:
                print(f"Failed to generate reports: {e}", file=sys.stderr)

            return print_summary(results)

        return EXIT_OK

    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
