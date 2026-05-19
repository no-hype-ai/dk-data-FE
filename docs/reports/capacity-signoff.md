# Capacity Sign-Off — Feature 002 External Integration Foundation

**Feature**: 002-external-integration-foundation (US-17, T147)
**Date**: 2026-04-13
**Status**: Awaits infra team sign-off

## What this signs off

Before feature 002 lands in production (specifically T089a — migration
218 drop web_anon in prod), the infrastructure team must confirm that
the cluster can absorb the Phase 2 load profile documented here. This
document is the contract.

## Projected load — Phase 2 peak

| Resource | Current | Phase 2 peak | Delta |
|---|---|---|---|
| Metering proxy requests/sec | ~50 | 10,000 | +200× |
| PostgREST requests/sec | ~30 | 8,000 | +266× |
| Postgres connections (dk-data) | 25 | 100–250 | +4–10× |
| PgBouncer active connections | 20 | 80–200 | +4–10× |
| SQLMesh transform job concurrency | 1 | 1 | unchanged (intentionally sequential) |
| Adapter backfill cronjob concurrency | 1 | 1 | unchanged |
| Loki events/sec (adapter telemetry) | 0 | 500 | new stream |
| Loki events/day | 0 | 7M | new stream |

## Cluster resources required

### PostgreSQL

- `max_connections = 200` → `300` (to leave headroom for other tenants)
- Prefer **PgBouncer transaction pooling** rather than raising the
  raw limit if the shared Postgres can't grow
- `shared_buffers` unchanged (this is read-heavy; existing 25% of RAM
  is fine)
- `work_mem` per session unchanged
- Add monitoring alert on `pg_stat_activity` backends >= 80% of
  `max_connections`

### PostgREST

- `PGRST_DB_POOL = 30` → `50` (per-replica)
- Replicas = 3 (currently 2) for HA + headroom
- PDB `minAvailable: 1` — already shipped in this PR

### Metering proxy

- Replicas = 2 (currently 1) for HA
- PDB `minAvailable: 1` — already shipped in this PR
- Redis for shared rate-limit counters (optional — the code falls back
  to in-memory if Redis is unavailable, but multi-replica will then
  allow `N × configured_rpm` so Redis is strongly recommended)

### Loki

- Retention = 30 days
- PVC = 200 GB (7× daily volume for burst headroom)
- Distributor rate limit = 10,000 ingestion events/sec per tenant
- Ingester replicas = 3 (AZ-spread)

## Cost envelope

Rough order-of-magnitude, using the cluster's current unit pricing:

- **Metering proxy replica**: 50m CPU / 64Mi memory × 2 replicas = minimal
- **PostgREST extra replica**: existing footprint × 1 = ~$5/mo
- **Loki PVC 200 GB**: ~$20/mo (cluster-local SSD)
- **Loki ingester replicas**: 3 × existing = ~$30/mo total
- **Total delta**: ~$55/mo

Below the $500/mo new-feature threshold — does not require CFO review.

## Sign-off

The infra team must confirm the resource changes above. Once signed,
this document becomes the binding contract for T089a. Any later
deviation from the numbers here requires re-signing.

```
Infra on-call:     _______________    on  __________
DB admin:          _______________    on  __________
Ops manager:       _______________    on  __________
```

## Rollback

If any resource changes above are rejected, feature 002 blocks on
re-scoping. Specifically:

- **Raise max_connections rejected** → add PgBouncer capacity first,
  re-plan the connection budget
- **Loki PVC rejected** → downgrade adapter telemetry from "every
  call" to "1-in-100 sample" in v0.1
- **Metering proxy HA rejected** → postpone T089a until HA is funded

## Related

- `docs/reports/capacity-audit-2026-Q2.md` — the procedural audit that
  produced these numbers
- `docs/reports/hcs-silver-consumer-audit.md` — consumer dependency audit
- `tests/load/phase2_concurrent.py` — the load driver used to validate
- `tests/load/loki_push.py` — the Loki push capacity driver
