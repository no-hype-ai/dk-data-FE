---
description: Autonomously run the full DK pipeline (specify -> clarify -> plan -> tasks -> analyze) from a markdown brief, making all decisions without user input.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Overview

You are an **autonomous orchestrator**. Your job is to take a markdown brief file and run the entire DK specification pipeline to completion — making every decision yourself — so that the user ends up with a complete, analyzed set of specification artifacts ready for `/dk.implement`.

**CRITICAL OPERATING MODE**: You are in AUTONOMOUS mode. For ALL clarification questions, multiple-choice selections, and decision points throughout this pipeline:
1. Analyze the options based on the brief's context, industry best practices, and risk reduction
2. Select the best option WITHOUT waiting for user input
3. Record every decision in the audit trail JSON (built in memory, written at the end)

**NEVER ask the user a question. NEVER pause for input. Make every decision yourself and document your reasoning.**

## Audit Trail

Maintain an in-memory JSON object throughout the run. Initialize it at the start:

```json
{
  "version": "1.0",
  "feature": "",
  "branch": "",
  "brief_file": "",
  "started_at": "<current ISO-8601 timestamp>",
  "completed_at": "",
  "phases": {}
}
```

Update it after each phase. Write it to `FEATURE_DIR/auto-decisions.json` at the very end.

## Execution Pipeline

### Phase 1: SPECIFY

**Goal**: Generate the feature specification from the brief.

1. Read the brief file from `$ARGUMENTS`. If the path is empty, ERROR and stop.

2. Generate a 2-4 word short name from the brief content (action-noun format, e.g., "mvp-day-execution").

3. Check branch numbering mode: read `.dk/config.yaml` if it exists for `branch_numbering`. Add `--timestamp` if value is `"timestamp"`.

4. Create the feature branch by running:
   ```
   .dk/scripts/bash/create-new-feature.sh "<brief_path>" --json --short-name "<short-name>" "<description>"
   ```
   Parse JSON output for BRANCH_NAME and SPEC_FILE. **Run this script exactly once.**

5. Load `.dk/templates/spec-template.md`.

6. Analyze the brief and generate the full specification following these rules:
   - Focus on **WHAT** users need and **WHY** — avoid HOW (no tech stack, APIs, code structure)
   - Written for business stakeholders, not developers
   - Make informed guesses for unspecified details — document assumptions
   - Maximum 3 `[NEEDS CLARIFICATION]` markers, and only for decisions that significantly impact scope/security/UX with no reasonable default
   - Every requirement must be testable
   - Success criteria must be measurable and technology-agnostic
   - User stories must be prioritized (P1, P2, P3) and independently testable

   Required sections (from template):
   - User Scenarios & Testing (prioritized user stories with Given/When/Then acceptance scenarios, edge cases)
   - Requirements (functional requirements FR-001+, key entities)
   - Success Criteria (measurable outcomes SC-001+)
   - Assumptions

7. Write the specification to SPEC_FILE.

8. **Self-validate** the spec against quality criteria:
   - No implementation details (languages, frameworks, APIs)
   - All mandatory sections completed
   - Requirements are testable and unambiguous
   - Success criteria are measurable and technology-agnostic
   - If any `[NEEDS CLARIFICATION]` markers remain: resolve them NOW by choosing the most reasonable option. Record each resolution in audit trail under `phases.specify.autonomous_decisions`.

9. Create checklist at `FEATURE_DIR/checklists/requirements.md`.

10. Record in audit trail:
    ```json
    "specify": {
      "status": "completed",
      "spec_file": "<path>",
      "user_stories_count": <N>,
      "requirements_count": <N>,
      "success_criteria_count": <N>,
      "autonomous_decisions": [
        { "type": "clarification_resolution", "question": "...", "chosen": "...", "reasoning": "..." }
      ]
    }
    ```

### Phase 2: CLARIFY

**Goal**: Detect ambiguities in the spec and resolve them autonomously.

1. Run `.dk/scripts/bash/check-prerequisites.sh --json --paths-only` and parse FEATURE_SPEC.

2. Load the spec file. Perform the structured ambiguity scan across these categories:
   - Functional Scope & Behavior
   - Domain & Data Model
   - Interaction & UX Flow
   - Non-Functional Quality Attributes
   - Integration & External Dependencies
   - Edge Cases & Failure Handling
   - Constraints & Tradeoffs
   - Terminology & Consistency

3. Generate up to 5 prioritized clarification questions (high-impact, reduce downstream rework).

4. **For each question**: Autonomously select the best answer:
   - Analyze all options against the brief's intent, best practices, and risk profile
   - Choose the recommended option (or generate a better one if none fit well)
   - Record the decision with reasoning

5. After each answer, immediately integrate it into the spec:
   - Add a `## Clarifications` section with `### Session <date>` if not present
   - Append `- Q: <question> → A: <answer>` bullet
   - Update the relevant spec section (requirements, edge cases, entities, etc.)
   - Save the spec after each integration

6. If no meaningful ambiguities exist, skip to Phase 3.

7. Record in audit trail:
    ```json
    "clarify": {
      "status": "completed",
      "questions_resolved": <N>,
      "decisions": [
        { "question": "...", "category": "...", "options_considered": ["A", "B", "C"], "chosen": "...", "reasoning": "..." }
      ],
      "sections_updated": ["..."]
    }
    ```

### Phase 3: PLAN

**Goal**: Generate the implementation plan, research decisions, data model, and contracts.

1. Run `.dk/scripts/bash/setup-plan.sh --json` and parse FEATURE_SPEC, IMPL_PLAN, SPECS_DIR, BRANCH.

2. Load the spec file and check for `.dk/memory/constitution.md` (skip constitution check if absent).

3. Fill the plan template:
   - **Technical Context**: Extract from the brief (language, dependencies, storage, testing, platform, project type, performance goals, constraints, scale). Mark any unknowns as NEEDS CLARIFICATION.
   - **Constitution Check**: Evaluate gates if constitution exists.
   - **Phase 0 (Research)**: For each unknown/dependency/integration, research and document decisions in `research.md` with: Decision, Rationale, Alternatives considered.
   - **Phase 1 (Design)**: Generate `data-model.md` (entities, fields, relationships, validation rules, state transitions), `contracts/` (API endpoints, real-time events), `quickstart.md` (setup guide).

4. Write all artifacts to SPECS_DIR.

5. **Update global memory**:
   - **`.dk/memory/stack.md`**: Write discovered tech stack table and patterns
   - **`.dk/memory/tags.md`**: Review Available Tags against stack. Activate relevant tags (TypeScript → `[TYPED]`, API routes → `[VERSN]`/`[ZVAL]`, auth → `[RBAC]`, multi-tenant → `[SEGMN]`, etc.). Add project-specific tags if needed.
   - **`.dk/memory/decisions.md`**: Append each significant tech decision and tag activation
   - **`SPECS_DIR/memory/context.md`**: Initialize with feature name, active tags, and key context from planning

6. Run `.dk/scripts/bash/update-agent-context.sh` to update AI context files.

7. Record any autonomous research decisions and tag activations in audit trail:
    ```json
    "plan": {
      "status": "completed",
      "artifacts": ["plan.md", "research.md", "data-model.md", "contracts/", "quickstart.md"],
      "research_decisions": [
        { "topic": "...", "decision": "...", "reasoning": "..." }
      ],
      "tags_activated": ["[TAG1]", "[TAG2]"],
      "tags_added": [],
      "stack_entries": <N>
    }
    ```

### Phase 4: TASKS

**Goal**: Generate the dependency-ordered task list from design artifacts.

1. Run `.dk/scripts/bash/check-prerequisites.sh --json` and parse FEATURE_DIR, AVAILABLE_DOCS.

2. Load plan.md (tech stack, structure), spec.md (user stories with priorities), and optional artifacts (data-model.md, contracts/, research.md).

3. Generate tasks.md following this structure:
   - **Phase 1**: Setup (project initialization)
   - **Phase 2**: Foundational (blocking prerequisites for all user stories)
   - **Phase 3+**: One phase per user story in priority order (P1, P2, P3...)
   - **Final Phase**: Polish & cross-cutting concerns

   Task format: `- [ ] [TaskID] [P?] [Story?] Description with file path`
   - [P] marker for parallelizable tasks
   - [US1], [US2] labels for user story phases
   - Sequential IDs (T001, T002, ...)
   - Include exact file paths

4. Include dependency graph, parallel execution examples, and implementation strategy.

5. Write tasks.md to FEATURE_DIR.

6. Record in audit trail:
    ```json
    "tasks": {
      "status": "completed",
      "total_tasks": <N>,
      "phases": <N>,
      "user_stories": <N>,
      "parallel_opportunities": <N>
    }
    ```

### Phase 5: ANALYZE

**Goal**: Cross-artifact consistency check. Fix any issues found.

1. Run `.dk/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks`.

2. Load spec.md, plan.md, and tasks.md.

3. Run detection passes:
   - **Coverage gaps**: Requirements with zero tasks, tasks with no mapped requirement
   - **Inconsistencies**: Terminology drift, source tree vs task file paths, conflicting requirements
   - **Underspecification**: Vague requirements, missing acceptance criteria
   - **Dependency errors**: Tasks referencing artifacts not yet created, ordering contradictions
   - **Missing dependencies**: Packages referenced in tasks but not in setup tasks

4. Assign severity: CRITICAL, HIGH, MEDIUM, LOW.

5. **In autonomous mode**: Fix all CRITICAL and HIGH issues directly by editing the affected files. For MEDIUM issues, fix if straightforward. Document all fixes.

6. Re-analyze after fixes to verify resolution (max 2 iterations).

7. Record in audit trail:
    ```json
    "analyze": {
      "status": "completed",
      "issues_found": <N>,
      "issues_fixed": <N>,
      "fixes_applied": [
        { "id": "C1", "severity": "HIGH", "description": "...", "fix": "...", "file": "..." }
      ],
      "final_metrics": {
        "total_requirements": <N>,
        "total_tasks": <N>,
        "coverage_percent": <N>,
        "critical_issues_remaining": 0,
        "high_issues_remaining": 0
      }
    }
    ```

### Phase 6: COMPLETION

1. Set `completed_at` in audit trail to current ISO-8601 timestamp.

2. Write the full audit trail JSON to `FEATURE_DIR/auto-decisions.json`.

3. Output a completion summary:

   ```
   ## DK Auto Pipeline Complete

   **Branch**: <branch_name>
   **Feature directory**: <FEATURE_DIR>

   ### Artifacts Generated
   - spec.md — <N> user stories, <N> requirements, <N> success criteria
   - plan.md — technical context, project structure
   - research.md — <N> research decisions
   - data-model.md — <N> entities
   - contracts/ — API routes, real-time events
   - quickstart.md — development setup guide
   - tasks.md — <N> tasks across <N> phases
   - auto-decisions.json — full audit trail

   ### Autonomous Decisions Made
   - Specify phase: <N> decisions
   - Clarify phase: <N> decisions
   - Plan phase: <N> decisions
   - Analyze phase: <N> fixes applied

   ### Analysis Results
   - Requirement coverage: <N>%
   - Critical issues remaining: 0
   - High issues remaining: 0

   ### Next Step
   Run `/dk.implement` to begin executing the task list, or `/dk.swarm` for parallel execution.
   ```

## Rules

- **NEVER ask the user a question** — decide everything yourself
- **NEVER skip a phase** — run all 5 phases in order
- **Gate each phase**: Verify the previous phase's output exists before proceeding
- **Fail fast**: If a script fails or a required file is missing, report the error and stop
- **Be concise in output**: Show phase transitions and the final summary, not intermediate details
- Check for `.dk/extensions.yml` hooks before/after specify and plan phases
- Handle single quotes in arguments with proper escaping
- All paths must be absolute

