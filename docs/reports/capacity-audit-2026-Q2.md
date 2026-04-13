# Capacity Audit — 2026 Q2

**Feature**: 002-external-integration-foundation (T001a, T001b, T001c)
**Date**: 2026-04-13
**Status**: Procedural template — must be executed against staging
before feature 002 production cutover (T089a).

## Why

Feature 002 introduces the metering proxy as the single choke point in
front of PostgREST. 5 external consumers × 2–5 replicas each means the
effective PostgREST connection demand could grow by 10–25× depending on
adapter concurrency. Without an explicit capacity audit, the first
multi-consumer peak will look like an outage.

## Step 1 — PGRST_DB_POOL sizing (T001a)

PostgREST's `PGRST_DB_POOL` caps the max connections it will hold. Each
request grabs a pooled connection, executes, and returns it.

### Current value

```bash
kubectl -n dk-data-prod get configmap postgrest-config -o yaml \
  | grep PGRST_DB_POOL
```

### Target value

```
PGRST_DB_POOL = ceil(peak_rps × p99_query_seconds × 1.5)
```

Phase 2 projected peak: 10k rps distributed across replicas, p99 query
time 50 ms → per-replica pool ≥ 10000 × 0.05 × 1.5 / replicas.

With 3 PostgREST replicas, that's `10000 × 0.05 × 1.5 / 3 = 250` per
replica. The default 10 is WAY too small. **Raise PGRST_DB_POOL to 30
minimum, 50 for Phase 2 peak.**

### Fill-in (run against staging)

```
Current PGRST_DB_POOL value:   ___
Replica count:                 ___
Projected peak rps per replica: ___
Required pool size:            ___
Recommended PGRST_DB_POOL:     ___
Proposed change filed in PR:   ___
```

## Step 2 — Shared Postgres `max_connections` (T001b)

dk-data shares the cluster Postgres with other tenants (`behavior_labs`,
`litellm`). Total connection budget = `max_connections = 200` across
all tenants.

### Current steady-state

```sql
-- Run as postgres superuser
SELECT
    usename,
    COUNT(*) AS active_connections,
    MAX(backend_start) AS oldest_backend
FROM pg_stat_activity
WHERE state IS NOT NULL
GROUP BY usename
ORDER BY active_connections DESC;
```

### Projected growth

- **Current dk-data connections**: `___` (from query above)
- **New connections from adapter fleet**: 50–200 (5 consumers × 10–40
  replicas × 1 connection per active request)
- **Total after feature 002**: `___`
- **Headroom vs `max_connections=200`**: `___%`

If headroom < 20%, **raise `max_connections` to 300** OR add PgBouncer
capacity (transaction pooling) OR both. Document which in the fill-in
below.

### Fill-in

```
max_connections before:         ___
Current dk-data usage:          ___
behavior_labs usage:            ___
litellm usage:                  ___
Free headroom:                  ___
Projected adapter demand:       ___
Proposed max_connections:       ___
Proposed PgBouncer change:      ___
```

## Step 3 — Adapter routing (T001c)

Confirm every external read path goes **through** the metering proxy,
NOT a direct adapter → PostgreSQL connection. A direct connection
bypasses the proxy's auth, rate limit, and audit, which violates
feature 002's whole premise.

### Check

```bash
# Any non-PostgREST client connecting to Postgres?
psql ... -c "
  SELECT usename, application_name, client_addr, COUNT(*)
  FROM pg_stat_activity
  WHERE state IS NOT NULL
    AND usename NOT IN ('postgres', 'authenticator', 'postgrest')
  GROUP BY 1,2,3
  ORDER BY 4 DESC;
"
```

Expected output: no consumer-alias entries. If any consumer shows up
here, file a bug, do NOT ship feature 002 until it's remediated.

### NetworkPolicy lock-down

The structural fix is a NetworkPolicy that rejects direct consumer →
Postgres traffic at the network layer:

```yaml
# k8s/apps/metering-proxy/base/networkpolicy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: postgres-only-via-metering-proxy
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/component: postgres
  policyTypes: [Ingress]
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app.kubernetes.io/component: postgrest
        - podSelector:
            matchLabels:
              app.kubernetes.io/component: metering-proxy
        - podSelector:
            matchLabels:
              app.kubernetes.io/component: job-trigger
      ports:
        - protocol: TCP
          port: 5432
```

If the ingress namespace uses a different CNI that doesn't enforce
NetworkPolicy, the check above becomes the only guard — re-run it
before every production cutover.

### Fill-in

```
Direct consumer connections found: ___ (0 = pass)
NetworkPolicy in place:            ___ (yes/no)
Operator who verified:             ___
Date/time:                         ___
```

## Sign-off

This document must be signed off by the dk-data on-call engineer AND
the infra on-call engineer before migration 218 is applied to
production (T089a). Both sign below:

- dk-data on-call: `________________` on `__________`
- infra on-call: `________________` on `__________`

## Related

- `docs/runbooks/rollback-web-anon-drop.md` — rollback path
- `docs/reports/hcs-silver-consumer-audit.md` — consumer dependency audit
- `tests/load/phase2_concurrent.py` — load driver used to verify
