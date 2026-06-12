"""Feature tests for gitopsd — ignore globs, JSON Patch, drift score, CLI, MCP."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gitopsd import detect_drift, diff_resource, to_json_patch
from gitopsd.core import _to_jsonpointer
from gitopsd.cli import main

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESIRED = os.path.join(REPO_ROOT, "demos", "01-basic", "desired")
LIVE = os.path.join(REPO_ROOT, "demos", "01-basic", "live-snapshot.json")


class TestIgnore(unittest.TestCase):
    def test_ignore_exact_path(self):
        desired = {"kind": "X", "metadata": {"name": "a"}, "spec": {"replicas": 3}}
        live = {"kind": "X", "metadata": {"name": "a"}, "spec": {"replicas": 1}}
        self.assertTrue(diff_resource(desired, live))           # drift without ignore
        self.assertEqual(diff_resource(desired, live,
                                       ignore=["spec.replicas"]), [])  # ignored

    def test_ignore_glob(self):
        desired = {"kind": "X", "metadata": {"name": "a",
                   "annotations": {"x": "1"}}, "spec": {}}
        live = {"kind": "X", "metadata": {"name": "a",
                "annotations": {"x": "2"}}, "spec": {}}
        self.assertEqual(
            diff_resource(desired, live, ignore=["metadata.annotations.*"]), [])

    def test_ignore_in_detect_drift(self):
        # The demo Deployment drifts on spec.replicas + image; ignore replicas.
        r = detect_drift(DESIRED, LIVE, ignore=["spec.replicas"])
        dep = next(d for d in r["drifted"] if "Deployment" in d["key"])
        paths = {c["path"] for c in dep["changes"]}
        self.assertNotIn("spec.replicas", paths)
        self.assertTrue(any("image" in p for p in paths))


class TestJsonPatch(unittest.TestCase):
    def test_pointer_conversion(self):
        self.assertEqual(_to_jsonpointer("spec.replicas"), "/spec/replicas")
        self.assertEqual(
            _to_jsonpointer("spec.template.spec.containers[0].image"),
            "/spec/template/spec/containers/0/image")

    def test_replace_op(self):
        changes = [{"path": "spec.replicas", "op": "change", "from": 1, "to": 3}]
        patch = to_json_patch(changes)
        self.assertEqual(patch, [{"op": "replace", "path": "/spec/replicas", "value": 3}])

    def test_add_and_remove(self):
        patch = to_json_patch([
            {"path": "metadata.labels.new", "op": "add", "to": "v"},
            {"path": "spec.old", "op": "remove", "from": "x"}])
        self.assertEqual(patch[0]["op"], "add")
        self.assertEqual(patch[1], {"op": "remove", "path": "/spec/old"})

    def test_patch_attached_to_drifted(self):
        r = detect_drift(DESIRED, LIVE)
        dep = next(d for d in r["drifted"] if "Deployment" in d["key"])
        self.assertIn("patch", dep)
        self.assertTrue(all("op" in p and "path" in p for p in dep["patch"]))


class TestDriftScore(unittest.TestCase):
    def test_score_present_and_bounded(self):
        r = detect_drift(DESIRED, LIVE)
        self.assertIn("drift_score", r)
        self.assertTrue(0 <= r["drift_score"] <= 100)
        self.assertGreater(r["changed_fields"], 0)

    def test_perfect_sync_scores_100(self):
        r = detect_drift(DESIRED, DESIRED)
        self.assertEqual(r["drift_score"], 100.0)
        self.assertTrue(r["synced"])


class TestCliFeatures(unittest.TestCase):
    def test_patch_subcommand(self):
        self.assertEqual(main(["patch", DESIRED, LIVE]), 0)

    def test_diff_with_ignore(self):
        self.assertEqual(main(["diff", DESIRED, LIVE, "--ignore", "spec.replicas"]), 0)

    def test_plan_with_ignore(self):
        self.assertEqual(main(["plan", DESIRED, LIVE, "--ignore", "status.*",
                               "--prune"]), 0)


class TestMcpFeatures(unittest.TestCase):
    def test_diff_payload_has_score_and_patch(self):
        from gitopsd import mcp_server
        r = mcp_server.handle_request({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "diff",
                       "arguments": {"desired": DESIRED, "live": LIVE, "prune": True}}})
        payload = json.loads(r["result"]["content"][0]["text"])
        self.assertIn("drift_score", payload)
        dep = next(d for d in payload["drifted"] if "Deployment" in d["key"])
        self.assertIn("patch", dep)


if __name__ == "__main__":
    unittest.main()
