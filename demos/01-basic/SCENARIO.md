# Demo 01 — Detect drift between git and a live cluster

`desired/` holds three declared resources (a Deployment, a Service, a
ConfigMap). `live-snapshot.json` is what's "running" — produced out-of-band by
e.g. `kubectl get all -o json`.

## Run it

```bash
# Full drift report.
python -m gitopsd diff demos/01-basic/desired demos/01-basic/live-snapshot.json --prune

# Just the reconcile plan.
python -m gitopsd plan demos/01-basic/desired demos/01-basic/live-snapshot.json --prune

# Gate CI on drift.
python -m gitopsd diff demos/01-basic/desired demos/01-basic/live-snapshot.json --fail-on-drift
```

## What you should see

| Resource                       | Status   | Why                                    |
|--------------------------------|----------|----------------------------------------|
| ConfigMap/default/web-config   | MISSING  | declared in git, absent from cluster   |
| Deployment/default/web         | DRIFTED  | replicas 3→1, image tag 1.2.0→1.1.0    |
| Service/default/web            | in-sync  | identical                              |
| Secret/default/leftover        | EXTRA    | running but not declared (prune)       |

`status` and server-managed metadata (`uid`, `resourceVersion`, …) are ignored
so they never show up as false drift.
