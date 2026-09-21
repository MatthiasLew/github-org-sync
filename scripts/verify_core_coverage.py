"""Verify that core modules meet minimum line and branch coverage thresholds."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CORE_FILES: list[str] = [
    "models/repo_state.py",
    "models/sync_plan.py",
    "services/planner.py",
    "services/sync_service.py",
    "services/git_service.py",
    "services/validation_service.py",
    "services/update_service.py",
    "utils/git_url_parser.py",
    "utils/process.py",
    "utils/security.py",
    "utils/lock.py",
    "cli.py",
]


def verify_coverage(
    coverage_path: Path,
    min_branch_cov: float = 90.0,
    min_line_cov: float = 90.0,
) -> int:
    if not coverage_path.exists():
        print(f"ERROR: Coverage file not found at {coverage_path}", file=sys.stderr)
        return 1

    with coverage_path.open(encoding="utf-8") as f:
        data = json.load(f)

    files_data = data.get("files", {})
    totals = data.get("totals", {})

    print("=" * 85)
    print("CORE COVERAGE VERIFICATION GATE")
    print("=" * 85)
    header = f"{'Core Module':<32} | {'Statements':<12} | {'Line %':<9} | {'Branches':<10} | {'Branch %':<9}"
    print(header)
    print("-" * 85)

    core_stmts = 0
    core_cov_lines = 0
    core_branches = 0
    core_cov_branches = 0
    missing_files: list[str] = []

    for cf in CORE_FILES:
        matched_info = None
        for path, info in files_data.items():
            norm = path.replace("\\", "/")
            if norm.endswith("src/github_org_sync/" + cf) or norm.endswith("/" + cf):
                matched_info = info
                break

        if not matched_info:
            missing_files.append(cf)
            print(f"{cf:<32} | {'NOT FOUND':<12} | {'N/A':<9} | {'NOT FOUND':<10} | {'N/A':<9}")
            continue

        summary = matched_info.get("summary", {})
        stmts = summary.get("num_statements", 0)
        cov_lines = summary.get("covered_lines", 0)
        branches = summary.get("num_branches", 0)
        cov_branches = summary.get("covered_branches", 0)

        core_stmts += stmts
        core_cov_lines += cov_lines
        core_branches += branches
        core_cov_branches += cov_branches

        line_pct = (cov_lines / stmts * 100) if stmts else 100.0
        branch_pct = (cov_branches / branches * 100) if branches else 100.0

        stmt_str = f"{cov_lines}/{stmts}"
        branch_str = f"{cov_branches}/{branches}"
        print(f"{cf:<32} | {stmt_str:<12} | {line_pct:>8.2f}% | {branch_str:<10} | {branch_pct:>8.2f}%")

    print("-" * 85)

    core_line_pct = (core_cov_lines / core_stmts * 100) if core_stmts else 0.0
    core_branch_pct = (core_cov_branches / core_branches * 100) if core_branches else 0.0

    print(
        f"{'CORE TOTAL':<32} | {f'{core_cov_lines}/{core_stmts}':<12} | {core_line_pct:>8.2f}% | {f'{core_cov_branches}/{core_branches}':<10} | {core_branch_pct:>8.2f}%"
    )

    global_stmts = totals.get("num_statements", 0)
    global_cov_lines = totals.get("covered_lines", 0)
    global_branches = totals.get("num_branches", 0)
    global_cov_branches = totals.get("covered_branches", 0)
    global_line_pct = (global_cov_lines / global_stmts * 100) if global_stmts else 0.0
    global_branch_pct = (global_cov_branches / global_branches * 100) if global_branches else 0.0

    print(
        f"{'GLOBAL TOTAL (inc. GUI)':<32} | {f'{global_cov_lines}/{global_stmts}':<12} | {global_line_pct:>8.2f}% | {f'{global_cov_branches}/{global_branches}':<10} | {global_branch_pct:>8.2f}%"
    )
    print("=" * 85)
    sys.stdout.flush()

    failed = False
    if missing_files:
        print(f"FAILED: Missing coverage data for: {', '.join(missing_files)}", file=sys.stderr)
        failed = True

    if core_line_pct < min_line_cov:
        print(
            f"FAILED: Core line coverage {core_line_pct:.2f}% is below required threshold {min_line_cov:.2f}%",
            file=sys.stderr,
        )
        failed = True

    if core_branch_pct < min_branch_cov:
        print(
            f"FAILED: Core branch coverage {core_branch_pct:.2f}% is below required threshold {min_branch_cov:.2f}%",
            file=sys.stderr,
        )
        failed = True

    if failed:
        return 1

    print(
        f"SUCCESS: Core coverage exceeds all thresholds (Line: {core_line_pct:.2f}% >= {min_line_cov:.2f}%, Branch: {core_branch_pct:.2f}% >= {min_branch_cov:.2f}%)."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify core module coverage thresholds.")
    parser.add_argument(
        "--coverage-file",
        type=Path,
        default=Path("coverage.json"),
        help="Path to coverage.json file (default: coverage.json)",
    )
    parser.add_argument(
        "--min-branch-coverage",
        type=float,
        default=90.0,
        help="Minimum required branch coverage percentage for core (default: 90.0)",
    )
    parser.add_argument(
        "--min-line-coverage",
        type=float,
        default=90.0,
        help="Minimum required line coverage percentage for core (default: 90.0)",
    )
    args = parser.parse_args()
    return verify_coverage(
        coverage_path=args.coverage_file,
        min_branch_cov=args.min_branch_coverage,
        min_line_cov=args.min_line_coverage,
    )


if __name__ == "__main__":
    sys.exit(main())
