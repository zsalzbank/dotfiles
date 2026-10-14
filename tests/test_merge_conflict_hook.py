import json
import runpy
import subprocess
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

HOOK = Path(__file__).resolve().parents[1] / "hooks/pr-status-changed/merge-conflict.py"


class MergeConflictHookTests(unittest.TestCase):
    def run_hook(self, metadata=None, failure=None, conflict=True, episode=True):
        payload = {"current": {"state": "open", "conflict": conflict}}
        hooklib = ModuleType("hooklib")
        hooklib.load_payload = lambda: payload
        hooklib.is_terminal = lambda _: False
        hooklib.ref = lambda _: ("Example/repo", "123", "https://github.com/Example/repo/pull/123")
        hooklib.current = lambda _: payload["current"]
        hooklib.episode_guard = Mock(return_value=episode)
        hooklib.episode_clear = Mock()
        hooklib.skill = Mock(side_effect=lambda name: f"${name}")
        hooklib.inject = Mock()
        response = subprocess.CompletedProcess([], 0, json.dumps(metadata))
        with (
            patch.dict(sys.modules, {"hooklib": hooklib}),
            patch.object(sys, "path", sys.path.copy()),
            patch("subprocess.run", return_value=response, side_effect=failure) as query,
        ):
            runpy.run_path(str(HOOK))
        return hooklib, query

    def test_default_branch_conflict_automatically_invokes_merge_workflow(self):
        for base in ("main", "master"):
            with self.subTest(base=base):
                hooklib, _ = self.run_hook({"state": "open", "head": "feature", "base": base, "default": base})
                message = hooklib.inject.call_args.args[1]
                self.assertIn("$canals:merge-master Example/repo#123", message)
                self.assertIn(f"default-branch base {base}", message)
                self.assertIn("Re-read its current head, base", message)

    def test_stacked_conflict_waits_without_invoking_a_merge_workflow(self):
        hooklib, _ = self.run_hook({"state": "open", "head": "child", "base": "parent", "default": "master"})
        message = hooklib.inject.call_args.args[1]
        self.assertIn("child targets parent", message)
        self.assertIn("wait for their explicit request", message)
        self.assertNotIn("canals:merge-master", message)
        hooklib.skill.assert_not_called()

    def test_failed_metadata_lookup_does_not_merge(self):
        hooklib, _ = self.run_hook(failure=subprocess.TimeoutExpired("gh", 15))
        self.assertIn("could not be verified", hooklib.inject.call_args.args[1])
        hooklib.skill.assert_not_called()

    def test_missing_default_branch_does_not_merge(self):
        hooklib, _ = self.run_hook({"state": "open", "head": "feature", "base": "master"})
        self.assertIn("could not be verified", hooklib.inject.call_args.args[1])
        hooklib.skill.assert_not_called()

    def test_closed_pr_does_not_trigger_a_stale_merge(self):
        hooklib, _ = self.run_hook({"state": "closed"})
        hooklib.inject.assert_not_called()
        hooklib.skill.assert_not_called()

    def test_cleared_conflict_clears_episode_without_querying_github(self):
        hooklib, query = self.run_hook(conflict=False)
        query.assert_not_called()
        hooklib.inject.assert_not_called()
        hooklib.episode_clear.assert_called_once_with("merge-conflict-Example/repo#123")

    def test_repeated_episode_does_not_inject_again(self):
        hooklib, query = self.run_hook(episode=False)
        query.assert_not_called()
        hooklib.inject.assert_not_called()


if __name__ == "__main__":
    unittest.main()
