---
name: lessons-learned
description: Capture, record, and consult lessons learned from development mistakes, debugging sessions, or architectural decisions. Use when something went wrong, when completing a tricky task, or before starting work similar to past efforts.
---

## Before Starting Work

1. Read `.dk/memory/lessons.md` if it exists.
2. Surface any lessons relevant to the current task.
3. Quote the relevant lesson so the user sees it applied.

## After Something Goes Wrong (or a Non-Obvious Fix)

1. Identify the root cause.
2. Determine what signal was missed or what assumption was wrong.
3. Append a new entry to `.dk/memory/lessons.md` using the format below.
4. If a similar lesson already exists, update it instead of duplicating.

## Entry Format

```markdown
## [DATE] — [Short Title]

**Context**: What were you trying to do?
**What happened**: What went wrong or was surprising?
**Root cause**: Why did it happen?
**Lesson**: What should be done differently next time?
**Tags**: [comma-separated keywords for searchability]
```

## Rules

- Keep entries concise (5-8 lines max per entry).
- Use specific, searchable tags (e.g., `git`, `async`, `imports`, `testing`, `pyproject`).
- Do not duplicate existing lessons — update if a similar one exists.
- When consulting lessons before work, quote the relevant lesson so the user sees it.
- Create `.dk/memory/lessons.md` on first use if it does not exist.
