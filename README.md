# gitopsd

**GitOps drift detection, dependency-free.** Diff your declared Kubernetes
manifests (the git source of truth) against live cluster state and get a clear
drift report plus a reconcile plan — the core GitOps loop as a single CLI.

Part of the **Cognis Neural Suite**. Standard library only; needs no cluster
access of its own, so it runs in CI and in air-gapped review workflows.

---

## Why

GitOps is becoming the default way teams run Kubernetes, but you don't always
want a full controller in-cluster just to *answer the question* "does live match
git?". gitopsd answers it from a manifest directory and a state snapshot
(`kubectl get ... -o json`), with no dependencies.

## Commands

```bash
# Report drift (missing / extra / drifted / in-sync) + a reconcile plan.
python -m gitopsd diff ./manifests ./live-snapshot.json --prune

# Just the apply/delete plan.
python -m gitopsd plan ./manifests ./live-snapshot.json --prune

# Gate a pipeline: non-zero exit if anything has drifted.
python -m gitopsd diff ./manifests ./live-snapshot.json --fail-on-drift

# Run as a local MCP server (stdio JSON-RPC).
python -m gitopsd mcp
```

## What sets gitopsd apart

- **Noise-free diffs.** Ignores `status` and server-managed metadata
  (`uid`, `resourceVersion`, `managedFields`, last-applied annotations) so you
  see *real* drift, not cluster bookkeeping.
- **Field-level drift.** Tells you exactly which paths changed and from/to what.
- **Reconcile plan.** Emits an ordered apply/delete plan; `--prune` flags
  undeclared resources.
- **MCP-native** (`diff` / `plan`) and an opt-in local-fleet AI hook (default
  OFF) that summarizes drift and flags the riskiest change.
- **Pairs with the air-gap suite** — review drift before bundling with
  [airlock](https://github.com/cognis-digital/airlock).

## Tests

```bash
python -m pytest -q     # or: python -m unittest discover -s tests
```

## License

Cognis Open Collaboration License (COCL) 1.0 — see [`LICENSE`](LICENSE).
© 2026 Cognis Digital LLC. Original Cognis work; no third-party code, names, or
branding.
