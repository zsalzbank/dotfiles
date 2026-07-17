#!/usr/bin/env python3
"""pr-status-changed hook: unresolved review comments -> /plan-from-pr-comments."""

import sys

sys.path.insert(0, "/mnt/personal/hooks/lib")
import hooklib  # noqa: E402

payload = hooklib.load_payload()
if hooklib.is_terminal(payload):
    sys.exit(0)

repo, num, url = hooklib.ref(payload)
key = f"review-comments-{repo}#{num}"

if hooklib.current(payload).get("unresolved") is True:
    # Signature the episode on the unresolved-thread-set fingerprint the backend
    # now sends, so a *churn* (a reviewer resolves one thread and opens another —
    # `unresolved` stays True across polls) counts as a new episode and re-fires.
    # Fall back to a constant signature on older backends that don't emit
    # `unresolvedFingerprint`, preserving the previous fire-once-per-episode
    # behaviour (fires on the transition into unresolved, no re-fire on churn).
    sig = hooklib.current(payload).get("unresolvedFingerprint") or "unresolved"
    if hooklib.episode_guard(key, sig):
        hooklib.inject(
            "review-comments",
            f"/canals:plan-from-pr-comments (hook: {repo}#{num} has unresolved review comments — {url})",
        )
else:
    hooklib.episode_clear(key)
