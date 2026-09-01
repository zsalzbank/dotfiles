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
checks = hooklib.current(payload).get("checks")

if checks == "failure":
    # Signature is the SET OF FAILING CHECK NAMES, not the bare word "failure".
    # A constant signature can't tell a new failure from the one you were already
    # told about, and since `episode_clear` used to run on any non-failure rollup
    # (`pending` included), the ordinary fail -> re-run -> fail cycle re-armed the
    # guard and re-notified — one PR got pinged 7 times for the same break.
    names = hooklib.failing_checks(repo, num)
    sig = hooklib.failure_sig(names)
    if not hooklib.is_ignored(key, sig) and hooklib.episode_guard(key, sig):
        failing = ", ".join(names) if names else "unknown (couldn't read the check list)"
        hooklib.inject(
            "ci-failures",
            f"A hook detected CI failures on {repo}#{num} ({url}). Failing: "
            f"{failing}. First work out whether these are caused by this branch's "
            f"diff. If they are, run the {hooklib.skill('canals:plan-from-ci-failures')} "
            "workflow in a "
            "background subagent so I can keep working, and report the fix plan "
            "when it's ready. If they are NOT ours — a flake, a break already on "
            "master, or infra — don't fix them: tell me, and record it so this "
            "stops re-notifying:\n"
            f"  python3 /mnt/personal/hooks/lib/hooklib.py ignore {repo}#{num} \"<why>\"",
        )
elif checks == "success":
    # Deliberately NOT clearing on pending/merging/deploy-blocked: those are just
    # CI in flight, and clearing there is what caused the repeat notifications.
    hooklib.episode_clear(key)
