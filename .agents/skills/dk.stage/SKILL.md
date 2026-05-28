---
description: Group a big tasks.md into atomic, PR-sized stages with entry/exit gates, and maintain a stage-status.md checkpoint file across sessions. Runs between /dk.tasks and /dk.implement.
---

---
description: Group a big tasks.md into atomic, PR-sized stages with entry/exit gates, and maintain a stage-status.md checkpoint file across sessions. USE THIS when the user mentions stages, checkpoints, multi-stage rollouts, resumable execution, "how do I chunk this into PRs", atomic commits, staged delivery, or is resuming a half-done feature. Runs between /dk.tasks and /dk.implement. Writes .dk/specs/<feature>/stage-status.md.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty). The first token of `$ARGUMENTS` is the mode (`init`, `status`, `next`, `exec`, `defer`, `close`, `replan`, `resume`). The rest is mode-specific args. If `$ARGUMENTS` is empty, default to `status`.

## Principles

Read `.dk/memory/principles.md` before acting. All output must honor the project's principles: **simple, complete, senior**.

## Overview

You are a **stage manager**. A feature spec (from `/dk.specify` → `/dk.plan` → `/dk.tasks`) produces a long `tasks.md` organized by phase. Your job is to batch those phases into **stages** — each stage is one atomic commit group, one PR, one merge to main, with explicit entry/exit gates — and to maintain a single checkpoint file (`stage-status.md`) so that any fresh session can pick up execution exactly where the last one left off.

You do not write code. You never recursively invoke another skill. You emit delegation briefs telling the user (or `/dk.auto`) to run `/dk.implement <range>` or `/dk.swarm`, and you update `stage-status.md` when they report back.

### Stage vs phase vs wave

Three concepts coexist and none replaces the others:

- **Phase** — structural grouping in `tasks.md`, one per user story or cross-cut. Source: `/dk.tasks`.
- **Stage** — execution unit you manage. One or more phases bundled into a shippable PR. Source: this skill.
- **Wave** — parallelism unit inside `/dk.swarm` (dependency-graph-driven). Source: `/dk.swarm`. A stage usually contains one or more waves.

`swarm-state.json` remains the authoritative per-wave state. `stage-status.md` is the authoritative per-stage state. They coexist; neither subsumes the other.

## Prerequisites

1. Run `.dk/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` (or the wrapper at `.dk/scripts/bash/verify-feature-dir.sh`) and parse `FEATURE_DIR`.

2. Read `.dk/memory/principles.md` and the project context file (`AGENTS.md`, `AGENTS.md`, `GEMINI.md`, or `QWEN.md` depending on agent).

3. If the mode is anything other than `init`, read `FEATURE_DIR/stage-status.md`. If it doesn't exist, tell the user to run `/dk.stage init` first and stop.

## Modes

### `init` — group phases into stages and write the initial stage-status.md

**Input**: optional `--replan` flag, optional `--note "<reason>"`.

**Refuses** to overwrite an existing `stage-status.md` unless `--replan` is set. On `--replan`, see the `replan` mode below — `init --replan` is an alias.

**Steps**:

1. Read `tasks.md` fully. Extract:
   - All phase headers (`## Phase N — <title>`)
   - Tasks under each phase, including `[P]` parallel markers and `[USN]` user-story labels
   - The "Dependencies & Execution Order" section if present

2. Read `plan.md` to understand the user stories (US-1..US-N), their priorities, and any "blocked on" annotations.

3. Propose a stage grouping. Default heuristics, in priority order:
   - **Phase 1 (Setup) + Phase 2 (Foundational)** always become **Stage 1**. No exceptions.
   - **Any phase marked "blocked on hardware" or "blocked on external procurement"** becomes its own stage with emoji ⛔ and a placeholder "Entry gate: unblocked when <reason>".
   - **User stories with shared foundational code** (same adapters, same CRDs, same auth layer) bundle into one stage.
   - **User stories with explicit "Operator sign-off required"** on critical tasks get split — the code-safe part goes in Stage N, the operator-sign-off tasks defer to Stage N+1 with `exit-gate-type: code-only-safe` on Stage N.
   - **Cross-cutting hardening (Phase 12) and Polish (Phase 13)** become the final two stages.
   - Aim for 4-7 stages total. More is too granular; fewer makes individual PRs too large to review.

4. For each proposed stage, write:
   - **Title** — short, imperative (e.g., "Foundational scaffolding + auth").
   - **Entry gate** — one condition. Usually "Stage N-1 merged + post-merge validation passed". Stage 1's entry gate is "feature branch created and tasks.md generated".
   - **Exit gate type** — `runtime-green` (tests passing end-to-end with real config) or `code-only-safe` (tests passing in isolation; runtime config deferred via 503 fallback or similar). Default `runtime-green` unless the task list obviously ships code-without-config.
   - **Exit gate** — one condition. Usually "<exit-gate-type> + PR merged + stage-status.md updated".
   - **Task range** — a comma-separated list of task IDs or ranges that `/dk.implement $ARGUMENTS` accepts (e.g., `T010-T017,T050-T056`).
   - **Delegated via** — `/dk.implement` for sequential stages, `/dk.swarm` for stages with `[P]` parallel tasks spanning multiple user stories.

5. Write `FEATURE_DIR/stage-status.md` using the exact template at `.dk/templates/stage-status-template.md`. Preserve section order — the "Next action" line at the bottom is mandatory and is the cold-resume contract.

6. Print a summary: how many stages, which stage is the current pointer (always Stage 1 after `init`), and the literal "Next action" line.

7. Run any `after_stage_init` hooks in `.dk/extensions.yml` if present.

### `status` — print dashboard + next action

Default mode. Read `stage-status.md`, print:
- The dashboard line (`Stage 1 ✅  Stage 2 ⏳  ...`)
- The current stage block (title, entry gate, exit gate, task list, deferred list)
- The "Next action" line verbatim

### `next` — print delegation brief for the current stage

Read `stage-status.md`. For the current stage pointer, print:
- Stage title, entry gate, exit gate type, exit gate, task range
- The literal delegation command: `Run /dk.implement <task-range>` or `Run /dk.swarm`
- Any deferred tasks that are still `⏸` in this stage, with their reasons

Does NOT execute anything. Does NOT modify any file.

### `exec` — emit delegation brief (explicit action)

Same output as `next`, but framed as "here is the command to run now". Optional `--parallel` flag switches the brief from `/dk.implement` to `/dk.swarm`.

Important: you are **not** calling the sibling skill as a subroutine. You are printing the exact string the user should run next. The stage-awareness patches in `/dk.implement` and `/dk.swarm` handle the inbound reporting automatically when they see `stage-status.md`.

### `defer <TID> "<reason>"` — move a task out of the current stage

**Required args**: task ID (one or a range like `T104-T106`), and a reason.

**Reason must start with one of**:
- `hardware-block:` — waiting on procurement or physical infra
- `operator-sign-off:` — needs a human to approve a blast-radius decision
- `dependent-task:` — blocked by a task in a later stage
- `scope-split:` — moved to a different feature entirely
- `risk-defer:` — intentionally delayed to reduce blast radius of current stage

**Steps**:

1. Read `stage-status.md` and locate the task in the current stage.

2. Move the task from the task list to the "**Deferred from Stage N**" section. Format:
   ```
   - ⏸ T043 — reason-tag: <full reason> — natural reschedule: <when + what unblocks it>
   ```

3. If the reason is `operator-sign-off:`, create a stub at `FEATURE_DIR/verification/<TID>.md`:
   ```markdown
   # Verification: <TID>

   **Task**: <task description from tasks.md>
   **Deferred reason**: operator-sign-off — <reason text>
   **Preconditions**:
   - [ ] <list any preconditions from the task's body>

   **Signed-off-by**: <empty — fill in name + date when approved>
   ```
   Append `— preconditions doc: verification/<TID>.md` to the deferred bullet.

4. Edit `tasks.md` to annotate the task line with the defer marker:
   ```
   - [ ] ⏸ T043 (deferred — operator-sign-off) ...original task text...
   ```
   Do NOT mark it `[x]` — it is not complete.

5. Update `stage-status.md` footer `Last updated by` timestamp.

6. If deferring this task makes the current stage impossible to complete, print a warning and suggest `replan`. Otherwise the stage can still close.

### `close` — finalize the current stage

**Required before you run this**: the user must have merged the stage's PR (or explicitly confirmed the stage ships as code-only-safe).

**Steps**:

1. Read `stage-status.md`. Verify every task in the current stage's task range is either `✅` or `⏸`. If any are still `⏳` or `⛔`, refuse and tell the user to `defer` them first.

2. Verify the exit gate. Ask the user one direct question:
   - For `runtime-green`: "Are all tests green and is the PR merged? (y/n)"
   - For `code-only-safe`: "Is the code safe to ship with the documented fallback, and is the PR merged? (y/n)"
   Refuse to proceed on `n`.

3. Ask for new D-numbered decisions that emerged this stage. If the user gives any, append to `.dk/memory/decisions.md` in the existing format (read the file first, compute the next D-number). Never rewrite prior entries.

4. Ask for cumulative production-state rows: "What new runtime state landed this stage? (one row per change: what / where / reversal, or 'none')". Append to the "Cumulative production state" table. If the user says "none", explicitly write a row like "| no runtime state changed | — | — |" — the empty-by-decision row is load-bearing for rollback reasoning.

5. Mark the current stage `✅` in the dashboard. Tick its title. Advance the "Current stage pointer" to the next `⏳` or `⛔` stage. If none, set `Pipeline state: done`.

6. Update the "Next action" line to point at the new current stage (or to "Feature complete. Consider closing the branch." if done).

7. Update `Last updated by` timestamp.

8. Print a summary and the new "Next action" line.

### `replan` — regenerate remaining stages

Used when discovery invalidates the original grouping.

**Args**: `--note "<reason for replan>"` (required).

**Steps**:

1. Read `stage-status.md`. Preserve all `✅` stages exactly — their entry/exit gates, task lists, and cumulative prod rows are immutable.

2. For all `⏳` / `⏸` / `⛔` stages, discard their grouping but preserve the tasks that are already deferred (`⏸`) along with their reasons.

3. Re-run the stage-grouping heuristics from `init` against the remaining tasks in `tasks.md` that are not in any `✅` stage and not in the deferred bucket.

4. Surface any orphaned tasks (tasks in `tasks.md` that the new grouping cannot place) as explicit warnings.

5. Append a `## Replan history` section near the end of `stage-status.md` if not present, and add an entry:
   ```
   - <ISO-date>: <reason from --note>
   ```

6. Update `Last updated by` and the "Next action" line.

**Do not** modify `✅` stages, even to re-number them. Closed stages are immutable. If a closed stage's work turns out to be wrong, that's a post-merge bug (fix on a separate `fix/*` branch, not here).

### `resume` — cold-start a dead session

Use this when returning to a feature after the session that was executing it died.

**Steps**:

1. Read `stage-status.md`. Verify it has a "Next action" line. If it doesn't, refuse and tell the user to run `/dk.stage status --repair`.

2. Identify the first `⏳` stage (the current pointer).

3. Read `tasks.md` and diff the stage's task range against `[x]`-marked tasks. Any `[x]` tasks inside the range are already done; only the remaining `[ ]` tasks need execution.

4. Print:
   - The "Next action" line verbatim
   - A delegation brief for the remaining tasks only (not the whole stage range)
   - Any deferred tasks in this stage (they stay deferred — don't resurrect them)

5. Do not modify any file. Resume is read-only.

## Rules

- **Never recursively invoke another skill.** You emit commands the user runs. Nested skill invocation is an anti-pattern — it breaks the stage-awareness contract on both ends.
- **Never write code.** That is `/dk.implement`'s or `/dk.swarm`'s job.
- **Never touch** `spec.md`, `plan.md`, `research.md`, `data-model.md`, or `contracts/`. Those are immutable upstream outputs.
- **Closed stages are immutable.** `replan` rewrites only `⏳`/`⏸`/`⛔` stages. Post-merge bugs go on `fix/*` branches outside the stage flow.
- **Every defer needs a reason tag and a natural reschedule.** What, why, when — all three.
- **The "Next action" line is the cold-resume contract.** Never delete it. Never leave it empty. If you are unsure what the next action is, write `Run /dk.stage status --repair` and tell the user.
- **Close requires at least one cumulative prod row** (or the explicit "no runtime state changed" sentinel row). This is the rollback-reasoning contract.
- **Operator-sign-off defers get a `verification/<TID>.md` stub.** Stage cannot close against that task until the stub has a `Signed-off-by:` line filled in.
- **Backwards compatibility**: if a sibling feature has no `stage-status.md`, `/dk.implement` and `/dk.swarm` behave exactly as they always did. This skill never forces adoption.

## Reference files

Read as needed:

- `.dk/templates/stage-status-template.md` — the literal skeleton `init` writes. Preserve section order.
- `.dk/templates/example-stage-status.md` — a worked example. Use this when `init` is uncertain about grouping.
- `.dk/templates/gate-vocabulary.md` — the lexicon for emoji, deferral reasons, and gate types. Keep it closed — don't invent new reason tags without adding them here first.

## Integration with sibling skills

`/dk.implement` and `/dk.swarm` are **stage-aware** — when `stage-status.md` exists in the feature dir, they:

1. Default their task range to the current stage's range (if `$ARGUMENTS` is empty or `stage-current`).
2. Update the matching `⏳` → `✅` line in `stage-status.md` as each task completes.
3. Emit `Next: run /dk.stage close` when the stage's task range is fully `✅`.

If `stage-status.md` does not exist, they behave exactly as they always did. The stage-awareness is opt-in, feature-scoped, and backwards compatible.

## Example flow

```
$ /dk.tasks
# ... generates tasks.md with many tasks across multiple phases ...

$ /dk.stage init
# writes stage-status.md with N stages
# Next action: run /dk.stage exec (Stage 1 — Foundational)

$ /dk.stage exec
# prints: Run /dk.implement T001-T017

$ /dk.implement
# reads stage-status.md, executes T001-T017, updates ⏳→✅
# prints: Next: run /dk.stage close

$ /dk.stage close
# asks for exit-gate confirmation + cumulative prod rows + new D-entries
# advances to Stage 2
# Next action: run /dk.stage exec (Stage 2 — Auth + platform-api)

$ /dk.stage defer T043 "operator-sign-off: token blast-radius per D012"
# moves T043 to deferred, writes verification/T043.md stub

$ /dk.stage exec --parallel
# prints: Run /dk.swarm

$ /dk.swarm
# reads stage-status.md, scopes wave computation to Stage 2's range
# Wave 1 direct, Wave 2 parallel workers, merges back
# prints: Next: run /dk.stage close

$ /dk.stage close
# ...
```

