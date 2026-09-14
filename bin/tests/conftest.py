"""Shared fixtures. The log path is redirected so tests never touch the real one."""
import os
import pathlib
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ["GH_TRIAGE_LOG"] = str(pathlib.Path(tempfile.mkdtemp()) / "actions.jsonl")

import gh_triage  # noqa: E402


class FakeItem:
    """Stands in for a notification without needing the API."""

    def __init__(self, author="", repo="CanalsAI/canals", title="fix(core): thing",
                 number=1, thread_id=None, subject_type="PullRequest",
                 reason="subscribed", updated="2026-09-10T12:00:00Z", status=""):
        self.author, self.repo, self.title, self.status = author, repo, title, status
        self.number, self.subject_type, self.reason = number, subject_type, reason
        self.thread_id = thread_id or f"t{number}"
        self.updated = updated
        self.ref = ("CanalsAI", repo.split("/")[-1], number)

    @property
    def url(self):
        return f"https://github.com/{self.repo}/pull/{self.number}"

    @property
    def age(self):
        return "1d"


@pytest.fixture
def items():
    """A small synthetic inbox: two repos, three authors, one draft."""
    return [
        FakeItem(author="zsalzbank", title="feat(auth): rotate the signing key", number=1),
        FakeItem(author="canals-ai-debugger", title="fix(oe): citation markers", number=2),
        FakeItem(author="felipebedoya02", title="feat(erp): sync customers", number=3),
        FakeItem(author="zsalzbank", repo="CanalsAI/infrastructure",
                 title="feat(guardduty): suppress runc findings", number=4),
        FakeItem(author="canals-ai-debugger", repo="CanalsAI/infrastructure",
                 title="chore(tf): bump provider", number=5),
    ]


@pytest.fixture
def log_path():
    return pathlib.Path(os.environ["GH_TRIAGE_LOG"])


@pytest.fixture(autouse=True)
def clean_log(log_path):
    if log_path.exists():
        log_path.unlink()
    yield
