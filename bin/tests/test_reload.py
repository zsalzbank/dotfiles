"""`r` pulls a fresh inbox without losing the selection you were building."""
import os

import pytest
from conftest import FakeItem
from textual.widgets import DataTable, Input

import gh_triage
import gh_triage_tui
from gh_triage_tui import Triage

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("GITHUB_NOTIFICATIONS_PAT"),
                       reason="needs a classic PAT with the notifications scope"),
]

SIZE = (150, 30)


@pytest.fixture(scope="module")
def inbox():
    return gh_triage.build_items(gh_triage.get_notifications())


def stub_fetch(monkeypatch, items):
    """Make the next reload return exactly `items`."""
    monkeypatch.setattr(gh_triage_tui, "get_notifications", lambda: [])
    monkeypatch.setattr(gh_triage_tui, "build_items", lambda _: items)


async def wait_idle(app, pilot, timeout=30):
    for _ in range(int(timeout / 0.05)):
        if not app.busy:
            return
        await pilot.pause(0.05)
    raise AssertionError("reload never finished")


async def test_reload_swaps_in_the_new_list(inbox, monkeypatch):
    app = Triage(inbox)
    async with app.run_test(size=SIZE) as pilot:
        table = app.query_one(DataTable)
        table.focus()
        replacement = [FakeItem(number=n, title=f"new {n}") for n in (1, 2, 3)]
        stub_fetch(monkeypatch, replacement)

        await pilot.press("r")
        await wait_idle(app, pilot)
        await pilot.pause(0.2)
        assert len(app.items) == 3
        assert table.row_count == 3


async def test_a_check_survives_a_reload_when_the_thread_is_still_there(
    inbox, monkeypatch
):
    """Reloading mid-triage is for picking up new arrivals, not starting over."""
    app = Triage(inbox)
    async with app.run_test(size=SIZE) as pilot:
        app.query_one(DataTable).focus()
        await pilot.press("space")
        kept = next(iter(app.selected))

        # the same inbox comes back, plus one new arrival
        stub_fetch(monkeypatch, [*inbox, FakeItem(number=999, title="brand new")])
        await pilot.press("r")
        await wait_idle(app, pilot)
        await pilot.pause(0.2)
        assert kept in app.selected
        assert app.origin[kept] == "checked"


async def test_a_check_is_dropped_when_the_thread_is_gone(inbox, monkeypatch):
    app = Triage(inbox)
    async with app.run_test(size=SIZE) as pilot:
        app.query_one(DataTable).focus()
        await pilot.press("space")
        doomed = next(iter(app.selected))

        # that thread is no longer in the inbox
        stub_fetch(monkeypatch, [i for i in inbox if i.thread_id != doomed])
        await pilot.press("r")
        await wait_idle(app, pilot)
        await pilot.pause(0.2)
        assert doomed not in app.selected
        assert doomed not in app.origin


async def test_reload_keeps_the_active_filter(inbox, monkeypatch):
    app = Triage(inbox)
    async with app.run_test(size=SIZE) as pilot:
        app.query_one(Input).value = "feat"
        await pilot.pause(0.3)
        stub_fetch(monkeypatch, [FakeItem(number=1, title="feat(x): yes"),
                                 FakeItem(number=2, title="fix(y): no")])
        await pilot.press("r")
        await wait_idle(app, pilot)
        await pilot.pause(0.2)
        assert app.query_one(Input).value == "feat"
        assert [i.number for i in app.shown] == [1]


async def test_reload_discards_stale_pr_state(inbox, monkeypatch):
    """A stale map would let `c` and `author:` answer for threads that are gone.

    Asserts the planted entry is absent rather than that the map is empty: the
    re-enrich it triggers may well have repopulated it by the time this runs.
    """
    planted = ("CanalsAI", "canals", 999999)
    app = Triage(inbox)
    async with app.run_test(size=SIZE) as pilot:
        app.enriched = True
        app.pr_state = {planted: {"state": "OPEN"}}
        stub_fetch(monkeypatch, [FakeItem(number=1, title="x")])
        await pilot.press("r")
        await wait_idle(app, pilot)
        await pilot.pause(0.3)
        assert planted not in app.pr_state


async def test_reload_is_refused_while_an_action_is_running(inbox, monkeypatch):
    app = Triage(inbox)
    async with app.run_test(size=SIZE) as pilot:
        called = []
        monkeypatch.setattr(gh_triage_tui, "get_notifications",
                            lambda: called.append(1) or [])
        app.busy = True
        await pilot.press("r")
        await pilot.pause(0.2)
        assert not called


async def test_escape_does_not_claim_to_cancel_a_reload(inbox, monkeypatch):
    """Only a batch action is cancellable; saying otherwise would be a lie."""
    app = Triage(inbox)
    async with app.run_test(size=SIZE) as pilot:
        app.busy = True
        app.cancellable = False
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert not app.cancel.is_set()


async def test_a_failed_reload_clears_busy(inbox, monkeypatch):
    """An API error must not leave the ui wedged with every key refused."""
    def boom():
        raise SystemExit("notifications API 401")

    monkeypatch.setattr(gh_triage_tui, "get_notifications", boom)
    app = Triage(inbox)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("r")
        await wait_idle(app, pilot)
        assert app.busy is False
        assert len(app.items) == len(inbox)
