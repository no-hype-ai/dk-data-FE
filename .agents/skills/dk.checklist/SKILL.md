---
description: Generate a pre-merge verification checklist.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Overview

You are a **checklist generator**. Your job is to create a pre-merge verification checklist that ensures all specification requirements are met before the feature branch is merged.

## Process

1. Run `.dk/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks`.

2. Read `spec.md`, `plan.md`, `tasks.md`, and any existing checklists in `FEATURE_DIR/checklists/`.

3. Load `.dk/templates/checklist-template.md` for the checklist format and category structure.

4. Generate a checklist covering:

   **Functional Completeness**:
   - [ ] Each user story's acceptance criteria verified
   - [ ] All requirements (FR-001+) implemented
   - [ ] Edge cases handled

   **Technical Quality**:
   - [ ] Tests pass (unit, integration, e2e as applicable)
   - [ ] No linting errors
   - [ ] Type checking passes
   - [ ] No security vulnerabilities introduced

   **Documentation**:
   - [ ] API contracts match implementation
   - [ ] Data model matches schema
   - [ ] Setup guide is accurate

   **Deployment**:
   - [ ] Migrations are reversible
   - [ ] Environment variables documented
   - [ ] Feature flags configured (if applicable)

5. Write checklist to `FEATURE_DIR/checklists/pre-merge.md`.

## Output

Print the checklist and its file path.

## Rules

- Checklist items must be specific and verifiable — no vague items
- Reference specific files and tests where possible
- Include items from the constitution's quality standards if present

