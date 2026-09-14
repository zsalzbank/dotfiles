"""The status column, and its agreement with what `clean` sweeps."""
from conftest import FakeItem

from gh_triage import CLEANABLE, clean_reason, pr_status
from gh_triage_tui import STATUS_STYLE, matches

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
