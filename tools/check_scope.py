#!/usr/bin/env python3
"""Check changed paths against a lane; this is a review aid, not a security boundary."""

import argparse
import os
import re
import subprocess
import sys


PREFIXES = {
    "vision": ("Vision/", "tests/vision/"),
    "processing": ("Processing/", "tests/processing/"),
    "drivers": ("Drivers/", "tests/drivers/"),
    "integration": (),
}


def git(*args):
    return subprocess.run(
        ["git", *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ).stdout


def paths(*args):
    return {p.decode("utf-8", errors="surrogateescape") for p in git(*args).split(b"\0") if p}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="agreed base ref or PR base SHA")
    parser.add_argument("--lane", choices=tuple(PREFIXES), help="otherwise infer from source branch")
    parser.add_argument("--branch", help="source branch name, needed for detached CI checkouts")
    args = parser.parse_args()

    try:
        os.chdir(git("rev-parse", "--show-toplevel").decode().strip())
        lane = args.lane
        if lane is None:
            branch = args.branch or git("symbolic-ref", "--short", "HEAD").decode().strip()
            match = re.fullmatch(
                r"work/[a-z0-9][a-z0-9-]{0,39}/(vision|processing|drivers|integration)/"
                r"[a-z0-9][a-z0-9-]{0,39}", branch
            )
            if branch == "chore/team-agent-setup":
                lane = "integration"
            elif match:
                lane = match.group(1)
            else:
                parser.error("use work/<developer>/<lane>/<task>, or explicitly pass --lane locally")

        base = git("rev-parse", "--verify", "--end-of-options", args.base + "^{commit}").decode().strip()
        ancestor = git("merge-base", base, "HEAD").decode().strip()
        # Disable rename detection so both deleted and added paths are checked.
        changed = paths("diff", "--name-only", "--no-renames", "-z", ancestor, "HEAD")
        changed |= paths("diff", "--cached", "--name-only", "--no-renames", "-z", "HEAD")
        changed |= paths("diff", "--name-only", "--no-renames", "-z")
        changed |= paths("ls-files", "--others", "--exclude-standard", "-z")
    except (subprocess.CalledProcessError, OSError) as exc:
        detail = exc.stderr.decode(errors="replace").strip() if isinstance(
            exc, subprocess.CalledProcessError
        ) else str(exc)
        print(f"Scope check failed: {detail}", file=sys.stderr)
        return 2

    if lane == "integration":
        print(f"Integration lane: {len(changed)} changed paths; coordinate shared/component ownership in review.")
        return 0
    violations = sorted(path for path in changed if not path.startswith(PREFIXES[lane]))
    if violations:
        print(f"Paths outside the {lane} lane:", file=sys.stderr)
        for path in violations:
            print(f"  {path}", file=sys.stderr)
        print("Coordinate a handoff; do not remove other agents' changes to pass this check.", file=sys.stderr)
        return 1
    print(f"Scope OK: {lane}, {len(changed)} changed paths.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
