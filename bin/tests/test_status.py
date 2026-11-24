"""The status column, and its agreement with what `clean` sweeps."""
from conftest import FakeItem
from textual.widgets import Input, TextArea

import gh_triage
from gh_triage import CLEANABLE, clean_reason, pr_status, set_clean_searches
from gh_triage_tui import STATUS_STYLE, CleanSearches, Confirm, Triage, matches

PR = FakeItem(number=1)
CHECK = FakeItem(number=2, subject_type="CheckSuite")
CHECK.ref = None


def test_open_pr():
    assert pr_status(PR, {"state": "OPEN", "isDraft": False}) == "open"


def test_merged_pr():
    assert pr_status(PR, {"state": "MERGED", "isDraft": False}) == "merged"


def test_closed_means_closed_without_merging():
    assert pr_status(PR, {"state": "CLOSED", "isDraft": False}) == "closed"


def test_draft_wins_over_state():
    """A draft is open, but draft is the more useful label."""
    assert pr_status(PR, {"state": "OPEN", "isDraft": True}) == "draft"


def test_non_pr_subjects_are_other():
    assert pr_status(CHECK, None) == "other"
    assert pr_status(CHECK, {"state": "OPEN"}) == "other"


def test_unenriched_pr_has_no_status_yet():
    assert pr_status(PR, None) == ""


def test_an_unknown_state_is_passed_through_lowercased():
    assert pr_status(PR, {"state": "SOMETHING_NEW"}) == "something_new"


def test_every_status_has_a_style():
    for status in ("open", "draft", "closed", "merged", "other"):
        assert status in STATUS_STYLE


def test_clean_sweeps_exactly_draft_closed_and_other():
    assert clean_reason(PR, {"state": "OPEN", "isDraft": True}) == "draft"
    assert clean_reason(PR, {"state": "CLOSED", "isDraft": False}) == "closed"
    assert clean_reason(CHECK, None) == "CheckSuite"


def test_clean_leaves_merged_and_open_alone():
    """Merged work landed, so it stays; open work is live."""
    assert clean_reason(PR, {"state": "MERGED", "isDraft": False}) is None
    assert clean_reason(PR, {"state": "OPEN", "isDraft": False}) is None


def test_clean_leaves_an_unenriched_pr_alone():
    assert clean_reason(PR, None) is None


def test_a_saved_search_makes_merged_and_open_prs_cleanable():
    set_clean_searches("bump provider")
    bump = FakeItem(number=5, title="chore(tf): Bump Provider")
    assert clean_reason(bump, {"state": "MERGED", "isDraft": False}) == "search"
    assert clean_reason(bump, {"state": "OPEN", "isDraft": False}) == "search"
    assert clean_reason(bump, None) == "search"


def test_a_saved_search_leaves_other_prs_alone():
    set_clean_searches("bump provider")
    assert clean_reason(PR, {"state": "OPEN", "isDraft": False}) is None


def test_saved_searches_survive_a_restart_without_blanks_or_repeats(tmp_path):
    set_clean_searches("  one \n\n two\none\nONE\n")
    assert gh_triage.CLEAN_SEARCHES.read_text() == "one\ntwo\n"
    assert gh_triage._load_clean_searches() == ["one", "two"]


async def test_the_dialog_saves_one_search_per_line(monkeypatch):
    monkeypatch.setattr(Triage, "enrich", lambda self: None)
    app = Triage([FakeItem(number=1, title="bump a"), FakeItem(number=2, title="real")])
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("s")
        app.screen.query_one(TextArea).text = "bump\n\nother"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert gh_triage.CLEAN_TERMS == ["bump", "other"]
        assert not isinstance(app.screen, CleanSearches)


def test_cleanable_set_matches_the_status_vocabulary():
    assert CLEANABLE <= set(STATUS_STYLE)
    assert "merged" not in CLEANABLE
    assert "open" not in CLEANABLE


def test_status_is_filterable():
    merged = FakeItem(number=3)
    merged.status = "merged"
    assert matches(merged, ["status:merged"])
    assert matches(merged, ["status:merg"])
    assert not matches(merged, ["status:open"])


def test_status_filter_combines_with_author():
    item = FakeItem(author="canals-ai-debugger", number=4)
    item.status = "draft"
    assert matches(item, ["status:draft", "author:debugger"])
    assert not matches(item, ["status:merged", "author:debugger"])


async def test_ctrl_s_saves_the_active_search_only_after_confirming(monkeypatch):
    monkeypatch.setattr(Triage, "enrich", lambda self: None)
    app = Triage([FakeItem(number=1, title="bump a")])
    async with app.run_test(size=(120, 40)) as pilot:
        app.query_one(Input).value = "Bump"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, Confirm)
        assert gh_triage.CLEAN_TERMS == []
        await pilot.press("y")
        await pilot.pause()
        assert gh_triage.CLEAN_TERMS == ["Bump"]


async def test_ctrl_s_declined_or_already_saved_or_scoped_saves_nothing(monkeypatch):
    monkeypatch.setattr(Triage, "enrich", lambda self: None)
    set_clean_searches("bump")
    app = Triage([FakeItem(number=1, title="bump a")])
    async with app.run_test(size=(120, 40)) as pilot:
        app.query_one(Input).value = "other"
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        for query in ("BUMP", "author:foo"):
            app.query_one(Input).value = query
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert not isinstance(app.screen, Confirm)
        assert gh_triage.CLEAN_TERMS == ["bump"]
