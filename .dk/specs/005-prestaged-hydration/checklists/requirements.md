# Requirements Checklist

**Feature**: Pre-staged Hydration of dk-data-prod
**Purpose**: Validate requirement completeness, clarity, and testability before plan/tasks generation.
**Created**: 2026-04-14
**Spec**: [spec.md](../spec.md)
**Plan**: [plan.md](../plan.md)

## Completeness

- [ ] CHK001 — Every user story (US-1..US-5) has Given/When/Then acceptance scenarios and at least one edge case *[Completeness, Spec §User Scenarios]*
- [ ] CHK002 — Every FR-XXX maps to at least one task in tasks.md *[Coverage, Spec §Requirements]*
- [ ] CHK003 — Every SC-XXX is verifiable by a runnable command or query *[Completeness, Spec §Success Criteria]*

## Clarity

- [ ] CHK004 — No `[NEEDS CLARIFICATION]` markers remain in spec or plan *[Clarity, Spec §All]*
- [ ] CHK005 — Every functional requirement is testable from observable behavior (no "SHOULD feel fast") *[Clarity, Spec §Requirements]*
- [ ] CHK006 — Edge cases for chunk merging (retry_ vs numbered), silver-wins-over-bronze, and missing-hub-blocks-spoke are explicit *[Coverage, Spec §US-1, US-2]*

## Consistency

- [ ] CHK007 — Entity names (`Transform Run`, `Load Plan`, `Pre-staged Artifact`, `WAL Observation`) match between spec, plan, data-model, and tasks *[Consistency, All]*
- [ ] CHK008 — File paths in tasks.md match the `Create` / `Modify` lists in plan.md *[Consistency, Plan §Critical files]*
- [ ] CHK009 — Schema/table names referenced in FR-001 match the inventory in plan.md Design §Domain coverage *[Consistency, Plan §Data flow]*

## Technical Quality

- [ ] CHK010 — Dry-run mode (FR-012) does not require a live Postgres connection *[Quality, Spec §FR-012]*
- [ ] CHK011 — Idempotency (FR-011) is backed by a deterministic skip predicate, not a heuristic *[Quality, Spec §FR-011]*
- [ ] CHK012 — WAL throttling thresholds (70% / 40% / 2-pauses) are configurable, not hardcoded literals *[Quality, Spec §FR-007, FR-008]*
- [ ] CHK013 — No new direct dependencies on external observability services (alloy/OTLP) in the write path *[Security, Spec §FR-009]*

## Non-Functional

- [ ] CHK014 — 4-hour hydration budget (SC-002) is validated against expected restore throughput for the 5 WAL-mode tables *[Performance, Spec §SC-002]*
- [ ] CHK015 — Rerun-completes-in-5-min criterion (SC-006) accounts for metadata query + artifact walk cost *[Performance, Spec §SC-006]*

## Dependencies

- [ ] CHK016 — Prerequisites P1-P4 are referenced in plan.md with status and owner *[Dependencies, Plan §Prerequisites]*
- [ ] CHK017 — The `postgresql-client-16` requirement for `pg_restore` is documented in the deployment artifact *[Dependencies, Plan §Critical files]*
- [ ] CHK018 — Advisory-lock contract on `meta.job_locks` is described in plan.md *[Dependencies, Plan §Pre-processing]*

## Deployment

- [ ] CHK019 — One-shot Job manifest (FR-013) is in `deploy/jobs/` and has resource limits set *[Deployment]*
- [ ] CHK020 — Pre-staged volume (PVC or hostPath) selection is documented for both infra-down and infra-healthy states *[Deployment]*
- [ ] CHK021 — Run is re-triggerable from `kubectl create job --from=cronjob/...` with no manual cleanup *[Deployment]*

## Scope

- [ ] CHK022 — Out-of-scope domains (`ip_*`, `ind_*`, `hcp_silver`) are not referenced in any FR- or task *[Scope, Spec §Assumptions, Plan §Out of scope]*
- [ ] CHK023 — No tasks duplicate work in reused modules (`wal_budget.py`, `batch/job_runner.py`, `source_backfill.py:57`) *[Scope, Plan §Leave alone]*
