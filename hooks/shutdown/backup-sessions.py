#!/usr/bin/env python3
"""shutdown hook: back up this workspace's Claude sessions to the personal share.

Runs at pod teardown (stop *or* destroy) via the devspaces `shutdown`
workspace-hook event, with the event JSON as argv[1]. Claude Code's session
transcripts live under `~/.claude/projects/` and are per-pod — they vanish when
the pod is torn down. This copies them into the durable `/mnt/personal` share,
bucketed by the ISO week (UTC) of each session's last edit, so a weekly
`claude insights` pass can later distill learnings across every workspace.

Layout it maintains:

    /mnt/personal/claude-sessions/<YYYY-Www>/<session-id>.jsonl

Rules (this docstring is the source of truth; the README only points here):
- **Week bucket** = ISO year-week of the transcript's mtime, computed in UTC, so
  the same session buckets identically no matter which pod backs it up.
- **One bucket per session.** A session lives in exactly one week folder; when a
  resumed session's last-edit week changes, the stale copy is pruned so it never
  appears twice.
- **Session id is the whole key.** The transcript filename is the session UUID —
  globally unique — so no workspace/project namespacing is needed to avoid
  collisions, and the prune only ever touches copies of the exact session it's
  handling (which only this workspace produced). The transcript records its own
  `cwd`, so per-session context isn't lost by flattening the path.
- **Complete enough for insights.** The `.jsonl` transcript is the whole session
  (prompts, tool calls, results), so backing up every transcript captures what an
  insights pass needs.
- **Fast, idempotent, best-effort** for the copy itself: skips unchanged files,
  tolerates per-file errors, stays well under the hook's 15s budget, and may run
  more than once. The one thing it does NOT do quietly is a *missing projects
  dir*: since this hook runs first in teardown (fs still intact), an absent dir
  means we resolved the wrong path or the home volume isn't mounted — so it
  prints the resolved state to stderr and exits non-zero (loud) rather than
  reporting a clean "nothing to back up" while a live session is lost.
"""

from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

DEST_ROOT = Path("/mnt/personal/claude-sessions")


def projects_dir() -> Path:
    """Where Claude Code keeps transcripts: its config dir + `/projects`.

    Resolve it the way Claude itself does — `$CLAUDE_CONFIG_DIR` if set, else
    `~/.claude`. We deliberately do NOT widen the search (e.g. globbing
    `/home/*`): if transcripts aren't at the resolved path, that's a real fault
    (wrong `$HOME`, or the home volume isn't mounted at teardown) we want
    surfaced, not papered over.
    """
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(config) if config else Path.home() / ".claude"
    return base / "projects"


def week_bucket(mtime: float) -> str:
    """ISO year-week of a POSIX mtime, in UTC — e.g. `2026-W30`."""
    iso = datetime.fromtimestamp(mtime, tz=timezone.utc).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def main() -> None:
    # argv[1] is the shutdown payload. We back up on every teardown (a stop can
    # still reset the pod), so we don't branch on `toStatus` — but tolerate a
    # missing/garbage payload rather than assuming it's there.
    _payload = sys.argv[1] if len(sys.argv) > 1 else "{}"

    projects = projects_dir()

    # This hook runs FIRST in teardown (fs still intact), so a workspace that
    # ran Claude should always have its projects dir here. If it's missing we
    # resolved the wrong path (bad $HOME / $CLAUDE_CONFIG_DIR) or the home
    # volume isn't mounted — either way we'd silently lose the session. Fail
    # LOUD with the state that explains it (this is the trace we lacked when a
    # 27ms "nothing to back up" no-op ate a live session) instead of exiting 0
    # as if there were nothing to do.
    if not projects.is_dir():
        home = os.environ.get("HOME", "<unset>")
        home_exists = Path(home).is_dir() if home != "<unset>" else False
        claude_exists = (Path(home) / ".claude").is_dir() if home != "<unset>" else False
        print(
            "backup-sessions: projects dir not found — NOTHING BACKED UP\n"
            f"  resolved:          {projects}\n"
            f"  HOME:              {home} (exists={home_exists})\n"
            f"  CLAUDE_CONFIG_DIR: {os.environ.get('CLAUDE_CONFIG_DIR', '<unset>')}\n"
            f"  cwd:               {os.getcwd() if os.path.isdir('.') else '<gone>'}\n"
            f"  ~/.claude exists:  {claude_exists}",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        DEST_ROOT.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"cannot create {DEST_ROOT}: {exc}", file=sys.stderr)
        return

    copied = pruned = 0

    for transcript in projects.rglob("*.jsonl"):
        try:
            src_stat = transcript.stat()
            session_id = transcript.stem  # the session UUID — globally unique
            week = week_bucket(src_stat.st_mtime)
            target = DEST_ROOT / week / f"{session_id}.jsonl"

            # Globbing on the session's own UUID means we only ever prune copies
            # of *this* session — never another session's or workspace's backup.
            for existing in DEST_ROOT.glob(f"*/{session_id}.jsonl"):
                if existing != target:
                    existing.unlink()
                    pruned += 1

            # copy2 (not copy) so the dest keeps the source mtime — both the
            # skip-if-unchanged check below and the week bucket rely on it.
            if (
                not target.exists()
                or target.stat().st_mtime != src_stat.st_mtime
                or target.stat().st_size != src_stat.st_size
            ):
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(transcript, target)
                copied += 1
        except OSError as exc:
            print(f"skip {transcript}: {exc}", file=sys.stderr)

    print(f"backed up {copied} session(s), pruned {pruned} stale copy(ies)")


if __name__ == "__main__":
    main()
