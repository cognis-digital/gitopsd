# gitopsd — Usage Guide

gitopsd compares a *desired* state (declared manifests) against a *live* state
(a directory or a `kubectl get ... -o json` snapshot) and reports drift, a
reconcile plan, a drift score, and ready-to-apply JSON Patches.

## Producing a live snapshot

```bash
kubectl get deploy,svc,configmap,secret -A -o json > live-snapshot.json
```
gitopsd accepts that directly, or a `kind: List`, or a directory of manifests.

## Commands

### diff
```bash
python -m gitopsd diff ./manifests ./live-snapshot.json --prune
```
- `--prune` flags live-only resources (deletable).
- `--ignore GLOB` (repeatable) excludes intentional differences by flattened
  field path. Examples:
  ```bash
  --ignore spec.replicas            # an HPA owns scaling
  --ignore 'metadata.annotations.*' # controller-written annotations
  --ignore 'status.*'               # (already ignored by default)
  ```
- `--fail-on-drift` exits non-zero for CI gating.

The report includes a **drift score** (0–100, fraction of declared resources
that are clean) and **changed_fields** count.

### plan
```bash
python -m gitopsd plan ./manifests ./live-snapshot.json --prune
```
Just the ordered apply/delete plan.

### patch — RFC-6902 JSON Patches
```bash
python -m gitopsd patch ./manifests ./live-snapshot.json
```
Emits a `{resource-key: [json-patch]}` map. Each patch is a standard RFC-6902
document you can hand to `kubectl patch --type=json`:
```bash
kubectl patch deploy/web --type=json -p "$(jq '.["Deployment/default/web"]' patches.json)"
```

## What is ignored automatically

`status`, and server-managed metadata (`uid`, `resourceVersion`, `generation`,
`managedFields`, `selfLink`, `creationTimestamp`) and `kubectl.kubernetes.io/*`
annotations — so cluster bookkeeping never shows up as false drift.

## MCP server

```bash
python -m gitopsd mcp     # exposes diff / plan over stdio JSON-RPC
```

## CI recipe

```bash
kubectl get all -A -o json > live.json
python -m gitopsd diff k8s/ live.json --prune \
    --ignore spec.replicas --fail-on-drift
```
