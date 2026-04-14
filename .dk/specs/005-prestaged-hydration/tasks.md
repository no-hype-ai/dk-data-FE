# Task Breakdown

**Branch**: `feature/005-prestaged-hydration`
**Spec**: [spec.md](./spec.md)
**Plan**: [plan.md](./plan.md)

## Phase 1 — Setup

*Project initialization, config, image tooling. Serial.*

- [ ] T001 Add `postgresql-client-16` to the ingestion container image build — `deploy/docker/ingestion.Dockerfile`
- [ ] T002 Declare `tenacity` + `loguru` usage explicitly in a new `[project.optional-dependencies.prestaged]` group (already present in base deps; no new packages) — `pyproject.toml`
- [ ] T003 Add `scripts/prestaged_smoke.sh` — small shell helper that dry-runs one tier against a local Postgres — `scripts/prestaged_smoke.sh`

## Phase 2 — Foundational

*Blocking prerequisites: shared types, config, DB connection helpers. Serial.*

- [ ] T010 Define Pydantic models `PrestagedArtifact`, `LoadStep`, `LoadPlan` matching data-model.md — `src/dk_data/ingestion/prestaged_types.py`
- [ ] T011 [P] Define the `SOURCE_LOAD_ORDER` list (8 tiers, 120 sources) per plan.md §load_order — `src/dk_data/ingestion/load_order.py`
- [ ] T012 [P] Add `WAL_MODE_TABLES` set (5 tables >5 GB) to `load_order.py` — `src/dk_data/ingestion/load_order.py`
- [ ] T013 [P] Write `prestaged_manifest.schema.json` (JSON Schema for optional manifests) — `src/dk_data/ingestion/prestaged_manifest.schema.json`
- [ ] T014 Extend `SOURCE_TO_BRONZE_MODELS` dict with `depends_on: list[str]` and `prestaged_kind: str` fields — `src/dk_data/ingestion/source_backfill.py:57`
- [ ] T015 Add helper `compute_run_id(artifact_sha256s, cluster_fp)` per research.md R4 — `src/dk_data/ingestion/prestaged_types.py`
- [ ] T016 [P] Add helper `is_restorable_target(conn, schema, table) -> bool` that filters on `pg_class.relkind='r'` (FR-015) — `src/dk_data/ingestion/prestaged_safety.py`
- [ ] T017 [P] Add helper `transform_runs_writer(conn)` that discovers the actual column set via `information_schema.columns` and exposes `upsert(run_id, schema, table, **fields)` — `src/dk_data/ingestion/transform_runs_writer.py`
- [ ] T018 [P] Create small fixture `.dump` files (≤1 MB each) under `tests/fixtures/prestaged/` covering raw, bronze, silver layouts plus a multi-chunk case (`1_foo.dump`, `retry_foo.dump`) — `tests/fixtures/prestaged/`
- [ ] T019 Verify `tests/conftest.py` provides a Postgres 16 fixture (testcontainers-python OR docker-compose helper); document usage in `quickstart.md` — `tests/conftest.py`, `.dk/specs/005-prestaged-hydration/quickstart.md`
- [ ] T010a Create `src/dk_data/ingestion/prestaged.py` skeleton with named stub functions (`walk_prestaged_root`, `validate_magic_bytes`, `compute_sha256`, `group_by_table`, `select_highest_tier`, `dispatch_pg_restore`, `run_step`, `main`) each with docstrings and `raise NotImplementedError`, so Stage 2 swarm workers can fill disjoint function bodies without file-overlap conflicts — `src/dk_data/ingestion/prestaged.py`

## Phase 3 — Operator hydrates prod from pre-staged artifacts (P1) [US1]

*Primary success path. FR-001, FR-002, FR-003, FR-004, FR-009, FR-013.*

- [ ] T020 [US1] Implement `walk_prestaged_root(root) -> list[PrestagedArtifact]` supporting both `_staging/…/dk-data-files/` and `_loose_dumps/` layouts (FR-001) — `src/dk_data/ingestion/prestaged.py`
- [ ] T021 [US1] Implement `validate_magic_bytes(artifact)` checking `b"PGDMP"` prefix (FR-002) — `src/dk_data/ingestion/prestaged.py`
- [ ] T022 [US1] Implement `compute_sha256(artifact)` with inode cache (FR-002) — `src/dk_data/ingestion/prestaged.py`
- [ ] T023 [US1] Implement `group_by_table(artifacts) -> dict[(schema,table), list]` with lexical chunk ordering (FR-004) — `src/dk_data/ingestion/prestaged.py`
- [ ] T024 [US1] Implement `select_highest_tier(group) -> (tier, artifacts)` applying silver > bronze > raw precedence (FR-003) — `src/dk_data/ingestion/prestaged.py`
- [ ] T025 [US1] Implement `dispatch_pg_restore(conn, step, artifact)` — subprocess `pg_restore -Fc --section=data --single-transaction --no-owner --no-privileges`, `--clean --if-exists` on first chunk only, advisory lock per R5 — `src/dk_data/ingestion/prestaged.py`
- [ ] T026 [US1] Implement `run_step(conn, step)` — orchestrates view-safety check → per-chunk restore → row-count → `transform_runs_writer.upsert` — `src/dk_data/ingestion/prestaged.py`
- [ ] T027 [US1] Implement `main(argv)` CLI per contracts/cli.md — argparse + env-var loading + fail-fast on bad PRESTAGED_ROOT (FR-016) — `src/dk_data/ingestion/prestaged.py`
- [ ] T028 [US1] Unit tests: `walk_prestaged_root` discovers both layouts — `tests/ingestion/test_prestaged_discovery.py`
- [ ] T029 [US1] Unit tests: validation rejects a non-PGDMP file — `tests/ingestion/test_prestaged_validate.py`
- [ ] T030 [US1] Unit tests: `group_by_table` orders `1_`, `3_`, `retry_` correctly — `tests/ingestion/test_prestaged_discovery.py`
- [ ] T031 [US1] Integration test: restore a small fixture `.dump` into a docker-compose Postgres and assert row count — `tests/load/test_prestaged_e2e.py`
- [ ] T032 [US1] Write the k8s Job manifest per contracts/k8s-job.md — `deploy/jobs/prestaged-hydrate.yaml`

## Phase 4 — Hub → spoke load ordering is deterministic (P1) [US2]

*Deterministic ordering + dependency handling. FR-005, FR-006.*

- [ ] T040 [US2] Implement `plan_load(artifacts, source_load_order, available_fetchers) -> LoadPlan` — resolves tier ordering, `depends_on`, and marks missing sources for fallback (FR-005, FR-006) — `src/dk_data/ingestion/load_order.py`
- [ ] T041 [US2] Propagate `blocked` status to downstream steps when an upstream step fails — `src/dk_data/ingestion/prestaged.py`
- [ ] T042 [US2] Unit tests: load order with all sources present produces 8 tiers in declared order — `tests/ingestion/test_load_order.py`
- [ ] T043 [US2] Unit tests: missing hub → dependent spokes receive `blocked` status — `tests/ingestion/test_load_order.py`
- [ ] T044 [US2] Unit tests: silver dump for a hub suppresses lower-tier dumps for the same `(schema, table)` — `tests/ingestion/test_load_order.py`

## Phase 5 — WAL-aware throttling (P2) [US3]

*FR-007, FR-008.*

- [ ] T050 [US3] Implement `wal_pressure(conn) -> float` reading `meta.wal_usage` — `src/dk_data/ingestion/prestaged.py` (or extend `wal_budget.py` if natural)
- [ ] T051 [US3] Implement `pause_until_below(conn, low_pct, budget_s)` with loguru-logged pauses — `src/dk_data/ingestion/prestaged.py`
- [ ] T052 [US3] Wire pre-restore check on WAL-mode tables to call `pause_until_below` — `src/dk_data/ingestion/prestaged.py`
- [ ] T053 [US3] Implement two-consecutive-pauses → halve chunk size downshift (FR-008) — `src/dk_data/ingestion/prestaged.py`
- [ ] T054 [US3] Integration test: inject a stubbed `wal_usage` row at 80% → restore pauses until stub drops to 35% — `tests/ingestion/test_wal_throttle.py`
- [ ] T055 [US3] Integration test: two consecutive pauses → chunk size visibly halved in logs for subsequent step — `tests/ingestion/test_wal_throttle.py`

## Phase 6 — Fallback to live fetcher (P2) [US4]

*FR-010, FR-014.*

- [ ] T060 [US4] Implement `run_live_fetch(conn, step)` that calls `main.run_ingestion(source_id)` and writes outcome to `meta.transform_runs` with `source_kind='live_fetch'` (FR-010) — `src/dk_data/ingestion/prestaged.py`
- [ ] T061 [US4] Implement `FETCHERS_SUSPENDED` env-var parsing and honoring (suspended sources record `no_source_available`) — `src/dk_data/ingestion/prestaged.py`
- [ ] T062 [US4] Enforce FR-014: skip `ip_*`, `ind_*`, `hcp_silver` sources without recording any state — `src/dk_data/ingestion/load_order.py`
- [ ] T063 [US4] Unit test: source with no artifact + enabled fetcher → `run_live_fetch` invoked (mocked) — `tests/ingestion/test_prestaged_fallback.py`
- [ ] T064 [US4] Unit test: source in `FETCHERS_SUSPENDED` → `no_source_available` recorded, fetcher not called — `tests/ingestion/test_prestaged_fallback.py`
- [ ] T065 [US4] Unit test: source in out-of-scope list → step not present in LoadPlan at all — `tests/ingestion/test_load_order.py`

## Phase 7 — Observability + idempotency (P3) [US5]

*FR-009, FR-011, FR-012; SC-006, SC-007.*

- [ ] T070 [US5] Implement `--dry-run` branch in `main(argv)` emitting per-step JSON lines per contracts/cli.md (FR-012) — `src/dk_data/ingestion/prestaged.py`
- [ ] T071 [US5] Implement idempotency guard: skip steps already `completed` under the same `run_id` (FR-011) — `src/dk_data/ingestion/prestaged.py`
- [ ] T072 [US5] Emit one stdout JSON line per terminal transition per contracts/cli.md — `src/dk_data/ingestion/prestaged.py`
- [ ] T073 [US5] Best-effort OTLP emission wrapped in try/except (observability not in write path) — `src/dk_data/ingestion/prestaged.py`
- [ ] T074 [US5] Integration test: re-run after successful run completes in <5 s in test env with zero `pg_restore` subprocess calls (SC-006) — `tests/load/test_prestaged_e2e.py`
- [ ] T075 [US5] Integration test: `meta.transform_runs` has exactly one terminal row per source after a full run (SC-007) — `tests/load/test_prestaged_e2e.py`

## Phase 8 — Polish & cross-cutting

*Docs, lint, verify, cleanup.*

- [ ] T080 Run `mypy --strict` on all new `ingestion/prestaged*.py` files; fix violations — `src/dk_data/ingestion/`
- [ ] T081 [P] Update `CLAUDE.md` data-flow diagram to reference `prestaged.py` as the hydration path — `CLAUDE.md`
- [ ] T082 [P] Add a README snippet in `src/dk_data/ingestion/README.md` pointing to the new quickstart — `src/dk_data/ingestion/README.md`
- [ ] T083 [P] Verify checklist CHK001–CHK023 (`.dk/specs/005-prestaged-hydration/checklists/requirements.md`) — `.dk/specs/005-prestaged-hydration/checklists/requirements.md`
- [ ] T084 Add `scripts/prestaged_smoke.sh` invocation to `.github/workflows/ci.yml` as a non-blocking smoke step — `.github/workflows/ci.yml`
- [ ] T085 Delete the `bronze_ready` / `raw_csv` dispatch branches IF after the first prod run no CSV/parquet artifacts have appeared in inventory (tracked as a follow-up, not a blocker) — `src/dk_data/ingestion/prestaged.py`

---

## Dependencies & Execution Order

```
Phase 1 (Setup, T001-T003) — serial
  → Phase 2 (Foundation, T010-T017) — T010 first, then T011/T012/T013/T016/T017 parallel, then T014/T015
    → Phase 3 US1 (T020-T032) — T020→T021→T022→T023→T024→T025→T026→T027 serial; T028-T031 after implementations; T032 parallel
      → Phase 4 US2 (T040-T044) — depends on T011 + T026
        → Phase 5 US3 (T050-T055) — depends on T026
        → Phase 6 US4 (T060-T065) — depends on T026 + T040
        → Phase 7 US5 (T070-T075) — depends on T026 + T060
          → Phase 8 (T080-T085) — final polish
```

### Parallel opportunities

- **T011 / T012 / T013 / T016 / T017** after T010 lands (different files)
- **T028 / T029 / T030** (different tests, same file) can be written in parallel but committed together
- **Phase 5, 6, 7** are largely independent once Phase 3 + Phase 4 are in
- **T081 / T082 / T083** polish items are file-independent

## Implementation Strategy

- **MVP first**: Phases 1-3 produce a working hydrator for a single source in a local env. Demo before touching P2.
- **Schema safety**: T016 (view-safety) lands in Phase 2 because every other write task depends on it.
- **Idempotency debt**: T071 lands in Phase 7 deliberately — it depends on every terminal-status code path being implemented first.
- **Dead-code hygiene**: T085 is explicitly a follow-up, not a blocker for prod cutover.

## Metrics

- Total tasks: 56 (T001–T085 with gaps for readability)
- Actual count: 50
- Phases: 8
- User stories: 5 (all represented)
- Parallel opportunities: 11 tasks tagged [P]
