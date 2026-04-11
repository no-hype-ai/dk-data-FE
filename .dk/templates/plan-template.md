# Implementation Plan

**Branch**: [BRANCH_NAME]
**Date**: [CREATION_DATE]
**Spec**: [SPEC_FILE_LINK]

## Summary

**Primary requirement**: [One-sentence description from spec]
**Technical approach**: [High-level implementation strategy]

## Technical Context

| Dimension | Value |
|-----------|-------|
| Language/Version | [NEEDS RESEARCH] |
| Primary Dependencies | [NEEDS RESEARCH] |
| Storage | [NEEDS RESEARCH] |
| Testing Framework | [NEEDS RESEARCH] |
| Target Platform | [NEEDS RESEARCH] |
| Project Type | [library / CLI / web-service / mobile-app / desktop-app] |
| Performance Goals | [NEEDS RESEARCH] |
| Constraints | [NEEDS RESEARCH] |
| Scale/Scope | [NEEDS RESEARCH] |

## Constitution Check

*If `.dk/memory/constitution.md` exists, evaluate each gate before proceeding.*

| Gate | Status | Notes |
|------|--------|-------|
| [Principle 1] | PASS / FAIL / N/A | |
| [Principle 2] | PASS / FAIL / N/A | |

## Project Structure

```
project-root/
├── src/                    # Application source
│   ├── [module]/           # Feature modules
│   └── [shared]/           # Shared utilities
├── tests/                  # Test suite
│   ├── unit/
│   └── integration/
├── docs/                   # Documentation
└── config/                 # Configuration files
```

*Adapt to actual project layout. Common patterns:*
- **Single project**: `src/`, `tests/` at root
- **Web application**: `backend/src/`, `frontend/src/`
- **Monorepo**: `apps/`, `packages/`

## Phase 0 — Research

*For each unknown in Technical Context, document the research decision.*

### [Topic]

- **Decision**: [What was chosen]
- **Rationale**: [Why this option]
- **Alternatives considered**: [What else was evaluated]

## Phase 1 — Design

*Generate these artifacts in the feature directory:*

- **`data-model.md`**: Entities, fields, relationships, validation rules, state transitions
- **`contracts/`**: API endpoints (method, path, request/response), real-time events
- **`quickstart.md`**: Step-by-step setup guide for new developers

## Complexity Tracking

*Document any constitution violations or complexity tradeoffs.*

| Area | Violation | Justification | Approved By |
|------|-----------|---------------|-------------|
| | | | |
