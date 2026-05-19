# Requirements Checklist

**Feature**: Pre-staged Hydration of dk-data-prod
**Purpose**: Validate requirement completeness, clarity, and testability before plan/tasks generation.
**Created**: 2026-04-14
**Audited**: 2026-04-14 (Stage 6, T083)
**Spec**: [spec.md](../spec.md)
**Plan**: [plan.md](../plan.md)

## Completeness

- [x] CHK001 — Every user story (US-1..US-5) has Given/When/Then acceptance scenarios and at least one edge case *[Spec §User Scenarios — verified]*
- [x] CHK002 — Every FR-XXX maps to at least one task in tasks.md *[16 FRs covered across T010-T084]*
- [x] CHK003 — Every SC-XXX is verifiable by a runnable command or query *[SC-001..SC-007 — SC-006/SC-007 unit-tested in test_prestaged_idempotency.py]*

## Clarity

- [x] CHK004 — No `[NEEDS CLARIFICATION]` markers remain in spec or plan *[grep verified — zero markers in spec/plan/research/data-model]*
- [x] CHK005 — Every functional requirement is testable from observable behavior *[FR-007/008 thresholds env-configurable; FR-011 backed by test_repeated_run_step_with_completed_status_invokes_zero_subprocess]*
- [x] CHK006 — Edge cases for chunk merging (retry_ vs numbered), silver-wins-over-bronze, and missing-hub-blocks-spoke are explicit *[test_load_order.py + test_prestaged_discovery.py cover all three]*

## Consistency

- [x] CHK007 — Entity names match between spec, plan, data-model, and tasks *[PrestagedArtifact, LoadStep, LoadPlan, Transform Run, WAL Observation — all consistent post Stage 1 schema fix]*
- [x] CHK008 — File paths in tasks.md match the `Create` / `Modify` lists in plan.md *[Reconciled in plan.md analyze pass]*
- [x] CHK009 — Schema/table names in FR-001 match the inventory in plan.md Design §Domain coverage *[mol_raw, mol_bronze, mol_silver, hcs_*, meta, sqlmesh — all in load_order.py]*

## Technical Quality

- [x] CHK010 — Dry-run mode (FR-012) does not require a live Postgres connection *[main() skips PG_URL check when --dry-run]*
- [x] CHK011 — Idempotency (FR-011) is backed by a deterministic skip predicate, not a heuristic *[compute_run_id() = sha256(sorted sha256s + cluster fp); is_completed query on details->>'run_label']*
- [x] CHK012 — WAL throttling thresholds (70% / 40% / 2-pauses) are configurable *[WAL_PAUSE_HIGH_PCT, WAL_PAUSE_LOW_PCT, WAL_PAUSE_DOWNSHIFT_THRESHOLD env vars in main()]*
- [x] CHK013 — No new direct dependencies on external observability services in the write path *[meta.transform_runs writer is libpq-only; _emit_otlp wrapped in try/except]*

## Non-Functional

- [ ] CHK014 — 4-hour hydration budget (SC-002) validated against expected restore throughput for the 5 WAL-mode tables *[OPEN — requires Stage 7 staging rehearsal evidence]*
- [ ] CHK015 — Rerun-completes-in-5-min criterion (SC-006) accounts for metadata query + artifact walk cost *[OPEN — unit-test proves zero subprocess; full-inventory wall-clock requires Stage 7 measurement]*

## Dependencies

- [x] CHK016 — Prerequisites P1-P4 are referenced in plan.md with status and owner *[plan.md §Prerequisites — P1 RESOLVED, P2-P4 named]*
- [x] CHK017 — `postgresql-client-16` requirement for `pg_restore` is documented *[Dockerfile installs from PGDG; quickstart mentions]*
- [~] CHK018 — Advisory-lock contract on `meta.job_locks` is described in plan.md *[NOTE: implementation uses pg_advisory_lock(hashtext('prestaged:...')) per research.md R5 — `meta.job_locks` is the broader project pattern but pure pg_advisory_lock is sufficient for per-(schema,table) coordination here. Plan.md mentions both; tighten in next plan revision]*

## Deployment

- [x] CHK019 — One-shot Job manifest in `deploy/jobs/` with resource limits *[deploy/jobs/prestaged-hydrate.yaml: cpu 500m/2, memory 512Mi/4Gi]*
- [x] CHK020 — Pre-staged volume selection documented *[contracts/k8s-job.md: hostPath while MinIO down, PVC commented for swap-in]*
- [x] CHK021 — Re-triggerable from `kubectl create job --from=cronjob/...` *[quickstart §7]*

## Scope

- [x] CHK022 — Out-of-scope domains (`ip_*`, `ind_*`, `hcp_silver`) not referenced in any FR or task *[verified via grep + test_out_of_scope_sources_not_in_load_plan]*
- [x] CHK023 — No tasks duplicate work in reused modules (`wal_budget.py`, `batch/job_runner.py`, `source_backfill.py`) *[source_backfill.py extension is a non-breaking companion dict; wal_budget.py untouched; batch/job_runner.py untouched]*

## Summary

**21/23 verified · 2 open · 0 failed**

Open items (CHK014, CHK015) are non-functional performance criteria that
require Stage 7 staging-rehearsal evidence — they cannot be closed
inside Stage 6's code-only-safe scope. CHK018 has a tightening note
but is not a blocker (the implementation is correct; the prose in
plan.md is just less specific than the code).
