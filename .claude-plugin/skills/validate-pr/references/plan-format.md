# Plan File Format Reference

This document defines the expected structure for PR validation plan files consumed by the `validate-pr` skill.

## File Naming Conventions

Plan files live in the project root and follow one of these naming patterns:

- `PR<number>-PLAN.md` -- primary convention (e.g., `PR801-PLAN.md`)
- `<number>-validation-PLAN.md` -- alternate convention
- Any file matching `*PR<number>*` or `*<number>*PLAN*` (case-insensitive)

The orchestrator searches for these patterns when given a PR number as argument.

## File Structure

A plan file consists of YAML frontmatter followed by a markdown body containing phases.

### Frontmatter

```yaml
---
pr: 801
title: "Add user authentication flow"
branch: "feat/auth"
base: "staging"
created: "2026-03-30"
---
```

| Field    | Required | Description                                    |
|----------|----------|------------------------------------------------|
| `pr`     | yes      | PR number (integer)                            |
| `title`  | yes      | Human-readable PR title                        |
| `branch` | yes      | Source branch name                             |
| `base`   | no       | Target branch (defaults to `staging`)          |
| `created`| no       | Date the plan was created                      |

### Body: Phases

Each phase is a level-2 heading (`##`) prefixed with `Phase N:`. Phases execute in numerical order.

```markdown
## Phase 1: Code Review

Description of what this phase validates.

### Steps

1. **Review PR diff** -- Run `gh pr diff 801` and analyze changes
2. **Check lint** -- Run `pnpm check` in affected packages
3. **Verify types** -- Run `pnpm build` to confirm type correctness
4. **Review test coverage** -- Confirm new code has test coverage

### Verification

```bash
gh pr diff 801
pnpm check
pnpm build
```

### Checkpoint

Pause for human review of code quality findings.
```

### Phase Structure

Each phase contains:

| Section          | Required | Description                                            |
|------------------|----------|--------------------------------------------------------|
| Description      | yes      | Paragraph after the heading explaining the phase       |
| `### Steps`      | yes      | Ordered list of steps to execute                       |
| `### Verification` | no    | Bash commands to run for verification                  |
| `### Checkpoint`  | no      | If present, triggers a human-in-the-loop pause         |

### Steps Format

Each step is a numbered list item with a bold title and a description:

```markdown
1. **Step title** -- What to do and how to verify
2. **Another step** -- Description with expected outcome
```

Steps may reference:
- Shell commands to execute
- Files to read or check
- Sub-agents to dispatch (prefixed with `[agent:name]`)
- URLs to visit (prefixed with `[url:...]`)

### Agent Dispatch Markers

To indicate that a step should dispatch a sub-agent, use the `[agent:name]` prefix:

```markdown
3. **[agent:visual-validator] Check login page** -- Navigate to /login, take screenshot, verify layout at 1280x720 and 375x812
4. **[agent:pr-code-reviewer] Review auth module** -- Focus on packages/auth changes, check for security issues
5. **[agent:infra-health-checker] Verify staging pods** -- Confirm all pods running, check recent restarts
```

The orchestrator parses these markers and dispatches the named agent with the step description as context.

### Checkpoint Markers

A phase with a `### Checkpoint` section triggers the human-in-the-loop protocol. The text under the checkpoint heading describes what the human should evaluate:

```markdown
### Checkpoint

Review the visual validation results. Confirm:
- Login page renders correctly at all breakpoints
- No console errors present
- Lighthouse performance score above 80
```

Phases without a `### Checkpoint` section execute without pausing.

## Full Example Plan

```markdown
---
pr: 801
title: "Add user authentication flow"
branch: "feat/auth"
base: "staging"
created: "2026-03-30"
---

# Validation Plan: PR #801

## Phase 1: Code Review

Review all code changes for quality, security, and adherence to project conventions.

### Steps

1. **Review PR diff** -- Run `gh pr diff 801` and analyze changed files
2. **Check lint and formatting** -- Run `pnpm check` across affected packages
3. **Verify TypeScript compilation** -- Run `pnpm build` to confirm no type errors
4. **[agent:pr-code-reviewer] Deep review** -- Review auth module for security issues, missing error handling, and test coverage

### Verification

```bash
gh pr diff 801
pnpm check
pnpm build
```

### Checkpoint

Review code quality findings before proceeding to visual validation.

## Phase 2: Visual Validation

Verify UI changes render correctly across breakpoints.

### Steps

1. **[agent:visual-validator] Check login page** -- Navigate to http://localhost:3000/login, screenshot at 1280x720 and 375x812, check console for errors
2. **[agent:visual-validator] Check signup flow** -- Navigate through /signup, verify form validation states
3. **Lighthouse audit** -- Run performance audit on /login, target score above 80

### Verification

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/login
```

### Checkpoint

Review visual validation screenshots and Lighthouse scores.

## Phase 3: Infrastructure Health

Verify staging environment is healthy after deployment.

### Steps

1. **[agent:infra-health-checker] Pod health** -- Check all pods in staging namespace, verify no restarts
2. **[agent:infra-health-checker] Service connectivity** -- Test API health endpoint, verify database connectivity

### Checkpoint

Confirm infrastructure is stable before final report.

## Phase 4: Final Report

Generate and present the validation summary.

### Steps

1. **Generate report** -- Compile results from all phases into the final validation report table
```

## Auto-Generated Plans

When no plan file exists for a PR number, the orchestrator generates a minimal plan with two phases:

1. **Code Review** -- diff analysis, lint check, type check, and pr-code-reviewer agent dispatch
2. **Verification** -- build confirmation and test execution

The generated plan is written to `PR<number>-PLAN.md` and presented for human approval before execution begins.
