#!/usr/bin/env python3
"""Search, select, and act on GitHub notifications in bulk.

  (no args)   Open the TUI: the whole unread inbox in a list you can search by
              title, check off, and then act on. The notifications web UI has no
              title search, which is the whole reason this exists.

  clean       The non-interactive sweep: mark done every unread notification
              that is a draft PR, a PR closed without merging, or not a PR at
              all. Merged PRs are left alone. Kept as a subcommand so it works
              in a script and still works if the TUI's venv is broken.

PR state is cached in ~/.cache/gh-triage/prs.json and only re-fetched when the
notification's updated_at moves. Delete that file to force a full refresh.

Listing notifications needs a classic PAT with the `notifications` scope in
GITHUB_NOTIFICATIONS_PAT -- fine-grained PATs cannot reach that endpoint at all.
PR state is read through `gh`, which already holds org access.

Runs anywhere those two are available, laptop included. `o` opens the selected
PRs with the platform opener, so run it where your browser is; in a remote
workspace there is no browser to open, so it prints the urls instead.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import dataclasses
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.github.com"
CACHE = Path(os.environ.get("GH_TRIAGE_CACHE", Path.home() / ".cache" / "gh-triage"))
PR_CACHE = CACHE / "prs.json"
PR_CACHE_MAX_AGE = 30 * 86400
# Bump when the GraphQL selection changes, or entries cached under the old
# shape get reused and the missing field just reads as absent.
PR_FIELDS = 2


def _default_log():
    """Decisions are training data, not cache, so they go under the user data
    dir rather than the prunable cache path. In a devspaces pod that dir is
    ephemeral, so the persistent share wins there; GH_TRIAGE_LOG overrides both,
    which is how a pod and a laptop can append to the same file.
    """
    personal = Path("/mnt/personal")
    if os.environ.get("DEVSPACES_WORKSPACE_ID") and personal.is_dir():
        base = personal
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "gh-triage" / "actions.jsonl"


LOG = Path(os.environ.get("GH_TRIAGE_LOG") or _default_log())

# GitHub asks for serial mutations a second apart, which is ten minutes for a
# full inbox. A small pool with real backoff is the compromise: fast enough to
# use, and it yields the moment the API pushes back.
WORKERS = 6


# ---------------------------------------------------------------- github

def notif_token():
    tok = os.environ.get("GITHUB_NOTIFICATIONS_PAT")
    if not tok:
        sys.exit(
            "GITHUB_NOTIFICATIONS_PAT is not set.\n"
            "Create a *classic* PAT with the `notifications` scope "
            "(fine-grained tokens cannot list notifications) and export it."
        )
    return tok


def _auth(extra=None):
    h = {"Authorization": f"token {notif_token()}",
         "Accept": "application/vnd.github+json"}
    h.update(extra or {})
    return h


def get_notifications():
    out, page = [], 1
    while page <= 40:
        req = urllib.request.Request(
            f"{API}/notifications?per_page=100&page={page}", headers=_auth())
        try:
            with urllib.request.urlopen(req) as r:
                batch = json.load(r)
        except urllib.error.HTTPError as e:
            sys.exit(f"notifications API {e.code}: {e.read().decode()[:200]}")
        # The endpoint caps a page at 50 regardless of per_page, so an empty
        # batch is the only reliable end-of-list signal.
        if not batch:
            break
        out.extend(batch)
        page += 1
    return out


def gh_graphql(query: str):
    """GraphQL has its own points-based limit, and a throttled call here returns
    no PR state rather than an error, so say something instead of going quiet."""
    p = subprocess.run(["gh", "api", "graphql", "-f", f"query={query}"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        print(f"  gh graphql failed: {p.stderr.strip()[:200]}", file=sys.stderr)
        return {}
    try:
        return json.loads(p.stdout).get("data") or {}
    except json.JSONDecodeError:
        print("  gh graphql returned unparseable output", file=sys.stderr)
        return {}


def _load_pr_cache():
    try:
        return json.loads(PR_CACHE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _save_pr_cache(cache):
    cutoff = time.time() - PR_CACHE_MAX_AGE
    keep = {k: v for k, v in cache.items() if v.get("seen", 0) >= cutoff}
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = PR_CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(keep))
    tmp.replace(PR_CACHE)


def fetch_prs(refs, notif_updated=None, progress=None):
    """refs: [(owner, repo, number)] -> {(owner,repo,number): pr dict}

    A PR is only re-fetched when its notification's updated_at has moved.
    GitHub bumps that on new commits, comments, and state changes, so an
    unchanged timestamp means the cached copy still describes the PR. Passing no
    timestamps skips the cache entirely.
    """
    cache = _load_pr_cache()
    now, found, stale = time.time(), {}, []
    for ref in refs:
        hit = cache.get(f"{ref[0]}/{ref[1]}#{ref[2]}")
        stamp = (notif_updated or {}).get(ref)
        if hit and stamp and hit.get("stamp") == stamp and hit.get("v") == PR_FIELDS:
            found[ref] = hit["pr"]
            hit["seen"] = now
        else:
            stale.append(ref)

    for i in range(0, len(stale), 25):
        chunk = stale[i:i + 25]
        parts = [
            f'a{n}: repository(owner:"{o}", name:"{r}"){{ '
            f'pullRequest(number:{num}){{ number title isDraft state '
            f'author{{login}} }} }}'
            for n, (o, r, num) in enumerate(chunk)
        ]
        data = gh_graphql("query{ " + " ".join(parts) + " }")
        for n, ref in enumerate(chunk):
            node = (data.get(f"a{n}") or {}).get("pullRequest")
            if not node:
                continue
            found[ref] = node
            stamp = (notif_updated or {}).get(ref)
            if stamp:
                cache[f"{ref[0]}/{ref[1]}#{ref[2]}"] = {
                    "stamp": stamp, "pr": node, "seen": now, "v": PR_FIELDS}
        if progress:
            progress(min(i + 25, len(stale)), len(stale))

    if notif_updated:
        _save_pr_cache(cache)
    return found


NOTIF_URL = re.compile(r"/repos/([^/]+)/([^/]+)/pulls/(\d+)")


def notif_ref(n):
    m = NOTIF_URL.search((n.get("subject") or {}).get("url") or "")
    return (m.group(1), m.group(2), int(m.group(3))) if m else None


@dataclasses.dataclass
class Item:
    thread_id: str
    repo: str
    title: str
    reason: str
    updated: str
    subject_type: str
    ref: tuple | None
    # Only the GraphQL enrichment knows these; the notifications list carries
    # neither an author nor a state, so they stay empty until that lands.
    author: str = ""
    status: str = ""

    @property
    def number(self):
        return self.ref[2] if self.ref else None

    @property
    def url(self):
        if not self.ref:
            return None
        return f"https://github.com/{self.ref[0]}/{self.ref[1]}/pull/{self.ref[2]}"

    @property
    def age(self):
        try:
            d = datetime.now(timezone.utc) - datetime.fromisoformat(self.updated)
        except (TypeError, ValueError):
            return "?"
        if d.days >= 1:
            return f"{d.days}d"
        return f"{d.seconds // 3600}h" if d.seconds >= 3600 else f"{d.seconds // 60}m"


def build_items(notifs):
    """Oldest first: the API hands back newest first, but the stale end of the
    inbox is the part that needs deciding about."""
    return sorted((
        Item(thread_id=n["id"],
             repo=n["repository"]["full_name"],
             title=(n.get("subject") or {}).get("title") or "",
             reason=n.get("reason") or "",
             updated=n.get("updated_at") or "",
             subject_type=(n.get("subject") or {}).get("type") or "?",
             ref=notif_ref(n),
             # A non-PR subject needs no enrichment to be classified.
             status="" if notif_ref(n) else "other")
        for n in notifs
    ), key=lambda i: i.updated)


def local_opener():
    """The platform command that hands a url to the desktop browser, if any.

    Inside a devspaces pod `open`/`xdg-open` are the oauth-browser-shim, not a
    browser: it swallows the url and exits 0. So a pod reports no opener rather
    than a broken one, and `o` prints the urls instead.
    """
    if os.environ.get("DEVSPACES_WORKSPACE_ID"):
        return None
    if sys.platform == "darwin":
        return ["open"] if shutil.which("open") else None
    if sys.platform.startswith("win"):
        return ["cmd", "/c", "start", ""]
    return ["xdg-open"] if shutil.which("xdg-open") else None


def open_urls(items):
    """Open the chosen PRs in browser tabs. True if they were handed off.

    One platform-opener call per url, so the whole batch opens with no click.
    False means there is nowhere to open them and the caller should print.
    """
    opener = local_opener()
    if not opener:
        return False
    for i in items:
        try:
            subprocess.run([*opener, i.url], capture_output=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            return False
    return True


def pr_author(pr):
    return ((pr or {}).get("author") or {}).get("login") or ""


def log_records(records):
    """Append decisions as JSONL. A logging failure must never break an action."""
    if not records:
        return
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as fh:
            for r in records:
                fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    except OSError as e:
        print(f"  could not write {LOG}: {e}", file=sys.stderr)


def decision(item, pr, action, via, ok, batch, query=""):
    """One recorded decision.

    `via` is the part worth keeping honest: a thread you checked by hand is a
    much stronger statement than one caught by select-all, so store how it was
    chosen rather than flattening every action into the same label. Raw fields
    only, so later training can derive labels a different way.
    """
    return {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "action": action,
        "via": via,
        "ok": ok,
        "batch": batch,
        "query": query,
        "thread": item.thread_id,
        "repo": item.repo,
        "number": item.number,
        "title": item.title,
        "author": item.author or pr_author(pr),
        "reason": item.reason,
        "type": item.subject_type,
        "updated": item.updated,
        "pr_state": (pr or {}).get("state"),
        "draft": (pr or {}).get("isDraft"),
        "cleanable": clean_reason(item, pr),
    }


def pr_status(item, pr):
    """open / draft / merged / closed, or `other` for a non-PR subject.

    Closed means closed without merging; GitHub reports a merged PR as MERGED,
    not CLOSED. Empty until enrichment lands, since the notification list says
    nothing about state.
    """
    if not item.ref:
        return "other"
    if not pr:
        return ""
    if pr.get("isDraft"):
        return "draft"
    return {"OPEN": "open", "MERGED": "merged", "CLOSED": "closed"}.get(
        pr.get("state"), (pr.get("state") or "").lower())


CLEANABLE = {"other", "draft", "closed"}


def clean_reason(item, pr):
    """Why `clean` would sweep this, or None to leave it alone.

    Merged and open PRs are deliberately excluded: that work landed, or is live.
    Derived from pr_status so the status column and the sweep cannot disagree.
    """
    status = pr_status(item, pr)
    if status not in CLEANABLE:
        return None
    return item.subject_type if status == "other" else status


# ---------------------------------------------------------------- actions

class Pacer:
    """Shared brake. One worker seeing a secondary limit pauses all of them."""

    def __init__(self):
        self._lock = threading.Lock()
        self._until = 0.0

    def wait(self):
        while True:
            with self._lock:
                delay = self._until - time.time()
            if delay <= 0:
                return
            time.sleep(min(delay, 2.0))

    def brake(self, seconds):
        with self._lock:
            self._until = max(self._until, time.time() + seconds)


ACTIONS = {
    # done   DELETE /threads/{id}
    # unsub  PUT /threads/{id}/subscription {"ignored": true}, then the DELETE
    #
    # Unsubscribing takes both calls. Ignoring the subscription stops future
    # pings but leaves the notification already in the inbox, so on its own it
    # looks like nothing happened; the web UI's Unsubscribe button is this pair.
    # PATCH on the thread is a third thing again -- it only marks read, which
    # also leaves it in the inbox.
    #
    # The subscription is a PUT with ignored rather than a DELETE because these
    # threads arrive through watching the repo: there is no per-thread
    # subscription to delete (that path 404s), and dropping an override would
    # only fall back to the repo watch and keep the pings coming.
    "done": (("DELETE", "", None),),
    "unsub": (("PUT", "/subscription", {"ignored": True}), ("DELETE", "", None)),
}


def thread_action(thread_id, action, pacer=None):
    """Apply one action to one thread. Returns None on success, else an error."""
    for method, suffix, payload in ACTIONS[action]:
        err = _request(thread_id, method, suffix, payload, pacer)
        if err:
            return err
    return None


def throttle_delay(headers, code, body, attempt):
    """Seconds to wait before retrying, or None if this was not throttling.

    403 covers both throttling and plain permission failures, so retrying every
    403 spends minutes asleep on an error that will never clear -- and GitHub
    warns that hammering a limit is itself what escalates it. These are the
    three signals that say a wait is the right response.
    """
    if code not in (403, 429):
        return None
    retry = headers.get("retry-after")
    if retry and retry.isdigit():
        return int(retry)
    if headers.get("x-ratelimit-remaining") == "0":
        reset = headers.get("x-ratelimit-reset")
        return max(1, int(reset) - int(time.time())) if reset and reset.isdigit() else 60
    if "secondary rate limit" in body.lower() or "abuse" in body.lower():
        return 30 * (2 ** attempt)
    # A bare 403 is a permission problem; a bare 429 is still throttling.
    return 30 * (2 ** attempt) if code == 429 else None


# Past this, sleeping just freezes the caller; report back instead so the whole
# batch is not stuck waiting on a limit that resets in half an hour.
MAX_WAIT = 120


def _message(body):
    try:
        return (json.loads(body).get("message") or "")[:60]
    except (ValueError, AttributeError):
        return ""


def _request(thread_id, method, suffix, payload, pacer):
    for attempt in range(4):
        if pacer:
            pacer.wait()
        req = urllib.request.Request(
            f"{API}/notifications/threads/{thread_id}{suffix}",
            method=method,
            data=json.dumps(payload).encode() if payload else None,
            headers=_auth({"content-type": "application/json"} if payload else None),
        )
        try:
            urllib.request.urlopen(req, timeout=30)
            return None
        except urllib.error.HTTPError as e:
            body = e.read()[:400].decode("utf8", "replace")
            delay = throttle_delay(e.headers, e.code, body, attempt)
            if delay is None:
                msg = _message(body)
                return f"HTTP {e.code}" + (f": {msg}" if msg else "")
            if delay > MAX_WAIT:
                return f"rate limited, resets in {round(delay / 60)}m"
            if pacer:
                pacer.brake(delay)
            else:
                time.sleep(delay)
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 3:
                return str(getattr(e, "reason", e))[:40]
            time.sleep(2 ** attempt)
    return "still throttled after 4 tries"


def act_on_threads(ids, action, progress=None, cancel=None):
    """Apply `action` to every thread id. Returns (ok_ids, [(id, error)]).

    There is no batch endpoint: GraphQL exposes no notification mutations, and
    the only bulk REST calls mark a whole scope as read rather than done. So
    this is one request per thread, run through a small pool.
    """
    pacer, ok, failed, done = Pacer(), [], [], 0
    lock = threading.Lock()

    def run(tid):
        if cancel is not None and cancel.is_set():
            return tid, "cancelled"
        return tid, thread_action(tid, action, pacer)

    with cf.ThreadPoolExecutor(WORKERS) as ex:
        futures = [ex.submit(run, t) for t in ids]
        for fut in cf.as_completed(futures):
            tid, err = fut.result()
            with lock:
                (failed.append((tid, err)) if err else ok.append(tid))
                done += 1
                if progress:
                    progress(done, len(ids))
    return ok, failed


# ---------------------------------------------------------------- clean

def confirm(question):
    """Ask before a mutation. Non-interactive callers must pass --apply instead."""
    if not sys.stdin.isatty():
        print(f"\nnot a terminal; re-run with --apply to {question}")
        return False
    try:
        return input(f"\n{question}? [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def cmd_clean(args):
    items = build_items(get_notifications())
    stamps = {i.ref: i.updated for i in items if i.ref}
    detail = fetch_prs([i.ref for i in items if i.ref], stamps)

    plan = [(i, w) for i in items for w in [clean_reason(i, detail.get(i.ref))] if w]
    if not plan:
        print("nothing to clean")
        return
    print(f"{'marking done' if args.apply else 'would mark done'}: {len(plan)}\n")
    for i, why in plan:
        print(f"   [{why:<8}] {i.repo}  {i.title[:64]}")
    if not args.apply and not confirm(f"mark these {len(plan)} done"):
        print("left alone")
        return

    # The plan may have been built from cached PR state. Marking done cannot be
    # undone from here, so re-read the affected PRs straight from the API.
    fresh = fetch_prs([i.ref for i, _ in plan if i.ref])
    keep, dropped = [], []
    for i, why in plan:
        if i.ref and not clean_reason(i, fresh.get(i.ref)):
            dropped.append((i, (fresh.get(i.ref) or {}).get("state", "open").lower()))
        else:
            keep.append((i, why))
    if dropped:
        print(f"\nskipping {len(dropped)} that changed since the plan:")
        for i, st in dropped:
            print(f"   [{st:<8}] {i.title[:64]}")
    if not keep:
        print("\nnothing left to mark done")
        return

    ok, failed = act_on_threads([i.thread_id for i, _ in keep], "done")
    print(f"\nmarked done: {len(ok)}/{len(keep)}")
    for tid, err in failed:
        print(f"   thread {tid}: {err}", file=sys.stderr)

    done = set(ok)
    log_records([decision(i, fresh.get(i.ref), "done", "clean-cmd",
                          i.thread_id in done, len(keep))
                 for i, _ in keep])


def cmd_tui(args):
    try:
        import gh_triage_tui
    except ModuleNotFoundError:
        sys.exit("the TUI needs textual, which this interpreter lacks.\n"
                 f"Install it ({sys.executable} -m pip install textual), run the\n"
                 "`gh-triage` launcher instead of this file directly, or use\n"
                 "`gh-triage clean`, which needs no dependencies.")
    gh_triage_tui.run()


def main():
    ap = argparse.ArgumentParser(prog="gh-triage", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    c = sub.add_parser("clean", help="mark done drafts, abandoned PRs, non-PR notifications")
    c.add_argument("--apply", action="store_true")
    c.set_defaults(func=cmd_clean)

    args = ap.parse_args()
    (getattr(args, "func", None) or cmd_tui)(args)


if __name__ == "__main__":
    main()
