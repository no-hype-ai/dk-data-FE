# T166 / T167 / T168 / T169 — Phase-boundary analyze gates

**Feature**: 002-external-integration-foundation
**Date**: 2026-04-13
**Status**: Procedural — must be completed at each phase boundary

## Why

Feature 002's spec, plan, and task list drift under normal development
pressure. The mitigation is a `/dk.analyze` (or equivalent manual
cross-artifact audit) at each major phase boundary. This document is
the standing checklist — four runs, one per gate, each gating the
next phase.

## Gate definitions

### T166 — End of Phase 3 (adapter v0.1 complete) → Phase 4 (migrations)

Before Phase 4 starts, re-audit:

- [ ] Every requirement in `spec.md` still has at least one task in `tasks.md`
- [ ] No orphan tasks (tasks that don't map to a requirement)
- [ ] Every migration planned for Phase 4 has a corresponding entry in
      `contracts/migration-ddl.md`
- [ ] The adapter package v0.1 contract in `contracts/client-package-api.md`
      matches what shipped in `packages/dk-data-client/`
- [ ] All Phase 3 tasks (`T030-T066`) are marked `[x]`
- [ ] Dead metrics ratchet still shrinking monotonically

**Outcome file**: `docs/reports/T166-analyze-after-phase-3.md`
**Gate status**: pending — Phase 3 completed 2026-04-13, gate pending before Phase 4 kick-off

### T167 — End of Phase 4 (migrations applied) → Phase 5 (consumer migration)

Before Phase 5 starts, re-audit:

- [ ] Migrations 215, 216, 217, 218, 220, 222 all applied to staging
      (not production)
- [ ] `docs/reviews/migrations-215-220.md` fully checked off
- [ ] `docs/reports/hcs-silver-consumer-audit.md` has 30d of sampling data
- [ ] All consumer specs (behavior-labs-ai, carbon-5, dk-os,
      ground-truth-charlie, trials-predictor) reference the provisioned
      API key
- [ ] `tests/test_21[5-8]*.py` and `tests/test_220*.py` all pass
- [ ] Rollback drill ran against staging in ≤ 5 min

**Outcome file**: `docs/reports/T167-analyze-after-phase-4.md`
**Gate status**: pending

### T168 — End of Phase 5 (consumers upgraded) → Phase 4b (production cutover)

Before T089a fires, re-audit:

- [ ] `docs/reports/phase-5-coordination.md` shows all consumers `complete`
- [ ] Staging has been running the adapter + new migrations for ≥ 48h
      with no 401/403/429 regressions in the metering proxy logs
- [ ] `docs/reports/capacity-signoff.md` signed by infra
- [ ] Rollback drill was actually executed (not just documented)
- [ ] On-call schedule in place for the production cutover window

**Outcome file**: `docs/reports/T168-analyze-before-production.md`
**Gate status**: pending

### T169 — Immediately before T089a fires

The last-mile checklist — run within 15 minutes of the production
migration apply:

- [ ] `docs/reports/T001-verify-gold-backfill.md` filled in with
      fresh-within-1-hour numbers, PASS verdict
- [ ] `pg_stat_activity` shows 0 sessions as `web_anon`
      (run T088c kill loop if any remain)
- [ ] PostgREST rolling-update runbook queued
- [ ] Incident channel (#dk-data-oncall) paged in advance
- [ ] Rollback SQL file + runbook open in a terminal tab (not in a
      browser — the browser could be unreachable if ingress dies)

**Outcome file**: `docs/reports/T169-preflight-before-089a.md`
**Gate status**: pending

## Run procedure

1. Create the outcome file listed above (`T166-analyze-after-phase-3.md`,
   etc.)
2. Work through the checklist — one checkbox at a time
3. For each failed item, file a blocking issue and DO NOT proceed
4. Sign off at the bottom of the file (dk-data on-call + infra on-call
   for T168/T169; dk-data on-call alone for T166/T167)
5. Link the outcome file from this document

## Automating

When the project has a `/dk.analyze` equivalent wired into CI, these
gates become automatic. Until then, they are manual — but they still
MUST happen before each transition.

## Related

- `.dk/specs/002-external-integration-foundation/spec.md`
- `.dk/specs/002-external-integration-foundation/tasks.md`
- `docs/reports/phase-5-coordination.md`
- `docs/runbooks/rollback-web-anon-drop.md`
