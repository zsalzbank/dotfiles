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

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

MARKER_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "devspaces" / "hook-episodes"
LOG_DIR = Path("/tmp/devspaces/hooks")
DEVSPACES_BIN = os.environ.get("DEVSPACES_AGENT_BIN", "devspaces")
CUSTOM_ENV_FILE = Path(os.environ.get("DEVSPACES_CUSTOM_ENV_FILE", "/etc/custom.env"))
# Episode markers live in /tmp and die with the pod — fine for de-duping repeated
# deliveries. A "this failure is unrelated, stop telling me" decision has to
# outlive the pod, so it goes on the personal volume instead.
IGNORE_DIR = Path(os.environ.get("DEVSPACES_HOOK_IGNORE_DIR",
                                 "/mnt/personal/hooks/state/ci-ignore"))


def skill(name: str) -> str:
    """Format a plugin skill invocation for the workspace's selected agent."""
    frontend = os.environ.get("DEVSPACES_CLAUDE_FRONTEND")
    if not frontend:
        try:
            for line in CUSTOM_ENV_FILE.read_text().splitlines():
                key, separator, value = line.partition("=")
                if separator and key == "DEVSPACES_CLAUDE_FRONTEND":
                    frontend = value.strip().strip("'\"")
                    break
        except OSError:
            pass
    return f"${name}" if frontend == "codex" else f"/{name}"


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


def failing_checks(repo: str, num: str) -> list[str]:
    """Names of the PR's currently-failing checks, sorted.

    The event payload only carries a single rolled-up `checks` enum, so the names
    have to come from GitHub. `gh pr checks` exits non-zero precisely when
    something is failing, so the return code is ignored and only stdout is read.
    Returns [] if GitHub can't be reached — callers degrade to a coarse signature
    rather than going silent."""
    if not repo or not num:
        return []
    try:
        proc = subprocess.run(
            ["gh", "pr", "checks", str(num), "--repo", repo,
             "--json", "name,bucket"],
            capture_output=True, text=True, timeout=30)
        rows = json.loads(proc.stdout or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    if not isinstance(rows, list):
        return []
    return sorted({r["name"] for r in rows if isinstance(r, dict)
                   and r.get("bucket") == "fail" and r.get("name")})


def failure_sig(names: list[str]) -> str:
    """Signature for a *set* of failing checks, so a different failure is a
    different episode and re-notifies, while the same one stays quiet."""
    if not names:
        return "failure"
    return "checks-" + hashlib.sha256("\n".join(names).encode()).hexdigest()[:12]


def is_ignored(key: str, sig: str) -> bool:
    """Has this exact failure set been judged unrelated to the branch before?"""
    try:
        for line in (IGNORE_DIR / _key(key)).read_text().splitlines():
            if line.split("\t", 1)[0] == sig:
                return True
    except OSError:
        pass
    return False


def ignore_add(key: str, sig: str, names: list[str], reason: str) -> None:
    """Record a failure set as unrelated, so it stops re-notifying."""
    try:
        IGNORE_DIR.mkdir(parents=True, exist_ok=True)
        with (IGNORE_DIR / _key(key)).open("a") as fh:
            fh.write(f"{sig}\t{reason}\t{', '.join(names)}\n")
    except OSError as exc:
        print(f"could not record ignore: {exc}", file=sys.stderr)


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


# Small CLI so an agent (or you) can mark a CI failure as unrelated to the branch
# and stop it re-notifying. Lives here rather than in bin/ so the existing hook
# installer ships it — no extra PATH entry to maintain.
if __name__ == "__main__":
    argv = sys.argv[1:]
    if len(argv) >= 2 and argv[0] == "ignore":
        repo, _, num = argv[1].partition("#")
        why = " ".join(argv[2:]).strip() or "unrelated to this branch"
        checks = failing_checks(repo, num)
        sig = failure_sig(checks)
        ignore_add(f"ci-failures-{repo}#{num}", sig, checks, why)
        print(f"ignoring {sig} on {repo}#{num} "
              f"({', '.join(checks) or 'check list unavailable'}): {why}")
    elif len(argv) >= 2 and argv[0] == "list":
        repo, _, num = argv[1].partition("#")
        path = IGNORE_DIR / _key(f"ci-failures-{repo}#{num}")
        print(path.read_text().rstrip() if path.exists() else "(nothing ignored)")
    else:
        print("usage: hooklib.py ignore <owner/repo>#<num> [reason]\n"
              "       hooklib.py list   <owner/repo>#<num>", file=sys.stderr)
        sys.exit(2)
