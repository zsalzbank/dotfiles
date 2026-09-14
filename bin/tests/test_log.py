"""The action log: one record per PR, with provenance and outcome."""
import json

from conftest import FakeItem

from gh_triage import decision, log_records
from gh_triage_tui import session_record


def read(log_path):
    return [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]


def test_one_record_per_pr(items, log_path):
    log_records([decision(i, None, "done", "checked", True, len(items)) for i in items])
    rows = read(log_path)
    assert len(rows) == len(items)
    assert {r["number"] for r in rows} == {i.number for i in items}


def test_provenance_is_preserved(items, log_path):
    log_records([
        decision(items[0], None, "done", "checked", True, 2),
        decision(items[1], None, "done", "all-shown", True, 2),
    ])
    assert [r["via"] for r in read(log_path)] == ["checked", "all-shown"]


def test_failures_are_recorded_as_not_ok(items, log_path):
    log_records([decision(items[0], None, "unsub", "checked", False, 1)])
    assert read(log_path)[0]["ok"] is False


def test_pr_state_is_captured(items, log_path):
    pr = {"state": "MERGED", "isDraft": False, "author": {"login": "someone"}}
    log_records([decision(items[0], pr, "done", "cursor", True, 1)])
    row = read(log_path)[0]
    assert row["pr_state"] == "MERGED"
    assert row["draft"] is False


def test_author_falls_back_to_the_pr_when_the_item_lacks_one(items, log_path):
    bare = FakeItem(author="", number=9)
    log_records([decision(bare, {"author": {"login": "from-pr"}},
                          "done", "cursor", True, 1)])
    assert read(log_path)[0]["author"] == "from-pr"


def test_the_query_is_stored_with_the_decision(items, log_path):
    log_records([decision(items[0], None, "done", "checked", True, 1, "auth")])
    assert read(log_path)[0]["query"] == "auth"


def test_every_field_training_needs_is_present(items, log_path):
    log_records([decision(items[0], None, "open", "checked", True, 1)])
    row = read(log_path)[0]
    for field in ("at", "action", "via", "ok", "batch", "query", "thread", "repo",
                  "number", "title", "author", "reason", "type", "updated",
                  "pr_state", "draft", "cleanable"):
        assert field in row, field


def test_a_logging_failure_does_not_raise(items, monkeypatch):
    """An unwritable log must never take an action down with it."""
    import gh_triage
    monkeypatch.setattr(gh_triage, "LOG",
                        gh_triage.Path("/proc/nonexistent/actions.jsonl"))
    log_records([decision(items[0], None, "done", "checked", True, 1)])


def test_empty_records_write_nothing(log_path):
    log_records([])
    assert not log_path.exists()


def test_session_record_partitions_the_inbox(items):
    acted = {items[0].thread_id, items[2].thread_id}
    r = session_record(items, acted, ["auth"], [items[1].thread_id])
    assert r["action"] == "session"
    assert r["inbox"] == len(items)
    assert len(r["acted"]) + len(r["left"]) == len(items)
    assert not set(r["acted"]) & set(r["left"])
    assert r["searches"] == ["auth"]
    assert r["rejected"] == [items[1].thread_id]
