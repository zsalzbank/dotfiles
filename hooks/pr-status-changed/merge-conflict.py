#!/usr/bin/env python3
"""pr-status-changed hook: merge conflict -> /merge-master."""

import sys

sys.path.insert(0, "/mnt/personal/hooks/lib")
import hooklib  # noqa: E402

payload = hooklib.load_payload()
if hooklib.is_terminal(payload):
    sys.exit(0)

repo, num, url = hooklib.ref(payload)
key = f"merge-conflict-{repo}#{num}"

if hooklib.current(payload).get("conflict") is True:
    if hooklib.episode_guard(key, "conflict"):
        hooklib.inject(
            "merge-conflict",
            f"/canals:merge-master (hook: {repo}#{num} has a merge conflict — {url})",
        )
else:
    hooklib.episode_clear(key)
