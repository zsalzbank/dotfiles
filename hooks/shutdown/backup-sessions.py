#!/usr/bin/env python3
"""shutdown hook: back up this workspace's agent sessions to the personal share.

Runs at pod teardown (stop *or* destroy) via the devspaces `shutdown`
workspace-hook event, with the event JSON as argv[1]. Claude Code's session
transcripts live under `~/.claude/projects/`; Codex's live and archived
transcripts live under `~/.codex/sessions/` and `~/.codex/archived_sessions/`.
These per-pod files vanish at teardown. This copies them into the durable
`/mnt/personal` share, bucketed by the ISO week (UTC) of each session's last
edit. Claude's backup remains available to the weekly `claude insights` pass.

Layout it maintains:

    /mnt/personal/claude-sessions/<YYYY-Www>/<session-id>.jsonl
    /mnt/personal/codex-sessions/<YYYY-Www>/<rollout-filename>.jsonl

Rules (this docstring is the source of truth; the README only points here):
- **Week bucket** = ISO year-week of the transcript's mtime, computed in UTC, so
  the same session buckets identically no matter which pod backs it up.
- **One bucket per session.** A session lives in exactly one week folder; when a
  resumed session's last-edit week changes, the stale copy is pruned so it never
  appears twice.
- **Transcript filename is the whole key.** Claude's filename is the session
  UUID; Codex's rollout filename includes the session UUID. Separate agent
  folders prevent collisions, and pruning only touches copies of the exact
  transcript being handled. Each transcript records its own `cwd`.
- **Complete enough for insights.** The `.jsonl` transcript is the whole session
  (prompts, tool calls, results), so backing up every transcript captures what an
  insights pass needs.
- **Fast, idempotent, best-effort** for the copy itself: skips unchanged files,
  tolerates per-file errors, stays well under the hook's 15s budget, and may run
  more than once. A missing transcript directory for the selected agent is a
  failure: the hook prints the resolved paths and exits non-zero rather than
  silently losing a live session. A workspace may also have sessions from the
  other agent, so any available transcripts are still backed up.
"""

from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

CLAUDE_DEST_ROOT = Path("/mnt/personal/claude-sessions")
CODEX_DEST_ROOT = Path("/mnt/personal/codex-sessions")


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


def codex_dir() -> Path:
    config = os.environ.get("CODEX_HOME")
    return Path(config) if config else Path.home() / ".codex"


def week_bucket(mtime: float) -> str:
    """ISO year-week of a POSIX mtime, in UTC — e.g. `2026-W30`."""
    iso = datetime.fromtimestamp(mtime, tz=timezone.utc).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def backup_transcripts(source: Path, dest_root: Path) -> tuple[int, int]:
    dest_root.mkdir(parents=True, exist_ok=True)
    copied = pruned = 0

    for transcript in source.rglob("*.jsonl"):
        try:
            src_stat = transcript.stat()
            filename = transcript.name
            week = week_bucket(src_stat.st_mtime)
            target = dest_root / week / filename

            if (
                not target.exists()
                or target.stat().st_mtime != src_stat.st_mtime
                or target.stat().st_size != src_stat.st_size
            ):
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(transcript, target)
                copied += 1

            for existing in dest_root.glob(f"*/{filename}"):
                if existing != target:
                    existing.unlink()
                    pruned += 1
        except OSError as exc:
            print(f"skip {transcript}: {exc}", file=sys.stderr)

    return copied, pruned


def main() -> None:
    # argv[1] is the shutdown payload. We back up on every teardown (a stop can
    # still reset the pod), so we don't branch on `toStatus` — but tolerate a
    # missing/garbage payload rather than assuming it's there.
    _payload = sys.argv[1] if len(sys.argv) > 1 else "{}"

    projects = projects_dir()
    codex = codex_dir()
    codex_sessions = codex / "sessions"
    selected = os.environ.get("DEVSPACES_CLAUDE_FRONTEND")
    missing = (selected == "codex" and not codex_sessions.is_dir()) or (
        selected not in (None, "codex") and not projects.is_dir()
    ) or (not projects.is_dir() and not codex_sessions.is_dir())

    if missing:
        home = os.environ.get("HOME", "<unset>")
        home_exists = Path(home).is_dir() if home != "<unset>" else False
        claude_exists = (Path(home) / ".claude").is_dir() if home != "<unset>" else False
        print(
            "backup-sessions: selected agent's sessions dir not found\n"
            f"  Claude projects:   {projects} (exists={projects.is_dir()})\n"
            f"  Codex sessions:    {codex_sessions} (exists={codex_sessions.is_dir()})\n"
            f"  selected frontend: {selected or '<unset>'}\n"
            f"  HOME:              {home} (exists={home_exists})\n"
            f"  CLAUDE_CONFIG_DIR: {os.environ.get('CLAUDE_CONFIG_DIR', '<unset>')}\n"
            f"  CODEX_HOME:        {os.environ.get('CODEX_HOME', '<unset>')}\n"
            f"  cwd:               {os.getcwd() if os.path.isdir('.') else '<gone>'}\n"
            f"  ~/.claude exists:  {claude_exists}",
            file=sys.stderr,
        )

    for label, source, dest in (
        ("Claude", projects, CLAUDE_DEST_ROOT),
        ("Codex", codex_sessions, CODEX_DEST_ROOT),
        ("Codex archived", codex / "archived_sessions", CODEX_DEST_ROOT),
    ):
        if not source.is_dir():
            continue
        try:
            copied, pruned = backup_transcripts(source, dest)
        except OSError as exc:
            print(f"cannot back up {source} to {dest}: {exc}", file=sys.stderr)
            missing = True
            continue
        print(f"{label}: backed up {copied} session(s), pruned {pruned} stale copy(ies)")

    if missing:
        sys.exit(1)


if __name__ == "__main__":
    main()
