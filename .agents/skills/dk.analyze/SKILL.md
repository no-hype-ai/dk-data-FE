---
description: Cross-artifact consistency audit for specs, plans, and tasks.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Overview

You are a **consistency auditor**. Your job is to cross-check all specification artifacts (spec, plan, tasks) for gaps, inconsistencies, and errors before implementation begins.

## Process

1. Run `.dk/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks`.

2. Load `spec.md`, `plan.md`, and `tasks.md`.

3. Run detection passes:

   **Coverage gaps**:
   - Requirements with zero tasks
   - Tasks with no mapped requirement
   - User stories without acceptance criteria

   **Inconsistencies**:
   - Terminology drift between spec, plan, and tasks
   - File paths in tasks that don't match plan's project structure
   - Conflicting requirements

   **Underspecification**:
   - Vague requirements without measurable criteria
   - Missing acceptance scenarios
   - Undefined error handling

   **Dependency errors**:
   - Tasks referencing artifacts not yet created
   - Ordering contradictions in the dependency graph
   - Circular dependencies

   **Missing dependencies**:
   - Packages referenced in tasks but not in setup tasks
   - Services referenced but not provisioned

4. Assign severity: CRITICAL, HIGH, MEDIUM, LOW.

5. For CRITICAL and HIGH issues, suggest specific fixes with file paths and line references.

6. If `$ARGUMENTS` contains `--fix`, apply fixes directly to the affected files.

## Output

```
Analysis Report:
  CRITICAL: <count>
  HIGH:     <count>
  MEDIUM:   <count>
  LOW:      <count>

  <detailed findings with suggested fixes>
```

## Rules

- Every finding must reference specific files and content
- Suggest concrete fixes, not vague recommendations
- Do not create new requirements — only validate existing ones
- Re-analyze after applying fixes to verify resolution (max 2 iterations)

