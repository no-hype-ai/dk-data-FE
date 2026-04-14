# Stage Status Template

This is the literal skeleton `/dk.stage init` writes to
`FEATURE_DIR/stage-status.md`. Preserve section order when writing — the
"Next action" line at the bottom is the cold-resume contract and must
always be last.

Fill in every `<placeholder>`. Remove any sections marked `(optional)`
only after confirming the information genuinely does not exist.

---

```markdown
# Feature <nnn>-<slug> — Stage Status (as of <ISO-date>)

**Branch**: feature/<nnn>-<slug>
**Feature dir**: .dk/specs/<nnn>-<slug>/
**Pipeline state**: init | in-progress | closing | done
**Current stage pointer**: Stage <N>
**Last updated by**: /dk.stage <mode> at <ISO-ts>

## Dashboard

Stage 1 ⏳  Stage 2 ⏳  Stage 3 ⏳  Stage 4 ⏳  ...

Legend: ✅ closed · ⏳ in progress or next up · ⏸ deferred · ⛔ blocked

---

## Stage 1 — <Title> ⏳

**Entry gate**: <prerequisite condition — usually "feature branch created and tasks.md generated" for Stage 1, otherwise "Stage N-1 merged + post-merge validation passed">
**Exit gate type**: runtime-green | code-only-safe
**Exit gate**: <runtime-green: "all tests pass + PR merged"; code-only-safe: "code compiles + unit tests pass + fallback-safe + PR merged">
**Task range**: <e.g., T001-T017>
**Delegated via**: /dk.implement | /dk.swarm
**PR**: <url or "not opened">

- ⏳ T001 — <task summary>
- ⏳ T002 — <task summary>
- ...

**Deferred from Stage 1** (with explicit reason + natural reschedule):
- (none yet)

---

## Stage 2 — <Title> ⏳

**Entry gate**: Stage 1 merged + post-merge validation passed
**Exit gate type**: runtime-green
**Exit gate**: all tests pass + PR merged
**Task range**: <e.g., T018-T049>
**Delegated via**: /dk.implement
**PR**: not opened

- ⏳ T018 — <task summary>
- ...

**Deferred from Stage 2** (with explicit reason + natural reschedule):
- (none yet)

---

## Stage 3 — ... (repeat for each stage)

---

## Cumulative production state

| Change | Where | Reversal |
|---|---|---|

(Populated as each stage closes. Empty until Stage 1 closes.)

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

## Replan history

(Appended by `/dk.stage replan` if ever invoked. Omit the section
entirely if there have been no replans.)

---

## Next action

Run `/dk.stage exec` to start Stage 1.
```

---

## Required invariants

1. **The "Next action" line must exist and be non-empty.** It is the
   single source of truth for `/dk.stage resume`. If you ever find
   yourself unsure what to write here, write
   `Run /dk.stage status --repair` and tell the user.

2. **Stage numbers never change.** Even after `replan`, a closed
   Stage 3 stays Stage 3. Replan rewrites only `⏳`/`⏸`/`⛔` stages.

3. **Every deferred bullet has three components**: *what* (task ID +
   summary), *why* (tag + reason), *when* (natural reschedule). All
   three are mandatory at `defer` time.

4. **Operator-sign-off defers reference a verification stub**:
   `— preconditions doc: verification/<TID>.md`.

5. **The cumulative production state table is append-only**. Each
   `close` adds at least one row or the explicit sentinel row
   `| no runtime state changed | — | — |`.

6. **Exit gate type is load-bearing**. `runtime-green` means you can
   prove the feature works end-to-end with real config in prod;
   `code-only-safe` means the code ships safely behind a fallback
   (e.g. 503 on missing credentials) and a follow-up enables it.
   Default to `runtime-green` unless the task list is
   "code + tests + docs" without runtime configuration.
