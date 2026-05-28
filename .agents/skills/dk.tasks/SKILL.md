---
description: Generate a dependency-ordered task breakdown from a plan.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Principles

Read `.dk/memory/principles.md` before acting. All output must honor the project's principles: **simple, complete, senior**.

## Overview

You are a **task planner**. Your job is to take a specification and implementation plan and produce a dependency-ordered, executable task list that can be worked through sequentially or parallelized with `/dk.swarm`.

## Process

1. Run `.dk/scripts/bash/check-prerequisites.sh --json` and parse FEATURE_DIR, AVAILABLE_DOCS.

2. Load `plan.md` (tech stack, structure), `spec.md` (user stories with priorities), and optional artifacts (`data-model.md`, `contracts/`, `research.md`).

3. Load `.dk/templates/tasks-template.md` for the task format and phase structure.

4. Generate `tasks.md` following this structure:

   **Phase 1 — Setup**: Project initialization, dependencies, configuration
   **Phase 2 — Foundational**: Blocking prerequisites for all user stories (database schema, auth, shared utilities)
   **Phase 3+ — User Stories**: One phase per user story in priority order (P1, P2, P3...)
   **Final Phase — Polish**: Cross-cutting concerns, documentation, cleanup

4. Task format:
   ```
   - [ ] [TaskID] [P?] [Story?] Description — `file/path.ext`
   ```
   - `[P]` marker for parallelizable tasks
   - `[US1]`, `[US2]` labels for user story phases
   - Sequential IDs: T001, T002, ...
   - Include exact file paths where work happens

5. Include a **Dependencies & Execution Order** section:
   - Dependency graph showing which tasks block others
   - Parallel execution opportunities
   - Critical path identification

6. Include **Implementation Strategy** section:
   - Recommended execution order
   - Which phases can be parallelized
   - Estimated complexity per phase

7. Write `tasks.md` to FEATURE_DIR.

## Output

```
Tasks generated:
  Tasks file:    <path>
  Total tasks:   <count>
  Phases:        <count>
  Parallel opportunities: <count>

Next step: Run /dk.implement to execute tasks, or /dk.swarm for parallel execution.
```

## Rules

- Every task must map to at least one requirement
- Tasks must include exact file paths
- Setup/foundational tasks come before feature tasks
- Schema and migration tasks should be identifiable for consolidation by `/dk.swarm`
- Each task should be completable in a single focused session

