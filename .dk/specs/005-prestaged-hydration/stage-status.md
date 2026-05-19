# Feature 005-prestaged-hydration — Stage Status (as of 2026-04-14)

**Branch**: feature/005-prestaged-hydration
**Feature dir**: .dk/specs/005-prestaged-hydration/
**Pipeline state**: in-progress
**Current stage pointer**: Stage 7
**Last updated by**: extended Stages 7-10 + dashboard at 2026-04-15T02:10:00Z

## Dashboard

Stage 1 ✅  Stage 2 ✅  Stage 3 ✅  Stage 4 ✅  Stage 5 ✅  Stage 6 ✅  Stage 7 ⏳  Stage 8 ⏳  Stage 9 ⏳  Stage 10 ⏳

Legend: ✅ closed · ⏳ in progress or next up · ⏸ deferred · ⛔ blocked

---

## Stage 1 — Foundation: types, load-order, packaging scaffold ✅

**Entry gate**: feature branch created; tasks.md, plan.md, spec.md committed (commit `86048a9`)
**Exit gate type**: code-only-safe
**Exit gate**: `mypy --strict src/dk_data/ingestion/prestaged_types.py src/dk_data/ingestion/prestaged_safety.py src/dk_data/ingestion/transform_runs_writer.py` exits 0; `pytest tests/ingestion/test_load_order.py` constructs plans without errors; `docker build -f deploy/docker/ingestion.Dockerfile .` succeeds locally; migration `229_transform_runs_status_details.sql` lints and applies cleanly against a fresh Postgres; PR merged
**Task range**: T001-T003, T010-T019, T010a, T017a
**Delegated via**: /dk.implement
**PR**: not opened

- ✅ T001 — Add `postgresql-client-16` to ingestion container image
- ✅ T002 — Declare prestaged optional-deps group in pyproject.toml
- ✅ T003 — Add scripts/prestaged_smoke.sh helper
- ✅ T010 — Pydantic models: PrestagedArtifact, LoadStep, LoadPlan
- ✅ T010a — prestaged.py skeleton with named stub functions (enables Stage 2 swarm file-disjoint)
- ✅ T011 — SOURCE_LOAD_ORDER list (8 tiers, 120 sources)
- ✅ T012 — WAL_MODE_TABLES set (5 tables >5 GB)
- ✅ T013 — prestaged_manifest.schema.json
- ✅ T014 — Extend SOURCE_TO_BRONZE_MODELS with depends_on/prestaged_kind
- ✅ T015 — compute_run_id() helper (deterministic hash)
- ✅ T016 — is_restorable_target() view-safety helper
- ✅ T017a — Migration 229: add `status text` + `details jsonb` to `meta.transform_runs` (also fixes P3)
- ✅ T017 — transform_runs_writer using the post-229 schema (append-only INSERTs, skip-if-complete idempotency)
- ✅ T018 — Fixture .dump files under tests/fixtures/prestaged/
- ✅ T019 — Verify tests/conftest.py provides Postgres 16 fixture + document in quickstart.md

**Deferred from Stage 1** (with explicit reason + natural reschedule):
- (none yet)

---

## Stage 2 — Core restore engine + k8s manifest ✅

**Entry gate**: Stage 1 merged + post-merge validation passed
**Exit gate type**: code-only-safe
**Exit gate**: `pytest tests/ingestion/test_prestaged_discovery.py tests/ingestion/test_prestaged_validate.py tests/load/test_prestaged_e2e.py` green; `python -m dk_data.ingestion.prestaged --dry-run --source-list all` against a fixture emits ordered JSON plan; `kubectl --dry-run=client apply -f deploy/jobs/prestaged-hydrate.yaml` validates; PR merged
**Task range**: T020-T032
**Delegated via**: /dk.swarm (2 workers: `discovery-validate` → T020-T024,T028-T030; `dispatch-cli` → T025-T027,T031-T032)
**Budget**: `--max-budget-usd 10` per worker (default); max $20 across the stage
**PR**: not opened

- ✅ T020 — walk_prestaged_root() supporting both layouts
- ✅ T021 — validate_magic_bytes() PGDMP check
- ✅ T022 — compute_sha256() with inode cache
- ✅ T023 — group_by_table() with lexical chunk ordering
- ✅ T024 — select_highest_tier() precedence resolver
- ✅ T025 — dispatch_pg_restore() subprocess with advisory lock
- ✅ T026 — run_step() orchestrator (view-check → restore → row-count → upsert)
- ✅ T027 — CLI main(argv) per contracts/cli.md
- ✅ T028 — Unit tests: walk_prestaged_root discovers both layouts
- ✅ T029 — Unit tests: validation rejects non-PGDMP file
- ✅ T030 — Unit tests: group_by_table orders numbered + retry_ chunks
- ✅ T031 — Integration test: restore small fixture .dump
- ✅ T032 — k8s Job manifest deploy/jobs/prestaged-hydrate.yaml

**Deferred from Stage 2** (with explicit reason + natural reschedule):
- (none yet)

---

## Stage 3 — Load ordering + dependency resolution ✅

**Entry gate**: Stage 2 merged + post-merge validation passed
**Exit gate type**: code-only-safe
**Exit gate**: `pytest tests/ingestion/test_load_order.py` green covering 8-tier order, missing-hub-blocks-spoke, silver-suppresses-bronze; PR merged
**Task range**: T040-T044
**Delegated via**: /dk.implement
**PR**: not opened

- ✅ T040 — plan_load() with tier ordering + depends_on resolution
- ✅ T041 — Blocked-state propagation to downstream steps
- ✅ T042 — Unit tests: full-inventory produces 8 tiers in declared order
- ✅ T043 — Unit tests: missing hub blocks dependent spokes
- ✅ T044 — Unit tests: silver dump suppresses lower tiers

**Deferred from Stage 3** (with explicit reason + natural reschedule):
- (none yet)

---

## Stage 4 — WAL-aware throttling ✅

**Entry gate**: Stage 3 merged + post-merge validation passed
**Exit gate type**: code-only-safe
**Exit gate**: `pytest tests/ingestion/test_wal_throttle.py` green with injected stub `meta.wal_usage` rows at 80% → pause; two consecutive pauses → chunk-size halve visible in structured logs; PR merged
**Task range**: T050-T055
**Delegated via**: /dk.implement
**PR**: not opened

- ✅ T050 — wal_pressure() reading meta.wal_usage
- ✅ T051 — pause_until_below() with budget cap
- ✅ T052 — Wire pre-restore WAL check on WAL_MODE_TABLES
- ✅ T053 — Two-consecutive-pauses → halve chunk size
- ✅ T054 — Integration test: injected 80% WAL → restore pauses
- ✅ T055 — Integration test: two pauses → chunk size halved

**Deferred from Stage 4** (with explicit reason + natural reschedule):
- (none yet)

---

## Stage 5 — Fallback + idempotency + dry-run ✅

**Entry gate**: Stage 4 merged + post-merge validation passed
**Exit gate type**: code-only-safe
**Exit gate**: `pytest tests/ingestion/test_prestaged_fallback.py tests/load/test_prestaged_e2e.py` green; SC-006 rerun-is-noop test validates zero `pg_restore` subprocess calls on second invocation; `FETCHERS_SUSPENDED=patentsview` test confirms `no_source_available` path; PR merged
**Task range**: T060-T065, T070-T075
**Delegated via**: /dk.swarm (2 workers: `fallback-us4` → T060-T065; `idempotency-us5` → T070-T075)
**Budget**: `--max-budget-usd 10` per worker (default); max $20 across the stage
**PR**: not opened

- ✅ T060 — run_live_fetch() invoking main.run_ingestion
- ✅ T061 — FETCHERS_SUSPENDED parsing + no_source_available recording
- ✅ T062 — Skip out-of-scope domains in LoadPlan (FR-014)
- ✅ T063 — Unit test: missing artifact + enabled fetcher → run_live_fetch invoked
- ✅ T064 — Unit test: suspended fetcher → no_source_available, no call
- ✅ T065 — Unit test: out-of-scope source absent from LoadPlan
- ✅ T070 — --dry-run branch emitting per-step JSON lines
- ✅ T071 — Idempotency guard: skip completed steps under same run_id
- ✅ T072 — Terminal-transition JSON lines per contracts/cli.md
- ✅ T073 — Best-effort OTLP emission wrapped in try/except
- ✅ T074 — Integration test: rerun completes in <5 s with zero pg_restore calls (SC-006)
- ✅ T075 — Integration test: exactly one terminal row per source (SC-007)

**Deferred from Stage 5** (with explicit reason + natural reschedule):
- (none yet)

---

## Stage 6 — Polish, docs, lint ✅

**Entry gate**: Stage 5 merged + post-merge validation passed
**Exit gate type**: code-only-safe
**Exit gate**: `mypy --strict src/dk_data/ingestion/prestaged*.py` exits 0; CLAUDE.md updated (`git diff CLAUDE.md` mentions the hydration path); CI smoke step in PR preview exits 0; PR merged
**Task range**: T080-T084
**Delegated via**: /dk.implement
**PR**: not opened

- ✅ T080 — mypy --strict on all new prestaged*.py; fix violations
- ✅ T081 — Update CLAUDE.md data-flow diagram
- ✅ T082 — Add README snippet in src/dk_data/ingestion/README.md
- ✅ T083 — Verify checklist CHK001-CHK023
- ✅ T084 — Wire scripts/prestaged_smoke.sh into .github/workflows/ci.yml

**Deferred from Stage 6** (with explicit reason + natural reschedule):
- ⏸ T085 — dependent-task: Delete `bronze_ready`/`raw_csv` dispatch branches in prestaged.py — natural reschedule: after Stage 7 prod rehearsal confirms no CSV/parquet artifacts appeared in the inventory

---

## Stage 7 — Local-orchestrator small-source rehearsal against prod + dashboard ⏳

**Entry gate**: Stage 6 closed; SSH tunnel to prod PgBouncer reachable; venv ready locally
**Exit gate type**: runtime-green
**Exit gate**: `mol_raw.kegg_drug` restored to prod via local orchestrator; `meta.transform_runs` shows `status='completed'` for it; `pg_dump -Fc` snapshot of impacted schemas captured pre-run; dashboard renders correctly in browser; operator sign-off in `verification/stage-7.md`
**Task range**: T100, T101, T102, T103, T104, T105, T106, T121, T122, T123, T124
**Delegated via**: /dk.implement
**PR**: not opened

- ⏳ T100 — CronJob manifest + kustomize patch (optional, for future in-cluster invocations)
- ⏳ T101 — Pre-snapshot prod schemas via kubectl exec | pg_dump
- ⏳ T102 — Apply migration 229 to prod (kubectl exec | psql)
- ⏳ T103 — Open SSH tunnel from mac to prod PgBouncer
- ⏳ T104 — Local --dry-run against prod for mol_raw.kegg_drug
- ⏳ T105 — Local live restore of mol_raw.kegg_drug against prod
- ⏳ T106 — Author + sign verification/stage-7.md
- ⏳ T121 — Author migration 230 (3 hydration views + grants)
- ⏳ T122 — GRANT SELECT on hydration views to api_user (in 230)
- ⏳ T123 — Build dashboards/hydration-dashboard.html via playground skill
- ⏳ T124 — Apply migration 230 to prod + open dashboard in browser

**Deferred from Stage 7** (with explicit reason + natural reschedule):
- (none yet)

**Operator sign-off preconditions doc**: verification/stage-7.md (create at T106)

---

## Stage 8 — Full prod hydration (local orchestrator, all sources) ⏳

**Entry gate**: Stage 7 signed; user explicitly says "go full inventory"
**Exit gate type**: runtime-green
**Exit gate**: `meta.transform_runs` shows ≥110 rows with `details->>'run_label' = '<prod_run_label>'` and `status='completed'`; zero `meta.wal_usage` rows above 70% during the run; `mol_silver.molecules` and `hcs_silver.provider_profile` non-empty; operator sign-off in `verification/stage-8.md`
**Task range**: T107, T108, T109, T110
**Delegated via**: /dk.implement
**PR**: not opened

- ⏳ T107 — Local full-inventory restore (caffeinate -is python -m dk_data.ingestion.prestaged --source-list all)
- ⏳ T108 — Watch WAL pressure + completion progress + dashboard
- ⏳ T109 — Verify acceptance queries; record any failed rows
- ⏳ T110 — Author + sign verification/stage-8.md

**Deferred from Stage 8**: (none yet)

---

## Stage 9 — SQLMesh backfill (post-hydration) ⏳

**Entry gate**: Stage 8 signed
**Exit gate type**: runtime-green
**Exit gate**: SQLMesh `audit` reports zero failures for `mol_silver.*`, `hcs_silver.*`, `mol_gold.*`, `mol_gold_ext.*`; PostgREST smokes return non-empty for molecule_profile + provider_profile
**Task range**: T111, T112, T113, T114, T115
**Delegated via**: /dk.swarm (2 workers: `mol-backfill` → T111+T113; `hcs-backfill` → T112)
**Budget**: --max-budget-usd 10 per worker; max $20

- ⏳ T111 — [Swarm A] SQLMesh mol_silver.* backfill for non-dump-covered spokes
- ⏳ T112 — [Swarm B] SQLMesh hcs_silver.* backfill
- ⏳ T113 — [Swarm A] SQLMesh mol_gold.* + mol_gold_ext.* rebuild
- ⏳ T114 — PostgREST smoke against prod
- ⏳ T115 — Stakeholder ping: dark surfaces (ip/ind/hcp) acknowledged per FR-014

**Deferred from Stage 9**: (none yet)

---

## Stage 10 — Clone staging from prod (no second hydration cycle) ⏳

**Entry gate**: Stage 9 signed; staging Postgres reachable
**Exit gate type**: runtime-green
**Exit gate**: staging `meta.transform_runs` shows full hydration row set under a staging run_label; PostgREST smoke returns non-empty for staging molecule_profile + provider_profile; SC-010 satisfied (no re-download of Drive artifacts)
**Task range**: T116, T117, T118, T119, T120
**Delegated via**: /dk.implement

- ⏳ T116 — Generate prod-schema dumps for staging clone (kubectl exec | pg_dump per schema)
- ⏳ T117 — Apply migration 229 to staging Postgres
- ⏳ T118 — Run prestaged.py against staging using prod-derived dumps
- ⏳ T119 — SQLMesh backfill on staging (mirror of T111-T113)
- ⏳ T120 — PostgREST smoke against staging

**Deferred from Stage 10**: (none yet)

---

## Cumulative production state

| Change | Where | Reversal |
|---|---|---|
| Stage 1: migration 229 ALTER TABLE meta.transform_runs ADD COLUMN status text, details jsonb + 2 partial indexes | `meta.transform_runs` (applied when migration runner picks up 229) | `ALTER TABLE meta.transform_runs DROP COLUMN status, DROP COLUMN details;` (drops dependent indexes) |
| Stage 1: Dockerfile installs postgresql-client-16 from PGDG | container image `dk-data` | revert Dockerfile commit |
| Stage 1+2: new Python surface in `src/dk_data/ingestion/` (prestaged*.py, load_order.py, transform_runs_writer.py); not yet imported by any existing path | source tree only | `git revert` the merge commits; no DB rollback needed |
| Stage 2: `deploy/jobs/prestaged-hydrate.yaml` shipped in repo, NOT yet auto-applied by ArgoCD | source tree | leave dormant or delete the file |

---

## New decisions by stage

- (Populated as each stage closes with any new D-numbered entries from .dk/memory/decisions.md)

---

## Recommended pre-merge actions

(Populated during execution. These are human-in-the-loop gates before
the user un-drafts the PR for the current stage — NOT the stage exit
gate itself.)

1. (none yet)

---

## Next action

Stages 1-6 closed (code complete). Stage 7 prep underway:
1. T100, T121, T122 (CronJob + migration 230 + grants) ready to author
2. T123 dashboard built via `playground` skill
3. T101 pre-snapshot prod (read-only, safe)
4. T103 SSH tunnel to prod PgBouncer (read-only TCP forward)
5. T104 local --dry-run against prod (zero writes)

Then surface gates for user go-ahead:
- T102 + T124: apply migrations 229 + 230 to prod (additive, ~50ms each)
- T105: single-source live restore against prod (mol_raw.kegg_drug only)
- T106: operator sign-off, then Stage 8 full inventory

Drive Stages 7-8-10 with `/dk.implement`. Stage 9 (SQLMesh backfill) uses `/dk.swarm` with 2 workers (mol-backfill, hcs-backfill) at $10/worker cap.
