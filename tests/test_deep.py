"""Deep tests for gitopsd — manifest parsing, normalization, diff, plan, MCP."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gitopsd import (
    detect_drift,
    diff_resource,
    explain_drift,
    load_state_dir,
    parse_manifests,
    resource_key,
)
from gitopsd import mcp_server

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESIRED = os.path.join(REPO_ROOT, "demos", "01-basic", "desired")
LIVE = os.path.join(REPO_ROOT, "demos", "01-basic", "live-snapshot.json")


class TestParse(unittest.TestCase):
    def test_multidoc_yaml(self):
        docs = parse_manifests("kind: A\nmetadata:\n  name: x\n---\nkind: B\nmetadata:\n  name: y\n")
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0]["kind"], "A")

    def test_json_list(self):
        docs = parse_manifests('{"kind":"List","items":[{"kind":"P","metadata":{"name":"a"}}]}')
        self.assertEqual(len(docs), 1)

    def test_resource_key(self):
        self.assertEqual(
            resource_key({"kind": "Pod", "metadata": {"name": "p"}}),
            "Pod/default/p")


class TestNormalizationDiff(unittest.TestCase):
    def test_ignores_status_and_server_md(self):
        desired = {"kind": "X", "metadata": {"name": "a"}, "spec": {"r": 3}}
        live = {"kind": "X", "metadata": {"name": "a", "uid": "z",
                "resourceVersion": "9"}, "spec": {"r": 3}, "status": {"ready": 1}}
        self.assertEqual(diff_resource(desired, live), [])

    def test_detects_spec_change(self):
        desired = {"kind": "X", "metadata": {"name": "a"}, "spec": {"r": 3}}
        live = {"kind": "X", "metadata": {"name": "a"}, "spec": {"r": 1}}
        changes = diff_resource(desired, live)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["op"], "change")


class TestPlan(unittest.TestCase):
    def test_plan_actions(self):
        r = detect_drift(DESIRED, LIVE, prune=True)
        actions = {(s["action"], s["key"]) for s in r["plan"]}
        self.assertIn(("apply", "ConfigMap/default/web-config"), actions)
        self.assertIn(("apply", "Deployment/default/web"), actions)
        self.assertIn(("delete", "Secret/default/leftover"), actions)

    def test_no_prune_excludes_delete(self):
        r = detect_drift(DESIRED, LIVE, prune=False)
        self.assertFalse(any(s["action"] == "delete" for s in r["plan"]))


class TestLoad(unittest.TestCase):
    def test_load_dir_and_file(self):
        d = load_state_dir(DESIRED)
        self.assertEqual(len(d), 3)
        live = load_state_dir(LIVE)
        self.assertEqual(len(live), 3)


class TestMcp(unittest.TestCase):
    def test_list_and_diff(self):
        tl = mcp_server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {t["name"] for t in tl["result"]["tools"]}
        self.assertEqual(names, {"diff", "plan"})
        r = mcp_server.handle_request({
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "diff",
                       "arguments": {"desired": DESIRED, "live": LIVE, "prune": True}}})
        self.assertTrue(r["result"]["isError"])  # drift present
        payload = json.loads(r["result"]["content"][0]["text"])
        self.assertIn("ConfigMap/default/web-config", payload["missing"])


class TestAiHook(unittest.TestCase):
    def test_off_by_default(self):
        for v in ("COGNIS_AI_BACKEND", "COGNIS_AI_ENDPOINT"):
            os.environ.pop(v, None)
        out = explain_drift(detect_drift(DESIRED, LIVE))
        self.assertTrue(out["_ai"].startswith("disabled"))


if __name__ == "__main__":
    unittest.main()
