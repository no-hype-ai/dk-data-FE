---
description: Create a technical implementation plan from a specification.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Principles

Read `.dk/memory/principles.md` before acting. All output must honor the project's principles: **simple, complete, senior**.

## Overview

You are a **technical architect**. Your job is to take a specification and produce a comprehensive implementation plan including technology decisions, data models, API contracts, and project structure. You also manage the project's **principle tags** and **tech stack memory**.

## Process

1. Run `.dk/scripts/bash/setup-plan.sh --json` and parse FEATURE_SPEC, IMPL_PLAN, SPECS_DIR, BRANCH.

2. Load the spec file and check for `.dk/memory/constitution.md` (reference if present).

3. Load `.dk/templates/plan-template.md` for the plan structure and sections.

4. Generate the implementation plan:

   ### Technical Context
   Extract from the spec and project: language, dependencies, storage, testing framework, platform, project type, performance goals, constraints, scale expectations. Mark unknowns as `[NEEDS RESEARCH]`.

   ### Phase 0 — Research
   For each unknown or dependency:
   - Research options and document decisions in `research.md`
   - Format: Decision, Rationale, Alternatives considered

   ### Phase 1 — Design
   Generate these artifacts in SPECS_DIR:
   - **`data-model.md`**: Entities, fields, relationships, validation rules, state transitions. Base schema contracts on `.dk/templates/contract-schema-template.md`.
   - **`contracts/`**: One file per interface. Use the appropriate template as a starting point:
     - REST/JSON APIs → `.dk/templates/contract-api-template.md`
     - Async events / webhooks → `.dk/templates/contract-webhook-template.md`
     - Persisted data models → `.dk/templates/contract-schema-template.md`
   - **`quickstart.md`**: Step-by-step setup guide for a new developer

5. Write `plan.md` to IMPL_PLAN with:
   - Technology decisions with rationale
   - Project structure (directory tree with purpose annotations)
   - Component breakdown with dependencies
   - Testing strategy
   - Deployment approach

6. **Update global memory** (critical — do not skip):

   ### Update `.dk/memory/stack.md`
   Write the discovered tech stack as a table:
   ```markdown
   | Layer | Technology | Version | Notes |
   |-------|-----------|---------|-------|
   | Language | <detected> | <version> | <notes> |
   ...
   ```
   Include a `## Patterns` section with discovered code patterns (route structure, component patterns, schema location, etc.).

   ### Manage `.dk/memory/tags.md`
   Read the tags file. Review the **Available Tags** against the discovered stack and spec requirements. For each relevant tag:
   - **Activate it**: Move from Available to Active Tags table
   - Apply these heuristics:
     - TypeScript project → activate `[TYPED]`
     - Has API routes → activate `[VERSN]`, `[ZVAL]`
     - Has authentication → activate `[RBAC]`
     - Multi-tenant / org-scoped → activate `[SEGMN]`
     - Uses LLMs / AI → activate `[STRM]`
     - Healthcare / regulated → activate `[HIPAA]`, `[NCMPL]`, `[AUDIT]`
     - Has frontend → activate `[A11Y]`
     - Has external API calls → activate `[BRKR]`
   - **Add new project-specific tags** if the spec reveals constraints not covered by available tags
   - Record each tag activation as a decision

   ### Update `.dk/memory/decisions.md`
   Append each significant technology choice and tag activation:
   ```markdown
   ## D00X — <Decision Title> (<date>)
   **Context**: <why this decision was needed>
   **Decision**: <what was chosen>
   **Rationale**: <why>
   **Tags**: [relevant tags]
   ```

   ### Initialize spec memory
   Create `SPECS_DIR/memory/` directory if it doesn't exist. Write `context.md`:
   ```markdown
   # Feature: <feature name>

   ## Key Constraints
   Tags: [list active tags relevant to this feature]

   ## Important Context
   - <key decisions and context from planning>

   ## Open Questions
   - [ ] <any unresolved items>
   ```

7. Run `.dk/scripts/bash/update-agent-context.sh` to propagate memory to agent context files.

## Output

```
Plan created:
  Plan file:     <IMPL_PLAN>
  Research:       <research.md path>
  Data model:     <data-model.md path>
  Contracts:      <contracts/ path>
  Quickstart:     <quickstart.md path>

Memory updated:
  Stack:          .dk/memory/stack.md (<N> technologies)
  Tags activated: [TAG1] [TAG2] [TAG3] (<N> total active)
  Decisions:      .dk/memory/decisions.md (<N> new)
  Feature context: <SPECS_DIR>/memory/context.md

Next step: Run /dk.tasks to generate the task breakdown.
```

## Rules

- Every technology choice needs rationale — no "just because"
- Data model must cover all entities referenced in the spec
- API contracts must cover all interactions from user stories
- Plan must be specific enough for a developer unfamiliar with the project to start working
- **Always update memory** — stack.md, tags.md, decisions.md after planning
- **Always activate relevant tags** — don't leave applicable tags in Available
- Check `.dk/extensions.yml` for hooks before/after plan phase

