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
- **Fast, idempotent, best-effort.** Skips unchanged files, never throws, and
  stays well under the hook's 15s budget. It may run more than once.
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

DEST_ROOT = Path("/mnt/personal/claude-sessions")
PROJECTS_DIR = Path.home() / ".claude" / "projects"


def week_bucket(mtime: float) -> str:
    """ISO year-week of a POSIX mtime, in UTC — e.g. `2026-W30`."""
    iso = datetime.fromtimestamp(mtime, tz=timezone.utc).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def main() -> None:
    # argv[1] is the shutdown payload. We back up on every teardown (a stop can
    # still reset the pod), so we don't branch on `toStatus` — but tolerate a
    # missing/garbage payload rather than assuming it's there.
    _payload = sys.argv[1] if len(sys.argv) > 1 else "{}"

    if not PROJECTS_DIR.is_dir():
        print(f"no {PROJECTS_DIR}; nothing to back up")
        return
    try:
        DEST_ROOT.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"cannot create {DEST_ROOT}: {exc}", file=sys.stderr)
        return

    copied = pruned = 0

    for transcript in PROJECTS_DIR.rglob("*.jsonl"):
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
