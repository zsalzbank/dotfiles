"""Driving the TUI headlessly. Needs GITHUB_NOTIFICATIONS_PAT; runs no mutations.

Marked `live` so the fast suite can skip it: `pytest -m "not live"`.
"""
import os

import pytest
from textual.widgets import DataTable, Input, Static

import gh_triage
import gh_triage_tui
from gh_triage_tui import Confirm, Triage

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("GITHUB_NOTIFICATIONS_PAT"),
                       reason="needs a classic PAT with the notifications scope"),
]


@pytest.fixture(scope="module")
def inbox():
    return gh_triage.build_items(gh_triage.get_notifications())


@pytest.fixture
def no_mutations(monkeypatch):
    """Every action succeeds without touching GitHub."""
    calls = []

    def fake(ids, action, progress=None, cancel=None):
        ids = list(ids)
        calls.append((ids, action))
        if progress:
            progress(len(ids), len(ids))
        return ids, []

    monkeypatch.setattr(gh_triage_tui, "act_on_threads", fake)
    return calls


async def settle(pilot, app, timeout=45):
    for _ in range(int(timeout / 0.05)):
        if app.enriched:
            return
        await pilot.pause(0.05)
    raise AssertionError("enrichment never finished")


async def test_every_notification_is_listed(inbox):
    app = Triage(inbox)
    async with app.run_test(size=(150, 40)):
        assert app.query_one(DataTable).row_count == len(inbox)


async def test_search_filters_and_escape_restores(inbox):
    app = Triage(inbox)
    async with app.run_test(size=(150, 40)) as pilot:
        table, search = app.query_one(DataTable), app.query_one(Input)
        await pilot.press("slash")
        for ch in "auth":
            await pilot.press(ch)
        await pilot.pause()
        assert table.row_count < len(inbox)

        await pilot.press("escape")
        await pilot.pause()
        assert search.value == ""
        assert table.row_count == len(inbox)
        assert app.focused is table


async def test_selection_survives_a_filter_change(inbox):
    app = Triage(inbox)
    async with app.run_test(size=(150, 40)) as pilot:
        app.query_one(DataTable).focus()
        await pilot.press("space")
        assert len(app.selected) == 1
        app.query_one(Input).value = "zzz-matches-nothing"
        await pilot.pause()
        assert len(app.selected) == 1


async def test_select_all_then_clear(inbox):
    app = Triage(inbox)
    async with app.run_test(size=(150, 40)) as pilot:
        app.query_one(DataTable).focus()
        await pilot.press("a")
        assert len(app.selected) == len(inbox)
        await pilot.press("x")
        assert not app.selected


async def test_confirm_dialog_appears_and_no_does_nothing(inbox, no_mutations):
    app = Triage(inbox)
    async with app.run_test(size=(150, 40)) as pilot:
        app.query_one(DataTable).focus()
        await pilot.press("space")
        before = len(app.items)
        await pilot.press("d")
        for _ in range(200):
            if isinstance(app.screen, Confirm):
                break
            await pilot.pause(0.02)
        assert isinstance(app.screen, Confirm)

        await pilot.press("n")
        await pilot.pause()
        assert not isinstance(app.screen, Confirm)
        assert len(app.items) == before
        assert not no_mutations


async def test_confirming_acts_and_removes_the_rows(inbox, no_mutations):
    app = Triage(inbox)
    async with app.run_test(size=(150, 40)) as pilot:
        app.query_one(DataTable).focus()
        for _ in range(3):
            await pilot.press("space")
        before = len(app.items)
        await pilot.press("d")
        for _ in range(200):
            if isinstance(app.screen, Confirm):
                break
            await pilot.pause(0.02)
        await pilot.press("y")
        for _ in range(400):
            if no_mutations and not app.busy:
                break
            await pilot.pause(0.02)
        await pilot.pause(0.3)
        assert no_mutations[0][1] == "done"
        assert len(no_mutations[0][0]) == 3
        assert len(app.items) == before - 3


async def test_author_filter_needs_enrichment_and_says_so(inbox):
    app = Triage(inbox)
    async with app.run_test(size=(150, 40)) as pilot:
        status = app.query_one("#status", Static)
        app.query_one(Input).value = "author:debugger"
        await pilot.pause(0.2)
        if not app.enriched:
            assert app.waiting_on_state()
            assert status.has_class("warn")
            assert "needs PR state" in str(status.render())

        await settle(pilot, app)
        assert not app.waiting_on_state()
        assert not status.has_class("warn")


async def test_author_filter_returns_only_that_author(inbox):
    app = Triage(inbox)
    async with app.run_test(size=(150, 40)) as pilot:
        await settle(pilot, app)
        authors = {i.author for i in app.items if i.author}
        if not authors:
            pytest.skip("no authors resolved in the current inbox")
        target = sorted(authors)[0]
        app.query_one(Input).value = f"author:{target.lower()}"
        await pilot.pause(0.3)
        assert app.shown
        assert all(i.author == target for i in app.shown)


async def test_cleanable_key_refuses_before_enrichment(inbox):
    """With a warm cache enrichment can beat the keypress, so assert on the
    state at press time rather than on the check a moment earlier."""
    app = Triage(inbox)
    async with app.run_test(size=(150, 40)) as pilot:
        app.query_one(DataTable).focus()
        was_enriched = app.enriched
        await pilot.press("c")
        await pilot.pause(0.1)
        if not was_enriched and not app.enriched:
            assert not app.selected


async def test_emptying_the_filtered_view_clears_the_search(inbox, no_mutations):
    app = Triage(inbox)
    async with app.run_test(size=(150, 40)) as pilot:
        app.query_one(DataTable).focus()
        app.query_one(Input).value = "auth"
        await pilot.pause(0.25)
        if not app.shown:
            pytest.skip("nothing matches 'auth' in the current inbox")
        await pilot.press("a")
        await pilot.press("d")
        for _ in range(200):
            if isinstance(app.screen, Confirm):
                break
            await pilot.pause(0.02)
        await pilot.press("y")
        for _ in range(400):
            if not app.busy and app.acted:
                break
            await pilot.pause(0.02)
        await pilot.pause(0.4)
        assert app.query_one(Input).value == ""
        assert app.query_one(DataTable).row_count == len(app.shown)


async def test_abandoned_searches_are_still_recorded(inbox):
    app = Triage(inbox)
    async with app.run_test(size=(150, 40)) as pilot:
        app.query_one(Input).value = "auth"
        await pilot.pause(1.0)
        app.query_one(Input).value = "database"
        await pilot.pause(1.0)
        assert "auth" in app.searches
        assert "database" in app.searches


async def test_unchecking_records_a_rejection(inbox):
    app = Triage(inbox)
    async with app.run_test(size=(150, 40)) as pilot:
        app.query_one(DataTable).focus()
        await pilot.press("space")
        await pilot.press("up")
        await pilot.press("space")
        await pilot.pause()
        assert len(app.rejected) == 1
