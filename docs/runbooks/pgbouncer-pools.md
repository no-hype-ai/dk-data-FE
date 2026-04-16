# PgBouncer pools — routing and budget

**Config**: `k8s/apps/infrastructure/base/pgbouncer.yaml` (ConfigMap `pgbouncer-config`).
**Service**: `pgbouncer.infra.svc.cluster.local:5432` (2 replicas).

## Pools

| Pool                | Backend DB  | `pool_size` (per replica) | Total (×2) | Intended consumers                                                                 |
|---------------------|-------------|---------------------------|------------|-------------------------------------------------------------------------------------|
| `dk_data`           | `dk_data`   | 50                        | 100        | PostgREST (3 replicas × `PGRST_DB_POOL=30` = 90), job-trigger, app cronjobs         |
| `dk_data_hydration` | `dk_data`   | 20                        | 40         | Prestaged hydration Job, bulk backfills, SQLMesh bulk loads — any long-running writer |
| `behavior_labs`     | `behavior_labs` | 25                    | 50         | behavior_labs database clients                                                      |
| `litellm`           | `litellm`   | 10                        | 20         | litellm database clients                                                            |

Per-replica sum: **105**. Enforced by `max_db_connections = 105` in `[pgbouncer]`.

## How to pick the right pool

All pools on PgBouncer share hostname + port (`pgbouncer.infra.svc.cluster.local:5432`). Selection is by the `dbname` (a.k.a. `POSTGRES_DB` env var, or `PGBOUNCER_DB` if the client builds its own DSN).

- **Interactive / latency-sensitive**: `POSTGRES_DB=dk_data` (this is the default for every app today).
- **Batch ingestion / long restores**: set `POSTGRES_DB=dk_data_hydration`. Both pools point at the same underlying `dk_data` database on the CNPG primary — they differ only in the PgBouncer server-connection pool they draw from.

## When to use `dk_data_hydration`

Use it for any workload that:

- Holds server connections for minutes or longer (e.g. `pg_restore`, bulk `COPY`, SQLMesh backfill with large transforms).
- Would otherwise evict PostgREST's 90 pooled client connections from the `dk_data` pool and cause user-facing 503s.

Examples that should move to `dk_data_hydration`:

- `deploy/jobs/prestaged-hydrate*.yaml` — the prestaged hydration Jobs (once feature/005 lands on main).
- Any one-off backfill Job that runs against `dk_data`.

Examples that should stay on `dk_data`:

- PostgREST (latency-sensitive reads and short writes).
- job-trigger and any other HTTP/app-tier writer.
- Short-lived cronjobs that open a connection, run one statement, and close.

## Setting the pool in a Job

```yaml
env:
  - name: POSTGRES_HOST
    valueFrom: { secretKeyRef: { name: dk-data-secrets, key: POSTGRES_HOST } }
  - name: POSTGRES_PORT
    valueFrom: { secretKeyRef: { name: dk-data-secrets, key: POSTGRES_PORT } }
  - name: POSTGRES_USER
    valueFrom: { secretKeyRef: { name: dk-data-secrets, key: POSTGRES_USER } }
  - name: POSTGRES_PASSWORD
    valueFrom: { secretKeyRef: { name: dk-data-secrets, key: POSTGRES_PASSWORD } }
  # Override the default dk_data database with the hydration pool.
  # Same underlying DB, different PgBouncer pool.
  - name: POSTGRES_DB
    value: dk_data_hydration
```

## Auth

Today both `dk_data` and `dk_data_hydration` authenticate against the same `POSTGRES_USER` (from `dk-data-secrets`, DopplerSecret-managed). The isolation is at the PgBouncer pool layer only — not at the Postgres role layer.

Future hardening (separate PR):

1. Create a dedicated `dk_data_hydration` Postgres role with SELECT/INSERT/UPDATE on the ingestion schemas only.
2. Add `HYDRATION_USER` / `HYDRATION_PASSWORD` to `dk-data-secrets` in Doppler.
3. Append a third `"HYDRATION_USER" "HYDRATION_PASSWORD"` line to `userlist.txt` in the `write-userlist` initContainer.
4. Update hydration Jobs to use the new credentials.

## Budget math and `max_db_connections`

See the `BUDGET MATH` block at the top of the ConfigMap in `pgbouncer.yaml` for the full inequality. In short:

- Per-replica server-connection cap: `max_db_connections = 105` (sum of all `pool_size` values).
- Total across 2 replicas: 210.
- Postgres side: `max_connections = 200`, with 30 reserved for superuser/replication/admin → 170 available for apps.

Today 210 > 170. PgBouncer will queue clients past 105 per replica rather than opening connections Postgres can't honor. This is safe while hydration is idle (as it is on main today). Once feature/005 starts driving sustained load on the hydration pool, bump Postgres `max_connections` to ≥ 240 in the CNPG cluster spec before the hydration workload runs at full concurrency.

## Verifying after an ArgoCD sync

```bash
kubectl -n infra exec deploy/pgbouncer -- \
  psql -h 127.0.0.1 -p 5432 -U "$POSTGRES_USER" pgbouncer \
  -c 'SHOW DATABASES;' -c 'SHOW POOLS;' -c 'SHOW CONFIG;' | grep -Ei 'dk_data|max_db_connections|pool_mode'
```

Expect:

- `SHOW DATABASES;` lists `dk_data` and `dk_data_hydration` (both pointing at the same host/dbname).
- `SHOW POOLS;` shows both pools with their configured `pool_size`.
- `SHOW CONFIG;` reports `max_db_connections = 105`.
