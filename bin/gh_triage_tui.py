"""The notification list as a searchable, checkable table.

Imported lazily by gh_triage so `clean` keeps working without textual.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Input, Label, Static

from gh_triage import (LOG, act_on_threads, build_items, clean_reason, decision,
                       fetch_prs, get_notifications, log_records, open_urls,
                       pr_author, pr_status)

COLUMNS = ("", "repo", "pr", "age", "author", "status", "title")

# Merged is dimmed because it is the common case and needs no attention; draft
# and closed are what `c` sweeps, so they stand out.
STATUS_STYLE = {
    "open": "green",
    "draft": "yellow",
    "closed": "red",
    "merged": "dim magenta",
    "other": "dim",
}

AUTHOR = "author:"

# Scoped filters, each a substring test against one field.
FIELDS = {
    AUTHOR: lambda i: i.author,
    "repo:": lambda i: i.repo,
    "status:": lambda i: i.status,
}


def matches(item, terms):
    """Plain terms match title, repo and number; `field:x` matches that field.

    Every test is a substring, so `author:debugger` finds canals-ai-debugger and
    `repo:infra` finds CanalsAI/infrastructure without typing either in full. The
    `[bot]` suffix is dropped because GitHub's own notification urls carry it
    (author:canals-ai-debugger[bot]) while the api returns the bare login, so
    pasting a filter from the web ui would otherwise match nothing.
    """
    for t in terms:
        for prefix, field in FIELDS.items():
            if t.startswith(prefix):
                want = t[len(prefix):].removesuffix("[bot]")
                if want and want not in field(item).lower():
                    return False
                break
        else:
            if t not in f"{item.title} {item.repo} {item.number}".lower():
                return False
    return True


class Confirm(ModalScreen[bool]):
    """Blocking yes/no for the two actions that change someone else's view."""

    BINDINGS = [
        Binding("y", "yes", "yes"),
        Binding("n", "no", "no"),
        Binding("escape", "no", "cancel"),
    ]

    def __init__(self, question: str, detail: str) -> None:
        super().__init__()
        self.question = question
        self.detail = detail

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.question, id="question")
            yield Static(self.detail, id="detail")
            with Horizontal(id="buttons"):
                yield Button("yes  (y)", variant="error", id="yes")
                yield Button("no  (n)", variant="primary", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)


class Triage(App):
    CSS = """
    Input { border: none; height: 1; background: $panel; }
    Input:focus { background: $boost; }
    #status { height: 1; color: $text-muted; padding-left: 1; }
    #status.warn { color: $warning; text-style: bold; }
    DataTable { height: 1fr; }
    Confirm { align: center middle; }
    #dialog {
        width: 84; height: auto; padding: 1 2;
        border: thick $error; background: $surface;
    }
    #question { text-style: bold; width: 100%; }
    #detail { color: $text-muted; margin-top: 1; height: auto; max-height: 12; }
    #buttons { margin-top: 1; height: auto; align: center middle; }
    Button { margin: 0 1; }
    """

    BINDINGS = [
        Binding("slash", "search", "search"),
        Binding("space", "toggle", "check"),
        Binding("a", "select_visible", "all shown"),
        Binding("v", "select_on_screen", "on screen"),
        Binding("x", "clear_selection", "none"),
        Binding("c", "select_cleanable", "cleanable"),
        Binding("o", "open", "open"),
        Binding("d", "mark_done", "done"),
        Binding("u", "unsubscribe", "unsub"),
        Binding("r", "reload", "reload"),
        Binding("escape", "escape", "back", show=False),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self, items) -> None:
        super().__init__()
        self.items = items
        self.shown = list(items)
        self.selected: set[str] = set()
        # How each selection was made, which is what separates a deliberate
        # choice from one swept up by select-all when this is read back later.
        self.origin: dict[str, str] = {}
        self.searches: list[str] = []
        self.acted: set[str] = set()
        # Checked and then unchecked: considered, then rejected.
        self.rejected: list[str] = []
        self._last_query = ""
        self._settle = None
        self.loading_note = ""
        self._warned_author = False
        self.pr_state: dict = {}
        self.enriched = False
        self.busy = False
        # A batch action can be stopped part-way; a reload cannot.
        self.cancellable = False
        self.cancel = threading.Event()

    def compose(self) -> ComposeResult:
        yield Input(placeholder="filter by title, or author: / repo: / status: "
                                "-- escape to clear", id="search")
        yield DataTable(cursor_type="row", zebra_stripes=True)
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns(*COLUMNS)
        table.focus()
        self.refresh_rows()
        self.enrich()

    # ---------------------------------------------------------------- render

    def refresh_rows(self, keep_cursor=True) -> None:
        table = self.query_one(DataTable)
        row = table.cursor_row if keep_cursor else 0
        table.clear()
        for item in self.shown:
            status = item.status
            checked = item.thread_id in self.selected
            style = "bold green" if checked else ""
            cells = [Text(str(c), style=style) for c in (
                "x" if checked else " ",
                item.repo.split("/")[-1][:14],
                f"#{item.number}" if item.number else item.subject_type[:7],
                item.age,
                item.author[:18],
            )]
            cells.append(Text(status, style=style or STATUS_STYLE.get(status, "")))
            cells.append(Text(item.title[:96], style=style))
            table.add_row(*cells)
        if table.row_count:
            table.move_cursor(row=min(row, table.row_count - 1))
        self.update_status()

    def waiting_on_state(self) -> bool:
        """An author filter is asking for something only enrichment can answer."""
        return not self.enriched and AUTHOR in self._last_query.lower()

    def update_status(self, message: str | None = None) -> None:
        status = self.query_one("#status", Static)
        if message is None:
            # Acting works on the selection, not the view, so say plainly when
            # some of it is filtered out of sight.
            on_screen = {i.thread_id for i in self.shown} & self.selected
            hidden = len(self.selected) - len(on_screen)
            parts = [f"{len(self.shown)} of {len(self.items)} shown",
                     f"{len(self.selected)} selected"]
            if hidden:
                parts.append(f"{hidden} of them hidden by the filter")
            if not self.enriched:
                parts.append(self.loading_note or "checking PR state...")
            message = "   ".join(parts)
            if self.waiting_on_state():
                message = "author needs PR state, still loading -- " + message
        status.set_class(self.waiting_on_state(), "warn")
        status.update(message)

    # ---------------------------------------------------------------- filter

    def on_input_changed(self, event: Input.Changed) -> None:
        self._last_query = event.value
        self.apply_filter()
        # Record the term once typing stops rather than on every keystroke, so a
        # search abandoned by typing over it is still kept.
        if self._settle is not None:
            self._settle.stop()
        self._settle = self.set_timer(0.8, self.note_search)

    def apply_filter(self) -> None:
        """Re-derive the visible rows from the current query and item list."""
        terms = self._last_query.lower().split()
        self.shown = [i for i in self.items if matches(i, terms)]
        if self.waiting_on_state() and not self._warned_author:
            self._warned_author = True  # once per load, not once per keystroke
            self.notify("author filtering has no data until PR state finishes "
                        "loading, so this will look empty", severity="warning")
        self.refresh_rows(keep_cursor=False)

    def on_input_submitted(self) -> None:
        self.note_search()
        self.query_one(DataTable).focus()

    def note_search(self) -> None:
        """Keep the terms searched for, but only once settled on -- logging every
        keystroke would store 'a', 'au', 'aut' alongside 'auth'.

        Reads the stored term rather than the widget so it also works on the way
        out, once the app has stopped.
        """
        term = (self._last_query or "").strip()
        if term and (not self.searches or self.searches[-1] != term):
            self.searches.append(term)

    def action_search(self) -> None:
        self.query_one(Input).focus()

    def action_escape(self) -> None:
        if self.busy:
            # Only a batch action is cancellable; a reload is one request that
            # will land shortly, so claiming "cancelling" there would be a lie.
            if self.cancellable:
                self.cancel.set()
                self.update_status("cancelling...")
            return
        search = self.query_one(Input)
        if search.value:
            self.note_search()
            search.value = ""  # fires Input.Changed, which unfilters the list
        self.query_one(DataTable).focus()

    # ---------------------------------------------------------------- select

    def current(self):
        table = self.query_one(DataTable)
        return self.shown[table.cursor_row] if 0 <= table.cursor_row < len(self.shown) else None

    def chosen(self):
        """Selected items, or the row under the cursor when nothing is checked."""
        if self.selected:
            return [i for i in self.items if i.thread_id in self.selected]
        item = self.current()
        return [item] if item else []

    def action_toggle(self) -> None:
        item = self.current()
        if not item:
            return
        table = self.query_one(DataTable)
        row = table.cursor_row
        if item.thread_id in self.selected:
            self.selected.discard(item.thread_id)
            if self.origin.pop(item.thread_id, None) == "checked":
                self.rejected.append(item.thread_id)
        else:
            self.selected.add(item.thread_id)
            self.origin[item.thread_id] = "checked"
        self.refresh_rows()
        if row + 1 < table.row_count:
            table.move_cursor(row=row + 1)

    def on_screen_rows(self):
        """The filtered rows actually painted right now, not the whole filter.

        The scrollable region includes the header row, so its height overshoots
        the data rows by exactly that much.
        """
        table = self.query_one(DataTable)
        top = int(table.scroll_y)
        height = table.scrollable_content_region.height - (
            table.header_height if table.show_header else 0)
        return self.shown[top:top + height]

    def action_select_visible(self) -> None:
        for i in self.shown:
            self.selected.add(i.thread_id)
            self.origin.setdefault(i.thread_id, "all-shown")
        self.refresh_rows()

    def action_select_on_screen(self) -> None:
        rows = self.on_screen_rows()
        for i in rows:
            self.selected.add(i.thread_id)
            self.origin.setdefault(i.thread_id, "on-screen")
        self.refresh_rows()
        self.notify(f"selected the {len(rows)} rows on screen")

    def action_clear_selection(self) -> None:
        self.selected.clear()
        self.origin.clear()
        self.refresh_rows()

    def action_select_cleanable(self) -> None:
        if not self.enriched:
            self.notify("PR state is still loading, so nothing is known to be "
                        "cleanable yet", severity="warning")
            return
        hits = [i for i in self.shown if clean_reason(i, self.pr_state.get(i.ref))]
        if not hits:
            self.notify("nothing cleanable in the current view")
            return
        for i in hits:
            self.selected.add(i.thread_id)
            self.origin.setdefault(i.thread_id, "cleanable")
        self.refresh_rows()

    # ---------------------------------------------------------------- reload

    def action_reload(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.update_status("reloading the inbox...")
        self.reload()

    @work(thread=True)
    def reload(self) -> None:
        try:
            items = build_items(get_notifications())
        except SystemExit as e:  # get_notifications exits on an API error
            self.call_from_thread(self._reload_failed, str(e))
            return
        self.call_from_thread(self._reloaded, items)

    def _reload_failed(self, message) -> None:
        self.busy = False
        self.update_status()
        self.notify(f"reload failed: {message[:80]}", severity="error")

    def _reloaded(self, items) -> None:
        """Swap in a fresh inbox, keeping checks on threads that are still here.

        Dropping the selection would be safer to write but wrong to use: the
        reason to reload mid-triage is to pull in new arrivals, and losing a
        half-built selection to do that is worse than carrying it across.
        Anything that left the inbox is no longer selectable, so its check and
        its origin go with it.
        """
        gone = {i.thread_id for i in self.items} - {i.thread_id for i in items}
        fresh = {i.thread_id for i in items} - {i.thread_id for i in self.items}
        self.busy = False
        self.items = items
        self.selected -= gone
        for tid in gone:
            self.origin.pop(tid, None)
        # Re-enrich from scratch: the new items have no PR state, and a stale
        # `enriched` flag would let `c` and `author:` answer from a stale map.
        self.pr_state = {}
        self.enriched = False
        self._warned_author = False
        self.apply_filter()
        self.enrich()
        note = f"reloaded: {len(items)} unread"
        if fresh:
            note += f", {len(fresh)} new"
        if gone:
            note += f", {len(gone)} gone"
        self.notify(note)

    # ---------------------------------------------------------------- enrich

    @work(thread=True, exclusive=True)
    def enrich(self) -> None:
        refs = [i.ref for i in self.items if i.ref]
        stamps = {i.ref: i.updated for i in self.items if i.ref}
        state = fetch_prs(refs, stamps,
                          progress=lambda n, tot: self.call_from_thread(
                              self._loading, f"checking PR state {n}/{tot}"))
        self.call_from_thread(self._enriched, state)

    def _loading(self, note) -> None:
        # Held rather than written straight to the status line, which any table
        # refresh would otherwise overwrite.
        self.loading_note = note
        self.update_status()

    def _enriched(self, state) -> None:
        self.loading_note = ""
        self.pr_state = state
        self.enriched = True
        for i in self.items:
            i.author = pr_author(state.get(i.ref))
            i.status = pr_status(i, state.get(i.ref))
        self.refresh_rows()
        missing = len([i for i in self.items if i.ref]) - len(state)
        if missing:
            self.notify(f"no PR state for {missing}; 'c' will under-select",
                        severity="warning")

    # ---------------------------------------------------------------- act

    def action_open(self) -> None:
        items = [i for i in self.chosen() if i.url]
        if not items:
            self.notify("nothing to open")
            return
        # Opening is the strongest positive signal here: it is the one action
        # that says this was worth reading rather than worth clearing.
        self.record(items, "open", True, self.query_one(Input).value)
        if open_urls(items):
            self.notify(f"opened {len(items)} in your browser")
            return
        # Not in a pod, or the cli failed: print them rather than claim a tab.
        with self.suspend():
            print()
            for i in items:
                print(i.url)
            print(f"\n{len(items)} urls")
            try:
                input("enter to go back ")
            except (EOFError, KeyboardInterrupt):
                pass

    def action_mark_done(self) -> None:
        self.act("done", "Mark done", "clears them from the inbox; "
                 "a new comment brings them back")

    def action_unsubscribe(self) -> None:
        self.act("unsub", "Unsubscribe", "clears them and stops them pinging you "
                 "for good, even on new comments; reversing it means finding the "
                 "PR by hand")

    # A worker, because push_screen_wait refuses to block outside one.
    @work(exclusive=True)
    async def act(self, action, verb, consequence) -> None:
        if self.busy:
            return
        items = self.chosen()
        if not items:
            self.notify("nothing selected")
            return
        preview = "\n".join(f"  {i.repo.split('/')[-1]} #{i.number}  {i.title[:56]}"
                            for i in items[:10])
        if len(items) > 10:
            preview += f"\n  ... and {len(items) - 10} more"
        ok = await self.push_screen_wait(Confirm(
            f"{verb} {len(items)} notification{'s' if len(items) != 1 else ''}?",
            f"{consequence}\n\n{preview}"))
        if ok:
            # Read the filter here: apply runs on a thread and must not touch widgets.
            self.apply(action, items, verb, self.query_one(Input).value)

    def record(self, items, action, ok, query="") -> None:
        succeeded = ok if isinstance(ok, (set, frozenset)) else None
        log_records([
            decision(i, self.pr_state.get(i.ref), action,
                     self.origin.get(i.thread_id, "cursor"),
                     i.thread_id in succeeded if succeeded is not None else bool(ok),
                     len(items), query)
            for i in items
        ])
        self.acted.update(i.thread_id for i in items)

    @work(thread=True)
    def apply(self, action, items, verb, query="") -> None:
        self.busy = True
        self.cancellable = True
        self.cancel.clear()
        ids = [i.thread_id for i in items]
        done, failed = act_on_threads(
            ids, action, cancel=self.cancel,
            progress=lambda n, tot: self.call_from_thread(
                self.update_status, f"{verb.lower()} {n}/{tot}   escape to stop"))
        self.record(items, action, set(done), query)
        self.call_from_thread(self._applied, set(done), failed, verb)

    def _applied(self, done, failed, verb) -> None:
        self.busy = False
        self.cancellable = False
        self.items = [i for i in self.items if i.thread_id not in done]
        self.shown = [i for i in self.shown if i.thread_id not in done]
        self.selected -= done
        if self._last_query and not self.shown:
            # Nothing the filter matched survived, so drop it instead of leaving
            # an empty table behind a search that can no longer match anything.
            self.note_search()
            self.query_one(Input).value = ""  # fires Input.Changed, which refreshes
        else:
            # To the first surviving row rather than the old index, which after a
            # removal points at whatever shifted up into it. Clearing a whole
            # screenful would otherwise leave the cursor mid-list on a row that
            # was never looked at; the list is oldest-first, so the top is the
            # next thing to work through. A row that failed stays put and lands
            # under the cursor, which is where the attention belongs.
            self.refresh_rows(keep_cursor=False)
        note = f"{verb.lower()}: {len(done)}"
        if failed:
            reasons = {err for _, err in failed}
            note += f"   failed: {len(failed)} ({', '.join(sorted(reasons))})"
        self.notify(note, severity="warning" if failed else "information")


def session_record(items, acted, searches, rejected=()):
    """One record per session, so what was left alone is recoverable too.
    Without it the log holds only actions, which is all positives, no negatives."""
    return {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "action": "session",
        "inbox": len(items),
        "searches": list(searches),
        "acted": sorted(acted),
        "rejected": list(rejected),
        "left": sorted({i.thread_id for i in items} - set(acted)),
    }


def run() -> None:
    print("loading notifications...", flush=True)
    items = build_items(get_notifications())
    if not items:
        print("inbox is empty")
        return
    app = Triage(items)
    app.run()
    app.note_search()  # a term still in the box when you quit was never settled
    log_records([session_record(items, app.acted, app.searches, app.rejected)])
    print(f"{len(app.acted)} acted on, logged to {LOG}")
