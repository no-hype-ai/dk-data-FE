# T002 — PostgREST k8s probes are TCP-only

**Feature**: 002-external-integration-foundation
**Date**: 2026-04-13
**Status**: PASS — verified against the manifest at repo HEAD

## Check

```bash
grep -A 5 -E 'startupProbe:|livenessProbe:|readinessProbe:' \
  k8s/apps/postgrest/base/deployment.yaml
```

## Expected

All three probes use `tcpSocket: {port: 3000}` — no `httpGet`.

## Actual

```yaml
startupProbe:
  tcpSocket:
    port: 3000
  initialDelaySeconds: 5
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 30
livenessProbe:
  tcpSocket:
    port: 3000
  initialDelaySeconds: 30
  periodSeconds: 30
  timeoutSeconds: 5
  failureThreshold: 3
readinessProbe:
  tcpSocket:
    port: 3000
  initialDelaySeconds: 5
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 3
```

## Result

PASS. All three probes are `tcpSocket`. No HTTP probe carve-out is
required, so `web_anon` does not need a `SELECT` grant on `api.health`
for the k8s probe path (the stale comment claiming otherwise was
removed by T085).

## Related

- `.dk/memory/lessons.md` — "Stale comment in deployment.yaml"
- `k8s/apps/postgrest/base/deployment.yaml`
- T085 — stale comment fix
