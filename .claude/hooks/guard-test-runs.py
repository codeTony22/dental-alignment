#!/usr/bin/env python3
"""Guard the two ways this repo has actually wasted wall-clock on test batteries.

Rules in CLAUDE.md are advisory: an agent under load forgets them, and the cost lands
20 minutes later when the run comes back. These two are mechanical instead.

1. STALE GATE. pytest imports the tree at collection, so a battery started before the
   last write reports — confidently — on code that no longer exists on disk. On
   2026-07-28 a run started at 21:27 and `adjust.py` was edited at 21:33; the 24-minute
   answer was about a version of the file nobody had. We block a battery when a source
   file changed within QUIET_SECONDS.

2. DUPLICATE RUN. Two copies of one suite on one box are slower than one, not faster.
   Same evening: a second identical slow lane was launched while the first had 6 minutes
   left, and both got slower.

Only LONG runs are guarded. `npm test` finishes in seconds and is never blocked; a
narrow `pytest tests/test_foo.py` is the encouraged inner loop and is never blocked.
Exit 2 blocks the call and returns stderr to the agent as feedback.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

QUIET_SECONDS = 20
REPO = Path(__file__).resolve().parents[2]

# A "battery": the whole worker suite, or a marker lane. A command naming specific test
# files is the narrow inner loop this repo WANTS and is deliberately not matched.
BATTERY = re.compile(
    r"(make\s+(test|test-slow|test-fast|rehearse)\b"
    r"|pytest(?!.*\btests/test_\w+\.py)"
    r"(?=.*(-m\s+[\"']?slow|-m\s+[\"']?not slow|\btests\b\s*$|\s*$)))"
)


def strip_quoted(command: str) -> str:
    """Blank out quoted segments before matching.

    Caught immediately on first use: an `echo '... make test-slow ...'` that merely NAMES
    a battery was blocked as though it ran one. A guard that fires on discussion of a
    command rather than the command is worse than no guard — it teaches everyone to
    disable it. Quoted text is data, so it cannot be the thing being invoked.
    """
    return re.sub(r"'[^']*'|\"[^\"]*\"", " ", command)


def recently_written() -> list[tuple[str, float]]:
    """Tracked source files written within QUIET_SECONDS, newest first."""
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:
        return []
    now, fresh = time.time(), []
    for line in out.splitlines():
        name = line[3:].strip().strip('"')
        if not name or name.endswith("/"):
            continue
        if not name.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".toml", ".css")):
            continue
        path = REPO / name
        try:
            age = now - path.stat().st_mtime
        except OSError:
            continue
        if age < QUIET_SECONDS:
            fresh.append((name, age))
    return sorted(fresh, key=lambda pair: pair[1])


def already_running() -> str | None:
    """An equivalent battery already in flight, as its elapsed time."""
    try:
        out = subprocess.run(
            ["ps", "-eo", "etime,command"], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        return None
    for line in out.splitlines():
        if "pytest" in line and "guard-test-runs" not in line and "grep" not in line:
            if " -m slow" in line or line.rstrip().endswith("pytest -q"):
                return line.split(maxsplit=1)[0]
    return None


def main() -> int:
    try:
        command = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    except Exception:
        return 0
    if not BATTERY.search(strip_quoted(command)):
        return 0

    elapsed = already_running()
    if elapsed is not None:
        print(
            f"BLOCKED: an equivalent test battery is already running ({elapsed} elapsed).\n"
            f"A second copy on one box makes both slower. Wait for the one in flight and "
            f"read its output, or stop it first if it is stale.",
            file=sys.stderr,
        )
        return 2

    fresh = recently_written()
    if fresh:
        listed = ", ".join(f"{name} ({age:.0f}s ago)" for name, age in fresh[:3])
        print(
            f"BLOCKED: source files were written in the last {QUIET_SECONDS}s: {listed}.\n"
            f"pytest imports the tree at collection, so a battery started now may report on "
            f"code you are still changing — that has cost this repo 18 minutes before.\n"
            f"Finish editing, wait {QUIET_SECONDS}s, then gate. To run anyway, the narrow "
            f"form (`pytest tests/test_<name>.py`) is never blocked.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
