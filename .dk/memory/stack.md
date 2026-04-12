# Tech Stack

> Auto-updated by dk commands. Reflects current project state.

| Layer | Technology | Version | Notes |
|-------|-----------|---------|-------|
| Language | Python | 3.11+ | `requires-python = ">=3.11"` in `pyproject.toml` |
| Database | PostgreSQL via CloudNativePG | 16.4 | Single shared cluster in `infra` namespace; tenants `dk_data`, `behavior_labs`, `litellm` |
| Connection pooler | PgBouncer | — | `pgbouncer.infra.svc.cluster.local:5432`, transaction mode |
| ETL framework | SQLMesh | ≥0.90 | Models in `src/dk_data/sqlmesh/models/{molecules,healthcare,intellectual_property}/{bronze,silver,gold}/` |
| Database driver | psycopg2-binary | — | Connections via `dk_data.ingestion.utils.database.build_dsn()` only |
| API surface | PostgREST | v12.2.3 | Exposes silver and gold tables to consumers |
| Auth | JWT | — | Min 256-bit secrets, validated at startup |
| Orchestration | Kubernetes (K3s) | — | Single-node on penguin |
| GitOps | ArgoCD | — | All k8s changes via sync, no manual kubectl apply |
| Image registry | GHCR | — | `ghcr.io/data-kinetic/`, SHA-pinned tags only |
| Secrets | Doppler | — | `dk-data-staging`, `dk-data-prod` configs |
| Observability | Prometheus + Grafana + Mimir | — | App-side metrics (no `pg_stat_statements` available) |
| Tracing | OpenTelemetry SDK | — | OTLP export to cluster collector |
| Logging | structlog | — | JSON output, `application_name` set per-pod |
| Testing | pytest + responses | — | Real CNPG postgres for integration tests, no DB mocks |
| Linting | ruff | — | `ruff check .` from `src/` |

## Patterns

### Hub + crosswalk + name index per entity type (added by feature 001-silver-medallion-rebuild)

Each top-level entity type (molecules, drug_products, targets, conditions, companies, providers, facilities, patents, trademarks, designs) has:

- **Hub table**: synthetic `bigserial` PK, canonical fields only, first/last seen timestamps
- **Identifier crosswalk**: `(source, identifier)` composite PK, points at hub row
- **Name index**: `(normalized_name, hub_id, source)` composite PK, with `display_name` for unnormalized text and `confidence` for fuzzy matches
- **Resolve function**: one PL/pgSQL function per entity type, `STABLE PARALLEL SAFE`, walks the documented priority tree

### Chunked PL/pgSQL bootstrap procedures (added by feature 001-silver-medallion-rebuild)

Heavy data loads (>1M rows) use procedures with mid-loop COMMITs:

- Chunk size ≤50K rows / ≤200 MB WAL per chunk
- `pg_sleep(0.05)` between chunks for multi-tenant fairness
- WAL accounting via `pg_current_wal_lsn()` brackets, written to `meta.transform_runs`
- Resumable via `meta.refresh_state.last_chunk_position`
- `INSERT ... ON CONFLICT DO NOTHING` for idempotence
- Conflicts logged to `meta.linkage_conflicts` (never silently overwrite)

### Connection-string helper (added by feature 001-silver-medallion-rebuild)

All Python DB connections go through `dk_data.ingestion.utils.database.build_dsn()`. Helper sets:

- `statement_timeout=600000`, `idle_in_transaction_session_timeout=300000`, `lock_timeout=30000`
- `keepalives=1`, `keepalives_idle=60`, `keepalives_interval=10`, `keepalives_count=6`
- `application_name=<pod_name>` for `pg_stat_activity` attribution

CI grep enforces no direct `psycopg2.connect(` calls outside the helper.

### Persistent job locks (added by feature 001-silver-medallion-rebuild)

Cross-pod coordination uses `meta.job_locks (name, locked_by, locked_at, expires_at)` instead of `pg_try_advisory_lock` because PgBouncer transaction mode breaks session-scoped advisory locks.
