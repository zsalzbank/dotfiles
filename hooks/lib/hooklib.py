"""Shared helpers for devspaces pr-status-changed hooks.

Each hook receives the event JSON as argv[1]. On its condition it calls
`inject(...)`, which spawns `devspaces agent send-message --wait-idle`
DETACHED, so the hook itself returns well under the dispatcher's 60s timeout
while the (possibly long) idle-wait + typing happens in the CLI command.

The injection primitive — resolving the zmx session, waiting for the user to
pause, bracketed-paste + submit — lives in the devspaces CLI, not here.

Episode marker files dedup at-least-once / repeated deliveries: a hook fires
once per episode and clears its marker when the condition no longer holds.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

MARKER_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "devspaces" / "hook-episodes"
LOG_DIR = Path("/tmp/devspaces/hooks")
DEVSPACES_BIN = os.environ.get("DEVSPACES_AGENT_BIN", "devspaces")


def load_payload() -> dict:
    """Parse argv[1] as the event JSON; exit 0 (no-op) if missing/malformed."""
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("no payload", file=sys.stderr)
        sys.exit(0)
    try:
        data = json.loads(sys.argv[1])
    except (ValueError, TypeError) as exc:
        print(f"bad payload: {exc}", file=sys.stderr)
        sys.exit(0)
    return data if isinstance(data, dict) else {}


def ref(payload: dict) -> tuple[str, str, str]:
    """(repo, number, url) from the event reference."""
    r = payload.get("reference") or {}
    return str(r.get("repo", "")), str(r.get("number", "")), str(r.get("url", ""))


def current(payload: dict) -> dict:
    return payload.get("current") or {}


def is_terminal(payload: dict) -> bool:
    """A merged/closed PR is terminal — nothing worth acting on."""
    return current(payload).get("state") in ("merged", "closed")


def _key(raw: str) -> str:
    return "".join(c if (c.isalnum() or c in "._-") else "_" for c in raw)


def episode_guard(key: str, sig: str) -> bool:
    """True (fire) iff `sig` hasn't already fired for `key`; records it."""
    try:
        MARKER_DIR.mkdir(parents=True, exist_ok=True)
        f = MARKER_DIR / _key(key)
        prev = f.read_text() if f.exists() else None
        if prev == sig:
            return False
        f.write_text(sig)
    except OSError:
        # If we can't persist state, err on the side of firing.
        return True
    return True


def episode_clear(key: str) -> None:
    """Drop the marker so the episode fires again next time it recurs."""
    try:
        (MARKER_DIR / _key(key)).unlink()
    except OSError:
        pass


def inject(hook: str, text: str, wait_idle: bool = True) -> None:
    """Fire-and-forget: run `devspaces workspaces send-message` detached."""
    if os.environ.get("DEVSPACES_HOOK_DRYRUN"):
        print(f"[dryrun] would inject ({hook}):\n{text}")
        return
    cmd = [DEVSPACES_BIN, "agent", "send-message"]
    if wait_idle:
        cmd.append("--wait-idle")
    cmd.append(text)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log = open(LOG_DIR / f"inject-{int(time.time())}-{hook}.log", "ab")
    except OSError:
        log = subprocess.DEVNULL
    subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,  # detach: survive the hook's 60s kill
    )
