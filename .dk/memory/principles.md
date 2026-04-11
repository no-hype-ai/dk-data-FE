# Project Principles

> Canonical rules for this project. Every dk command reads this. Every agent honors it.
> Edit freely — changes take effect immediately; no regeneration needed.

## The Bar

Every output is judged against three criteria:

1. **Simple** — no cleverness, no speculation, no unasked features
2. **Complete** — the job is fully done, verified, and cleaner than before
3. **Senior** — would a staff engineer approve this PR?

## Rules

### 1. Plan before code

Write a plan first when a task has 3+ steps:

- **Feature work** → `.dk/specs/<feature>/plan.md`
- **Ad-hoc work** → `.dk/plans/YYYY-MM-DD-<topic>.md`
- **Session plan mode** → `.claude/plans/` (Claude Code–managed)

Present the plan, wait for approval, then execute. Keep project root clean — plans live under `.dk/`, not at the top level.

**Bug-fix carve-out**: bugs with a clear root cause may skip plan mode — identify the cause from logs, errors, or failing tests, then fix it directly. For significant bugs (non-obvious cause, shared state, multi-module impact), document the investigation in `.dk/bugs/YYYY-MM-DD-<short-desc>/` with `report.md` (symptoms, reproduction, root cause) and `fix.md` (what changed, why, how verified). If the bug reveals a recurring pattern, also append to `.dk/memory/lessons.md`.

### 2. Clean context

- Offload research, exploration, and parallel work to subagents
- Throw compute at hard problems rather than cramming one context window

### 3. Transparent execution

- Mark todo items done as you go
- Work like a junior dev with a manager watching — methodical, no shortcuts
- Own the problem end-to-end; no hand-holding required from the user

### 4. Verify before done

- Run tests. Check logs. Diff changes against expectations.
- Never claim completion without proof
- Capture surprises in `.dk/memory/lessons.md`

### 5. Code standards

- Simple and readable over clever
- Build only what is asked — no speculative code
- No half-measures — if a fix is needed, fix it fully
- Leave the codebase cleaner than you found it
- No unnecessary dependencies
