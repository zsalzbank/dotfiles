"""`o` opens the selected PRs with the platform opener."""
import subprocess

import pytest
from conftest import FakeItem

import gh_triage


@pytest.fixture
def items():
    return [FakeItem(number=1, title="fix(core): a thing"),
            FakeItem(number=2, title="feat(oe): another")]


@pytest.fixture
def calls(monkeypatch):
    """Capture argv instead of running anything."""
    seen = []
    monkeypatch.setattr(
        gh_triage.subprocess, "run",
        lambda *a, **k: seen.append(a[0]) or
        subprocess.CompletedProcess(a[0], 0, "ok", ""))
    return seen


@pytest.fixture
def on_laptop(monkeypatch):
    monkeypatch.delenv("DEVSPACES_WORKSPACE_ID", raising=False)
    monkeypatch.setattr(gh_triage.sys, "platform", "darwin")
    monkeypatch.setattr(gh_triage.shutil, "which", lambda _: "/usr/bin/open")


def test_opens_one_tab_per_url(items, on_laptop, calls):
    assert gh_triage.open_urls(items) is True
    assert [c[-1] for c in calls] == [i.url for i in items]
    assert all(c[0] == "open" for c in calls)


def test_uses_xdg_open_on_linux(items, monkeypatch, calls):
    monkeypatch.delenv("DEVSPACES_WORKSPACE_ID", raising=False)
    monkeypatch.setattr(gh_triage.sys, "platform", "linux")
    monkeypatch.setattr(gh_triage.shutil, "which", lambda _: "/usr/bin/xdg-open")
    assert gh_triage.open_urls(items) is True
    assert all(c[0] == "xdg-open" for c in calls)


def test_refuses_inside_a_pod(items, monkeypatch, calls):
    """A pod's `open` is the oauth shim: it swallows the url and exits 0, so
    using it would silently open nothing. Printing is the honest fallback."""
    monkeypatch.setenv("DEVSPACES_WORKSPACE_ID", "ws-1")
    monkeypatch.setattr(gh_triage.sys, "platform", "linux")
    monkeypatch.setattr(gh_triage.shutil, "which", lambda _: "/usr/bin/xdg-open")
    assert gh_triage.local_opener() is None
    assert gh_triage.open_urls(items) is False
    assert not calls


def test_reports_false_with_no_opener(items, monkeypatch):
    monkeypatch.delenv("DEVSPACES_WORKSPACE_ID", raising=False)
    monkeypatch.setattr(gh_triage.sys, "platform", "linux")
    monkeypatch.setattr(gh_triage.shutil, "which", lambda _: None)
    assert gh_triage.open_urls(items) is False


def test_a_failure_does_not_raise(items, on_laptop, monkeypatch):
    def boom(*a, **k):
        raise OSError("no opener")

    monkeypatch.setattr(gh_triage.subprocess, "run", boom)
    assert gh_triage.open_urls(items) is False


def test_a_timeout_does_not_raise(items, on_laptop, monkeypatch):
    def slow(*a, **k):
        raise subprocess.TimeoutExpired("open", 20)

    monkeypatch.setattr(gh_triage.subprocess, "run", slow)
    assert gh_triage.open_urls(items) is False


def test_windows_passes_the_empty_title_argument(items, monkeypatch, calls):
    """`start` reads its first quoted arg as a window title, so a url alone
    would be taken as the title and never opened."""
    monkeypatch.delenv("DEVSPACES_WORKSPACE_ID", raising=False)
    monkeypatch.setattr(gh_triage.sys, "platform", "win32")
    gh_triage.open_urls(items[:1])
    assert calls[0] == ["cmd", "/c", "start", "", items[0].url]
