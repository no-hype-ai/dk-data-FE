---
description: Parallel implementation orchestrator — launches worker sessions in git worktrees to execute tasks.md phases concurrently, then merges results back.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).
If `$ARGUMENTS` contains `--resume`, skip to the **Resume** section.

## Principles

Read `.dk/memory/principles.md` before acting. All output must honor the project's principles: **simple, complete, senior**.

## Overview

You are a **swarm orchestrator**. Your job is to implement the tasks in `tasks.md` using parallel worker sessions running in isolated git worktrees. You execute foundational work directly, then launch headless worker processes for independent task groups, merge their branches back, and repeat until all tasks are complete.

## Prerequisites

1. Run `.dk/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` and parse FEATURE_DIR.
2. Read `tasks.md`, `plan.md`, and the project's context file (AGENTS.md, AGENTS.md, etc.).
3. Check checklists in `FEATURE_DIR/checklists/` — if any are incomplete, warn and ask whether to proceed.
3a. **Stage awareness (optional, backwards-compatible)**: If `FEATURE_DIR/stage-status.md` exists, read it. It was written by `/dk.stage init` and carries the current stage pointer, each stage's task range, and the deferred-task list. If `$ARGUMENTS` is empty or equals `stage-current`, restrict the **wave computation below** to tasks in the current stage's task range only — all pre-stage tasks are assumed already merged (no schema re-run, no migration re-run), and all post-stage tasks are out of scope for this run. Skip any task listed as `⏸` deferred. If `stage-status.md` does NOT exist, behave exactly as before — this step is a no-op.
4. **Ensure clean git state**: Run `git status --porcelain`. If there are uncommitted changes:
   - Stage all tracked and untracked files relevant to the project (spec artifacts, plugin files, docs, config)
   - Commit with message: `"Swarm pre-flight: commit working state before parallel execution"`
   - This is REQUIRED — worktree workers branch from HEAD, so all spec artifacts must be committed for workers to access them
   - Do NOT ask the user — just commit automatically. A clean git state is a hard prerequisite for worktree isolation.

## Wave Computation

Parse `tasks.md` and compute execution waves based on the dependency graph.

### Step 1: Identify Schema Tasks

Scan tasks.md for ALL tasks that add database schema (e.g., Drizzle, Prisma, or raw SQL). These are identified by descriptions containing schema-related keywords ("Add schema", "Create table", "schema for").

Collect all schema task IDs.

### Step 2: Identify Migration Tasks

Find all tasks that run database migrations (e.g., `drizzle-kit push`, `prisma migrate`, etc.). These will be consolidated into a single migration after all schemas are written.

### Step 3: Build Waves

**Wave 1 — Foundation (execute directly in this session)**:
- ALL Phase 1 (Setup) tasks
- ALL Phase 2 (Foundational) tasks
- ALL schema tasks from ALL phases (pulled forward)
- ONE consolidated migration at the end
- After completion: `git add -A && git commit -m "Wave 1: Foundation + complete schema"`

**Wave 2+ — Parallel implementation**:
Read the "Dependencies & Execution Order" section of tasks.md. Parse the dependency graph to determine which user story phases can run in parallel. Group them into waves:

- Each wave contains 2 workers (user story groups that have no file overlap)
- A wave cannot start until its dependency wave has been merged
- Within each worker's task list, skip schema tasks (already done) and migration tasks (already done)
- Tasks within a worker run sequentially in task ID order

**Typical wave pattern** (adapt based on actual dependency graph):
- Wave 2: First independent stories (e.g., US1 + US6 if billing is independent)
- Wave 3: Stories dependent on Wave 2 results
- Wave 4: Stories dependent on Wave 3 results
- Continue until all user story phases are complete

**Final wave — Polish (execute directly in this session)**:
- All tasks in the final "Polish & Cross-Cutting Concerns" phase
- These touch multiple files across stories, so run sequentially

### Step 4: Validate No File Overlap

Before launching a wave, verify workers in that wave don't modify the same files:
- Extract file paths from task descriptions (text in backticks)
- If overlap detected: move the overlapping task to the wave's second worker or defer to the next wave
- Schema files are safe — already complete from Wave 1

## Wave 1 Execution

Execute Wave 1 directly in this session (no worktrees needed):

1. Implement each Setup task following the task descriptions exactly
2. Implement each Foundational task
3. Implement ALL schema definitions from every phase
4. Run a single consolidated migration
5. Mark each completed task as `[x]` in tasks.md
6. Commit: `git add -A && git commit -m "Wave 1: Foundation + complete schema"`

**Report progress** after Wave 1 completes.

## Worker Launch (Waves 2-5)

For each wave with parallel workers:

### Build Worker Prompts

For each worker, construct a focused prompt containing:
1. The exact task list (task ID, full description, file paths) — only tasks assigned to this worker, excluding already-completed schema/migration tasks
2. Project context summary (from context file and plan.md — tech stack, conventions, file structure)
3. The instruction: "The database schema is already complete — do NOT modify schema files."
4. Implementation rules (see Worker Rules below)
5. **If `stage-status.md` exists**: include a line like `"You are implementing tasks in Stage <N> — <stage title>. Exit gate: <entry/exit gate from stage-status.md>."` so workers know which atomic PR unit their commits belong to. Workers never modify `stage-status.md` themselves — the merge path below handles that.

### Launch Workers

Launch each worker using the Bash tool with `run_in_background: true`:

**IMPORTANT**: Workers MUST use `--dangerously-skip-permissions` because `--permission-mode auto` does NOT grant file write permissions in worktree paths. The worktree is an isolated copy of the repo — sandboxed by design.

```bash
Codex -p \
  --worktree "swarm-<worker-name>" \
  --dangerously-skip-permissions \
  --max-budget-usd 10 \
  --model sonnet \
  --append-system-prompt "You are a swarm worker. Follow these rules strictly:
1. Implement each task in the order given
2. After each task, commit with message: T0XX: <task description summary>
3. If a task fails, document the error in a comment and continue to the next task
4. At the very end of your response, output exactly one line: SWARM_RESULT:{JSON}
   where JSON is: {\"completed\":[\"T0XX\",...],\"failed\":[{\"id\":\"T0XX\",\"error\":\"...\"},...]}
5. Do NOT modify schema files — the schema is already complete
6. Read plan.md and the relevant spec files for architectural context before starting" \
  "<FULL WORKER PROMPT WITH TASK LIST>" \
  > /tmp/swarm-<worker-name>.log 2>&1 &
echo $! > /tmp/swarm-<worker-name>.pid
```

Replace `<worker-name>` with the worker identifier (e.g., `core-us1`, `billing`, `us2`, `us3`).

**IMPORTANT**: Use `run_in_background: true` on the Bash tool call so the orchestrator doesn't block.

### Monitor Workers

After launching all workers in a wave, poll for completion:

```bash
kill -0 $(cat /tmp/swarm-<worker-name>.pid) 2>/dev/null && echo "RUNNING" || echo "DONE"
```

Poll every 30 seconds. When a worker finishes:
1. Read the log: `tail -50 /tmp/swarm-<worker-name>.log`
2. Extract the `SWARM_RESULT:` line and parse the JSON
3. Record completed and failed tasks

Wait for ALL workers in the wave to complete before proceeding to merge.

### Merge Workers

For each completed worker in the wave:

```bash
BRANCH=$(git -C .Codex/worktrees/swarm-<worker-name> branch --show-current 2>/dev/null)
git merge "$BRANCH" --no-ff -m "Swarm: Merge <worker-name> (<description>)"
git worktree remove .Codex/worktrees/swarm-<worker-name> 2>/dev/null || true
git branch -d "$BRANCH" 2>/dev/null || true
```

**If merge conflicts occur**:
1. Run `git diff --name-only --diff-filter=U` to identify conflicting files
2. For each conflicting file, read both versions and resolve the conflict by combining both workers' changes
3. `git add <resolved-file>` and `git commit --no-edit`
4. If resolution is too complex, abort the merge and fall back to implementing the failed worker's tasks sequentially in the main session

After all workers in a wave merge:
- Update tasks.md to mark merged tasks as `[x]`
- Update `swarm-state.json`
- **If `stage-status.md` exists**: for each task that the merged worker branches completed, update the matching task line in the current stage's block from `⏳ T0XX — pending` to `✅ T0XX — <one-line result summary>` via an Edit. This is the stage-level progress signal that makes `/dk.stage resume` cheap after a session death. `swarm-state.json` and `stage-status.md` coexist — neither replaces the other.
- Proceed to next wave

## Final Wave (Polish) Execution

Execute the final Polish phase directly in this session (same as Wave 1 — no worktrees):
1. Implement each task sequentially
2. Mark completed tasks as `[x]`
3. Commit after each logical group

## State Persistence

Maintain `FEATURE_DIR/swarm-state.json` throughout execution. Update it:
- After Wave 1 completes
- After each worker launches (record PID)
- After each worker completes (record results)
- After each merge
- After each wave completes

Schema:
```json
{
  "feature_dir": "<absolute path>",
  "branch": "<feature branch name>",
  "current_wave": <number>,
  "total_waves": <number>,
  "total_tasks": <number>,
  "completed_tasks": <number>,
  "waves": {
    "1": {
      "status": "completed|in_progress|pending",
      "type": "direct|parallel",
      "tasks_completed": <number>,
      "committed_at": "<ISO-8601>"
    },
    "2": {
      "status": "in_progress",
      "type": "parallel",
      "workers": {
        "<name>": {
          "pid_file": "/tmp/swarm-<name>.pid",
          "log_file": "/tmp/swarm-<name>.log",
          "status": "running|completed|failed|merged",
          "tasks_assigned": ["T020", "T021"],
          "tasks_completed": ["T020", "T021"],
          "tasks_failed": [],
          "started_at": "<ISO-8601>",
          "completed_at": "<ISO-8601>"
        }
      }
    }
  },
  "failed_tasks": []
}
```

## Resume

If `$ARGUMENTS` contains `--resume`:

1. Read `FEATURE_DIR/swarm-state.json`
2. Determine the current wave and worker statuses
3. For any workers still marked "running": check if their PID is alive
   - If alive: continue monitoring
   - If dead: read their log, extract results, mark as completed or failed
4. For any incomplete waves: determine remaining work
5. Resume execution from the current point

## Error Recovery

- **Worker exits with no SWARM_RESULT**: Read the full log. If tasks were committed (check `git log` on the worktree branch), extract completed task IDs from commit messages. Mark uncommitted tasks as failed.
- **Worker fails entirely**: Fall back to implementing its tasks sequentially in the main session after merging other successful workers.
- **Merge conflict**: Resolve programmatically if possible (both sides added different files = safe auto-merge). If same-file conflict, resolve by reading both versions. Last resort: sequential fallback.
- **All workers in a wave fail**: Implement the entire wave sequentially in the main session. Log the failure in swarm-state.json.

## Completion

After all waves complete:

1. Verify all tasks in tasks.md are marked `[x]`
2. Count any remaining `[ ]` tasks — these are failures
3. Run validation (lint, typecheck) if available
4. Write final swarm-state.json with `"status": "completed"`
5. Report summary:

```
## Swarm Implementation Complete

**Branch**: <branch>
**Total tasks**: <N>
**Completed**: <N> | **Failed**: <N>

### Wave Execution Summary
| Wave | Type | Workers | Tasks | Duration |
|------|------|---------|-------|----------|
| 1 | Direct | — | 25 | 12m |
| 2 | Parallel | us1, billing | 27 | 8m |
| ... | ... | ... | ... | ... |

### Failed Tasks (if any)
- T0XX: <error description>

### Next Steps
- Review failed tasks (if any) and implement manually
- Run full test suite
- Deploy to preview environment
```

6. **Stage completion hint**: If `stage-status.md` exists and every task in the current stage's task range is now `✅` or `⏸`, print exactly one additional line: `Next: run /dk.stage close — exit gate is <type>`, where `<type>` is the `Exit gate type:` field from the current stage block. Do NOT auto-invoke `/dk.stage close` — it is always user-gated because the exit gate involves external state (PR merged, tests passing) that this skill cannot verify unilaterally.

## Rules

- **Commit frequently**: After Wave 1 and after each merge
- **Never modify schema after Wave 1**: Workers must not touch it
- **Max 2 workers per wave**: Keep parallelism manageable
- **Always update swarm-state.json**: Enables resume capability
- **Clean up worktrees**: Remove after successful merge
- **Cost guardrails**: Each worker has a `--max-budget-usd` limit
- Check for `.dk/extensions.yml` hooks before and after implementation

