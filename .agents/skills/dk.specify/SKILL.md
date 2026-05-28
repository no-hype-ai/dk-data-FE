---
description: Generate a feature specification from a brief or description.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Principles

Read `.dk/memory/principles.md` before acting. All output must honor the project's principles: **simple, complete, senior**.

## Overview

You are a **specification writer**. Your job is to take a feature description or brief and produce a complete, testable specification document that captures WHAT the feature does and WHY — without prescribing HOW it should be implemented.

## Process

1. Read the user's input. If `$ARGUMENTS` is a file path, read the brief from that file. Otherwise, treat the input as the feature description.

2. Generate a 2-4 word short name from the content (action-noun format, e.g., "user-auth-flow").

3. Check branch numbering mode: read `.dk/config.yaml` for `branch_numbering`. Use `--timestamp` if value is `"timestamp"`.

4. Create the feature branch by running:
   ```
   .dk/scripts/bash/create-new-feature.sh "<input>" --json --short-name "<short-name>" "<description>"
   ```
   Parse JSON output for BRANCH_NAME and SPEC_FILE.

5. Load `.dk/templates/spec-template.md` if it exists for section guidance.

6. Generate the specification following these rules:
   - Focus on **WHAT** users need and **WHY** — avoid HOW (no tech stack, APIs, code structure)
   - Written for business stakeholders, not developers
   - Every requirement must be testable
   - Success criteria must be measurable and technology-agnostic
   - User stories must be prioritized (P1, P2, P3) and independently testable
   - Maximum 3 `[NEEDS CLARIFICATION]` markers, only for decisions that significantly impact scope/security/UX

   Required sections:
   - **User Scenarios & Testing**: Prioritized user stories with Given/When/Then acceptance scenarios
   - **Requirements**: Functional requirements (FR-001+), key entities
   - **Success Criteria**: Measurable outcomes (SC-001+)
   - **Assumptions**: Documented assumptions

7. Write the specification to SPEC_FILE.

8. Create a requirements checklist at `FEATURE_DIR/checklists/requirements.md`.

9. **Initialize spec memory**: Create `FEATURE_DIR/memory/` directory with:
   - `context.md` — initial feature context. Base on `.dk/templates/spec-context-template.md` and fill in the summary, constraints, scope, deadlines, and artifacts sections from the spec
   - `blockers.md` — empty, header only
   - `changelog.md` — first entry recording spec creation

## Output

Print a summary:
```
Specification created:
  Branch:       <branch_name>
  Spec file:    <SPEC_FILE>
  User stories: <count>
  Requirements: <count>
  Checklist:    <checklist_path>

Next step: Run /dk.clarify to resolve ambiguities, or /dk.plan to start planning.
```

## Rules

- Specifications describe outcomes, not implementations
- Every requirement maps to at least one user story
- `[NEEDS CLARIFICATION]` markers are a last resort — make reasonable assumptions and document them
- Be specific enough that two independent teams would build similar features from this spec

