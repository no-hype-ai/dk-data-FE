# Implementation Plan: Pre-staged Hydration of dk-data-prod

**Branch**: `feature/005-prestaged-hydration`
**Date**: 2026-04-14
**Spec**: [spec.md](./spec.md)

## Summary

**Primary requirement**: Hydrate dk-data-prod from 120 PostgreSQL custom-format dumps (42.5 GB across 13 archives) in hub → spoke order with WAL-aware throttling, falling back to live fetchers for any source without a pre-staged artifact.

**Technical approach**: A single new Python module (`src/dk_data/ingestion/prestaged.py`, ~300 LOC) that walks the pre-staged path, builds an ordered load plan from a declared `SOURCE_LOAD_ORDER` list (in `src/dk_data/ingestion/load_order.py`), dispatches serial `pg_restore -Fc` invocations per (schema, table) under an advisory lock, records outcomes to `meta.transform_runs`, and calls existing helpers in `wal_budget.py` / `batch/job_runner.py`. A one-shot Kubernetes Job (`deploy/jobs/prestaged-hydrate.yaml`) mounts the artifact volume and runs the module. No DAG framework, no new orchestration layer.

## Technical Context

| Dimension | Value |
|-----------|-------|
| Language/Version | Python 3.11 |
| Primary Dependencies | `psycopg2-binary>=2.9.9`, `sqlmesh==0.230.0`, `loguru`, `pydantic>=2.5`, `tenacity`; CLI `pg_restore` from `postgresql-client-16` |
| Storage | PostgreSQL 16 (target); host filesystem (PVC or hostPath) for pre-staged artifacts |
| Testing Framework | `pytest` (existing in `tests/`) — unit tests in `tests/ingestion/`, integration tests in `tests/load/` |
| Target Platform | Kubernetes (k3s cluster), namespace `dk-data-prod`, one-shot Job |
| Project Type | Python CLI / library embedded in the `dk-data` ingestion service |
| Performance Goals | Full hydration in <4 h (SC-002); re-run with identical inventory <5 min (SC-006) |
| Constraints | Zero WAL observations >70% of `max_wal_size` (SC-003); idempotent re-runs (FR-011); no dependency on MinIO/alloy in the write path (FR-009) |
| Scale/Scope | 120 dump files, ~42.5 GB, 5 tables >5 GB; 2 domains (mol, hcs) covered; 3 domains (ip, ind, hcp) explicitly out of scope |

## Constitution Check

*No `.dk/memory/constitution.md` present — gates skipped.*

## Project Structure

```
dk-data-FE/
├── src/dk_data/
│   ├── ingestion/
│   │   ├── prestaged.py           # NEW: artifact discovery, validation, dispatch (main module + CLI)
│   │   ├── prestaged_types.py     # NEW: Pydantic models (PrestagedArtifact, LoadStep, LoadPlan), run_id hash
│   │   ├── prestaged_safety.py    # NEW: view-safety (is_restorable_target) — FR-015
│   │   ├── transform_runs_writer.py  # NEW: column-drift-tolerant writer for meta.transform_runs — FR-009
│   │   ├── load_order.py          # NEW: SOURCE_LOAD_ORDER, WAL_MODE_TABLES, plan_load()
│   │   ├── prestaged_manifest.schema.json  # NEW: optional per-artifact manifest schema
│   │   ├── wal_budget.py          # REUSE: chunked_insert, bulk_load_session, wal_usage poll
│   │   ├── source_backfill.py     # MODIFY: extend SOURCE_TO_BRONZE_MODELS with depends_on/prestaged_kind
│   │   ├── main.py                # REUSE: fetcher fallback path
│   │   └── batch/job_runner.py    # REUSE: status tracking wrapper
│   └── sql/migrations/
│       └── 227_autovacuum_per_table_tuning.sql  # ALREADY RESOLVED on main
├── tests/
│   ├── ingestion/
│   │   ├── test_prestaged_discovery.py    # NEW
│   │   ├── test_prestaged_validate.py     # NEW
│   │   ├── test_prestaged_dispatch.py     # NEW (with real Postgres, uses testcontainers or docker-compose fixture)
│   │   └── test_load_order.py             # NEW
│   └── load/
│       └── test_prestaged_e2e.py          # NEW — small dump file → restored rows
├── deploy/
│   ├── docker/
│   │   └── ingestion.Dockerfile           # MODIFY: add `postgresql-client-16` apt package
│   └── jobs/
│       └── prestaged-hydrate.yaml         # NEW: k8s Job manifest
└── .dk/specs/005-prestaged-hydration/     # this feature
    ├── spec.md
    ├── plan.md
    ├── research.md
    ├── data-model.md
    ├── contracts/
    ├── quickstart.md
    ├── tasks.md
    ├── auto-decisions.json
    └── checklists/requirements.md
```

## Phase 0 — Research

### R1: pg_restore flags for chunked, append-only loads

- **Decision**: `pg_restore -Fc --no-owner --no-privileges --single-transaction --section=data --dbname=$PG_URL <file>`. `--clean --if-exists` only on the first chunk per table; subsequent chunks omit `--clean`.
- **Rationale**: `--single-transaction` guarantees atomicity per chunk; `--section=data` skips pre-existing DDL (schema already created by migrations/SQLMesh); `--no-owner`/`--no-privileges` avoids permission churn against the prod role. Append semantics for retry_ and multi-chunk is native: later chunks INSERT without clean.
- **Alternatives considered**: `--jobs=N` (parallel) — rejected per the serial-WAL-determinism clarification. Raw SQL `COPY … FROM STDIN` — rejected because dumps are custom-format, not plain-text.

### R2: WAL-aware throttling signal source

- **Decision**: Poll `meta.wal_usage` view (added in commit `3b1c1e7`) every 30 s; derive `pct_used = current_wal_bytes / max_wal_size`. Pause policy per FR-007/FR-008 with env-var overrides.
- **Rationale**: View already exists; no new instrumentation. Reuses the `wal_budget.py:headroom_check()` helper.
- **Alternatives considered**: `pg_current_wal_lsn()` directly — requires tracking the delta client-side and racing with the checkpointer; view-based approach amortizes the calculation on the server.

### R3: Artifact discovery heuristic

- **Decision**: Walk `${PRESTAGED_ROOT}` depth-2 for two layouts: `_staging/<archive>/dk-data-files/{schema}/{table_dir}/*.dump` and `_loose_dumps/{schema}/*.dump`. `table_dir` is either `{table}` (raw) or `{schema}__{table}__{hash}` (bronze/silver). Compute sha256 on first encounter, cache by inode.
- **Rationale**: Two distinct layouts observed in inventory; no manifest provided; path-based inference is deterministic given the sampled structure.
- **Alternatives considered**: Require a manifest.json per dump — rejected because upstream (Drive export) does not produce one. A full-tree glob — rejected because it returns `.dump` files under irrelevant dirs like `drugbank/`.

### R4: Idempotency key

- **Decision**: `run_id = sha256(sorted(artifact_sha256s) + cluster_fingerprint)`. Store one row per `(run_id, schema, table)` in `meta.transform_runs` with terminal status `completed` / `failed` / `blocked` / `skipped_view`. Re-runs read and skip `completed` rows before dispatch.
- **Rationale**: Deterministic → same inventory on same cluster = same run_id = skip everything already done. New inventory → new run_id → fresh sweep.
- **Alternatives considered**: Client-supplied UUID in a ConfigMap — rejected (operator ergonomics, accidental double-runs). Artifact mtime — rejected (fs-dependent, not portable across PVC/hostPath).

### R5: Advisory lock key

- **Decision**: `pg_advisory_xact_lock(hashtext('prestaged:' || schema || '.' || table))`. Acquired at the start of each chunk, held across all chunks for one table via a wrapping session-level `pg_advisory_lock` released in the `finally` block.
- **Rationale**: 64-bit hash of a stable string; collisions are acceptable (worst case: two loads of unrelated tables briefly serialize).
- **Alternatives considered**: Table-name based hashing using pg_class OID — rejected (table may not exist yet pre-first-chunk).

### R6: View-safety check (FR-015)

- **Decision**: Before `pg_restore`, query `SELECT relkind FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid WHERE n.nspname=:schema AND c.relname=:table`. If result is not `'r'` (table), write `status='skipped_view'` and move on.
- **Rationale**: Same pattern used in the resolved migration 227 fix (`relkind='r'` filter). Prevents catastrophic overwrite of SQLMesh-managed views.
- **Alternatives considered**: Try `pg_restore` and catch the error — rejected (partial state on view, error message inconsistent across PG versions).

### R7: Fallback fetcher invocation

- **Decision**: When a source in `SOURCE_LOAD_ORDER` has zero artifacts and `fetchers.is_enabled(source)` returns True, call `main.run_ingestion(source)`. Record the outcome identically in `meta.transform_runs` with `source_kind='live_fetch'`.
- **Rationale**: Zero code duplication; the existing `main.run_ingestion` already handles retries, OAuth, and per-source logic.
- **Alternatives considered**: Skip-with-warning only — rejected (would regress sources that still have working fetchers like ChEMBL monthly).

## Phase 1 — Design

### Artifacts generated alongside this plan

- **`data-model.md`**: Load Plan, Pre-staged Artifact, Transform Run, WAL Observation, Source Dependency — fields, state transitions, invariants
- **`contracts/cli.md`**: CLI contract for `python -m dk_data.ingestion.prestaged --…`
- **`contracts/k8s-job.md`**: Kubernetes Job contract (env vars, volumes, resource limits)
- **`contracts/meta-transform-runs.md`**: Column contract for writes to `meta.transform_runs`
- **`quickstart.md`**: Local-dev setup and dry-run walk-through

## Complexity Tracking

| Area | Violation | Justification | Approved By |
|------|-----------|---------------|-------------|
| Dead code | `prestaged.py` ships a `bronze_ready`/`raw` dispatch branch that is unreachable on this run | Kept per plan.md — upstream may ship CSV/parquet in later archives; branch is covered by unit tests with fixtures | autonomous (reasoning: cost to add ≈ cost to delete-and-re-add later; risk of omission > risk of dead code) |
| Hostpath volume | Mounting a hostPath volume on `k3s-master-1` violates the "no host coupling" convention | Required while MinIO is down (per P2 prereq); once MinIO returns the Job swaps to the PVC with no code change | autonomous (operational necessity) |
