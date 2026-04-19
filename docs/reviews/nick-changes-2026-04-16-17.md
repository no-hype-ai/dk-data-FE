# Nick King's changes on `main` — 2026-04-16 to 2026-04-17

**Scope**: all commits authored by Nick King that landed on `origin/main`
between Philipp's last 04-14 commit (`23c911b`) and HEAD (`937c9f6`).

- **Commits**: 44 (non-merge, non-bot)
- **Days active**: 2 (2026-04-16, 2026-04-17)
- **Co-author on every commit**: Claude Opus 4.6 (1M context)
- **PRs referenced**: #299–#308, #309–#323, #339–#347, plus several direct-to-main ops commits on 04-17
- **Relationship to Philipp's work**: Philipp's WAL circuit-breaker PR
  (`1cf9a54`, #289) merged on 04-17 in the middle of this run and is a
  sibling to Nick's C.2 (#315) work. Your WAL dir-size / archiver-health
  circuit breakers sit at the transform and backfill entry points; Nick's
  C.2 replaces the `wal_pressure()` stub with a live view read inside
  `wal_throttle.py`. Overlap in intent, not in file changes.

The work divides cleanly into **eight themes**. Themes 1–3 are the
orchestration rewrite (plan.md §C/§D/§E). Theme 4 is observability.
Themes 5–8 are supporting work: client package hardening, k8s fix-ups,
docs, and miscellaneous infra.

---

## Theme 1 — Horizon 2 "C-series": hydration reliability + observability

Rebuilds the safety nets around the prestaged hydration pipeline.
Eight PRs, all landed 2026-04-16, all keyed to sections of `plan.md`.

### #311 (`2a3103a`) — C.1 SeaweedFS boto3 client module

- **New module**: `src/dk_data/ingestion/storage/minio_admin.py` (+305)
- Introduces a boto3-based client for SeaweedFS (S3-compatible object
  store). This is the foundation for Theme-1 artifact work — every
  downstream C-series piece assumes it can read/write to SeaweedFS.
- New runbook: `docs/runbooks/seaweedfs-client.md` (+136)
- `pyproject.toml` gains the boto3 dep.
- Tests: `tests/unit/test_minio_admin.py` (+267).

### #315 (`8ba06a6`) — C.2 Real WAL backpressure + per-source pause budgets

**Before**: `wal_throttle.py::wal_pressure()` was a stub returning `0.0`.
Pauses were applied off a single run-level `WAL_PAUSE_BUDGET_SECONDS`,
so one pathological source could drain the whole budget and leave the
rest of the run un-protected.

**After**:

- **Migration 231** (`meta.wal_pressure` view):
  ```
  pct_used = 100 * pg_wal_lsn_diff(current_lsn, last_checkpoint_redo)
                 / pg_size_bytes(max_wal_size)
  oldest_replica_lag_bytes = from pg_stat_replication (NULL on permission error)
  ```
  `CREATE OR REPLACE VIEW` — idempotent. Graceful degradation when the
  hydration role cannot read `pg_stat_replication`.
- `wal_throttle.py` (+264 LOC):
  - `wal_pressure()` now queries `SELECT pct_used FROM meta.wal_pressure`,
    fail-open (returns `0.0`) on missing view / DB error / empty result.
    Never raises.
  - `WalThrottle.maybe_pause(source_id=...)` — new per-source pause
    budget `WAL_PAUSE_BUDGET_PER_SOURCE_SECONDS` (default 180s). Once a
    source exhausts its share, pauses are skipped **for that source only**
    while others continue to honour the 70/40 hysteresis band.
  - Every `paused ↔ running` edge emits a single INFO line with the
    observed `pct_used`.
- **New counter** `dk_wal_source_budget_exhausted_total{source}` —
  increments once per (run, source) on first exhaustion. Alert-driven
  (`DkWalSourceBudgetExhausted` PrometheusRule); not on dashboards.
- **Tests**: `tests/ingestion/test_wal_throttle.py` 8 → 18, covering the
  view-query path (happy / empty / DB-error / NUMERIC-cast), hysteresis
  edge transitions, and per-source budget isolation.

### #316 (`715bc3a`) — C.3 DLQ + source quarantine (`meta.hydration_backlog`)

- **Migration 232** — `meta.hydration_backlog` (natural key `(source_id,
  schema, table)`), exponential-backoff `next_retry_at`, and a
  `consecutive_same_error_count` gate so auto-quarantine fires only on
  truly repeatable failures, not flapping upstreams. *(Originally
  migration 231, renumbered to 232 when PR #315 landed on the same
  number first.)*
- **New module** `src/dk_data/ingestion/hydration_backlog.py` (+391):
  `HydrationBacklogWriter` with `record_failure / is_quarantined /
  unquarantine / list_all`. **FR-030 compliant** — uses
  `get_connection_pool()`, no raw `psycopg2.connect()`. Tolerant failure
  semantics: missing creds degrade to a no-op DLQ.
- Wired into `prestaged.py::run_step` (+222 LOC): quarantine pre-flight
  returns `RunStepOutcome(status='quarantined', ...)` before any
  dispatch; failures normalise to `CONN_LOST / PG_RESTORE_FATAL /
  ROW_MISMATCH / UNKNOWN_*` error codes.
- **New CLI flags** on prestaged: `--list-backlog` (JSON dump),
  `--unquarantine` (clears + writes audit row with
  `procedure_name='dlq:unquarantine'` in `meta.transform_runs`).
- **3 new counters** — `dk_hydration_dlq_added_total`,
  `_quarantined_total`, `_skipped_total`. Allowlisted as alert-driven
  (DLQ events page ops; primary surface is the table itself).
- **Tests**: `tests/unit/test_hydration_backlog.py` (+372) with FR-030
  regression guard asserting no direct `psycopg2.connect` call.

### #313 (`8363636`) — C.4 Download integrity pipeline (`meta.artifact_provenance`)

- **Migration 229** — `meta.artifact_provenance` table for artifact
  lineage (source URL, byte size, SHA256, Content-Length observed,
  download duration).
- **New module** `src/dk_data/ingestion/common/integrity.py` (+363):
  Content-Length guard, SHA256 recording, provenance-row writes.
- **Integration**: `cms_downloader.py` gains +109 LOC wiring integrity
  checks into the download path.
- **New metrics**: `dk_artifact_changed_total`, `_size_mismatch_total`,
  `_provenance_write_errors_total`.
- **Tests**: `tests/unit/test_integrity.py` (+344).

### #310 (`323242c`) — C.5 Dedicated `dk_data_hydration` pgbouncer pool

- `k8s/apps/infrastructure/base/pgbouncer.yaml` (+97 −30): separate pool
  with its own budget math, isolating hydration connections from the
  rest of the app. Default size **20 connections** — referenced by D.3's
  `db_connections=20` budget seed.
- New runbook `docs/runbooks/pgbouncer-pools.md` (+93) documents the
  math and the reason to isolate (blast-radius during large restores).

### #312 (`49e25dd`) — C.6 Hydration phase + artifact + freshness metrics

- `src/dk_data/observability/metrics.py` gains +49 metric definitions.
- New SLO doc `docs/slos/hydration.md` (+126).
- Expands `dk-data-fe-hydration.json` (+277) and
  `dk-data-fe-source-registry.json` (+375) dashboards.
- `tests/observability/test_metric_coverage.py` +21 new coverage asserts.

### #314 (`4ffd294`) — C.7 SQLMesh audits at silver/gold boundaries

- **New**: `src/dk_data/sqlmesh/audits/custom_audits.sql` (+123) —
  reusable audit queries.
- **New**: `docs/sqlmesh/audits.md` (+132) — the "why / when / how" doc.
- **Wired audits into 20 models across all domains**:
  - `hcp/silver/researchers.sql`
  - `hcs/silver/{facilities, providers}.sql`
  - `hcs/gold/{cms_facility_360, cms_market_analytics, cms_provider_360,
    facility_master}.sql`
  - `ind/silver/conditions.sql`, `ind/gold/indication_catalog.sql`
  - `ip/silver/{patents, trademarks}.sql`
  - `molecules/silver/{companies, drug_products, molecules, targets}.sql`
  - `molecules/gold/{competitive_landscape, kol_profiles, market_summary,
    molecule_profile, safety_signals}.sql`
- **Tests**: `tests/sqlmesh/test_audits.py` (+266).

### #305 (`3555592`) — Manifest row-count gate

After `pg_restore`, the hydrator now looks up `<dump>.manifest.json`
next to each artifact and fails the step if the actual row count
doesn't match the expected count ±tolerance.

- **New module** `prestaged_manifest.py` (+182) + JSON Schema
  (`prestaged_manifest.schema.json`, +56).
- Integration: `prestaged.py` (+89) and `prestaged_types.py` (+7).
- **2 new metrics** for manifest hit/miss and row mismatch.
- **Tests**: `test_prestaged.py` (+219).

---

## Theme 2 — Horizon 3 "D-series": hydration orchestration

Replaces the monolithic serial prestaged-hydrate Job with a tier-ordered,
bounded-parallelism per-source fan-out governed by an in-cluster
dispatcher. Breaking one source no longer blocks the other 61. All
landed 2026-04-16, with the D.1↔D.3 wiring following on 04-16 afternoon.

### #322 (`34a9d68`) — D.1 Dispatcher + per-source Jobs fan-out

- **New**: `src/dk_data/ingestion/hydrate_dispatcher.py` — reads
  `SOURCE_LOAD_ORDER`, groups by tier, applies per-source Jobs via the
  Kubernetes Python client (already a runtime dep). Caps in-flight with
  a `threading.Semaphore` at `--max-parallel` (default 4). Watches each
  Job to a terminal state, skips sources flagged in
  `meta.hydration_backlog` (C.3), and records every outcome to
  `meta.transform_runs` under `procedure_name='dispatcher:<source_id>'`.
  Failed Jobs increment the backlog `failure_count`.
- **New kubernetes RBAC**: `k8s/apps/hydrate/base/` — dispatcher Job +
  ServiceAccount + Role + RoleBinding (`batch/jobs: create,get,list,watch`
  in `dk-data-prod`; `pods/log` read-only for post-mortem).
- **New renderer**: `scripts/render_hydrate_jobs.py` (idempotent) reads
  `deploy/hydrate/sources.yaml` and emits one
  `job-hydrate-<name>.yaml` per source plus an auto-generated
  `kustomization.yaml`. **62 rendered per-source Jobs** shipped in the
  same PR.
- **Registry**: `deploy/hydrate/sources.yaml` — 62 current sources in
  `SOURCE_LOAD_ORDER`.
- `src/dk_data/ingestion/prestaged.py` gains `--source <id>` alias
  (takes precedence over `--source-list`) and `--run-label` override so
  the dispatcher can pin one run label across every child Job.
- Inherits H1's hardened placement pattern: `dk.role=general` +
  `NotIn master` fallback (later removed by D.4), production-critical
  priority, ephemeral-storage 5Gi/20Gi, nvidia GPU toleration.
- **5 unit tests** covering tier+depends_on ordering, quarantine
  short-circuit, semaphore parallelism cap, `transform_runs` terminal-
  state write, backlog `record_failure` on failed Job. Full fakes —
  no kube/Postgres required.
- **Temporary allowlist** for `DK_BUDGET_REMAINING` /
  `DK_BUDGET_TOTAL_CAPACITY` (D.3 declared them; dashboard panel still
  TODO at this point — later removed by PR #339).

### #318 (`9216a55`) — D.2 Declarative descriptor schema + `meta.source_registry`

The data projection every downstream consumer reads from:

- **Schema**: `.dk/sources/_schema.yaml` (v1 human-readable sketch +
  embedded JSON-Schema so the spec and validator never drift).
- **Migration 233** — `meta.source_registry`:
  - PK `name` constrained to regex `^[a-z][a-z0-9_]*$`
  - CHECK constraints on `domain / tier / status`
  - JSONB for `depends_on / fetch / consumes`
  - Role-conditional GRANTs
  - Idempotent
- **New module**: `src/dk_data/ingestion/source_registry.py` (+626):
  frozen `SourceDescriptor` dataclass, hand-rolled validator (no new
  `jsonschema` dep), `load_all` walker, `sync_to_db` upsert that leases
  from `get_connection_pool()` (FR-030 — never raw `psycopg2.connect`).
- **New CLI**: `dk data source --sync | --list [--tier N]`.
- **3 seed descriptors**: `chembl_molecules.yaml` (mol/2/postgres_dump),
  `cms_open_payments.yaml` (hcs/5/http_csv, priority:top15),
  `openfda_enforcement.yaml` (mol/2/http_json_paginated).
- **Tests**: `tests/unit/test_source_registry.py` (+244) — 6 tests
  (happy path, missing fields, invalid tier, upsert via injected fake
  conn, `load_all` skips `_schema.yaml`, round-trip equality).
- **Gotcha**: had to quote `"fetch"` in DDL — PostgreSQL reserves
  `FETCH` for cursor syntax. Fixed mid-PR.

### #320 (`8c4e8c7`) — D.3 Admission control by budget (`meta.resource_budget`)

- **Migration 234** — `meta.resource_budget` (`budget_key` PK,
  `total_capacity`, `reserved`, `updated_at`). Seeded with:
  | key | capacity | maps to |
  |---|---|---|
  | `wal_headroom` | 100 | % of WAL headroom |
  | `db_connections` | 20 | matches C.5 `dk_data_hydration` pool |
  | `concurrent_restores` | 4 | matches dispatcher `--max-parallel` |
  | `seaweedfs_iops` | 1000 | SeaweedFS IOPS ceiling |
- **New module**: `src/dk_data/ingestion/resource_budget.py` (+504):
  - `ResourceBudget` class with `try_reserve / release / snapshot /
    publish_snapshot` (Prometheus gauges) and `decorate_dispatch`.
  - **Deadlock protection**: uses `SELECT ... FOR UPDATE` with a sorted
    lock order across budget rows so concurrent workers never collide.
  - FR-030 compliant; docstring deliberately phrased to avoid the
    literal `psycopg2.connect(` token that tripped the grep gate.
- **New metrics**: `DK_BUDGET_*` gauges + `DK_BUDGET_RESERVATION_DENIED_TOTAL`
  counter (allowlisted — alert-driven).
- Dashboard panel in `grafana/dashboards/applications/
  dk-data-fe-resource-budget.json` (stub, filled in later by PR #339).
- **7 unit tests** in `tests/unit/test_resource_budget.py`.
- *Deferred* integration with D.1 dispatcher — wired by #341.

### #317 (`aeb066a`) — D.4 Structural data-plane isolation via node taint

- `deploy/jobs/prestaged-hydrate.yaml` — **removes** the
  `kubernetes.io/hostname NotIn [k3s-master-1]` fallback
  `nodeSelectorTerm`. Keeps only `dk.role In (general)`.
- **Intentional non-toleration**: the pod does *not* tolerate
  `node.datakinetic.com/role=control-plane:NoSchedule`. That
  non-toleration is the structural guarantee — any pod without the
  toleration physically cannot land on a control-plane node.
- **New runbook**: `docs/runbooks/node-role-isolation.md` (+181) —
  label+taint model, verification commands (`describe-node`, scheduler
  dry-run with a tolerations-less dummy Pod), procedure to extend
  taxonomy (e.g. future `gpu-inference` role).
- **New**: `k8s/apps/security/policy-exceptions/
  hydrate-taint-exception.yaml` — PolicyException stub for a future
  `require-role-toleration` ClusterPolicy. Ships in Audit inheritance;
  no enforcement today.
- Coordination hook: the cluster-side taint itself is dk-alchemy #660.

### #321 (`aee3830`) — D.5 Per-source DopplerSecret CRs

Splits the monolithic `dk-data-secrets` (blast-radius-of-everything)
into **six per-source DopplerSecret CRs** so rotating one key never
touches another source:

| CR | Key | Doppler config |
|---|---|---|
| `dk-data-secrets-drugbank` | `DRUGBANK_API_KEY` | `drugbank` |
| `dk-data-secrets-openfda` | `OPENFDA_API_KEY` | `openfda` |
| `dk-data-secrets-ncbi` | `NCBI_API_KEY` | `ncbi` |
| `dk-data-secrets-openalex` | `OPENALEX_API_KEY` | `openalex` |
| `dk-data-secrets-uspto` | `USPTO_API_KEY` | `uspto` |
| `dk-data-secrets-ttd` | `TTD_API_KEY` | `ttd` |

- Each CR follows the canonical dk-alchemy DopplerSecret shape
  (`tokenSecret + project + config + managedSecret + single-entry
  secrets list`).
- Staging overlay patches flip each CR to `<source>-stg`.
- **Proof-of-pattern**: `deploy/jobs/prestaged-hydrate.yaml` references
  `DRUGBANK_API_KEY` via `valueFrom` against `dk-data-secrets-drugbank`
  specifically (not `envFrom` the monolith).
- **New runbook**: `docs/runbooks/credential-rotation.md` (+215) covers
  adding a new per-source secret, rotating a single key, and which keys
  legitimately stay monolithic (`POSTGRES_*`, `JWT_SECRET`).
- The full fetcher CronJob sweep to use these CRs lands in #323.

### #341 (`641fe6a`) — D.1 ↔ D.3 integration wiring

The single-line integration that was deferred from #320:

- `self._dispatch = self.budget.decorate_dispatch(self._dispatch_one)`
- **New `_DISPATCH_IN_FLIGHT` sentinel** disambiguates the three possible
  outcomes: `None` (budget denied), `_DISPATCH_IN_FLIGHT` (Job created),
  or a `StepResult` (short-circuit terminal). Without the sentinel,
  `None` would collide between "budget denied" and "Job created — move
  to in-flight."
- In `dispatch_all`, a `None` outcome releases the semaphore slot,
  leaves the source unmarked (so the next poll tick retries),
  increments `DK_HYDRATION_DISPATCH_DEFERRED_TOTAL{source}`, and breaks
  the ready loop so the poll-interval sleep provides natural
  backpressure. **No busy-spin on a saturated budget.**
- `__init__` takes an optional `budget` kwarg; production path
  lazy-creates a `ResourceBudget` so importing the module never touches
  the pool. `_owns_budget` mirrors the existing `_owns_writer_conn`
  ownership pattern.
- `close()` cascades to `budget.close()` when the dispatcher owns the
  budget (returns the leased pool conn — FR-030).
- **New counter**: `DK_HYDRATION_DISPATCH_DEFERRED_TOTAL{source}`.
- **Tests**: new `FakeBudget` mirroring the `decorate_dispatch` contract
  + 5 new tests (admit-wrap, deny-defer-retry with counter tick,
  persistent-deny never calls underlying fn, release-after-success,
  release-on-exception).

---

## Theme 3 — "E-series" Wave B source onboarding

15 new / aligned data sources (top-15 priority list), wired end-to-end
with fetcher + source loader + descriptor YAML + CronJob manifest +
`main.py` SOURCES dict + `fetchers/__init__.py`.

### #340 (`36f6f57`) — Seed 14 READMEs (prep work)

- Lands `.dk/sources/<name>/README.md` stubs for 14 of the 15 top-15
  sources (cms_open_payments skipped — descriptor already seeded by D.2).
- `fda_enforcement` README notes the existing `openfda_enforcement.yaml`
  descriptor and flags the naming reconciliation.
- GH tracking issues #324–#338 opened with labels `source:stub +
  domain:<d> + tier:T1|T2 + priority:top15`.
- **Pure stub seeding** — no code / infra / SQLMesh changes.

### #343 (`9056274`) — Align cms_open_payments / pecos / nih_reporter descriptors

These three already had live fetchers + CronJobs in prod; this PR only
closes the D.2 gap:

- Missing descriptor YAMLs (`pecos.yaml`, `nih_reporter.yaml`) with the
  D.2 schema (`name / domain / tier / depends_on / fetch / schedule /
  credentials_ref / expected_row_count_fn / sla_seconds / manifest /
  consumes`).
- READMEs promoted to `status: live`.
- **Migration 235** (`235_seed_source_registry_wave_b.sql`) seeds
  `meta.source_registry` for all three. Idempotent via `ON CONFLICT
  (name) DO NOTHING`, with `statement_timeout=30s / lock_timeout=10s`.

### #344 (`9299799`) — fda_enforcement + fda_shortages fetchers

- `fda_enforcement` → `mol_raw.fda_enforcement` (daily, drug recalls
  Class I/II/III, endpoint `/drug/enforcement.json`).
- `fda_shortages` → `mol_raw.fda_shortages` (weekly, drug supply
  disruptions, endpoint `/drug/shortages.json`).
- Follows the existing `openfda_faers/labels` pattern: paginated
  `skip+limit`, urllib3 retry for 429, dedup via `response_body_hash`.
- Reads `OPENFDA_API_KEY` from DopplerSecret `dk-data-secrets-openfda`
  (per D.5).
- Deletes the stale `openfda_enforcement.yaml` (renamed per plan
  naming convention).

### #345 (`8fb5ef2`) — CMS hospital quality trio (HAC / HRRP / VBP)

Three CMS Provider Data quality-program sources completing the
hospital-quality trio needed for `hcs_gold` facility scorecards:

| Source | Dataset ID | Schedule |
|---|---|---|
| `cms_hac_reduction` | `yq43-i98g` | Feb 1 00:00 UTC annually |
| `cms_hrrp` | `9n3s-kdb3` | Feb 1 00:15 UTC annually |
| `cms_vbp` | `ypbt-wvdk` | Feb 1 00:30 UTC annually |

- Staggered 15 min apart to spread load.
- Extends `cms_downloader.py` with +20 lines adding the dataset IDs to
  `CMS_DATASET_REGISTRY`.
- Targets `hcs_raw`. Each source: fetcher (~180 LOC) + source loader
  (~71 LOC) + descriptor + CronJob.

### #346 (`afd8c82`) — 4 international health data sources (T1, no auth)

| Source | Target | Schedule |
|---|---|---|
| `who_ghed` | `hcs_raw.who_ghed` | annual |
| `worldbank_health` | `hcs_raw.worldbank_health` | annual (v2 REST API, `indicator_code` column) |
| `oecd_health` | `hcs_raw.oecd_health` | annual (SDMX protocol) |
| `pbs_australia` | `mol_raw.pbs_australia` | monthly |

- All T1 free/open — no authentication required.
- Bulk CSV downloads use the **C.4 pattern**: `stream=True` +
  `Content-Length` guard.
- Two squashed fix commits in the PR for ruff lint (unused imports,
  `F841` suppression on OECD SDMX dimension vars held for future use).
- **Net +1,499 LOC**.

### #347 (`f8f4357`) — ema_epar, health_canada_dpd, research_orgs_ror

Three mixed-type sources (one bulk CSV, one ZIP/TXT, one Zenodo JSON):

| Source | Target | Notes |
|---|---|---|
| `ema_epar` | `mol_raw.ema_epar` | bulk CSV, EMA EPAR assessment reports |
| `health_canada_dpd` | `mol_raw.health_canada_dpd` | ZIP/TXT, Canadian DPD |
| `research_orgs_ror` | **`hcp_raw.research_orgs_ror`** | Zenodo JSON (introduces `hcp_raw` schema) |

- **Migration 235** in this PR creates the 3 tables *and* creates the
  `hcp_raw` schema.
- **⚠️ Duplicate migration number**: PRs #343 and #347 both use
  `235_*.sql`. Unresolved at merge. One will need renumbering.

### `a1e7ca8` — Migration 236 raw tables (committed after prod apply)

Creates the 9 raw tables for Wave B (3 CMS + 2 FDA + 4 international).
Commit message is explicit: *"Applied manually to prod on 2026-04-17;
this file ensures reproducibility on staging and future environments."*
— so **prod was hand-migrated first**, file committed after.

Minimal schema:

```sql
CREATE TABLE IF NOT EXISTS <schema>.<table> (
  id BIGSERIAL PRIMARY KEY,
  api_endpoint TEXT,
  response_body JSONB NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- CMS adds: source_year INT
-- worldbank_health adds: indicator_code TEXT
```

### `9f48402` — Image tag bump (manual)

Manual update of `k8s/overlays/prod/kustomization.yaml` to
`main-a1e7ca8`. Normal manifest-update step failed on branch protection
(dk-alchemy #650), so Nick bumped it by hand.

### `937c9f6` — Wave B activation hotfix

Two real problems surfaced when sources tried to actually run:

1. **Migration 237** — The Wave B loaders use the standard raw-layer
   INSERT pattern expecting `request_id, response_status,
   response_body_hash, source_id, api_version, request_params`, but
   migration 236 created minimal schemas without them. Migration 237 is
   a PL/pgSQL `DO` block that loops the 9 tables and runs
   `ADD COLUMN IF NOT EXISTS` for each column, then creates unique
   indexes on `response_body_hash WHERE NOT NULL` for idempotency.
   **Applied to prod via `kubectl exec` first, then committed.**
2. **EMA EPAR fetcher** (`ema_epar.py`, +37 −4) — single CSV URL was
   returning 404 (EMA changed their endpoint). Replaced with a 3-URL
   fallback loop (XLSX primary → CSV fallback → legacy URL), matching
   the working `ema_mol.py` pattern. Returns `source_unavailable` on
   all-404 rather than hard-failing.
3. (Noted in commit message but not in diff) **Grafana API key rotated**
   in Doppler — old key returned 401; new service-account token created
   via Grafana admin API.

---

## Theme 4 — Observability surface (dashboards + alerts)

### #306 (`cb07ba4`) — Own dashboards in-repo via push-via-API ⭐ MASSIVE

**This is the flip-point for Grafana dashboard ownership** — from now
on, dashboards are sourced from the repo and pushed by CI, not edited
in the Grafana UI.

- **Renames 6 existing dashboards** with the `dk-data-fe-` prefix:
  `adapter-telemetry`, `api-services`, `cms-pipeline-health`,
  `pipeline-sources`, `platform-status`, `transformations`.
- **Adds 10 new dashboard files**:
  - `dk-data-fe-adapter-telemetry.json` — 699 lines
  - `dk-data-fe-api-services.json` — 149
  - `dk-data-fe-cms-pipeline-health.json` — 2,107
  - `dk-data-fe-hydration-backlog.json` — 46 (stub; filled in by #339)
  - `dk-data-fe-hydration.json` — 46 (stub)
  - `dk-data-fe-pipeline-sources.json` — 3,584
  - `dk-data-fe-platform-status.json` — 2,248
  - `dk-data-fe-resource-budget.json` — 46 (stub)
  - `dk-data-fe-seaweedfs-artifacts.json` — 46 (stub)
  - `dk-data-fe-source-registry.json` — 46 (stub)
  - `dk-data-fe-transformations.json` — 1,454
  - `dk-data-fe-wal-pressure.json` — 46 (stub)
- **New scripts**:
  - `grafana/scripts/sync-all.sh` (+383) — push dashboards to Grafana
    via API.
  - `grafana/scripts/validate.sh` (+464) — pre-push validation.
  - `grafana/scripts/import-dashboard.sh` (+176) — one-off import.
  - `grafana/scripts/lib/grafana-api.sh` (+512) — shared API helper.
  - `scripts/rename-dashboards.py` (+85) — one-shot rename helper.
  - `scripts/render-stub-dashboards.py` (+124) — stub dashboard
    generator for in-progress features.
- **New CI workflow** `.github/workflows/grafana-dashboards.yaml` (+149)
  replacing `grafana-uplift.yaml` (-50).
- `tests/observability/test_dashboard_smoke.py` updated (+11/-1).
- **Net +12,422 / −10,052** (mostly moves during the rename).

⚠️ **Workflow implication**: if you edit a dashboard via Grafana UI, it
will be stomped by the next `grafana-dashboards.yaml` sync. Use the
`grafana/scripts/sync-all.sh` flow instead.

### #339 (`a3618df`) — Fill in real panel content for 4 Grafana dashboards

Replaces the TODO stubs with live panels for plan.md §J.3 dashboards
(all metrics already emit on main from Horizon 2/3):

- **`hydration-backlog`** (+387): 24h DLQ stats + per-source failure /
  quarantine / skip timeseries driven by `dk_hydration_dlq_{added,
  quarantined, skipped}_total`, plus a `meta.hydration_backlog` table
  panel and an `--unquarantine` operator note.
- **`wal-pressure`** (+266): postgres-backed current/historical
  `pct_used` gauge + timeseries (no prom gauge emitted — throttle reads
  `meta.wal_pressure` directly), per-source pause-budget exhaustion
  from `dk_wal_source_budget_exhausted_total`, hysteresis-threshold
  reference stats, hysteresis-band explainer.
- **`seaweedfs-artifacts`** (+224): source-level timeseries for
  `dk_artifact_{changed, size_mismatch, provenance_write_errors}_total`
  and a `DISTINCT ON` provenance-row table from
  `meta.artifact_provenance`.
- **`resource-budget`** (+386): 4-key bar-gauge row (wal_headroom,
  db_connections, concurrent_restores, seaweedfs_iops) plus
  reservation-denial and utilization timeseries driven by
  `dk_budget_{remaining, total_capacity, reservation_denied_total}`;
  `meta.resource_budget` table.

Also **drops the two temporary `DASHBOARD_ALLOWLIST` entries**
(`DK_BUDGET_REMAINING` / `DK_BUDGET_TOTAL_CAPACITY`) added under #322 —
the resource-budget dashboard now consumes them directly.

Validation: `grafana/scripts/validate.sh` → 0 errors (warnings are
friendly-alias datasource UIDs, same as the existing
`dk-data-fe-hydration.json`). `test_dashboard_smoke` +
`test_metric_coverage` → 20/20 pass.

### #304 (`650dce5`) — Missing alert rules

4 new PrometheusRule files:

- `dk-data-cnpg.yaml` (+53) — CNPG operator health alerts.
- `dk-data-hydration-jobs.yaml` (+71) — hydrate job failures, DLQ
  quarantine events.
- `dk-data-node-pressure.yaml` (+72) — node-level memory/disk/CPU
  pressure.
- `dk-data-pgbouncer.yaml` (+53) — pool saturation, auth failures.

### `8d221df` — grafana/folders/folders.yaml (7-line unblocker)

The `grafana-dashboards` workflow's sync script warned `"Folders file
not found"` and failed to push all 12 dashboards. The `applications`
folder already exists in Grafana (created by dk-alchemy), but the sync
script needs a local declaration to function. This ships the one-liner
to declare it.

---

## Theme 5 — DkDataClient retry-with-backoff (#281 / #308)

`24c96ab` — client-side resilience for transient PostgREST / PgBouncer
failures.

**Retry policy** (one automatic retry; caller owns strategy beyond that):

| Class | Trigger | Wait |
|---|---|---|
| 503 + Retry-After | PostgREST rolling update | `Retry-After` header seconds, capped at 5s |
| 429 + Retry-After | Rate limit | Same; automatic retry *before* raising `DkDataRateLimitError` so the caller's existing handler still runs |
| Transport error | Connection reset / timeout | 0.5s + 0-0.5s jitter |
| 401 / 403 / 404 / 410 / other 5xx | Semantic / server bug | **Not retried** |

**Kept in lockstep across languages**:

- Python: `packages/dk-data-client/python/dk_data_client/client.py`
  (+83), tests `test_client.py` (+305).
- TypeScript: `packages/dk-data-client/typescript/src/client.ts`
  (+106), tests `client.test.ts` (+201).

Tests cover: 200 happy path with no sleep, 503/429 with Retry-After,
header capping at 5s, missing-Retry-After default, transport-error
retry-then-succeed, transport-error-twice raises
`DkDataServerError(status=0)`, explicit no-retry for 401/403/404/410/500.

**Net +655 / −40 LOC across both clients + test suites.**

---

## Theme 6 — k8s activation fixes (all 04-17, direct to main)

After the D-series landed on 04-16, ArgoCD sync broke in several ways.
These four commits unblocked it:

### `67e793d` — Swap `db-init` image to CNPG-approved registry

Kyverno `restrict-image-registries` blocks `postgres:16.4` (Docker Hub)
from `dk-data-prod`. ArgoCD sync of the full `dk-data-prod` Application
fails because `db-init` is a PreSync hook that must pass admission first.

Swap to `ghcr.io/cloudnative-pg/postgresql:16.4` — same psql 16.4 binary,
same Postgres version, from the infrastructure registry that CNPG
already uses. This image is in Kyverno's allowed set (the CNPG Cluster
pods run it).

> The `disallow-latest-tag` JMESPath error on `initContainers[]` is a
> Kyverno autogen bug (`nil` array → JMESPath type error), flagged for
> dk-alchemy — not this repo's issue.

### `56be8cc` — Replace `prod-<sha>` placeholder across 64 files

The D.1 renderer generated 63 per-source Job manifests + the dispatcher
with `image: ghcr.io/data-kinetic/dk-data:prod-<sha>` — the `<sha>`
placeholder was never substituted, causing `InvalidImageName` on the
live cluster after ArgoCD sync.

**Bulk-replaced** to
`ghcr.io/data-kinetic/dk-data-fe/job-trigger:prod-a89d6ac` (the current
production image that includes the full `dk_data` package +
`postgresql-client-16`). Same fix applied to
`deploy/jobs/prestaged-hydrate.yaml`.

**64 files updated, zero placeholders remain.**

### `9206200` — Exclude hydrate Jobs from ArgoCD sync (RBAC stays)

ArgoCD treats never-run `batch/Jobs` as `Progressing` health and blocks
the entire sync waiting for them to complete — which they never will
(they're triggered manually via `dk data hydrate run`).

**Split `k8s/apps/hydrate/`**:

- `rbac/` — ServiceAccount + Role + RoleBinding (ArgoCD-synced, always
  present so the dispatcher can use the kube API).
- `base/` — dispatcher + 62 per-source Jobs (applied manually, NOT in
  ArgoCD's manifest set).

This unblocked the `dk-data-prod` Application sync that had been stuck
in `Progressing` for 30 min waiting for `hydrate-dispatch` health.

### #342 (`a89d6ac`) — Probes + resource limits for Kyverno Wave 4

Adds resource limits to two containers that violated dk-alchemy's
`require-resource-limits` ClusterPolicy (Wave 4 audit, 2026-04-16):

- `postgrest` init container `jwt-secret-validator`: was missing a
  `resources` block entirely. Matched by the policy's
  `autogen-check-init-container-limits` rule via the owning ReplicaSet.
  Budget is minimal (16Mi/32Mi, 10m/50m) — container runs `wc -c` once
  and exits.
- `db-init` Job container: only Job/CronJob manifest in the repo with
  no `resources` block at all. Sized to match the sibling `db-migrate`
  PreSync Job (64Mi/256Mi, 50m/200m) — both are idempotent DDL-only
  containers against an already-provisioned CNPG cluster.

**Out of scope for this PR (644 of 686 `dk-data-*` audit fails)**:
Batch Job / CronJob Pods flagged by `require-probes`. Adding
`livenessProbe / readinessProbe` to run-to-completion batch workloads
is semantically wrong (probes gate Service endpoints and restart
containers, neither of which applies to Jobs). Policy needs a
ClusterPolicy exclude for `Kind: Job` + `Kind: CronJob` (dk-alchemy-side)
or a namespaced `PolicyException` here (precedent:
`hydrate-taint-exception.yaml`).

---

## Theme 7 — The foundational monster commit: `dfeee7f` (#309)

**7,644 insertions in one PR** — the "Stage 7 + Stage 8 repair" commit
that ships the prestaged-hydration module everything in Themes 1–2
builds on top of. Landed 2026-04-16 early in the day.

What's in it:

| Path | Purpose | LOC |
|---|---|---|
| `src/dk_data/ingestion/prestaged.py` | Core prestaged hydrator | 822 |
| `src/dk_data/ingestion/load_order.py` | `SOURCE_LOAD_ORDER` + tier/depends_on graph | 425 |
| `src/dk_data/ingestion/wal_throttle.py` | WAL-pressure pause loop (the stub C.2 replaces) | 182 |
| `src/dk_data/ingestion/source_backfill.py` | Per-source backfill helper | 51 |
| `src/dk_data/ingestion/transform_runs_writer.py` | Writes to `meta.transform_runs` | 120 |
| `src/dk_data/ingestion/prestaged_types.py` | Shared types / dataclasses | 105 |
| `src/dk_data/ingestion/prestaged_safety.py` | Safety preconditions | 53 |
| `sql/migrations/229_transform_runs_status_details.sql` | `transform_runs` status detail | 93 |
| `sql/migrations/230_hydration_dashboard_view.sql` | Dashboard view | 136 |
| `deploy/cronjobs/prestaged-hydrate-cronjob.yaml` | Monolithic cronjob (later D.1-superseded) | 77 |
| `dashboards/hydration-dashboard.html` | Static HTML dashboard | 611 |
| `plan.md` | **The plan document** the rest of the work indexes against | 697 |
| `.dk/templates/*` | 8 templates (bug report, contract, gate vocab, stage status, etc.) | ~900 |
| `.dk/specs/005-backfill-refactor/verification/stage-7.md` | Verification spec | 78 |
| `.github/workflows/ci.yaml` | CI for prestaged tests | 72 |
| `tests/ingestion/test_load_order.py` | Load order tests | 328 |
| `tests/ingestion/test_prestaged_discovery.py` | Discovery tests | 187 |
| `tests/ingestion/test_prestaged_fallback.py` | Fallback tests | 174 |
| `tests/ingestion/test_prestaged_idempotency.py` | Idempotency | 198 |
| `tests/ingestion/test_prestaged_validate.py` | Validation | 109 |
| `tests/ingestion/test_wal_throttle.py` | WAL throttle (the 8-test baseline C.2 grew to 18) | 231 |
| `tests/load/test_prestaged_e2e.py` | End-to-end load test | 277 |
| `tests/fixtures/prestaged/` | Fixtures + `generate_fixtures.sh` | 97 |
| `scripts/prestaged_smoke.sh` | Smoke test shell script | 36 |
| `Dockerfile` | +10 additions | — |
| `CLAUDE.md` | +7 additions | — |
| `pyproject.toml` | +2 additions | — |

---

## Theme 8 — Supporting ops / docs

### `3765f63` (#323) — Sweep fetcher CronJobs to per-source DopplerSecrets

The follow-up to D.5 (#321). Wires each fetcher that actually consumes a
per-source API key to its dedicated DopplerSecret CR instead of
inheriting from the monolithic `dk-data-secrets`. Rotating a source's
key now touches one Secret and one fetcher.

**Swept (6 manifests)**:

| Manifest | → DopplerSecret | Key |
|---|---|---|
| `fetch-drugbank` | `dk-data-secrets-drugbank` | `DRUGBANK_API_KEY` |
| `fetch-openfda-faers` | `dk-data-secrets-openfda` | `OPENFDA_API_KEY` |
| `fetch-openfda-labels` | `dk-data-secrets-openfda` | `OPENFDA_API_KEY` |
| `fetch-openalex-ci` | `dk-data-secrets-openalex` | `OPENALEX_API_KEY` |
| `fetch-uspto-patents` | `dk-data-secrets-uspto` | `USPTO_API_KEY` |
| `fetch-pubmed` | `dk-data-secrets-ncbi` | `NCBI_API_KEY` |

**Not swept** (documented in PR body):
- `fetch-uspto-ci` — fetcher does not read `USPTO_API_KEY`.
- `fetch-uspto-trademarks` — uses `USPTO_TSDR_API_KEY` (separate secret).
- `fetch-ttd` — TTD is bulk-file; `TTD_API_KEY` unused in code.
- `fetch-europepmc` — does not read `NCBI_API_KEY`.

The monolithic `dk-data-secrets` `envFrom` stays in place for shared DB
credentials (`POSTGRES_HOST/USER/PASSWORD/DB/PORT`) — splitting those is
a separate effort. Explicit `env` entries override any inherited value
from `envFrom`, so there is no double-injection hazard.

**Validation**: `kubectl kustomize k8s/overlays/{prod,staging}/` both
render 230 manifests cleanly, `yaml.safe_load_all` parses each.
**Diff is pure-additive** (72 lines across 6 files). Closes #319.

### #307 (`39667a5`) — Zip extraction + Content-Length guard

- `cms_downloader.py` (+340 −59): extracts **all files** from a ZIP
  (previously only the first), adds Content-Length guard for download
  integrity.
- Updates to `fetch_cms_puf.py`, `cms_nppes.py`, `npi_registry.py` to
  consume the new interface.
- New test `test_cms_downloader_zip_extraction.py` (+253).
- 1 new metric.

### #303 (`1aa8292`) — Isolate + resilient Job manifests

New `deploy/jobs/prestaged-hydrate.yaml` (+221) — hardened Job manifest
(node selector + tolerations + resource budget + priority class).
Serves as the pattern D.1 (#322) later fans out per-source.

### #302 (`77b8142`) — Procurement-tracking issue bootstrap

`scripts/open-procurement-issues.sh` (+69) — idempotent GitHub CLI
script that creates procurement issues for paid data sources.

### #299 (`bb89b8e`) — GH label taxonomy bootstrap

`scripts/bootstrap-gh-labels.sh` (+58) — idempotent script that creates
the full `source:* / domain:* / tier:* / priority:*` label taxonomy in
the repo so downstream PRs (like #340's 14 tracking issues) can apply
them.

### #301 (`5ee80eb`) — Lessons entries

`.dk/memory/lessons.md` (+16) — documents two incidents:
- Hydration-specific failure modes.
- ArgoCD `selfHeal` caused an outage by re-creating a deleted resource
  mid-debugging.

### #300 (`1d631a9`) — CNPG operator deadlock runbook

`docs/runbooks/cnpg-operator-deadlock.md` (+337) — recovery procedure
for when the CNPG operator deadlocks (observed incident).

### Five tiny `docs(plan)` checkbox commits

`51a37d8`, `94ed9f7`, `0d731db`, `8287839`, `2521179` — all are small
edits to `plan.md` marking sections complete as PRs merged throughout
2026-04-16. Net a few KB across all five.

---

## Cross-cutting observations

### Migration number hygiene

| # | Taken by | PR | Landed |
|---|---|---|---|
| 229 | `transform_runs_status_details.sql` (dfeee7f) | #309 | 04-16 |
| 229 | `artifact_provenance.sql` (C.4) | #313 | 04-16 |
| 230 | `hydration_dashboard_view.sql` (dfeee7f) | #309 | 04-16 |
| 231 | `wal_pressure_view.sql` (C.2) | #315 | 04-16 |
| 232 | `hydration_backlog.sql` (C.3) — renumbered from 231 | #316 | 04-16 |
| 233 | `source_registry.sql` (D.2) | #318 | 04-16 |
| 234 | `resource_budget.sql` (D.3) | #320 | 04-16 |
| 235 | `seed_source_registry_wave_b.sql` (Wave B) | #343 | 04-17 |
| 235 | `new_sources_ema_epar_hc_dpd_ror.sql` | #347 | 04-17 |
| 236 | `wave_b_raw_tables.sql` | post-prod commit | 04-17 |
| 237 | `fix_wave_b_raw_table_columns.sql` | hotfix | 04-17 |

⚠️ **Unresolved**: 229 appears twice (dfeee7f + C.4) and 235 appears
twice (#343 + #347). One of each pair will need renumbering before
staging replay.

### Loader↔schema contract not CI-enforced

Migration 236 shipped Wave B tables with a minimal schema; loaders
needed 6 more columns; migration 237 patched it after the image was
already deployed. This drift cost a kubectl-exec fix to prod. A CI
check that the loader SQL templates against the committed schema would
have caught it.

### Prod-first, commit-second pattern

Three commits explicitly state the change was applied to prod first
and then committed for reproducibility:

- `a1e7ca8` — migration 236 (applied via kubectl exec)
- `937c9f6` — migration 237 (applied via kubectl exec)
- `9f48402` — image tag bump (manual to bypass branch protection)

This is worth flagging in review; staging drift is possible until those
migrations are replayed cleanly.

### FR-030 discipline (pool-only DB access)

Every new DB-touching module Nick added uses `get_connection_pool()` /
`init_connection_pool()` — no raw `psycopg2.connect()`. Several
docstrings are even phrased to avoid the literal `psycopg2.connect(`
string because there's a grep-gate in CI that rejects it. Nick's work
is clean on this front.

### Dashboard ownership flip

Post-#306, Grafana dashboards are repo-sourced and CI-pushed. The
workflow file is `.github/workflows/grafana-dashboards.yaml`. The
old `grafana-uplift.yaml` is gone. Editing via Grafana UI will be
silently reverted.

### Relationship to Philipp's concurrent work

- **WAL circuit breaker (#289, `1cf9a54`)** — sibling to Nick's C.2
  (#315). Philipp's work is at transform / backfill entry points and
  checks WAL dir size + archiver health; Nick's is inside
  `wal_throttle.py` and replaces the `wal_pressure()` stub with a live
  view. They do not touch the same files but they do overlap in intent.
- **`prestaged.py`** — heavily edited by Nick (created in `dfeee7f`,
  extended in C.3 `#316` by +222 LOC). Any further edits from your side
  will rebase.
- **DkDataClient retry (#308)** — directly relevant to the BehaviorLabs
  integration per Philipp's project priorities. Python and TypeScript
  clients now share identical retry policy.

---

## Commit index (44 commits, chronological oldest → newest)

| SHA | Date | Subject |
|---|---|---|
| `cb07ba4` | 04-16 | feat(observability): own dashboards in-repo (push-via-API) (#306) |
| `bb89b8e` | 04-16 | chore(gh): ship idempotent GH label taxonomy bootstrap (#299) |
| `1d631a9` | 04-16 | docs(runbook): CNPG operator deadlock recovery (#300) |
| `5ee80eb` | 04-16 | docs(lessons): hydration + ArgoCD selfHeal incidents (#301) |
| `77b8142` | 04-16 | chore(gh): ship procurement-tracking issue bootstrap (#302) |
| `1aa8292` | 04-16 | feat(hydrate): isolate + resilient Job manifests (#303) |
| `650dce5` | 04-16 | feat(observability): missing alert rules (#304) |
| `39667a5` | 04-16 | fix(ingest): extract all files from zip + Content-Length guard (#307) |
| `323242c` | 04-16 | feat(pgbouncer): dedicated dk_data_hydration pool with budget math (C.5) (#310) |
| `2a3103a` | 04-16 | feat(storage): SeaweedFS boto3 client module (C.1) (#311) |
| `49e25dd` | 04-16 | feat(observability): hydration phase + artifact + freshness metrics (C.6) (#312) |
| `8363636` | 04-16 | feat(ingest): download integrity pipeline — meta.artifact_provenance (C.4) (#313) |
| `4ffd294` | 04-16 | feat(sqlmesh): audits at silver/gold layer boundaries (C.7) (#314) |
| `dfeee7f` | 04-16 | feat(005): prestaged hydration (Stage 7 + Stage 8 repair commits) (#309) |
| `3555592` | 04-16 | feat(hydrate): manifest row-count gate (#305) |
| `8ba06a6` | 04-16 | feat(hydrate): real WAL backpressure — meta.wal_pressure view + un-stub throttle (C.2) (#315) |
| `715bc3a` | 04-16 | feat(hydrate): DLQ + source quarantine — meta.hydration_backlog (C.3) (#316) |
| `aeb066a` | 04-16 | feat(node-policy): structural data-plane isolation via node taint (D.4) (#317) |
| `8c4e8c7` | 04-16 | feat(hydrate): admission control by budget — meta.resource_budget (D.3) (#320) |
| `aee3830` | 04-16 | feat(secrets): per-source DopplerSecret CRs (D.5) (#321) |
| `9216a55` | 04-16 | feat(sources): declarative descriptor schema + meta.source_registry (D.2) (#318) |
| `2521179` | 04-16 | docs(plan): mark H1/H2/H3 items complete against main state |
| `34a9d68` | 04-16 | feat(hydrate): dispatcher + per-source Jobs fan-out (D.1) (#322) |
| `8287839` | 04-16 | docs(plan): mark D.1 complete — PR #322 merged, Horizon 3 done |
| `0d731db` | 04-16 | docs(plan): F.2+F.5 complete via dk-cli #4; B.10 dk-alchemy #651 reopened |
| `94ed9f7` | 04-16 | docs(plan): B.10 ✅ labels live; D.4 ⚠️ #660 reopened (taint missing) |
| `3765f63` | 04-16 | chore(319): sweep fetcher CronJobs to per-source DopplerSecrets (#323) |
| `51a37d8` | 04-16 | docs(plan): #319 ✅ via PR #323; max_connections sync pending; #660 still open |
| `a3618df` | 04-16 | chore(j3): fill in real panel content for 4 Grafana dashboards (#339) |
| `36f6f57` | 04-16 | chore(E.4): seed READMEs for 14 of 15 top-15 future data sources (#340) |
| `641fe6a` | 04-16 | feat(hydrate): wire ResourceBudget.decorate_dispatch into HydrateDispatcher (D.1 + D.3) (#341) |
| `a89d6ac` | 04-16 | fix(k8s): add probes + resource limits to align with dk-alchemy Kyverno policies (#342) |
| `67e793d` | 04-17 | fix(k8s): swap db-init image to CNPG-approved registry |
| `56be8cc` | 04-17 | fix(k8s): replace prod-<sha> image placeholder with real tag across all hydrate Jobs |
| `9206200` | 04-17 | fix(k8s): exclude hydrate Jobs from ArgoCD sync (RBAC stays) |
| `8d221df` | 04-17 | fix(grafana): add folders.yaml for dashboard push workflow |
| `24c96ab` | 04-17 | feat(#281): retry-with-backoff on 503/transport errors in DkDataClient (#308) |
| `9056274` | 04-17 | feat(wave-b): align cms_open_payments, pecos, nih_reporter source descriptors (#343) |
| `9299799` | 04-17 | feat(ingestion): onboard fda_enforcement and fda_shortages fetchers (#344) |
| `8fb5ef2` | 04-17 | feat(hcs): onboard CMS hospital quality trio (HAC, HRRP, VBP) (#345) |
| `f8f4357` | 04-17 | feat: onboard ema_epar, health_canada_dpd, research_orgs_ror sources (#347) |
| `afd8c82` | 04-17 | feat: onboard 4 international health data sources (#346) |
| `a1e7ca8` | 04-17 | feat(migrations): 236 — raw tables for Wave B top-15 sources |
| `9f48402` | 04-17 | chore: update image tag to main-a1e7ca8 (Wave B sources) |
| `937c9f6` | 04-17 | fix: Wave B activation — table columns + EMA EPAR URL fallback |
