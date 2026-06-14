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

## Interoperability

`gitopsd` composes with the 300+ tool Cognis suite — JSON in/out and a shared
OpenAI-compatible `/v1` backbone. See **[INTEROP.md](INTEROP.md)** for the
suite map, composition patterns, and reference stacks.

## Integrations

Forward `gitopsd`'s findings to STIX/MISP/Sigma/Splunk/Elastic/Slack/webhooks via
[`cognis-connect`](https://github.com/cognis-digital/cognis-connect). See **[INTEGRATIONS.md](INTEGRATIONS.md)**.

## License

Cognis Open Collaboration License (COCL) 1.0 — see [`LICENSE`](LICENSE).
© 2026 Cognis Digital LLC. Original Cognis work; no third-party code, names, or
branding.

<!-- cognis:domains:start -->
## Domains

**Primary domain:** Intelligence & OSINT  ·  **JTF MERIDIAN division:** NULLBYTE · BLACK CELL

**Topics:** `cognis` `osint` `intelligence` `recon` `kubernetes`

Part of the **Cognis Neural Suite** — 300+ source-available tools organized across 12 domains under the JTF MERIDIAN command structure. See the [suite on GitHub](https://github.com/cognis-digital) and [jtf-meridian](https://github.com/cognis-digital/jtf-meridian) for how the pieces fit together.
<!-- cognis:domains:end -->

## Usage — step by step

`gitopsd` diffs declared Kubernetes manifests against a live-state snapshot and emits a drift report plus a reconcile plan — no cluster access of its own.

1. **Install** (pure stdlib, Python 3.10+):
   ```bash
   pip install "git+https://github.com/cognis-digital/gitopsd.git"
   ```
2. **Snapshot live state** with kubectl, then diff it against your manifests (`--prune` flags undeclared live resources, `--ignore` skips field globs):
   ```bash
   kubectl get deploy,svc -o json > live-snapshot.json
   gitopsd diff ./manifests ./live-snapshot.json --prune --ignore spec.replicas
   ```
3. **Get just the reconcile plan** (ordered apply/delete steps):
   ```bash
   gitopsd plan ./manifests ./live-snapshot.json --prune
   ```
4. **Use the output** — `--format json` for tooling, or RFC-6902 patches for the drifted resources:
   ```bash
   gitopsd diff ./manifests ./live-snapshot.json --format json
   gitopsd patch ./manifests ./live-snapshot.json
   ```
5. **Gate CI** — `--fail-on-drift` exits non-zero whenever live differs from git:
   ```bash
   gitopsd diff ./manifests ./live-snapshot.json --fail-on-drift
   ```
   Or run it as a local MCP server (stdio JSON-RPC): `gitopsd mcp`.
