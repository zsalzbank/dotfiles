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
    if hooklib.episode_guard(key, "unresolved"):
        hooklib.inject(
            "review-comments",
            f"/canals:plan-from-pr-comments (hook: {repo}#{num} has unresolved review comments — {url})",
        )
else:
    hooklib.episode_clear(key)
