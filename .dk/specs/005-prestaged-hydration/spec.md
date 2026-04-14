# Feature: Pre-staged Hydration of dk-data-prod

## Summary

Hydrate the production dk-data database from a set of pre-staged artifacts (PostgreSQL custom-format dumps received via Drive) in a deterministic hub → spoke order with WAL-aware throttling, bypassing broken upstream fetchers for the majority of sources while falling back to live fetch for any source without a pre-staged artifact.

## User Scenarios & Testing

### US-1: Operator hydrates prod from pre-staged artifacts (P1)

**As a** platform operator, **I want to** run a single one-shot job that loads all pre-staged artifacts into prod, **so that** prod exits its zero-data state without waiting for upstream API fixes.

**Acceptance Scenarios:**

```gherkin
Given 120 pre-staged artifact files are present in the configured prestaged path
  And all upstream fetcher prerequisites (migration 227, status-column drift, MinIO) are cleared
When the operator triggers the prestaged-hydrate Job in the prod namespace
Then every artifact is validated, dispatched in the correct load order, and recorded
  And molecule and healthcare-provider surfaces return non-empty data end-to-end
```

**Edge Cases:**
- A dump file fails checksum/magic-byte validation → the run halts for that table and continues with the next, with the failure recorded.
- A table has both a silver dump and bronze dump → the silver dump wins; bronze and silver transforms for that hub are skipped.
- A table has multiple chunk files (`1_…`, `3_…`, `retry_…`) → all are restored serially in lexical order; retries append, not replace.
- A source is absent from the artifact inventory → the orchestrator falls through to the live fetcher path.
- A restore fails mid-table → the run can be re-started and completes the remaining tables without re-restoring completed ones.

### US-2: Hub → spoke load ordering is deterministic (P1)

**As a** data engineer, **I want** hydration to follow a fixed metadata → hub → crosswalk → spoke → gold order, **so that** silver and gold transforms succeed on the first run without manual intervention.

**Acceptance Scenarios:**

```gherkin
Given the pre-staged artifact inventory covers hubs, spokes, and metadata
When the hydration job runs
Then metadata (fetch_checkpoints, SQLMesh snapshots) is restored first
  And molecule hubs (ChEMBL, DrugBank, PubChem, RxNorm) restore before spokes
  And the hcs provider hub restores before hcs aggregates
  And gold-layer transforms run only after all silver data is present
```

**Edge Cases:**
- A hub dependency is missing → spokes that declare it in `depends_on` are skipped with a recorded "blocked-on-missing-hub" state rather than silently failing.
- A silver dump exists for a hub but an upstream bronze dump is also present → silver wins; bronze dump is skipped to avoid redundant writes.

### US-3: WAL-aware throttling protects Postgres under large-table load (P2)

**As a** platform operator, **I want** the job to throttle automatically when PostgreSQL WAL usage approaches its ceiling, **so that** the 5 tables over 5 GB do not trigger checkpointer backpressure or write failures.

**Acceptance Scenarios:**

```gherkin
Given a table in the WAL-mode set (>5 GB) is about to be restored
When measured WAL usage exceeds 70% of max_wal_size
Then the job pauses before starting the restore
  And resumes once WAL drops below 40%
```

**Edge Cases:**
- Two consecutive WAL pauses occur → the default chunk size is halved for subsequent loads in the same run.
- Pause budget is exhausted (N seconds) → the job logs a WAL-exhaustion warning and proceeds anyway; operators are alerted.

### US-4: Fallback to live fetcher for missing sources (P2)

**As a** platform operator, **I want** any source without a pre-staged artifact to fall through to the existing live fetcher path, **so that** hydration completes to the best possible extent without manual orchestration.

**Acceptance Scenarios:**

```gherkin
Given a source has no pre-staged artifact and a working live fetcher
When the hydration job reaches that source in the load order
Then the existing fetcher is invoked
  And the outcome is recorded in the same metadata tracking table as pre-staged sources
```

**Edge Cases:**
- A source has no artifact AND its fetcher is broken (e.g. PatentsView 410, EPO 401) → the source is skipped with a recorded "no-source-available" state; downstream dependents are blocked.
- A source is explicitly out of scope (ip_*, ind_*, hcp_silver per Out-of-Scope) → never attempted; no blocked record.

### US-5: Operator observes per-source run state and checksums (P3)

**As a** platform operator, **I want** per-source run state (status, row count, checksum result, started/finished timestamps) written directly to the metadata tracking table, **so that** I can verify completion and diagnose partial failures without depending on the broken observability stack.

**Acceptance Scenarios:**

```gherkin
Given the hydration job is running
When an operator queries meta.transform_runs for the current run_id
Then every source has a row with a terminal status, row count, and finished_at
  And checksum/magic-byte validation results are present per artifact
```

**Edge Cases:**
- External observability (OTLP → alloy) is down → metadata writes succeed; OTLP emission is best-effort only.
- The metadata tracking table has schema drift → the writer uses the actual column names present post-restore (the meta dump carries prod schema).

## Requirements

### Functional Requirements

- **FR-001**: System MUST discover pre-staged artifact files under a configured path, supporting both archive-expanded (`data/_staging/<archive>/dk-data-files/{schema}/{table}/*.dump`) and loose (`data/_loose_dumps/{schema}/*.dump`) layouts.
- **FR-002**: System MUST validate each artifact's PostgreSQL custom-format magic bytes and, when a manifest is present, its sha256 checksum; invalid artifacts MUST NOT be restored.
- **FR-003**: System MUST select the highest-tier dump available per (schema, table) using the precedence silver > bronze > raw, and MUST skip the transformation layers covered by the restored dump for that hub.
- **FR-004**: System MUST restore all chunks for a single table serially in lexical filename order; numbered chunks and `retry_` chunks MUST both be treated as additional data for the same target table.
- **FR-005**: System MUST enforce a declared load order: metadata/lineage → molecule hub raw → molecule bronze → molecule silver hubs → clinical/activity spokes → hcs raw → hcs bronze → hcs silver → gold.
- **FR-006**: System MUST respect per-source `depends_on` declarations and skip sources whose dependencies failed, recording a blocked state.
- **FR-007**: System MUST throttle restores based on observed WAL usage, pausing before a WAL-mode (>5 GB) restore when usage exceeds a configurable high-water mark (default 70% of `max_wal_size`) and resuming below a configurable low-water mark (default 40%). Thresholds exposed as env vars `WAL_PAUSE_HIGH_PCT`, `WAL_PAUSE_LOW_PCT`.
- **FR-008**: System MUST halve the default chunk size for remaining loads after a configurable number of consecutive WAL pauses (default 2) within one run. Limit exposed as env var `WAL_PAUSE_DOWNSHIFT_THRESHOLD`.
- **FR-009**: System MUST write per-source run state directly to `meta.transform_runs` using the existing columns (`procedure_name`, `chunk_position`, `started_at`, `ended_at`, `rows_processed`, `wal_bytes`) plus two new columns added by migration 229 (`status text`, `details jsonb`). The write path MUST NOT depend on external observability services. `procedure_name` is formatted `prestaged:{schema}.{table}`; `details` JSONB carries `{run_label, source_kind, target_schema, target_table, artifact_sha256, error_detail}`.
- **FR-010**: System MUST fall back to the existing live-fetch path for any source present in the load order but absent from the artifact inventory, provided the source's live fetcher is not explicitly suspended.
- **FR-011**: System MUST be idempotent across restarts: a re-run MUST skip tables already marked complete in `meta.transform_runs` where `details->>'run_label'` matches the current run's deterministic hash (sha256 of sorted artifact sha256s + cluster fingerprint) and `status='completed'`.
- **FR-012**: System MUST provide a dry-run mode that emits the ordered plan (source, kind, target, artifact paths, validation result) without performing any write.
- **FR-013**: System MUST run as a one-shot Kubernetes Job capable of mounting the pre-staged data volume and executing a single hydration pass.
- **FR-014**: System MUST NOT attempt to hydrate explicitly out-of-scope domains (`ip_*`, `ind_*`, `hcp_silver`) even if fetchers exist.
- **FR-015**: System MUST NOT drop or replace relations whose `pg_class.relkind` is not `'r'` (e.g. SQLMesh-managed views); an artifact targeting such a relation MUST be skipped with a recorded warning. This check takes precedence over FR-003 tier selection — a silver dump targeting a view is still skipped; the loader then falls through to bronze/raw for the same hub.
- **FR-016**: System MUST derive a single discovery base path from env var `PRESTAGED_ROOT` (prod default `/data/prestaged`, local default `./data`) and MUST fail fast if that path is absent or unreadable.

### Key Entities

| Entity | Description | Key Attributes |
|--------|-------------|----------------|
| Pre-staged Artifact | A single PostgreSQL custom-format dump file covering part or all of one table | target_schema, target_table, tier (raw/bronze/silver), chunk_index, size_bytes, sha256, magic_ok |
| Load Plan | The ordered execution sequence produced from the artifact inventory plus declared dependencies | ordered_sources, kind_per_source, dependency_graph, wal_mode_tables |
| Transform Run | A metadata row describing the outcome of loading one source within one hydration run | run_id, schema, table, status, row_count, started_at, finished_at, error_detail |
| WAL Observation | A sampled snapshot of PostgreSQL WAL usage used as a throttling signal | observed_at, current_wal_bytes, max_wal_size, pct_used |
| Source Dependency | A declaration that source B cannot run until source A is complete | source, depends_on, parallelizable |

## Success Criteria

- **SC-001**: 100% of (schema, table) pairs present in the final 13/13 artifact inventory (120 dumps, 42.5 GB) are restored to the target schema with row counts within 1% of the row count recorded at dump time.
- **SC-002**: Within 4 hours of job start on prod, PostgREST returns non-empty responses for `mol_silver.molecules`, `mol_silver.clinical_trials`, `mol_silver.drug_labels`, and `hcs_silver.provider_profile`.
- **SC-003**: Zero WAL observations exceed 70% of `max_wal_size` during the run.
- **SC-004**: Zero `column "…" does not exist` errors are emitted from the metadata tracking path for 1 hour after run completion.
- **SC-005**: All gold-layer transforms (`ind_gold.indication_catalog`, `ip_gold.molecule_profile`, `mol_gold_ext.safety_signals`, `mol_gold_ext.lifecycle_stages`) complete without error after hydration.
- **SC-006**: A second invocation of the same hydration job, with no changes to artifacts, completes in under 5 minutes and performs zero table restores (full idempotency).
- **SC-007**: For every source listed in the load order, `meta.transform_runs` contains exactly one terminal-status row per run, queryable without errors.

## Assumptions

- All pre-staged artifacts are PostgreSQL custom-format (`pg_dump -Fc`) dumps; the pre-processor for bare data files (CSV/parquet) is dead code on this run.
- Manifests are not shipped with the artifacts; target schema and table are inferred from directory path, and sha256 is computed post-hoc.
- Prerequisites P1 (migration 227), P2 (MinIO or resilient reporter), P3 (status-column drift), P4 (parked fetchers) are cleared out-of-band before the hydration job is triggered against prod. P1 is already resolved on origin/main.
- The target Postgres cluster (prod) runs a version compatible with the dump format.
- The domains `ip_*`, `ind_*`, `hcp_silver` remain empty post-hydration by design; stakeholders accept that IP/indication/HCP surfaces will be dark until fetcher repairs land.
- The meta dump backfills `meta.transform_runs` history but does NOT remove the need for P3 (platform-api query schema alignment).
- A single Python list suffices for load ordering; adopting a DAG framework is explicitly out of scope.

## Clarifications

### Session 2026-04-14 (autonomous via /dk.auto)

- **Q: What path convention does the discovery module use in production vs local-dev?**
  **A:** Single configurable base via `PRESTAGED_ROOT` env var. Prod default `/data/prestaged/`; local-dev default `./data/` (which already contains `_staging/` and `_loose_dumps/`). No multi-path scan — if a path is wrong, fail loudly rather than silently discover a stale layout.
  *Reason:* Plan describes two layouts (`data/_staging/<archive>/dk-data-files/` and `data/_loose_dumps/{schema}/`); both fit under a single root. Keeps discovery deterministic.

- **Q: Within a tier with parallel-safe tables (e.g. HCS bronze, 34 tables all <700 MB), run restores serially or concurrently?**
  **A:** Serial always for v1. Parallelism is a follow-up optimization gated on observed WAL stability.
  *Reason:* Plan explicitly states "Skip `--jobs` flag … we want serial restore to keep WAL pressure deterministic." SC-003 (zero WAL >70%) is easier to guarantee serially. Throughput cost is acceptable — 34 × ~300 MB bronze files restore in well under the 4-hour SC-002 budget.

- **Q: What is the scope of the `meta.job_locks` advisory lock around each restore?**
  **A:** Per `(schema, table)` — the same lock covers all chunks (numbered + retry_) for one table. Released only after the last chunk's `pg_restore` returns. No cross-table coupling.
  *Reason:* Plan's own description ("scoped to `(schema, table)`"). Prevents two concurrent runs from interleaving chunks on the same table.

- **Q: What does the loader do when an artifact targets what is currently a SQLMesh-managed view (e.g. `mol_silver.publications`, `mol_silver.bioactivity`)?**
  **A:** Skip with a recorded warning; do NOT drop-and-recreate as a table. The current inventory does not include dumps for these views, but if one appears in a future archive the loader refuses rather than breaking SQLMesh lineage.
  *Reason:* These views are the reason migration 227 needed the `pg_class.relkind='r'` fix; overwriting them breaks downstream transforms. SQLMesh owns their materialization.

- **Q: How is a single hydration "run" identified for the purposes of FR-011 idempotency?**
  **A:** `run_id` is a deterministic hash of `(sorted artifact sha256s, target PG cluster fingerprint)`. A re-run with the same inventory against the same cluster produces the same `run_id`, so per-table completion rows already in `meta.transform_runs` match and are skipped. A new artifact (new sha256) or a new cluster produces a new `run_id`.
  *Reason:* Satisfies SC-006 (re-run completes in <5 min doing zero restores) without requiring operators to pass a run identifier or coordinate via ConfigMap. Rules out "copy-paste the same job twice = double-restore".

### Sections Updated
- User Scenarios (US-1 edge case: silver-wins-over-bronze restated to "skip bronze dump entirely, not just its transform")
- Requirements (FR-007 / FR-008 thresholds are configurable via env; FR-011 references deterministic `run_id` derivation)
- Key Entities (Transform Run gains `run_id` semantics note)
- Assumptions (explicit: views in silver schemas are never overwritten by a restore)
