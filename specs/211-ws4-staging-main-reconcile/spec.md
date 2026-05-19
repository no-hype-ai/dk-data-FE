# Feature Specification: WS4 — `staging`/`main` Reconcile (port #415 hardening, unify branches, dedupe ingestion)

**Feature Branch**: `211-ws4-staging-main-reconcile`
**Created**: 2026-05-19
**Status**: Clarified
**Input**: User description: "WS4 staging-main reconcile: additively port PR #415 db_query/H1/isolation hardening onto canonical main (env-gated, default-off), then replace staging branch with main, then deduplicate data creation across staging and prod environments"

## Context (why this exists)

`main` (the production-promotion branch) and `staging` evolved on **unrelated git
histories**. `main` carries the canonical production platform (feature-015 MCP
layer with 63 HTTP-only adapters, plus TAVR/hydrate/prod-promotion work).
`staging` is a from-scratch rewrite that added the PR #415 robustness work
(DB-first serving with a "database outage ≠ not-found" safety contract) for a
34-adapter subset. The stakeholder decisions: **`main` stays canonical**, the
#415 robustness value is **ported additively onto `main`**, then **`staging` is
replaced by `main`**, and finally **external data is created once** instead of
separately per environment.

## Clarifications

### Session 2026-05-19

- Q: How are the 34 ported serving implementations reconciled against `main`'s
  63 adapters where source names overlap and `main`'s adapter behavior differs?
  → A: Graft the database-serving behavior onto `main`'s **existing** adapter
  classes by source name as an **additive method only** (do not alter existing
  normalization/behavior). The single `staging`-only source is added as a new
  adapter. The 24 generic placeholder serving queries are present but remain
  gated off and documented as backlog.
- Q: What concrete recoverable reference preserves the pre-reconcile `staging`?
  → A: An immutable tag (e.g. `staging-pre-ws4-reconcile`) pushed to the remote
  pointing at the current `staging` tip, retained until explicitly cleaned. The
  reconcile is performed only after US1 is green on `main`.
- Q: What single shared store is external data created into for SP3?
  → A: The shared production data warehouse is the single origin; ingestion
  runs once (production-side) and the staging environment consumes the same
  warehouse read-only. The exact mechanism is finalized in SP3's own design
  cycle.
- Q: When DB-first is enabled and the warehouse returns an empty/zero-row
  result (not an error), is that "fall through" or "served empty"?
  → A: An empty/no-match warehouse result is **"no local result" → fall through**
  to the existing external path. Only a non-empty match is "served"; only an
  exception is "error".
- Q: Must SP1 wire DB-first into the live production dispatch, or be a parallel
  path the live router consults only when gated on?
  → A: A **parallel, additively-invoked** path. The existing production dispatch
  is unchanged and consults the new path only when the per-source gate is on.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Production gains safe, opt-in DB-first serving (Priority: P1)

As the platform operator, the canonical production branch must gain the ability
to serve MCP data-tool requests from the local data warehouse, governed by a
safety rule that distinguishes a real database failure from a legitimate
"not found", **without changing today's production behavior unless explicitly
enabled per source**.

**Why this priority**: This is the entire residual value of the #415 effort and
it gates everything else — once `staging` is replaced by `main` (US2), any #415
work not yet on `main` is lost permanently. It must land first, and it must be
provably zero-risk to production by default.

**Independent Test**: Deploy `main` with the DB-first switch off → every
existing MCP tool response is identical to today. Enable one source via
configuration → that source is served from the warehouse with no external call.
Force a database error for that source → the system returns an error response
and never silently falls back to the external call.

**Acceptance Scenarios**:

1. **Given** DB-first is disabled (default), **When** any MCP data-tool is
   invoked, **Then** the response is byte-identical to the pre-change production
   behavior.
2. **Given** DB-first is enabled for source S and S has a non-empty warehouse
   match, **When** S is invoked, **Then** the result is served from the
   warehouse with zero external HTTP calls.
3. **Given** DB-first is enabled for source S and the warehouse has no match
   (including an empty/zero-row result), **When** S is invoked, **Then** the
   system falls through to the existing external path and behaves as today.
4. **Given** DB-first is enabled for source S and the database is unavailable,
   **When** S is invoked, **Then** the system returns a surfaced error
   (not a silent miss) and does **not** fall through to the external call.
5. **Given** the change is merged, **When** the operator wants to undo it,
   **Then** flipping the single global configuration switch fully disables the
   new path with no code change.

---

### User Story 2 - One canonical branch; `staging` mirrors `main` (Priority: P2)

As the platform operator, there must be a single source-of-truth branch so that
`staging` stops being a divergent parallel rewrite and instead reflects
canonical `main` (inheriting `main`'s stronger continuous-integration suite),
eliminating drift and reviewer confusion.

**Why this priority**: High value but strictly dependent on US1 — replacing
`staging` before the #415 value is on `main` would destroy that work.

**Independent Test**: After the reconcile, comparing the canonical and mirror
branches shows no unintended content divergence; a deploy from the mirror
branch to the staging environment succeeds; the previous `staging` tip is
recoverable from the preserved tag.

**Acceptance Scenarios**:

1. **Given** US1 has merged green on `main`, **When** the reconcile runs,
   **Then** `staging` content equals canonical `main` (except intentional
   deploy-target configuration), and the pre-reconcile `staging` tip is
   preserved as an immutable recoverable tag on the remote.
2. **Given** the reconcile is complete, **When** integration runs against the
   mirror branch, **Then** it uses `main`'s richer CI and passes.
3. **Given** US1 has **not** merged on `main`, **When** the reconcile is
   attempted, **Then** it is blocked (hard precondition).

---

### User Story 3 - External data created once, shared across environments (Priority: P3)

As the platform operator, external source data must be created a single time
and shared across environments, rather than fetched and built separately for
`staging` and production, so that ingestion cost and cross-environment data
drift are eliminated.

**Why this priority**: Independent infrastructure improvement; valuable but not
blocking US1/US2 and logically follows having one canonical branch.

**Independent Test**: Inspection shows each external source is ingested in
exactly one place per scheduled cycle; both environments read identical data
from the shared warehouse; no duplicate external fetches occur.

**Acceptance Scenarios**:

1. **Given** the deduplicated ingestion design is in place, **When** a
   scheduled ingestion cycle runs, **Then** each external source is fetched at
   most once across all environments.
2. **Given** both environments are operating, **When** the same dataset is
   queried in each, **Then** the data is identical (single shared origin).
3. **Given** a genuinely environment-specific data need exists, **When** the
   deduplication is designed, **Then** that need is explicitly enumerated and
   preserved.

---

### Edge Cases

- DB-first switch references an unknown/misspelled source → that source behaves
  as if DB-first is off (no error, existing path used).
- An adapter module is absent or older than the contract on `main` → treated as
  "no DB path" (fall through to existing behavior), never an error.
- Warehouse returns an empty/zero-row result → "no local result" → fall through
  (NOT served as an empty success).
- `db_query` raises vs returns nothing/empty vs returns a non-empty match →
  exactly one of: surfaced error / fall-through / served-from-warehouse.
- Reconcile attempted while US1 is not yet on `main` → blocked.
- Force-reconcile would discard the only copy of some work → preconditioned on
  US1 landed + prior `staging` tip tagged for recovery.
- Deduplicated ingestion hides a real per-environment need → must be enumerated
  during SP3 design before cut-over.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The canonical branch MUST expose a database-serving capability on
  the adapter contract whose outcomes are exactly: "no local result"
  (no match / empty result → fall through to the existing external path),
  "local result" (a non-empty match → serve it), or "error" (an exception →
  surface it). It MUST be a parallel, additively-invoked path; adding it MUST
  NOT remove or alter the existing adapter behavior present on the canonical
  branch.
- **FR-002**: The database-first path MUST be disabled by default and
  enable-able **per source** through configuration, with a single global switch
  that disables the entire path.
- **FR-003**: With the database-first path disabled, system behavior MUST be
  identical to current production for every MCP data-tool.
- **FR-004**: When the database-serving step reports an error, the system MUST
  surface that error and MUST NOT fall through to the external path (a database
  outage is not a "not found").
- **FR-005**: All 34 hardened source serving implementations from the #415 work
  MUST be present on the canonical branch, grafted onto `main`'s existing
  adapter classes by source name as additive behavior only (the one
  `staging`-only source added as a new adapter); generic/placeholder serving
  queries remain present but gated off and documented as backlog.
- **FR-006**: The change MUST include automated regression protection for the
  previously-identified module-import isolation defect and automated
  verification of the error/serve/fall-through contract across adapters.
- **FR-007**: The change MUST be reversible both by the single global
  configuration switch and by a clean revert (the change is additive only).
- **FR-008**: US1 MUST be verified green against the canonical branch's full
  continuous-integration suite before any branch-reconcile action.
- **FR-009**: `staging` MUST be reconciled to canonical `main` **only after**
  US1 lands on `main`, and the pre-reconcile `staging` tip MUST be preserved as
  an immutable tag on the remote, retained until explicitly cleaned.
- **FR-010**: After reconcile there MUST be exactly one canonical
  source-of-truth branch; `staging` functions as a deploy mirror.
- **FR-011**: External source data MUST be created once into the shared
  production data warehouse and consumed by all environments; duplicate
  per-environment ingestion MUST be eliminated.
- **FR-012**: Any genuinely environment-specific data need MUST be explicitly
  enumerated before ingestion deduplication is cut over.
- **FR-013**: Every merge to `main` or `staging` for this feature MUST be
  manually verified with required checks (build/lint + test + model + manifest
  validation) passing on the verified change revision; automated merge MUST NOT
  be used while required status checks are unenforced.
- **FR-014**: Pre-existing accepted limitations from earlier phases (exact-match
  search, external-leg silent-miss on one source, time-to-live edge, optional
  file-format fallback, by-design not-found response) remain documented-accepted
  and out of scope for this feature.

### Key Entities *(include if feature involves data)*

- **Source Adapter**: Represents one external data source; identified by a
  stable name, a target warehouse table/schema, a normalization behavior, and
  (new) an optional database-serving behavior governed by FR-001/FR-004.
- **Tool Registry**: Maps a public tool slug to its source adapter; the
  database-first dispatch is driven by this registry.
- **DB-First Gate**: Configuration consisting of a global on/off switch and a
  per-source allowlist; default off.
- **Branch Roles**: `main` = canonical source of truth / production promotion;
  `staging` = (post-reconcile) deploy mirror of `main`.
- **Ingestion Job Set**: The scheduled units that fetch/build external data;
  must run once and feed the shared warehouse consumed by all environments.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With the database-first path disabled, 100% of existing MCP
  data-tool invocations return responses identical to the pre-change baseline
  (zero behavioral difference).
- **SC-002**: For an enabled source, a warehouse non-empty match is served with
  0 external calls, an empty result falls through, and an induced database
  failure produces a surfaced error in 100% of trials with 0 silent
  fall-throughs.
- **SC-003**: 100% of the canonical branch's required CI checks pass on the US1
  change before it is merged.
- **SC-004**: After reconcile, unintended content divergence between the
  canonical and mirror branches is 0, and the prior `staging` state is
  recoverable from the preserved tag in 100% of cases.
- **SC-005**: After ingestion deduplication, each external source is fetched at
  most once per scheduled cycle across all environments (target: 100%
  elimination of duplicate fetches; minimum acceptable: ≥50% reduction).
- **SC-006**: The canonical branch's existing adapter behavior test suite shows
  0 regressions (100% of previously-passing checks still pass).

## Assumptions

- `main` is and remains the canonical/production branch; `staging` is to be
  replaced by it.
- The value worth preserving from #415 is the database-first serving capability
  plus its error-vs-not-found safety contract; the 24 generic placeholder
  serving queries are accepted as gated backlog, not blockers.
- Both environments can read the single shared production warehouse, which
  justifies creating data once; any environment-specific data need is minimal
  and will be enumerated during the SP3 design cycle (per FR-012).
- The database-first path stays disabled by default after merge; enabling any
  source is a deliberate post-merge operational decision.
- Neither `main` nor `staging` currently enforces required status checks; until
  that governance gap is closed, all merges for this feature are manually gated
  (FR-013). Recommendation to stakeholder: make build/lint + test required on
  both branches.
- Pre-existing accepted limitations from earlier phases remain accepted
  (FR-014).

## Scope & Sequencing

This feature comprises three independently testable sub-projects executed in
strict order: **SP1 (US1)** port #415 hardening additively onto `main` →
**SP2 (US2)** replace `staging` with `main` → **SP3 (US3)** deduplicate
ingestion. SP1 is the hard gate for SP2. SP3 follows SP2. SP2 and SP3 each
require their own detailed design before implementation; this specification and
the downstream plan treat SP1 as implementation-ready and SP2/SP3 as scoped
outlines.
