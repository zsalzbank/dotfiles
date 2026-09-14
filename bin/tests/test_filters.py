"""Search filters: plain terms, author:, repo:, and how they combine."""
from conftest import FakeItem

from gh_triage_tui import matches

BOT = FakeItem(author="canals-ai-debugger")
INFRA = FakeItem(repo="CanalsAI/infrastructure", author="zsalzbank")


def test_author_matches_a_substring():
    assert matches(BOT, ["author:debug"])
    assert matches(BOT, ["author:ai-deb"])
    assert matches(BOT, ["author:canals-ai-debugger"])


def test_author_accepts_the_bot_suffix_from_a_github_url():
    assert matches(BOT, ["author:canals-ai-debugger[bot]"])


def test_author_excludes_a_different_login():
    assert not matches(BOT, ["author:zsalz"])


def test_repo_matches_a_substring():
    assert matches(INFRA, ["repo:infra"])
    assert matches(INFRA, ["repo:canalsai/infra"])
    assert matches(INFRA, ["repo:canalsai/infrastructure"])


def test_repo_excludes_a_different_repo():
    assert not matches(INFRA, ["repo:canals/canals"])
    assert not matches(BOT, ["repo:infra"])


def test_scoped_terms_and_together():
    assert matches(INFRA, ["repo:infra", "author:zsalz"])
    assert not matches(INFRA, ["repo:infra", "author:debugger"])


def test_scoped_term_combines_with_a_plain_term():
    assert matches(INFRA, ["repo:infra", "core"])
    assert not matches(INFRA, ["repo:infra", "nonsense"])


def test_a_bare_prefix_filters_nothing_out():
    """Typing `repo:` mid-word should not blank the list before the value lands."""
    assert matches(INFRA, ["repo:"])
    assert matches(INFRA, ["author:"])


def test_plain_terms_still_search_title_repo_and_number():
    assert matches(INFRA, ["infrastructure"])
    assert matches(INFRA, ["core"])
    assert matches(INFRA, ["1"])
    assert matches(FakeItem(title="feat(guardduty): suppress"), ["guardduty"])


def test_matching_is_case_insensitive_on_the_field_side():
    assert matches(FakeItem(author="ZSalzbank"), ["author:zsalz"])
    assert matches(FakeItem(repo="CanalsAI/Canals"), ["repo:canals"])
