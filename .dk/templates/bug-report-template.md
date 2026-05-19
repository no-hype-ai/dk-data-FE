# <Bug Title>

> Copy to `.dk/bugs/YYYY-MM-DD-<short-desc>/report.md` when investigating a
> significant bug. Pair with `fix.md` once the fix lands.

**Severity**: `Critical | High | Medium | Low`
**Discovered**: YYYY-MM-DD via `<source: /dk.sweep, user report, alert, CI, etc.>`
**Service / Component**: `<service name or file path>`
**Reporter**: `<name or agent>`

## Symptoms

<What does the user or observer see? Include log patterns, error messages,
user-visible impact, affected environments.>

```
<sample error output, stack trace, or log line>
```

## Reproduction

Minimal steps to surface the issue:

1. <step>
2. <step>
3. <observed vs expected>

## Root Cause

<Analysis of why the bug happens. Be specific — name files, functions, and
the exact assumption that was wrong.>

## Scope & Impact

- **Affected users**: <all users | users with <condition> | internal only>
- **Data impact**: <none | corrupted data in <table/field> | lost events since <time>>
- **Downstream effects**: <list>

## Planned Fix

- **Approach**: <1-2 sentences on how to fix>
- **Affected files**:
  - `path/to/file.py`
  - `path/to/other.py`
- **Verification**: <how will we know the fix worked — test, metric, log pattern>

## Related

- Past lessons: <path in `.dk/memory/lessons.md` if this echoes a prior issue>
- Past bugs: <paths to similar `.dk/bugs/` entries>
- GitHub issues/PRs: <links>
