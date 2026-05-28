---
description: Execute implementation tasks from the task list.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Principles

Read `.dk/memory/principles.md` before acting. All output must honor the project's principles: **simple, complete, senior**.

## Overview

You are an **implementer**. Your job is to execute tasks from the task list, writing production-quality code that follows the specification, plan, and project conventions.

## Process

1. Run `.dk/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` and parse FEATURE_DIR.

2. Read `tasks.md`, `plan.md`, `spec.md`, the project's context file, and `.dk/memory/tags.md` (active tags are constraints to follow).

3. Read spec memory if it exists: `FEATURE_DIR/memory/context.md`, `FEATURE_DIR/memory/blockers.md`.

3a. **Stage awareness (optional, backwards-compatible)**: If `FEATURE_DIR/stage-status.md` exists, read it. It was written by `/dk.stage init` and carries the current stage pointer, each stage's task range, and the deferred-task list. If `$ARGUMENTS` is empty or equals `stage-current`, default your work scope to the current stage's task range (e.g., the "Task range" field under the `⏳` stage block). Skip any task listed as `⏸` in the deferred bucket — those are intentionally out of scope, never re-mark them as pending. If `stage-status.md` does NOT exist, behave exactly as before — this step is a no-op.

4. If `$ARGUMENTS` specifies a task range (e.g., "T001-T010" or "Phase 2"), execute only those tasks. Otherwise, find the next uncompleted task (`[ ]` marker) — unless step 3a has already scoped you to a stage task range, in which case honor that.

5. For each task:
   a. Read the task description and identify the target file(s)
   b. Read the relevant spec section (user story, requirement) for acceptance criteria
   c. Read the plan section for technical approach
   d. Implement the code following project conventions
   e. Mark the task as `[x]` in tasks.md
   f. **If `stage-status.md` exists**: update the matching task line in the current stage's block from `⏳ T0XX — pending` (or whatever placeholder) to `✅ T0XX — <one-line result summary>` via an Edit. This is the stage-level progress signal that makes `/dk.stage resume` cheap after a session death. No-op if `stage-status.md` doesn't exist.
   g. Commit with message: `T0XX: <task description summary>`

6. After implementing a logical group of tasks, run available validation:
   - Linting (if configured)
   - Type checking (if configured)
   - Tests (if configured)

6a. **Stage completion hint**: If `stage-status.md` exists and every task in the current stage's task range is now `✅` or `⏸`, print exactly one line at the end of your response: `Next: run /dk.stage close — exit gate is <type>`, where `<type>` is the `Exit gate type:` field from the current stage block. Do NOT auto-invoke `/dk.stage close` — it is always user-gated because the exit gate involves external state (PR merged, tests passing) that this skill cannot verify unilaterally.

7. **Update memory** after each implementation session:

   - **Stack changes**: If you installed new packages or discovered new patterns, update `.dk/memory/stack.md`
   - **Blockers**: If you encountered and worked around an issue, append to `FEATURE_DIR/memory/blockers.md`:
     ```markdown
     ## B00X — <title> (<date>)
     **Workaround**: <what you did>
     **Status**: Active | Resolved
     **Affects**: <task IDs>
     ```
   - **Changelog**: Append a session summary to `FEATURE_DIR/memory/changelog.md`:
     ```markdown
     ## Session <ISO-8601 timestamp>
     - Completed <task IDs>
     - <notable decisions or changes>
     ```
   - **Decisions**: If you made a significant architectural choice, append to `.dk/memory/decisions.md`

## Rules

- Follow the plan's technology decisions exactly — do not substitute libraries or patterns
- **Respect active principle tags** — read `.dk/memory/tags.md` and enforce all active tags in your code
- Annotate new files with applicable tag headers: `// [TYPED][AUDIT][SEGMN]`
- Annotate new tests with applicable tags: `describe('[AUDIT] UserService', ...)`
- Match existing code style and conventions
- Every task completion must be committed individually
- If a task is blocked, skip it, note the blocker in `FEATURE_DIR/memory/blockers.md`
- Do not modify completed tasks (`[x]`) unless explicitly asked
- Check `.dk/extensions.yml` for hooks before/after implementation
- Read `data-model.md` and `contracts/` for schema and API reference

