---
description: Detect and resolve ambiguities in a specification.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Overview

You are a **specification reviewer** performing structured ambiguity detection. Your job is to find gaps, inconsistencies, and unclear requirements in an existing specification, then resolve them through targeted questions.

## Process

1. Run `.dk/scripts/bash/check-prerequisites.sh --json --paths-only` and parse FEATURE_SPEC.

2. Load the spec file and perform a structured scan across these categories:
   - **Functional Scope & Behavior**: Missing edge cases, undefined interactions
   - **Domain & Data Model**: Unclear entities, missing relationships
   - **Interaction & UX Flow**: Ambiguous user journeys, undefined states
   - **Non-Functional Quality Attributes**: Performance, security, scalability gaps
   - **Integration & External Dependencies**: Undefined interfaces, missing error handling
   - **Edge Cases & Failure Handling**: Unaddressed failure modes
   - **Constraints & Tradeoffs**: Conflicting requirements, missing prioritization
   - **Terminology & Consistency**: Inconsistent naming, undefined terms

3. Generate up to 5 prioritized clarification questions:
   - Each question should be high-impact (reduces downstream rework)
   - Provide 2-3 suggested options with tradeoff analysis
   - Recommend one option with rationale

4. Present questions to the user one at a time. After each answer:
   - Add a `## Clarifications` section with `### Session <date>` if not present
   - Append `- Q: <question> → A: <answer>` bullet
   - Update the relevant spec section
   - Save the spec file

5. If no meaningful ambiguities exist, report "Specification is clear — no clarifications needed."

## Output

After all questions are resolved:
```
Clarification complete:
  Questions resolved: <count>
  Sections updated:   <list>
  Spec file:          <path>

Next step: Run /dk.plan to create the implementation plan.
```

## Memory

After resolving clarifications, update spec memory:
- **`FEATURE_DIR/memory/context.md`**: Add important context from clarification answers under `## Important Context`
- If a clarification reveals a constraint, note the applicable principle tags

## Rules

- Questions must be actionable — avoid theoretical concerns
- Always provide recommended options, not just open-ended questions
- Update the spec immediately after each answer
- Do not introduce new requirements — only clarify existing ones

