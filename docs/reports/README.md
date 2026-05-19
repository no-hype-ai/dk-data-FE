# Verification Reports

**Feature**: 002-external-integration-foundation (T163, D13)

Every verification task in feature 002 (T001–T009, T067a, T088a–c,
T115, etc.) must produce a written artifact here. Checking a box in
`tasks.md` is **not** sufficient — the artifact is the audit trail
and the input to the rollback decision if something regresses.

## Naming convention

One file per task, named `T<id>-<short-slug>.md`:

- `T001-verify-gold-backfill.md`
- `T002-k8s-probes-verified.md`
- `T005-drug-labels-columns-verified.md`
- `T008-metric-coverage-audit.md`
- etc.

Longer aggregate reports (dashboard audit, capacity signoff, consumer
dependency audit) can use descriptive names without a task ID:

- `dashboard-audit.md`
- `capacity-audit-2026-Q2.md`
- `hcs-silver-consumer-audit.md`
- `test-coverage-2026-04.md`
- `phase-5-coordination.md`

## Required content

Every verification report must include:

1. **Task ID** and feature reference
2. **Date** the verification was run
3. **The exact command** that was run (copyable)
4. **The output** (or a pointer to a log / screenshot)
5. **PASS / FAIL verdict** with a reason
6. **Sign-off line** — who ran it, when

Template:

```markdown
# T<id> — <task description>

**Feature**: 002-external-integration-foundation (<user story>)
**Date**: YYYY-MM-DD
**Status**: PASS | FAIL | BLOCKED
**Operator**: <name>

## Check

\`\`\`bash
<the exact command>
\`\`\`

## Result

<output, or a pointer to logs>

## Verdict

<PASS with reason | FAIL with remediation | BLOCKED with owner>
```

## Current reports

| File | Task | Status |
|---|---|---|
| `T001-verify-gold-backfill.md` | T001 | template — run against prod before T089a |
| `T002-k8s-probes-verified.md` | T002 | PASS (verified 2026-04-13) |
| `T005-drug-labels-columns-verified.md` | T005 | PASS (verified 2026-04-13) |
| `T007-data-platform-auth-verified.md` | T007 | PASS (verified 2026-04-13) |
| `capacity-audit-2026-Q2.md` | T001a, T001b, T001c | template — run against staging |
| `hcs-silver-consumer-audit.md` | T001d | template — needs 30d sampling |
| `dashboard-audit.md` | T115 | in-progress (blocked on T109/T110) |
| `metric-coverage-audit.md` | T008 | live (enforced by T113 CI check) |
| `phase-5-coordination.md` | T160 | template — filled as consumers migrate |
| `capacity-signoff.md` | T147 | awaits infra sign-off |
| `test-coverage-2026-04.md` | T148 | 2026-04-13 snapshot |
| `hydration-priority-2026-Q2.md` | T140 | template — filled after 2w telemetry |

## Rules

- **Never delete a report**. If a task is re-run, append a new section
  dated at the bottom, don't overwrite the old result.
- **Reports are checked into git**. The filesystem is the audit trail.
- **Fail loudly**: if a verification fails, the report must stay at
  the top of this README until the remediation ships.
