#!/usr/bin/env python3
"""pr-status-changed hook: CI failure -> run plan-from-ci-failures in the background.

Kept simple: fires when the checks rollup reads `failure`. The waiting/polling of
still-running automated checks and the skipping of user-input gates (Chromatic,
manual review gates) all live in the `/plan-from-ci-failures` skill, so we hand
off rather than gating here.

"In the background": a typed slash command only expands as the first token, so
we can't background it as `/plan-from-ci-failures &`. Instead we inject a prose
instruction telling Claude to run the workflow in a background subagent, keeping
the foreground session free during its (~30 min) poll.
"""

import sys

sys.path.insert(0, "/mnt/personal/hooks/lib")
import hooklib  # noqa: E402

payload = hooklib.load_payload()
if hooklib.is_terminal(payload):
    sys.exit(0)

repo, num, url = hooklib.ref(payload)
key = f"ci-failures-{repo}#{num}"

if hooklib.current(payload).get("checks") == "failure":
    if hooklib.episode_guard(key, "failure"):
        hooklib.inject(
            "ci-failures",
            f"A hook detected CI failures on {repo}#{num} ({url}). Run the "
            "/canals:plan-from-ci-failures workflow for it in a background subagent "
            "so I can keep working, and report the fix plan when it's ready.",
        )
else:
    hooklib.episode_clear(key)
