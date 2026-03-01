#!/usr/bin/env python3
"""
Version bump script for AutoTrader beta merges.

Bumps pyproject.toml version, commits on development, merges to beta (ff-only),
creates an annotated git tag, and pushes everything to origin.

Usage: python scripts/bump_version.py VERSION [--dry-run]

Examples:
  python scripts/bump_version.py 3.2        # bump to v3.2.0, merge to beta, tag
  python scripts/bump_version.py 3.2.1      # bump to v3.2.1
  python scripts/bump_version.py 3.2 --dry-run  # show what would happen
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_TOML = PROJECT_ROOT / "pyproject.toml"
VERSION_PATTERN = re.compile(r"^\d+\.\d+(\.\d+)?$")
CO_AUTHOR = "Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bump version, merge development -> beta, and tag.",
        epilog=(
            "Examples:\n"
            "  python scripts/bump_version.py 3.2        # bump to v3.2.0\n"
            "  python scripts/bump_version.py 3.2.1      # bump to v3.2.1\n"
            "  python scripts/bump_version.py 3.2 --dry-run  # show plan only\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("version", help="Target version (X.Y or X.Y.Z)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making changes",
    )
    return parser.parse_args()


def run_git(*args: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a git command from the project root."""
    cmd = ["git", *args]
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        check=check,
        capture_output=capture,
        text=True,
    )


def fail(message: str) -> None:
    """Print error and exit."""
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def normalize_version(raw: str) -> tuple[str, str]:
    """
    Validate and normalize version string.
    Returns (full_version, tag_version).
      - full_version: X.Y.Z  (for pyproject.toml)
      - tag_version:  X.Y    (for git tag vX.Y) or X.Y.Z if patch > 0
    """
    if not VERSION_PATTERN.match(raw):
        fail(f"Invalid version format: '{raw}'. Expected X.Y or X.Y.Z")

    parts = raw.split(".")
    if len(parts) == 2:
        full = f"{parts[0]}.{parts[1]}.0"
        tag = f"{parts[0]}.{parts[1]}"
    else:
        full = raw
        patch = int(parts[2])
        tag = raw if patch > 0 else f"{parts[0]}.{parts[1]}"

    return full, tag


def check_branch() -> None:
    """Ensure we are on the development branch."""
    result = run_git("branch", "--show-current")
    branch = result.stdout.strip()
    if branch != "development":
        fail(f"Must be on 'development' branch, currently on '{branch}'")


def check_clean_worktree() -> None:
    """Ensure no uncommitted changes (excluding .claude/ directory)."""
    result = run_git("status", "--porcelain")
    dirty_files = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        # Extract file path from status line (skip the 2-char status + space)
        filepath = line[3:].strip()
        # Allow .claude/ changes
        if filepath.startswith(".claude/") or filepath.startswith(".claude\\"):
            continue
        dirty_files.append(line)

    if dirty_files:
        fail(
            "Working tree is not clean. Uncommitted changes:\n"
            + "\n".join(f"  {f}" for f in dirty_files)
        )


def check_tag_not_exists(tag: str) -> None:
    """Ensure the tag does not already exist."""
    result = run_git("tag", "--list", tag)
    if result.stdout.strip():
        fail(f"Tag '{tag}' already exists. Choose a different version.")


def check_beta_branch_exists() -> None:
    """Ensure the beta branch exists locally."""
    result = run_git("branch", "--list", "beta")
    if not result.stdout.strip():
        fail(
            "Local 'beta' branch does not exist. "
            "Create it first: git checkout -b beta && git checkout development"
        )


def read_current_version() -> str:
    """Read current version from pyproject.toml."""
    content = PYPROJECT_TOML.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"(.+?)"', content, re.MULTILINE)
    if not match:
        fail("Could not find version field in pyproject.toml")
    return match.group(1)


def update_pyproject_version(new_version: str) -> None:
    """Update version in pyproject.toml."""
    content = PYPROJECT_TOML.read_text(encoding="utf-8")
    updated = re.sub(
        r'^(version\s*=\s*")(.+?)(")',
        rf"\g<1>{new_version}\g<3>",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    PYPROJECT_TOML.write_text(updated, encoding="utf-8")


def main() -> None:
    args = parse_args()
    dry_run = args.dry_run
    full_version, tag_version = normalize_version(args.version)
    tag_name = f"v{tag_version}"

    current_version = read_current_version()

    # --- Pre-flight checks ---
    print("Running pre-flight checks...")
    check_branch()
    check_clean_worktree()
    check_tag_not_exists(tag_name)
    check_beta_branch_exists()
    print("  All checks passed.\n")

    # --- Plan summary ---
    print("=== Version Bump Plan ===")
    print(f"  Current version : {current_version}")
    print(f"  New version     : {full_version}")
    print(f"  Git tag         : {tag_name}")
    print(f"  Commit message  : chore: bump version to {full_version}")
    print(f"  Merge           : development -> beta (fast-forward only)")
    print(f"  Push            : development, beta, {tag_name}")
    print()

    if dry_run:
        print("[DRY RUN] No changes were made.")
        return

    # --- Step 1: Update pyproject.toml ---
    print("Step 1/6: Updating pyproject.toml...")
    update_pyproject_version(full_version)
    print(f"  version = \"{full_version}\"")

    # --- Step 2: Stage and commit ---
    print("Step 2/6: Committing version bump on development...")
    run_git("add", "pyproject.toml")
    commit_msg = (
        f"chore: bump version to {full_version}\n"
        f"\n"
        f"{CO_AUTHOR}"
    )
    run_git("commit", "-m", commit_msg)
    print("  Committed.")

    # --- Step 3: Merge to beta (ff-only) ---
    print("Step 3/6: Merging development -> beta (fast-forward only)...")
    run_git("checkout", "beta")
    result = run_git("merge", "--ff-only", "development", check=False)
    if result.returncode != 0:
        # Abort: switch back to development
        print(f"  Merge failed: {result.stderr.strip()}", file=sys.stderr)
        run_git("checkout", "development")
        fail(
            "Fast-forward merge to beta failed. "
            "Beta may have diverged from development. "
            "Resolve manually before retrying."
        )
    print("  Merged.")

    # --- Step 4: Create annotated tag on beta ---
    print(f"Step 4/6: Creating annotated tag {tag_name}...")
    tag_msg = f"Release {tag_name} - version {full_version}"
    run_git("tag", "-a", tag_name, "-m", tag_msg)
    print(f"  Tagged: {tag_name}")

    # --- Step 5: Push everything ---
    print("Step 5/6: Pushing to origin...")
    push_errors = []

    r = run_git("push", "origin", "development", check=False)
    if r.returncode != 0:
        push_errors.append(f"  development: {r.stderr.strip()}")
    else:
        print("  Pushed development.")

    r = run_git("push", "origin", "beta", check=False)
    if r.returncode != 0:
        push_errors.append(f"  beta: {r.stderr.strip()}")
    else:
        print("  Pushed beta.")

    r = run_git("push", "origin", tag_name, check=False)
    if r.returncode != 0:
        push_errors.append(f"  {tag_name}: {r.stderr.strip()}")
    else:
        print(f"  Pushed tag {tag_name}.")

    if push_errors:
        print("\nWARNING: Some pushes failed (local state is correct):")
        for err in push_errors:
            print(err)
        print("You can retry with: git push origin development beta", tag_name)

    # --- Step 6: Switch back to development ---
    print("Step 6/6: Switching back to development...")
    run_git("checkout", "development")
    print("  On development branch.")

    # --- Summary ---
    print("\n" + "=" * 50)
    print("  VERSION BUMP COMPLETE")
    print("=" * 50)
    print(f"  Version : {current_version} -> {full_version}")
    print(f"  Tag     : {tag_name}")
    print(f"  Branches: development, beta updated")
    print(f"  Next    : Run tests on beta, then merge beta -> main")
    print("=" * 50)


if __name__ == "__main__":
    main()
