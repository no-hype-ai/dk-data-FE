# FINDINGS.md Format Specification

## Entry Format

Each finding is a table row with these fields:

| Field | Required | Values |
|-------|----------|--------|
| # | Yes | Auto-incrementing integer |
| Severity | Yes | `critical`, `warning`, `info` |
| Category | Yes | `bug`, `improvement`, `security`, `accessibility`, `performance`, `style` |
| Description | Yes | Brief description of the finding |
| File | No | File path where issue was found |
| PR | No | PR number associated with discovery |
| Status | Yes | `open`, `in-progress`, `resolved` |

## Severity Definitions

- **critical**: Blocks merge. Broken functionality, security vulnerability, data loss risk.
- **warning**: Should fix before merge. Degraded UX, missing error handling, accessibility violation.
- **info**: Note for later. Optimization opportunity, style preference, tech debt observation.

## Category Definitions

- **bug**: Incorrect behavior, broken functionality
- **improvement**: Enhancement opportunity, better patterns available
- **security**: Vulnerability, exposed secrets, missing validation
- **accessibility**: WCAG violation, missing ARIA, keyboard navigation issue
- **performance**: Slow rendering, unnecessary re-renders, large bundle impact
- **style**: Code style, naming convention, formatting inconsistency

## Status Lifecycle

```
open → in-progress → resolved
```

- **open**: Newly discovered, not yet addressed
- **in-progress**: Being worked on
- **resolved**: Fixed, with resolution note and date

## Example Entries

### Active Finding
```
| 1 | critical | bug | Missing APP_FILTER import causes build failure | apps/api/src/app.module.ts | 800 | open |
```

### Resolved Finding
```
| 1 | critical | bug | Missing APP_FILTER import causes build failure | Fixed by keeping HEAD import during rebase | 2026-03-30 |
```

## Summary Section

Update counts after every add/resolve operation:

```
- **Critical**: 2 | **Warning**: 5 | **Info**: 3
- **Open**: 7 | **Resolved**: 3
```
