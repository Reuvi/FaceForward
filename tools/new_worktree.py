#!/usr/bin/env python3
"""Create a private branch/worktree without modifying an existing checkout."""

import argparse
from pathlib import Path
import re
import subprocess
import sys


LANES = ("vision", "processing", "drivers", "integration")


def git(*args, cwd=None):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def slug(value):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", value):
        raise argparse.ArgumentTypeError(
            "use 1–40 lowercase letters/digits/hyphens, starting with a letter or digit"
        )
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", choices=LANES)
    parser.add_argument("developer", type=slug)
    parser.add_argument("task", type=slug)
    parser.add_argument("--base", required=True, help="explicit clean starting commit/ref")
    args = parser.parse_args()

    try:
        root = Path(git("rev-parse", "--show-toplevel").decode().strip())
        if git("status", "--porcelain", "--untracked-files=all", cwd=root).strip():
            parser.error("starting checkout is dirty; preserve it and use a clean checkout")
        base = git(
            "rev-parse", "--verify", "--end-of-options", args.base + "^{commit}", cwd=root
        ).decode().strip()
        branch = f"work/{args.developer}/{args.lane}/{args.task}"
        git("check-ref-format", "--branch", branch, cwd=root)
        refs = git(
            "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes", cwd=root
        ).decode().splitlines()
        if any(ref == f"refs/heads/{branch}" or ref.endswith("/" + branch) for ref in refs):
            parser.error(f"branch already exists locally or in fetched remotes: {branch}")

        entries = git("worktree", "list", "--porcelain", "-z", cwd=root).split(b"\0")
        primary = Path(next(item[9:] for item in entries if item.startswith(b"worktree ")).decode())
        container = primary / ".worktrees"
        target = container / f"{args.developer}-{args.lane}-{args.task}"
        if target.exists() or target.is_symlink():
            parser.error(f"target already exists: {target}")
        container.mkdir(exist_ok=True)
        git("worktree", "add", "-b", branch, str(target), base, cwd=root)
    except (subprocess.CalledProcessError, OSError, StopIteration) as exc:
        detail = exc.stderr.decode(errors="replace").strip() if isinstance(
            exc, subprocess.CalledProcessError
        ) else str(exc)
        print(f"Worktree creation failed: {detail}", file=sys.stderr)
        return 1

    print(f"Branch: {branch}\nBase: {base}\nOpen this directory: {target}")
    print("Use this directory for one active agent. Existing checkouts were not switched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
