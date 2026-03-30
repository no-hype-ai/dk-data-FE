# Checkpoint Protocol Reference

This document defines the complete human-in-the-loop checkpoint protocol used by the `validate-pr` skill.

## Purpose

Checkpoints are gates between validation phases. They pause automated execution, present findings to the human, and require an explicit decision before proceeding. No phase transition occurs without human approval.

## When Checkpoints Trigger

A checkpoint triggers when a phase contains a `### Checkpoint` section in the plan file. Phases without this section execute and transition automatically.

## Checkpoint Prompt Format

Present the checkpoint using AskUserQuestion with this structure:

```
CHECKPOINT: [Phase Name] (Phase [N] of [Total])

Completed steps:
  [checkmark] [Step 1 title] -- [result summary]
  [checkmark] [Step 2 title] -- [result summary]
  [cross] [Step 3 title] -- [failure reason] (if applicable)

Sub-agent results:
  - visual-validator: [summary]
  - pr-code-reviewer: [summary]

Issues found this phase: [count]
  - [SEVERITY] [issue title]
  - [SEVERITY] [issue title]

Cumulative issues: [total across all phases]

---

Respond with one of:
  approve     -- proceed to Phase [N+1]: [next phase name]
  skip [phase] -- skip a phase by name (e.g., "skip Infrastructure Health")
  reject      -- halt validation entirely
  rerun [step] -- re-execute a step (e.g., "rerun Check login page")
  fix [desc]  -- describe a fix to apply before continuing
```

## Response Types

### approve (aliases: continue, proceed, ok, lgtm, yes)

**Behavior:**
1. Mark the current phase as `completed`
2. Advance to the next phase in the execution queue
3. If this is the final checkpoint, proceed to report generation

**No arguments required.**

### skip [phase name]

**Behavior:**
1. Match the provided name against remaining phases (case-insensitive, partial match allowed)
2. If exactly one match: mark that phase as `skipped` via TaskUpdate, remove from execution queue
3. If multiple matches: present the ambiguous matches and ask again
4. If no match: report the error and re-present the checkpoint
5. Continue with the current checkpoint decision (the skip does not substitute for approve/reject)

**Examples:**
- `skip Infrastructure Health` -- skips the infrastructure phase
- `skip infra` -- partial match, resolves to Infrastructure Health if unambiguous
- `skip Phase 3` -- matches by phase number

**After processing the skip, re-present the checkpoint prompt** since the human still needs to approve or reject the current phase.

### reject (aliases: stop, halt, abort, no)

**Behavior:**
1. Mark the current phase as `failed`
2. Mark all remaining phases as `cancelled` via TaskUpdate
3. Log the rejection to FINDINGS.md as an INFO entry
4. Immediately generate the final validation report with result `HALTED`
5. Do not attempt auto-merge regardless of flags

**No arguments required.**

### rerun [step identifier]

**Behavior:**
1. Match the identifier against steps in the current phase (by title, number, or partial match)
2. If matched: re-execute that single step
3. If the step dispatches a sub-agent, re-dispatch that agent
4. Update the step result in the checkpoint summary
5. Re-present the checkpoint prompt with updated results
6. Track the rerun count -- if the same step is rerun more than 3 times, warn the human

**Examples:**
- `rerun Check login page` -- re-executes the visual-validator step
- `rerun step 2` -- re-executes step 2 by number
- `rerun lint` -- partial match against step titles

**If no match is found**, list available steps and ask again.

### fix [description]

**Behavior:**
1. Parse the description to determine scope and intent
2. Select the appropriate agent based on the fix description:
   - UI/visual issues -> dispatch `visual-validator` agent is not appropriate; instead dispatch a general fix agent
   - Code issues -> dispatch an agent with write access to the codebase
   - Infrastructure issues -> dispatch `infra-health-checker` agent
3. Construct a focused agent prompt:
   ```
   Fix the following issue in PR #[number]:

   [description from human]

   Context:
   - Branch: [branch name]
   - Phase: [current phase]
   - Related findings: [any relevant findings from this phase]

   After fixing, report what changed.
   ```
4. Wait for the agent to complete
5. Re-run any steps in the current phase that are affected by the fix
6. Re-present the checkpoint prompt with updated results
7. Log the fix action to FINDINGS.md

**Examples:**
- `fix the login button is misaligned on mobile` -- dispatches fix agent for CSS adjustment
- `fix missing null check in auth middleware` -- dispatches code fix agent
- `fix add error handling to the signup endpoint` -- dispatches code fix agent

## Unrecognized Responses

If the response does not match any known type:

1. Echo the response back to the human
2. Present the valid options with brief descriptions
3. Ask again via AskUserQuestion

Do not guess intent. Do not default to approve.

## Timeout Handling

If AskUserQuestion returns empty or times out:

1. Treat as a `reject` for safety
2. Log the timeout to FINDINGS.md
3. Generate the final report with result `HALTED (timeout)`

## Multiple Skips

A single checkpoint interaction may include multiple skip commands before a final approve/reject. Process each skip in order, then wait for the terminal decision (approve or reject).

Example interaction:
```
Human: skip Infrastructure Health
Orchestrator: Skipped Phase 3: Infrastructure Health. Awaiting decision for current phase.
Human: approve
Orchestrator: Proceeding to Phase 4: Final Report.
```

## Checkpoint State Tracking

Maintain a checkpoint log throughout the validation run:

| Field        | Description                                      |
|--------------|--------------------------------------------------|
| `phase`      | Phase name                                       |
| `response`   | Final response type (approve/reject)             |
| `skips`      | List of phases skipped during this checkpoint    |
| `reruns`     | Count of step reruns requested                   |
| `fixes`      | Count of fix requests                            |
| `timestamp`  | When the checkpoint was resolved                 |

This log feeds into the final validation report's Checkpoint Log table.

## Interaction with Auto-Merge

The `--auto-merge` flag requires all checkpoints to pass cleanly. Any of the following disqualifies auto-merge:

- Any checkpoint receives `reject`
- Any checkpoint includes a `fix` request (indicates issues were found)
- Any checkpoint includes a `rerun` that changed the outcome
- Any CRITICAL or HIGH severity finding exists

Only pure `approve` responses (with optional `skip` commands) preserve auto-merge eligibility.

## Edge Cases

### Empty Phase (No Steps)
If a phase has a checkpoint but no steps, present the checkpoint immediately with an empty completed-steps list. This allows the human to make process decisions (e.g., skip remaining phases).

### All Steps Failed
If every step in a phase fails, still present the checkpoint. The human may choose to `fix`, `rerun`, or `reject`. Do not auto-reject.

### Phase With Only Agent Steps
If all steps dispatch sub-agents, wait for all agents to complete before presenting the checkpoint. If any agent fails, include the failure in the checkpoint summary.

### Concurrent Fix and Rerun
If a human requests `fix` and then `rerun` on the same step, process the fix first, then the rerun. The rerun should use the fixed state.
