"""Core engine for gitopsd — GitOps drift detection.

gitopsd compares a *desired* state (a directory of Kubernetes manifests — your
"git" source of truth) against a *live* state (a directory or JSON snapshot of
what is actually running) and reports the drift:

  * missing   — declared in git but absent from the cluster
  * extra     — present in the cluster but not declared in git
  * drifted   — present in both but with differing spec fields
  * in-sync   — identical

It produces a reconcile plan (apply / delete) to bring the cluster back to the
declared state — the core GitOps reconciliation loop, as a dependency-free CLI.

A live cluster snapshot can be produced out-of-band (e.g. ``kubectl get all -o
json``) and fed in; gitopsd itself needs no cluster access, so it runs in CI and
in air-gapped review workflows.

This is original Cognis Digital work; it shares no code, names, or branding with
any other GitOps controller.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

TOOL_NAME = "gitopsd"
TOOL_VERSION = "0.1.0"


class GitopsError(Exception):
    """User-facing manifest/snapshot error."""


# --------------------------------------------------------------------------- #
# Minimal multi-document YAML-subset parser (k8s manifests)
# --------------------------------------------------------------------------- #

def _coerce(text: str) -> Any:
    s = text.strip()
    if s in ("", "~", "null"):
        return None
    if s in ("true", "false"):
        return s == "true"
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    if len(s) >= 2 and s[0] == "[" and s[-1] == "]":
        inner = s[1:-1].strip()
        return [] if not inner else [_coerce(p) for p in inner.split(",")]
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _parse_single(text: str) -> Any:
    lines = text.replace("\t", "  ").splitlines()
    toks: List[Tuple[int, str]] = []
    for raw in lines:
        out, sgl, dbl = [], False, False
        for i, ch in enumerate(raw):
            if ch == "'" and not dbl:
                sgl = not sgl
            elif ch == '"' and not sgl:
                dbl = not dbl
            elif ch == "#" and not sgl and not dbl and (i == 0 or raw[i-1] in " \t"):
                break
            out.append(ch)
        line = "".join(out).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        toks.append((indent, line.strip()))
    if not toks:
        return {}
    pos = [0]

    def kv(s):
        i = s.find(":")
        if i == -1:
            return s, ""
        k, v = s[:i].strip(), s[i+1:].strip()
        if len(k) >= 2 and k[0] == k[-1] and k[0] in "\"'":
            k = k[1:-1]
        return k, v

    def parse_block(indent):
        if pos[0] >= len(toks):
            return None
        _c, content = toks[pos[0]]
        return parse_list(indent) if content.startswith("- ") else parse_map(indent)

    def parse_list(indent):
        items = []
        while pos[0] < len(toks):
            cur, content = toks[pos[0]]
            if cur != indent or not content.startswith("- "):
                break
            inner = content[2:].strip()
            pos[0] += 1
            if ":" in inner and not (inner.find(":")+1 < len(inner)
                                     and inner[inner.find(":")+1] != " "):
                k, v = kv(inner)
                obj = {k: (_coerce(v) if v else _child(indent + 2))}
                obj.update(cont_map(indent + 2))
                items.append(obj)
            elif inner == "":
                items.append(_child(indent + 2))
            else:
                items.append(_coerce(inner))
        return items

    def cont_map(indent):
        obj = {}
        while pos[0] < len(toks):
            cur, content = toks[pos[0]]
            if cur != indent or content.startswith("- "):
                break
            k, v = kv(content)
            pos[0] += 1
            obj[k] = _coerce(v) if v else _child(indent + 2)
        return obj

    def parse_map(indent):
        obj = {}
        while pos[0] < len(toks):
            cur, content = toks[pos[0]]
            if cur != indent or content.startswith("- "):
                break
            k, v = kv(content)
            pos[0] += 1
            obj[k] = _coerce(v) if v else _child(indent + 1)
        return obj

    def _child(min_indent):
        if pos[0] >= len(toks):
            return None
        cur, content = toks[pos[0]]
        if cur < min_indent:
            return None
        return parse_list(cur) if content.startswith("- ") else parse_map(cur)

    result = parse_block(0)
    return result if result is not None else {}


def parse_manifests(text: str) -> List[Dict[str, Any]]:
    """Parse a multi-document YAML/JSON string into a list of resource dicts."""
    text = text.strip()
    if not text:
        return []
    if text[:1] in "{[":
        data = json.loads(text)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        if isinstance(data, dict) and data.get("kind") == "List":
            return [i for i in data.get("items", []) if isinstance(i, dict)]
        return [data] if isinstance(data, dict) else []
    docs = []
    for chunk in text.split("\n---"):
        chunk = chunk.strip().lstrip("-").strip()
        if not chunk:
            continue
        obj = _parse_single(chunk)
        if isinstance(obj, dict) and obj:
            docs.append(obj)
    return docs


# --------------------------------------------------------------------------- #
# Resource identity + state loading
# --------------------------------------------------------------------------- #

def resource_key(obj: Dict[str, Any]) -> str:
    """A stable identity for a k8s object: kind/namespace/name."""
    kind = obj.get("kind", "?")
    md = obj.get("metadata", {}) or {}
    ns = md.get("namespace", "default")
    name = md.get("name", "?")
    return f"{kind}/{ns}/{name}"


def load_state_dir(path: str) -> Dict[str, Dict[str, Any]]:
    """Load every manifest under a directory into a key -> object map."""
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as fh:
            return {resource_key(o): o for o in parse_manifests(fh.read())}
    if not os.path.isdir(path):
        raise GitopsError(f"state path not found: {path}")
    out: Dict[str, Dict[str, Any]] = {}
    for root, _dirs, files in os.walk(path):
        for fn in sorted(files):
            if fn.endswith((".yaml", ".yml", ".json")):
                with open(os.path.join(root, fn), "r", encoding="utf-8") as fh:
                    for o in parse_manifests(fh.read()):
                        out[resource_key(o)] = o
    return out


# --------------------------------------------------------------------------- #
# Field-level diff
# --------------------------------------------------------------------------- #

# Live-cluster-only noise we ignore when comparing (status, server-managed md).
_IGNORE_TOP = {"status"}
_IGNORE_META = {"resourceVersion", "uid", "creationTimestamp", "generation",
                "managedFields", "selfLink"}


def _normalize(obj: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in obj.items() if k not in _IGNORE_TOP}
    md = dict(out.get("metadata", {}) or {})
    for k in _IGNORE_META:
        md.pop(k, None)
    if "annotations" in md and isinstance(md["annotations"], dict):
        md["annotations"] = {k: v for k, v in md["annotations"].items()
                             if not k.startswith("kubectl.kubernetes.io/")}
    out["metadata"] = md
    return out


def _flatten(d: Any, prefix: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.update(_flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = d
    return out


def diff_resource(desired: Dict[str, Any], live: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return field-level changes needed to bring live -> desired."""
    df, lf = _flatten(_normalize(desired)), _flatten(_normalize(live))
    changes = []
    for k in sorted(set(df) | set(lf)):
        if k not in lf:
            changes.append({"path": k, "op": "add", "to": df[k]})
        elif k not in df:
            changes.append({"path": k, "op": "remove", "from": lf[k]})
        elif df[k] != lf[k]:
            changes.append({"path": k, "op": "change", "from": lf[k], "to": df[k]})
    return changes


# --------------------------------------------------------------------------- #
# Drift report + reconcile plan
# --------------------------------------------------------------------------- #

def detect_drift(desired_path: str, live_path: str,
                 prune: bool = False) -> Dict[str, Any]:
    """Compare desired vs live state directories/snapshots."""
    desired = load_state_dir(desired_path)
    live = load_state_dir(live_path)

    missing = sorted(set(desired) - set(live))
    extra = sorted(set(live) - set(desired))
    drifted = []
    in_sync = []
    for key in sorted(set(desired) & set(live)):
        changes = diff_resource(desired[key], live[key])
        if changes:
            drifted.append({"key": key, "changes": changes})
        else:
            in_sync.append(key)

    plan = []
    for key in missing:
        plan.append({"action": "apply", "key": key, "reason": "missing in cluster"})
    for d in drifted:
        plan.append({"action": "apply", "key": d["key"],
                     "reason": f"{len(d['changes'])} field(s) drifted"})
    if prune:
        for key in extra:
            plan.append({"action": "delete", "key": key,
                         "reason": "not declared (prune)"})

    return {
        "desired_count": len(desired),
        "live_count": len(live),
        "missing": missing,
        "extra": extra,
        "drifted": drifted,
        "in_sync": in_sync,
        "synced": not missing and not drifted and (not extra or not prune),
        "plan": plan,
    }


# --------------------------------------------------------------------------- #
# AI hook (opt-in, default OFF)
# --------------------------------------------------------------------------- #

def explain_drift(report: Dict[str, Any]) -> Dict[str, Any]:
    out = {"summary": "", "_ai": "disabled — set COGNIS_AI_BACKEND to enable"}
    backend = _load_ai_backend()
    if backend is None or not backend.is_enabled() or not backend.health():
        return out
    brief = {"missing": report["missing"], "extra": report["extra"],
             "drifted": [d["key"] for d in report["drifted"]]}
    try:
        out["summary"] = backend._chat(
            "Summarize this Kubernetes GitOps drift in two sentences and flag "
            "the riskiest change.", json.dumps(brief)) or ""
        out["_ai"] = "summarized by local fleet"
    except Exception:
        pass
    return out


def _load_ai_backend():
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.abspath(os.path.join(here, "..", "..", "..", "_shared",
                                        "cognis_ai_backend.py"))
    if os.path.isfile(cand):
        try:
            spec = importlib.util.spec_from_file_location("cognis_ai_backend", cand)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod.CognisAIBackend()
        except Exception:
            return None
    return None
