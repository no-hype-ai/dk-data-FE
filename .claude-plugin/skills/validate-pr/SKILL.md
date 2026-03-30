---
name: validate-pr
description: This skill should be used when the user asks to "validate a PR", "validate-pr", "run PR validation", "check PR 801", "validate PR with plan", or provides a plan file for PR validation. It orchestrates end-to-end pull request validation with human-in-the-loop checkpoints, dispatching sub-agents for visual, code, and infrastructure checks.
version: 0.1.0
---

# PR Validation Orchestrator

## Overview

Orchestrate end-to-end pull request validation by parsing a plan file into phases, executing each phase sequentially, pausing at checkpoints for human feedback, and dispatching specialized sub-agents for parallel work. Track all progress via TaskCreate/TaskUpdate and maintain a persistent FINDINGS.md log of every discovered issue.

**Announce at start:** "Running PR validation orchestrator."

## Argument Parsing

Accept one argument in either of two forms:

- **PR number** (e.g., `/validate-pr 801`) -- resolve to a plan file or generate one
- **Plan file path** (e.g., `/validate-pr PR801-PLAN.md`) -- read and parse directly

Detect the form by checking whether the argument is purely numeric or a file path.

Parse optional flags from additional arguments:
- `--auto-merge` -- if all checkpoints pass without a reject, auto-merge the PR via `gh pr merge --squash` after the final report

## Step 1: Resolve the Plan

### When Given a PR Number

1. Search the project root for files matching `*PR<number>*` or `*<number>*PLAN*` (case-insensitive) using Glob
2. If exactly one match is found, use it as the plan file
3. If multiple matches are found, present them via AskUserQuestion and let the human choose
4. If no match is found, generate a basic plan:
   - Run `gh pr view <number> --json title,body,headRefName,baseRefName,files,additions,deletions`
   - Extract the PR title, branch name, and changed files
   - Construct a minimal two-phase plan: (a) Code Review phase, (b) Verification phase
   - Write the generated plan to `PR<number>-PLAN.md` in the project root
   - Present the generated plan to the human for approval before proceeding

### When Given a Plan File Path

1. Read the file using the Read tool
2. If the file does not exist, report the error and halt

## Step 2: Parse Plan into Phases

Parse the plan file according to the format documented in `${CLAUDE_PLUGIN_ROOT}/skills/validate-pr/references/plan-format.md`.

Extract from the plan:
- **Metadata**: PR number, title, branch
- **Phases**: ordered list, each containing steps and an optional checkpoint
- **Checkpoints**: the gate points requiring human approval

Create a TaskCreate entry for each phase with status `pending`. Announce the parsed phase list with a summary table:

```
| # | Phase               | Steps | Checkpoint |
|---|---------------------|-------|------------|
| 1 | Code Review         | 4     | yes        |
| 2 | Visual Validation   | 3     | yes        |
| 3 | Infrastructure      | 2     | yes        |
| 4 | Final Report        | 1     | no         |
```

## Step 3: Execute Phases Sequentially

For each phase in order:

1. Mark the phase task as `in_progress` via TaskUpdate
2. Execute each step within the phase (see Step 4 for sub-agent dispatch)
3. If the phase contains a checkpoint, run the checkpoint protocol (see Step 5)
4. Mark the phase task as `completed` via TaskUpdate
5. Proceed to the next phase

If a phase fails or a checkpoint returns `reject`, halt execution immediately. Report the failure and the current state of all phases.

## Step 4: Dispatch Sub-Agents

Dispatch specialized agents for parallel work within a phase. Each agent receives a focused prompt with only the context it needs.

### visual-validator Agent

Dispatch for phases involving UI or browser verification. The agent uses Chrome DevTools MCP tools to:
- Navigate to the target URL
- Take screenshots for visual comparison
- Check console for errors
- Validate responsive layouts at specified breakpoints
- Run Lighthouse audits when requested

Provide the agent with: target URLs, expected visual states, breakpoints to test, and any baseline screenshots for comparison.

### pr-code-reviewer Agent

Dispatch for code quality review phases. The agent:
- Reads the PR diff via `gh pr diff <number>`
- Checks for lint issues, type errors, and test coverage
- Reviews architecture alignment with project conventions
- Identifies security concerns, performance issues, and missing error handling

Provide the agent with: the PR number, relevant CLAUDE.md sections, and any specific review criteria from the plan.

### infra-health-checker Agent

Dispatch for infrastructure verification phases. The agent:
- Checks pod health via kubectl commands
- Verifies ArgoCD sync status
- Tests database migrations
- Validates environment variables and secrets
- Confirms service connectivity

Provide the agent with: the target environment (staging/production), expected service list, and any specific health checks from the plan.

### Identifying Agent Steps

Steps in the plan that begin with `[agent:name]` indicate sub-agent dispatch. Parse the agent name from the bracket prefix and the task description from the remainder of the step text. If a step does not have an agent prefix, execute it directly within the orchestrator.

### Dispatch Pattern

When a phase specifies parallel agent work:

```
TaskCreate("visual-validator: check login page")
TaskCreate("pr-code-reviewer: review auth changes")
```

Dispatch agents concurrently using the Task tool. Wait for all dispatched agents to complete before proceeding to the phase checkpoint. Collect each agent's output and merge findings into the phase results.

### Agent Failure Handling

If a sub-agent fails or times out:
1. Log the failure as a HIGH severity finding in FINDINGS.md
2. Mark the corresponding step as `failed` in the phase results
3. Continue with remaining steps in the phase -- do not halt on agent failure
4. Present the failure clearly at the checkpoint so the human can decide how to proceed

## Step 5: Checkpoint Protocol

At each checkpoint, pause execution and present findings to the human. Follow the full protocol documented in `${CLAUDE_PLUGIN_ROOT}/skills/validate-pr/references/checkpoint-protocol.md`.

### Checkpoint Prompt

Use AskUserQuestion with a structured prompt:

```
CHECKPOINT: [Phase Name]

Completed steps:
- [step 1 summary and result]
- [step 2 summary and result]

Issues found: [count]
[list any issues]

Action required — respond with one of:
  approve    - proceed to next phase
  skip [phase] - skip a named phase
  reject     - halt validation entirely
  rerun [step] - re-execute a specific step
  fix [description] - dispatch agent to fix before continuing
```

### Handling Responses

| Response | Action |
|----------|--------|
| `approve` or `continue` | Proceed to the next phase |
| `skip [phase]` | Mark the named phase as `skipped`, remove from execution queue |
| `reject` or `stop` | Halt all validation, mark remaining phases as `cancelled`, generate partial report |
| `rerun [step]` | Re-execute the named step within the current phase, then re-present the checkpoint |
| `fix [description]` | Dispatch an agent with the fix description, wait for completion, re-run affected steps, then re-present the checkpoint |

If the response is not recognized, ask again with clarification.

## Step 6: Maintain FINDINGS.md

Maintain a `FINDINGS.md` file in the project root as an append-only log.

### On Every Discovery

Append a new entry regardless of whether the finding relates to the current PR:

```markdown
## [SEVERITY] Finding Title
- **PR**: #801
- **Phase**: Visual Validation
- **Discovered**: 2026-03-30T14:22:00Z
- **Status**: open
- **Description**: Brief description of the issue
- **Evidence**: Screenshot path, log snippet, or command output
```

Severity levels: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`.

If FINDINGS.md does not exist, create it with a header:

```markdown
# PR Validation Findings

Append-only log of issues discovered during PR validation runs.

---
```

Never remove or modify existing entries. Only append new ones.

## Step 7: Auto-Merge Gate

If the `--auto-merge` flag was provided and all of the following are true:
- Every checkpoint received an `approve` response (no skips, no reruns, no fixes)
- Zero CRITICAL or HIGH severity findings
- All sub-agents completed successfully

Then execute:
```bash
gh pr merge <number> --squash --delete-branch
```

If any condition is not met, report why auto-merge was skipped and present the merge decision to the human.

## Step 8: Generate Final Report

After all phases complete (or after a halt), generate a validation report table:

```
# PR Validation Report: #801

## Summary
- **PR**: #801 - Add user authentication
- **Branch**: feat/auth -> staging
- **Duration**: 12m 34s
- **Result**: PASSED / FAILED / PARTIAL

## Phase Results
| # | Phase             | Status    | Issues | Duration |
|---|-------------------|-----------|--------|----------|
| 1 | Code Review       | passed    | 0      | 3m 12s   |
| 2 | Visual Validation | passed    | 1 LOW  | 5m 08s   |
| 3 | Infrastructure    | skipped   | --     | --       |
| 4 | Final Report      | completed | --     | 0m 14s   |

## Findings Summary
- CRITICAL: 0
- HIGH: 0
- MEDIUM: 0
- LOW: 1
- INFO: 0

## Checkpoint Log
| Phase             | Response | Notes          |
|-------------------|----------|----------------|
| Code Review       | approve  |                |
| Visual Validation | approve  | 1 low cosmetic |
| Infrastructure    | skip     | not applicable |
```

Present the report to the human as the final output.

## Error Handling

Handle errors gracefully at every stage:

- **Missing `gh` CLI** -- Report the error with installation instructions (`brew install gh` or see https://cli.github.com/) and halt
- **Sub-agent failure** -- Log the failure to FINDINGS.md with the agent name and error details, mark the step as failed, and present the failure at the next checkpoint for human decision
- **Malformed plan file** -- Report specific parsing errors (missing frontmatter, invalid phase structure, unrecognized agent names) and halt with a pointer to the plan format reference
- **AskUserQuestion timeout** -- Treat as `reject` and halt safely, generating a partial report with result `HALTED (timeout)`
- **Network or API errors** -- If `gh` commands fail due to network issues, retry once after a brief pause, then log the failure and present at checkpoint
- **File write failures** -- If FINDINGS.md or the generated plan cannot be written, report the filesystem error and continue execution without writing (findings still appear in the final report)

## Reference Files

For detailed specifications, consult:
- **`${CLAUDE_PLUGIN_ROOT}/skills/validate-pr/references/plan-format.md`** -- expected plan file structure, naming conventions, and full example
- **`${CLAUDE_PLUGIN_ROOT}/skills/validate-pr/references/checkpoint-protocol.md`** -- complete checkpoint response protocol with edge cases and error handling
