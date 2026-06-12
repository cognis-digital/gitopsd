"""Smoke tests for gitopsd. Standard library only."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gitopsd import TOOL_NAME, TOOL_VERSION, detect_drift
from gitopsd.cli import main

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESIRED = os.path.join(REPO_ROOT, "demos", "01-basic", "desired")
LIVE = os.path.join(REPO_ROOT, "demos", "01-basic", "live-snapshot.json")


class TestMetadata(unittest.TestCase):
    def test_metadata(self):
        self.assertEqual(TOOL_NAME, "gitopsd")
        self.assertTrue(TOOL_VERSION)


class TestDrift(unittest.TestCase):
    def test_demo_drift(self):
        r = detect_drift(DESIRED, LIVE, prune=True)
        self.assertIn("ConfigMap/default/web-config", r["missing"])
        self.assertIn("Secret/default/leftover", r["extra"])
        drifted_keys = [d["key"] for d in r["drifted"]]
        self.assertIn("Deployment/default/web", drifted_keys)
        self.assertIn("Service/default/web", r["in_sync"])
        self.assertFalse(r["synced"])


class TestCli(unittest.TestCase):
    def test_diff_runs(self):
        self.assertEqual(main(["diff", DESIRED, LIVE]), 0)

    def test_fail_on_drift(self):
        self.assertEqual(main(["diff", DESIRED, LIVE, "--fail-on-drift"]), 1)

    def test_plan(self):
        self.assertEqual(main(["plan", DESIRED, LIVE, "--prune"]), 0)

    def test_missing_path_exits_2(self):
        self.assertEqual(main(["diff", "/no/such", LIVE]), 2)

    def test_no_command_exits_2(self):
        self.assertEqual(main([]), 2)


if __name__ == "__main__":
    unittest.main()
