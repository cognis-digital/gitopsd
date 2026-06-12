"""Command-line interface for gitopsd."""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from gitopsd import TOOL_NAME, TOOL_VERSION
from gitopsd.core import GitopsError, detect_drift


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="GitOps drift detection — diff declared manifests against "
                    "live cluster state and emit a reconcile plan.")
    p.add_argument("--version", action="version",
                   version=f"{TOOL_NAME} {TOOL_VERSION}")
    sub = p.add_subparsers(dest="command")

    d = sub.add_parser("diff", help="Report drift between desired and live state.")
    d.add_argument("desired", help="Directory/file of declared manifests.")
    d.add_argument("live", help="Directory/file or snapshot of live state.")
    d.add_argument("--prune", action="store_true",
                   help="Treat undeclared live resources as drift (deletable).")
    d.add_argument("--format", choices=("table", "json"), default="table")
    d.add_argument("--fail-on-drift", action="store_true",
                   help="Exit non-zero if any drift is detected.")

    pl = sub.add_parser("plan", help="Print only the reconcile plan.")
    pl.add_argument("desired")
    pl.add_argument("live")
    pl.add_argument("--prune", action="store_true")
    pl.add_argument("--format", choices=("table", "json"), default="table")

    sub.add_parser("mcp", help="Run as an MCP server (stdio JSON-RPC).")
    return p


def _render(report) -> str:
    lines = ["gitopsd drift report", "=" * 60,
             f"  desired: {report['desired_count']}   live: {report['live_count']}"]
    if report["missing"]:
        lines.append(f"  MISSING ({len(report['missing'])}):")
        for k in report["missing"]:
            lines.append(f"    + {k}")
    if report["extra"]:
        lines.append(f"  EXTRA ({len(report['extra'])}):")
        for k in report["extra"]:
            lines.append(f"    ? {k}")
    if report["drifted"]:
        lines.append(f"  DRIFTED ({len(report['drifted'])}):")
        for d in report["drifted"]:
            lines.append(f"    ~ {d['key']}  ({len(d['changes'])} field change(s))")
            for c in d["changes"][:6]:
                if c["op"] == "change":
                    lines.append(f"        {c['path']}: {c['from']} -> {c['to']}")
                elif c["op"] == "add":
                    lines.append(f"        + {c['path']} = {c['to']}")
                else:
                    lines.append(f"        - {c['path']}")
    lines.append("-" * 60)
    lines.append(f"  in-sync: {len(report['in_sync'])}   "
                 f"plan steps: {len(report['plan'])}")
    lines.append("RESULT: " + ("IN SYNC" if report["synced"] else "DRIFT DETECTED"))
    return "\n".join(lines)


def _run_diff(a) -> int:
    try:
        report = detect_drift(a.desired, a.live, prune=a.prune)
    except (OSError, GitopsError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if a.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(_render(report))
    if a.fail_on_drift and not report["synced"]:
        return 1
    return 0


def _run_plan(a) -> int:
    try:
        report = detect_drift(a.desired, a.live, prune=a.prune)
    except (OSError, GitopsError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if a.format == "json":
        print(json.dumps({"plan": report["plan"]}, indent=2))
    else:
        print(f"gitopsd reconcile plan — {len(report['plan'])} step(s)")
        for step in report["plan"]:
            print(f"  {step['action']:<7} {step['key']}   ({step['reason']})")
    return 0


def _run_mcp() -> int:
    from gitopsd.mcp_server import run_mcp_server
    run_mcp_server()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "diff":
        return _run_diff(args)
    if args.command == "plan":
        return _run_plan(args)
    if args.command == "mcp":
        return _run_mcp()
    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
