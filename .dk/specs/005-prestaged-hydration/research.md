# Phase 0 Research

Cross-references to `plan.md § Phase 0 — Research` (R1–R7). This file records the alternatives considered in more detail and the evidence weighed for each decision.

## R1: pg_restore flags

**Evidence**: `pg_restore` custom-format dumps support atomic per-file restore. The dumps in inventory were produced by `pg_dump -Fc` (PGDMP magic bytes verified, 120/120 files).

**Flag matrix**:

| Flag | Keep? | Why |
|------|-------|-----|
| `-Fc` | yes | Custom format; no auto-detect needed |
| `--single-transaction` | yes | Atomicity per chunk; on failure, no partial rows left |
| `--no-owner` | yes | Prod role doesn't match dump owner |
| `--no-privileges` | yes | Skip GRANT/REVOKE churn |
| `--section=data` | yes | Schema already exists (migrations + SQLMesh own DDL) |
| `--clean --if-exists` | first chunk only | Subsequent chunks must append |
| `--jobs=N` | **no** | Breaks serial WAL-pressure guarantee |
| `--disable-triggers` | **no** | Would bypass downstream validation; not needed because `--section=data` doesn't run triggers-that-fire-on-replica anyway |

**Rejected alternatives**:
- Plain-text COPY: source files are `-Fc`, conversion is wasteful.
- `pg_restore --data-only`: equivalent to `--section=data` but less explicit; kept the verbose form.

## R2: WAL throttle signal

**Evidence**: `meta.wal_usage` view exists (`git log --oneline | grep wal_usage` → `3b1c1e7`). Polling cost ≈ 1 query / 30 s is negligible.

**Rejected**: Client-side LSN math — requires tracking two LSN snapshots and `max_wal_size` on every tick; fragile under failover.

## R3: Artifact discovery

**Evidence from inventory (plan.md §Data flow)**:
- 8 zips expanded into `_staging/<archive>/dk-data-files/{schema}/`
- 5 loose dumps landed under `_loose_dumps/{schema}/`
- Bronze/silver layout: `{schema}__{table}__{hash}/` (observed for pubchem, chembl_activities, clinicaltrials)
- Raw layout: `{table}/`

**Decision**: Two-layout walker, single `PRESTAGED_ROOT`, fail-fast if empty.

**Rejected**: Manifest-first — no manifests shipped.

## R4: Idempotency key

**Constraint**: SC-006 says re-run completes in <5 min with zero restores.

**Decision**: Deterministic `run_id = sha256(sorted_artifact_sha256s + cluster_fp)`.
- `sorted_artifact_sha256s` — order-independent fingerprint of the inventory
- `cluster_fp = concat(pg_host, pg_port, pg_database)` — prevents cross-cluster collision

**Rejected**:
- Random UUID per run — fails SC-006.
- Inventory mtime — fs-dependent, breaks when PVC is remounted.

## R5: Advisory lock

**Decision**: `hashtext('prestaged:' || schema || '.' || table)` as the lock key. Acquired on first chunk, released after last chunk.

**Collision math**: `hashtext` returns a 32-bit int; given ~120 tables, collision probability ≈ 120² / 2³² ≈ 3e-6. Tolerable.

**Rejected**: `pg_class.oid` — requires table to pre-exist; first chunk may create it.

## R6: View-safety check

**Evidence**: Migration 227 blew up on `mol_silver.publications` (a SQLMesh view); fix was to filter on `pg_class.relkind='r'`. Same principle must apply to `pg_restore` target.

**Decision**: Pre-flight `SELECT relkind` query; if not `'r'`, skip with `status='skipped_view'`.

**Rejected**: Attempt restore, catch error — error text varies; partial state risk.

## R7: Fallback fetcher

**Evidence**: `src/dk_data/ingestion/main.py:run_ingestion(source)` already handles all live fetchers; reusing it avoids duplication.

**Suspended fetchers** (P4): PatentsView v1 (410), EPO OPS (401), EUIPO TMview (RemoteDisconnected), `fetch-fda-ndc` (bad CLI arg). These are detected via `fetchers.is_enabled(source)` which reads a new `fetchers.suspended` set.

## Research summary

All unknowns from the spec now have decisions. No `[NEEDS CLARIFICATION]` remaining. Implementation can proceed to task breakdown.
