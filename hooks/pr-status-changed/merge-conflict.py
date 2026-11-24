#!/usr/bin/env python3
"""pr-status-changed hook: auto-sync standalone PRs, ask before changing a stack."""

import json
import subprocess
import sys

sys.path.insert(0, "/mnt/personal/hooks/lib")
import hooklib  # noqa: E402


def conflict_notification(repo: str, num: str, url: str) -> tuple[str, str] | None:
    """(episode signature, message), or None for a closed PR."""
    notification = f"A hook detected a merge conflict on {repo}#{num} ({url}). "
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/pulls/{num}", "--jq",
             "{state,sha:.head.sha,head:.head.ref,base:.base.ref,default:.base.repo.default_branch}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        pr = json.loads(result.stdout)
        if not isinstance(pr, dict):
            raise ValueError("PR metadata is not an object")
        if pr.get("state") == "closed":
            return None
        sha, head, base, default = pr.get("sha"), pr.get("head"), pr.get("base"), pr.get("default")
        if pr.get("state") != "open" or not all(isinstance(value, str) and value for value in (sha, head, base, default)):
            raise ValueError("PR head/base metadata is missing")
        signature = f"{sha}:{base}"
        if base == default:
            return signature, (
                f"{hooklib.skill('canals:merge-master')} {repo}#{num} "
                f"(hook: head {head} has a merge conflict with its default-branch base {base} — {url}). "
                f"Work only on this PR's head {head}. Re-read its current head, base, and repository default branch "
                "before acting. If it is closed, stop. If its base is no longer the default branch, or you cannot "
                "verify the metadata, notify the user and wait instead of merging. Do not update other stack branches."
            )
        notification += f"This is a stacked PR: {head} targets {base}, not the default branch {default}. "
    except (subprocess.SubprocessError, OSError, ValueError):
        signature = "unverified"
        notification += "Its current head/base could not be verified. "
    return signature, (
        notification + "Notify the user and wait for their explicit request before invoking a merge workflow "
        "or making Git/PR changes in response to this notification."
    )


payload = hooklib.load_payload()
if hooklib.is_terminal(payload):
    sys.exit(0)

repo, num, url = hooklib.ref(payload)

# GitHub reports `mergeable` as UNKNOWN while it recomputes after the base moves, which the payload
# flattens to conflict=false. Clearing the episode on that would re-notify the same conflict, so the
# episode is keyed on head commit and base instead: only a new push or a retarget notifies again.
if hooklib.current(payload).get("conflict") is True:
    notification = conflict_notification(repo, num, url)
    if notification and hooklib.episode_guard(f"merge-conflict-{repo}#{num}", notification[0]):
        hooklib.inject("merge-conflict", notification[1])
