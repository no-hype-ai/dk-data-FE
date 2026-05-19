---
name: pr-findings
description: "This skill should be used when the user asks to \"show findings\", \"add finding\", \"list issues\", \"view PR findings\", \"export findings\", \"mark finding resolved\", or wants to manage the FINDINGS.md issue tracker during PR validation."
version: 0.1.0
---

# PR Findings Tracker

Manage FINDINGS.md — a persistent issue tracker for discoveries made during PR validation. Track bugs, improvements, security issues, and observations even if unrelated to the current PR.

## File Location

FINDINGS.md lives at the project root. Create it if missing using this template:

```markdown
# PR Validation Findings

> Persistent tracker for issues discovered during PR validation.
> Managed by `/pr-findings`. Do not edit severity/status fields manually.

---

## Active Findings

| # | Severity | Category | Description | File | PR | Status |
|---|----------|----------|-------------|------|----|--------|

## Resolved

| # | Severity | Category | Description | Resolution | Resolved |
|---|----------|----------|-------------|------------|----------|

## Summary

- **Critical**: 0 | **Warning**: 0 | **Info**: 0
- **Open**: 0 | **Resolved**: 0
```

## Operations

### Add a Finding
Parse the user's input for: severity (critical/warning/info), category (bug/improvement/security/accessibility/performance/style), description, file path (optional), PR number (optional).

Append a new row to the Active Findings table. Auto-increment the finding number by reading the last entry.

### List / Filter
Read FINDINGS.md and present findings. Support filters:
- `list critical` — show only critical severity
- `list security` — show only security category
- `list PR 801` — show findings from specific PR

### Resolve a Finding
Move the specified row from Active to Resolved table. Add resolution description and current date.

### Summary
Count findings by severity and status. Present statistics table.

### Clear Resolved
Remove all resolved findings older than 30 days from the Resolved table.

## Additional Resources

For the complete FINDINGS.md format specification including severity definitions and category taxonomy, see **`references/findings-format.md`**.
