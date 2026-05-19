# Task Breakdown

**Branch**: [BRANCH_NAME]
**Spec**: [SPEC_FILE]
**Plan**: [PLAN_FILE]

## Task Format

```
- [ ] [ID] [P?] [Story?] Description — `file/path.ext`
```

- `[ID]`: Sequential (T001, T002, ...)
- `[P]`: Parallelizable (different files, no dependencies)
- `[Story]`: User story reference (US1, US2, ...)
- File paths in backticks for exact location

## Phase 1 — Setup

*Project initialization, dependencies, configuration. Run first, sequentially.*

- [ ] T001 Setup description — `path/to/file`

## Phase 2 — Foundational

*Blocking prerequisites for all user stories: database schema, auth, shared utilities.*

- [ ] T00X Foundational task — `path/to/file`

## Phase 3 — [User Story 1 Title] (P1)

*Highest priority user story. Each task maps to a requirement.*

- [ ] T0XX [US1] Task description — `path/to/file`

## Phase 4 — [User Story 2 Title] (P2)

- [ ] T0XX [P] [US2] Task description — `path/to/file`

## Phase N — Polish & Cross-Cutting

*Documentation, error handling improvements, performance, cleanup.*

- [ ] T0XX Polish task — `path/to/file`

---

## Dependencies & Execution Order

```
Phase 1 (Setup) → Phase 2 (Foundation) → Phase 3+ (Stories) → Phase N (Polish)

Parallel opportunities:
  Phase 3 tasks marked [P] can run concurrently
  Phase 3 and Phase 4 can run in parallel if no shared files
```

## Implementation Strategy

- **MVP-first**: Implement P1 stories before P2/P3
- **Schema consolidation**: All schema tasks can be pulled to Phase 2 for `/dk.swarm`
- **Independent testability**: Each user story phase should produce a testable increment
