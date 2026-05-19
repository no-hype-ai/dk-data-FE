# HCS Silver / Gold — `web_anon` Consumer Dependency Audit

**Feature**: 002-external-integration-foundation (T001d, US-2, US-3)
**Date**: 2026-04-13
**Status**: Procedural audit template

## Goal

Before migration 218 drops `web_anon`, enumerate every cluster service
that currently reads from `hcs_silver` or `hcs_gold` through the
anonymous path. Migration 218 will terminate those reads with 401 the
moment it lands in production — anything we miss here is an outage.

## Step 1 — Query pg_stat_activity history

If a query log / pg_stat_statements history is retained, use it.
Otherwise, poll `pg_stat_activity` for 30 days and aggregate:

```sql
-- Hourly sampler (run as a cron for 30 days ahead of the migration)
SELECT
    NOW() AS sampled_at,
    usename,
    application_name,
    client_addr,
    query
FROM pg_stat_activity
WHERE usename = 'web_anon'
  AND state = 'active'
  AND query ILIKE '%hcs_silver%'
   OR query ILIKE '%hcs_gold%';
```

Accumulate into `meta.web_anon_access_log` with `(client_addr,
application_name, query_hash) PRIMARY KEY` + `COUNT(*)`.

## Step 2 — Map IP → consumer

Every pod in the cluster has a stable consumer identity via k8s
service accounts. Map the client_addr column to a consumer:

```bash
# For each suspect IP in the sampler output:
kubectl -n <suspect-ns> get pods -o wide | grep <client_ip>
```

Known pods to check:
- `internal-*` (metering-proxy's "internal" alias)
- `carbon-5-*`
- `dk-os-*`
- `ground-truth-charlie-*`
- `trials-predictor-*`
- `litellm-*`
- any batch job pods

## Step 3 — Decision

For each service found in step 2:

| Consumer | Legitimate need? | Action |
|---|---|---|
| X | yes | Provision API key BEFORE migration 218 (T019) |
| Y | yes, but deprecated | Sunset the consumer, remove the read before 218 |
| Z | no — leftover debug | Revoke access, nothing to do |

## Fill-in

```
Audit window:                    ____-__-__ to ____-__-__
Samples collected:               ___
Distinct IPs seen:               ___
Identified consumers:            ___
Unidentified IPs:                ___
Legitimate consumers blocked if migration 218 ran today: ___
API keys provisioned in consumers.yaml: ___
Remaining blockers for T089a:    ___
```

## Sign-off

Before migration 218 lands in production, this document must show:

- ≥ 20 days of sampling data (one full monthly reporting cycle)
- `Unidentified IPs: 0`
- `Legitimate consumers blocked: 0` (all provisioned)
- dk-data on-call acknowledgement

```
dk-data on-call:  _______________ on ____-__-__
Ready for T089a:  yes / no
```

## Related

- `docs/reports/capacity-audit-2026-Q2.md`
- `docs/runbooks/rollback-web-anon-drop.md`
- `src/dk_data/sql/migrations/218_drop_web_anon.sql`
