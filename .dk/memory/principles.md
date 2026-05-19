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

### 6. Three-way binding for observability

Every metric must be bound three ways in the same PR that introduces it:

1. **Definition** — a `Counter`/`Gauge`/`Histogram` in `src/dk_data/observability/metrics.py`
2. **Emission** — at least one production code path that calls `.inc()` / `.set()` / `.observe()` on it
3. **Consumption** — a Grafana dashboard panel, alerting rule, or SLO query that reads it

A metric that exists without all three is dead code. PRs that add (1) without (2) and (3) will be rejected. The CI check in `tests/observability/test_metric_coverage.py` (T113) enforces (1)+(2); reviewers enforce (3).

**Why**: pre-feature-002 there were 38 metrics defined + helper function written + never called, because PR review accepted "definition + helper" as proof of wiring. See `.dk/memory/lessons.md` → "The 38 dead metrics pattern".

The same rule applies in reverse: never delete a metric definition without deleting its emitters and removing it from any dashboard that queries it.
