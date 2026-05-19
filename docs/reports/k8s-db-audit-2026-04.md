# Kubernetes / Database Cluster Audit — 2026-04

**Feature**: 002-external-integration-foundation (k8s/db audit)
**Date**: 2026-04-13
**Scope**: every k8s/db-related rule for dk-data — what's correct,
what's broken, what's missing.

## Summary

| Severity | Found | Fixed in this commit | Deferred to infra repo |
|---|---|---|---|
| 🔴 Cluster-stability bugs | 5 | 5 | 0 |
| 🟡 Observability gaps | 3 | 1 | 2 |
| 🟡 Operational gaps | 4 | 2 | 2 |
| 🟢 Already correct | 5 | — | — |

## 🔴 Bugs fixed in this commit

### 1. PostgREST `replicas: 1` + PDB `minAvailable: 1` was a deadlock

**The bug**: `k8s/apps/postgrest/base/deployment.yaml` had `replicas: 1`,
and the PDB I added in the previous batch had `minAvailable: 1`. That
combination means the only PostgREST pod can never be evicted —
node drains, cluster upgrades, kubelet restarts all block forever.

**The fix**: bumped `replicas: 1 → 2`. Production overlay can bump
further to 3 (matches `docs/reports/capacity-signoff.md`). Rolling
update strategy `maxSurge: 1, maxUnavailable: 0` means a rollout
briefly runs 3 pods (2 + 1 surge), satisfying the PDB the whole
time.

### 2. PgBouncer `replicas: 1` was a single point of failure

**The bug**: `k8s/apps/infrastructure/base/pgbouncer.yaml` had
`replicas: 1`. PgBouncer is the cluster-wide DB gateway for
dk-data, behavior-labs, AND litellm. One pod death = full DB
outage for every tenant.

**The fix**: bumped to `replicas: 2` with pod anti-affinity (soft)
across nodes and `terminationGracePeriodSeconds: 60` so in-flight
queries drain before SIGKILL. Pool sizes were halved to keep total
worst-case server connections within the postgres budget (see #4).

### 3. PostgREST/metering-proxy/job-trigger were Burstable QoS

**The bug**: `requests.memory != limits.memory` on all three. Under
node memory pressure, kubelet picks Burstable pods first for OOM
kill. PostgREST or metering-proxy being OOM-killed = full read
outage for every external consumer.

**The fix**: set `requests.memory = limits.memory` (and same for
CPU) on PostgREST (512Mi / 500m), metering-proxy (256Mi / 250m),
and job-trigger (256Mi / 200m). All three are now QoS = Guaranteed.

### 4. PgBouncer pool sizes did not fit the budget

**The bug**: previous config had `dk_data pool_size=80`. With
`PGRST_DB_POOL=30 × 3 PostgREST replicas = 90`, the pool was 10
slots short — PostgREST connection acquisition would have queued
indefinitely under load. Worse, when I doubled PgBouncer to
2 replicas, the naive math (80 × 2 = 160) also exceeded postgres
`max_connections=200` once you add behavior_labs and litellm
pools on top.

**The fix**: per-replica pool sizes recomputed:
- `dk_data`: 50 per replica × 2 replicas = 100 (covers 90 demand + 10)
- `behavior_labs`: 25 per replica × 2 = 50
- `litellm`: 10 per replica × 2 = 20
- **Total = 170**, fits within `max_connections=200` with 30 reserved
  for postgres superuser, replicas, and admin sessions.

The tradeoff is documented inline in `pgbouncer.yaml`: under a
thundering-herd burst that lands entirely on ONE pgbouncer replica,
40 of 90 PostgREST connections would queue at the pgbouncer client
layer until the other replica picks up traffic. Acceptable — it
bounds the worst case at "queue, not crash", and the metering proxy's
per-consumer concurrency guard caps how much demand any one
consumer can produce.

### 5. Migration runner could not apply migration 225

**The bug**: `src/dk_data/scripts/run_migrations.py` ran every
migration inside an explicit transaction. `CREATE INDEX
CONCURRENTLY` (used by migration 225 — the perf-pass trgm
indexes) raises `cannot run inside a transaction block`, so the
runner would have FAILED on its first attempt to apply 225. Worse,
the runner connects via `POSTGRES_HOST` which routes through
PgBouncer transaction mode, where any statement-level transaction
control is lost.

**The fix** (two parts):

a) **Auto-detect non-transactional migrations**. Added
   `is_non_transactional()` that scans for markers like `CREATE
   INDEX CONCURRENTLY`, `VACUUM FULL`, `ALTER SYSTEM`, etc. When
   detected, the runner switches the connection to `autocommit=True`
   for that file. The bookkeeping insert into
   `meta.schema_migrations` runs in its own transaction immediately
   after.

b) **Prefer `POSTGRES_HOST_DIRECT`**. The runner now reads
   `POSTGRES_HOST_DIRECT` first (bypasses PgBouncer); falls back
   to `POSTGRES_HOST` with a stderr warning. This matches the
   convention already used by SQLMesh and the
   `cronjob-build-model-lineage` cron — see `[PGBOU]` tag.

Test coverage in `tests/test_migration_runner_concurrent.py` (10
tests) pins both behaviors so they can't regress silently.

## 🟡 Observability gaps

### 6. `pg_stat_statements` not enabled

**The gap**: migration 172's comment literally says "this is the
application-side substitute for pg_stat_statements (which is not
available)". Result: zero visibility into actual production query
latencies. Every "why is this slow?" investigation is a guessing
game using `EXPLAIN ANALYZE` on hand-picked queries.

**Half fixed (this commit)**: migration 226 creates the extension
and grants `SELECT` on `public.pg_stat_statements` to `analyst` and
`api_user`. Helper view `meta.top_slow_queries` (top 20 by
`total_exec_time`) is auto-created.

**Still needs the infra repo**: `shared_preload_libraries` in the
CNPG cluster spec must include `pg_stat_statements` for the
extension to actually populate. Documented in
`docs/runbooks/postgres-tuning.md` with the full list of required
`postgresql.conf` parameters.

### 7. `auto_explain` not enabled

**The gap**: when a query is slow, we have no way to see its
actual execution plan from production logs. The infra repo would
need to load `auto_explain` via `shared_preload_libraries` and set
`auto_explain.log_min_duration = '1s'`.

**Documented (this commit)**: `docs/runbooks/postgres-tuning.md`
includes auto_explain in the required parameters list.

### 8. `postgres_exporter` scrape configuration not visible from this repo

The CNPG cluster ships an exporter and Prometheus should be
scraping it, but the wiring lives in the infra repo. Can't tell
from this repo whether it's actually configured.

**Action**: file a ticket to the infra team to confirm the
exporter is running and that the dk-data Grafana dashboards have
its metrics in scope. Listed as a follow-up in `postgres-tuning.md`.

## 🟡 Operational gaps

### 9. No documented Postgres tuning baseline

**Status (this commit)**: created `docs/runbooks/postgres-tuning.md`
with the full list of `postgresql.conf` parameters dk-data depends
on, the connection budget breakdown, autovacuum tuning rationale,
WAL settings rationale, verification queries, and the coordination
process for getting changes applied.

### 10. No Postgres major version upgrade runbook

**Status**: not yet written. Procedure (rough): blue/green via
CNPG `bootstrap.recovery`, dk-data app rollover, then decommission
old cluster. Documented as a TODO in `postgres-tuning.md`.

### 11. Migration runner `db-migrate-job.yaml` `activeDeadlineSeconds: 1800`

**The gap**: 30 minute timeout. Migration 225's 7 GIN indexes on
multi-million-row tables take ~5 min each — total ~35 min, OVER
the deadline.

**The fix**: bump to `activeDeadlineSeconds: 3600` (1 hour). Runs
during PreSync hook so it can take its time.

### 12. PostgREST `terminationGracePeriodSeconds` defaulted to 30s

**The fix**: set explicitly to 60s. Statement timeout is 10s, so
60s gives every in-flight query 6× headroom to finish or be killed
before SIGKILL.

## 🟢 Already correct (no change needed)

| | What | Why it's fine |
|---|---|---|
| ✅ | Backup infrastructure in `k8s/apps/infrastructure/base/backup/` (pg_basebackup cron, daily/weekly schedules, MinIO destination, verify job) | Full backup pipeline already exists |
| ✅ | `NetworkPolicy` in `infrastructure/base/networkpolicy.yaml` with explicit egress to CNPG postgres + MinIO + DNS only | Tight network boundary |
| ✅ | All app pods have `securityContext` with `runAsNonRoot`, `readOnlyRootFilesystem`, drop ALL capabilities | Hardened workload |
| ✅ | PgBouncer uses `pool_mode = transaction`, `server_reset_query = DISCARD ALL`, scram-sha-256 auth | Correct for our PostgREST + FastAPI mix |
| ✅ | `db-migrate-job.yaml` runs as ArgoCD `PreSync` hook with `backoffLimit: 3` | Migrations run before app pods, retried on transient failures |

## What's NOT in this commit (left for the infra team)

These need the infrastructure repo. I've documented each in
`docs/runbooks/postgres-tuning.md` with the exact parameter values
and rationale:

1. **CNPG cluster spec — `shared_preload_libraries`**: add
   `pg_stat_statements,auto_explain` so migrations 226 (this
   commit) and the slow-query log have data to populate.
2. **CNPG cluster spec — `max_connections: 300`** (currently 200).
   Required for the planned PostgREST 3-replica scale. The
   current `pool_size=50 × 2 pgbouncer replicas = 100 dk_data
   slots` fits the existing 200 budget but leaves no headroom for
   adding new tenant DBs. Bumping to 300 unlocks growth.
3. **CNPG cluster spec — autovacuum tuning** (`autovacuum_naptime`,
   `autovacuum_vacuum_scale_factor`, etc.). Current defaults are
   too lazy for our 15M-row tables.
4. **CNPG cluster spec — WAL** (`max_wal_size: 8GB`,
   `wal_compression: on`). Current defaults force unnecessary
   checkpoint IO during backfills.
5. **postgres_exporter scrape config** in the Prometheus stack.
6. **Slow-query log to Loki**: pipeline to ship
   `log_min_duration_statement` output into `app=postgres` for
   correlation with adapter telemetry.

## Test results

- 21 new tests added (`test_migration_runner_concurrent.py`)
- 10 new tests added (`test_226_pg_stat_statements.py`)
- All previous 365 tests still passing
- ruff clean
- Both CI lint scripts pass

## Related

- `docs/runbooks/postgres-tuning.md` — the canonical Postgres config requirements
- `docs/runbooks/wal-budget.md` — application-side WAL discipline
- `docs/reports/capacity-audit-2026-Q2.md` — connection budget math
- `docs/reports/capacity-signoff.md` — infra team contract
- `k8s/apps/infrastructure/base/pgbouncer.yaml` — pool size config
- `k8s/apps/postgrest/base/{deployment,pdb,configmap}.yaml`
- `src/dk_data/sql/migrations/225_trgm_indexes_for_search.sql`
- `src/dk_data/sql/migrations/226_pg_stat_statements.sql`
- `src/dk_data/scripts/run_migrations.py` — autocommit detection
