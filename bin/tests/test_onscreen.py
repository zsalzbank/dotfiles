"""`v` selects the rows painted on screen, unlike `a` which takes the whole filter."""
import os
import re

import pytest
from textual.widgets import DataTable, Input

import gh_triage
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


def visible_window(app):
    """The rows on screen, derived from the table's own scroll geometry.

    Independent of `on_screen_rows` only in that it is written here from the
    widget's public attributes; the point of the assertion is that the two
    agree, and that the height accounts for the header row.
    """
    table = app.query_one(DataTable)
    top = int(table.scroll_y)
    header = table.header_height if table.show_header else 0
    height = table.scrollable_content_region.height - header
    return app.shown[top:top + height]


async def test_v_matches_the_visible_window(inbox):
    app = Triage(inbox)
    async with app.run_test(size=SIZE) as pilot:
        app.query_one(DataTable).focus()
        await pilot.pause(0.2)
        expected = {i.thread_id for i in visible_window(app)}
        await pilot.press("v")
        await pilot.pause(0.2)
        assert {i.thread_id for i in app.chosen()} == expected


async def test_v_tracks_scrolling(inbox):
    app = Triage(inbox)
    async with app.run_test(size=SIZE) as pilot:
        table = app.query_one(DataTable)
        table.focus()
        await pilot.press("pagedown")
        await pilot.pause(0.3)
        if int(table.scroll_y) == 0:
            pytest.skip("inbox is shorter than one screen, nothing to scroll")
        second_page = {i.thread_id for i in visible_window(app)}
        await pilot.press("v")
        await pilot.pause(0.2)
        assert {i.thread_id for i in app.chosen()} == second_page
        # a window, not the whole list
        assert len(app.selected) < len(inbox)
        # and not the first page either
        assert app.shown[0].thread_id not in second_page


async def test_v_selects_no_more_than_a(inbox):
    app = Triage(inbox)
    async with app.run_test(size=SIZE) as pilot:
        table = app.query_one(DataTable)
        table.focus()
        await pilot.press("v")
        await pilot.pause(0.2)
        on_screen = len(app.selected)
        await pilot.press("x")
        await pilot.press("a")
        await pilot.pause(0.2)
        # Equal when the whole inbox fits on one screen, fewer when it doesn't.
        assert on_screen <= len(app.selected) == len(inbox)


async def test_v_respects_the_active_filter(inbox):
    app = Triage(inbox)
    async with app.run_test(size=SIZE) as pilot:
        app.query_one(Input).value = "feat"
        await pilot.pause(0.3)
        app.query_one(DataTable).focus()
        await pilot.press("v")
        await pilot.pause(0.2)
        assert app.selected
        assert all(i in app.shown for i in app.chosen())


async def test_v_records_its_own_provenance(inbox):
    """Training data has to tell a screenful apart from a deliberate check."""
    app = Triage(inbox)
    async with app.run_test(size=SIZE) as pilot:
        app.query_one(DataTable).focus()
        await pilot.press("v")
        await pilot.pause(0.2)
        assert set(app.origin.values()) == {"on-screen"}


async def test_a_deliberate_check_is_not_overwritten_by_v(inbox):
    app = Triage(inbox)
    async with app.run_test(size=SIZE) as pilot:
        table = app.query_one(DataTable)
        table.focus()
        await pilot.press("space")          # row 0, checked by hand
        first = app.shown[0].thread_id
        await pilot.press("v")
        await pilot.pause(0.2)
        assert app.origin[first] == "checked"


async def test_v_on_a_short_list_takes_everything(inbox):
    app = Triage(inbox)
    async with app.run_test(size=SIZE) as pilot:
        app.query_one(Input).value = "author:nonexistent-person-xyz"
        await pilot.pause(0.3)
        app.query_one(DataTable).focus()
        await pilot.press("v")
        await pilot.pause(0.2)
        assert len(app.selected) == len(app.shown)
