"""After an action the cursor goes to the first remaining row, not a stale index."""
import os

import pytest
from textual.widgets import DataTable, Input

import gh_triage
import gh_triage_tui
from gh_triage_tui import Confirm, Triage

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("GITHUB_NOTIFICATIONS_PAT"),
                       reason="needs a classic PAT with the notifications scope"),
]

SIZE = (150, 30)


@pytest.fixture(scope="module")
def inbox():
    return gh_triage.build_items(gh_triage.get_notifications())


@pytest.fixture
def succeed(monkeypatch):
    monkeypatch.setattr(
        gh_triage_tui, "act_on_threads",
        lambda ids, action, progress=None, cancel=None: (list(ids), []))


@pytest.fixture
def fail_all(monkeypatch):
    monkeypatch.setattr(
        gh_triage_tui, "act_on_threads",
        lambda ids, action, progress=None, cancel=None:
        ([], [(i, "HTTP 403") for i in ids]))


async def run_action(app, pilot, key="u"):
    await pilot.press(key)
    for _ in range(300):
        if isinstance(app.screen, Confirm):
            break
        await pilot.pause(0.02)
    await pilot.press("y")
    for _ in range(400):
        if not app.busy and app.acted:
            break
        await pilot.pause(0.02)
    await pilot.pause(0.3)


async def test_cursor_returns_to_the_top_after_clearing_a_screenful(inbox, succeed):
    """`v` then `u` is the case that stranded the cursor mid-list."""
    app = Triage(inbox)
    async with app.run_test(size=SIZE) as pilot:
        table = app.query_one(DataTable)
        table.focus()
        await pilot.press("pagedown")
        await pilot.pause(0.2)
        await pilot.press("v")
        await pilot.pause(0.2)
        assert app.selected

        await run_action(app, pilot)
        assert table.cursor_row == 0
        assert int(table.scroll_y) == 0


async def test_cursor_lands_on_the_first_surviving_item(inbox, succeed):
    if len(inbox) < 2:
        pytest.skip("need at least one row to survive the action")
    app = Triage(inbox)
    async with app.run_test(size=SIZE) as pilot:
        table = app.query_one(DataTable)
        table.focus()
        # Check every row but the last, so exactly one survives and the cursor
        # has somewhere unambiguous to land.
        take = len(inbox) - 1
        for _ in range(take):
            await pilot.press("space")
        expected = app.shown[take].thread_id

        await run_action(app, pilot)
        assert app.shown[table.cursor_row].thread_id == expected
        assert table.cursor_row == 0


async def test_a_failed_action_leaves_the_row_under_the_cursor(inbox, fail_all):
    """Nothing was removed, so the top is the failed row: where attention belongs."""
    app = Triage(inbox)
    async with app.run_test(size=SIZE) as pilot:
        table = app.query_one(DataTable)
        table.focus()
        await pilot.press("space")
        target = app.shown[0].thread_id
        before = len(app.items)

        await run_action(app, pilot)
        assert len(app.items) == before
        assert app.shown[table.cursor_row].thread_id == target


async def test_cursor_is_valid_when_the_filter_empties_and_clears(inbox, succeed):
    app = Triage(inbox)
    async with app.run_test(size=SIZE) as pilot:
        table = app.query_one(DataTable)
        table.focus()
        app.query_one(Input).value = "auth"
        await pilot.pause(0.3)
        if not app.shown:
            pytest.skip("nothing matches 'auth' in the current inbox")
        await pilot.press("a")
        await pilot.pause(0.1)

        await run_action(app, pilot)
        assert app.query_one(Input).value == ""
        assert 0 <= table.cursor_row < table.row_count
