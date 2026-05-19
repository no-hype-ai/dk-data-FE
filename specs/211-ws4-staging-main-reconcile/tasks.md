---
description: "Task list — WS4 staging/main reconcile"
---

# Tasks: WS4 — `staging`/`main` Reconcile

**Input**: `specs/211-ws4-staging-main-reconcile/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)
**Tests**: REQUIRED — FR-006 mandates regression + contract tests; SC-002/SC-006 are test-verified. TDD (RED→GREEN).
**Organization**: by user story. **SP1 (US1) is implementation-ready and the hard gate for SP2.** US2/US3 are gated outline phases requiring their own design cycle before code.

## Format: `[ID] [P?] [Story] Description`
- **[P]**: parallelizable (different files, no dependency)
- Paths are repository-root relative; SP1 work happens on a branch off canonical `main` (worktree `.agents/ws4`).

---

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 Confirm working branch `211-ws4-staging-main-reconcile` is based on canonical `origin/main` (worktree `.agents/ws4`); record base SHA in `specs/211-ws4-staging-main-reconcile/memory/context.md`.
- [x] T002 [P] Establish CI-faithful local harness per `quickstart.md` (`PYTHONPATH=$PWD/src .venv/bin/python -m pytest`; ruff at pyenv 3.14.3). NO `tests/conftest.py` sys.path hack.
- [x] T003 [P] Capture the pre-change MCP baseline for SC-001: record current `POST /api/v1/mcp-tools/{tool}/invoke` responses for a representative tool set into `specs/211-ws4-staging-main-reconcile/baseline-mcp.json` (used by the zero-diff assertion T024).

---

## Phase 2: Foundational (Blocking Prerequisites for US1)

**⚠️ No US1 implementation until this phase is complete.**

- [x] T004 [US1] Inventory the 34 staging `db_query` bodies vs `main`'s existing `Adapter` classes; produce a name-mapping table (33 graft targets + `ema_labels` new) in `specs/211-ws4-staging-main-reconcile/adapter-map.md`. Mark the 24 placeholder-ILIKE bodies as gated-backlog.
- [x] T005 [US1] Confirm the async DB handle source on `main` (`src/dk_data/api/dependencies.py`) and document the exact pool-acquisition wiring the dispatch will reuse (R1) in `adapter-map.md`.

**Checkpoint**: mapping + DB-handle wiring known → US1 may begin.

---

## Phase 3: User Story 1 — Safe, opt-in DB-first on canonical `main` (Priority: P1) 🎯 MVP

**Goal**: `main` gains gated DB-first serving with the H1 contract; zero default behavior change.
**Independent Test**: gate-off ⇒ byte-identical to baseline; gate-on a source ⇒ served/fallthrough/error per decision table.

### Tests first (RED) — write and confirm failing before any impl

- [x] T006 [P] [US1] `tests/test_mcp_adapters.py`: add test that `BaseAdapter.db_query` exists, is `async`, defaults to `None`, and does NOT remove feature-015 surface (`normalize`/`build_url`/`build_urls_with_resolution`/`validate_against_bronze`). (FR-001/FR-005)
- [x] T007 [P] [US1] NEW `tests/test_mcp_dbfirst_dispatch.py`: decision-table rows 1–5 (gate off; gate on + no adapter; gate on + `None`/empty → fallthrough; gate on + non-empty → served, no HTTP; gate on + raises → 502 `{"stage":"db_query"}`, NO fallthrough) using an in-process fake pool + `asyncio.run`. (FR-001/FR-003/FR-004, R4)
- [x] T008 [P] [US1] NEW `tests/test_mcp_data_tools_isolation.py`: sys.modules-landmine regression using a file-path probe under a throwaway name (NEVER `import tests.…`). (FR-006)
- [x] T009 [P] [US1] `tests/test_mcp_dbfirst_dispatch.py`: gate-config predicate tests (`MCP_DBFIRST_ENABLED` default false; `MCP_DBFIRST_SOURCES` csv; unknown source inert). (FR-002, contracts/gate-config.md)
- [x] T010 [P] [US1] `tests/test_mcp_dbfirst_dispatch.py`: assert `mcp_dbfirst_outcome_total{source,outcome}` increments for each of served/fallthrough/error/disabled. (R6, Constitution III)
- [x] T011 [US1] Run T006–T010 → confirm RED for the right reasons.

### Implementation (GREEN) — additive only

- [x] T012 [US1] `src/dk_data/services/mcp/adapters/base.py`: add `async def db_query(self, drug_name, db_pool) -> dict | None` returning `None` + the H1 contract docstring; **do not** remove/alter feature-015 methods. → T006 GREEN.
- [x] T013 [US1] NEW `src/dk_data/services/mcp/dispatch.py`: parallel registry-driven DB-first dispatch per `contracts/dispatch-decision-table.md`; `_load_db_adapter` never raises on absent/older module. → T007/T008.
- [x] T014 [US1] Gate config reader (`MCP_DBFIRST_ENABLED` + `MCP_DBFIRST_SOURCES`) per `contracts/gate-config.md`. → T009.
- [x] T015 [US1] `src/dk_data/observability/metrics.py`: register `mcp_dbfirst_outcome_total{source,outcome}`; emit from dispatch. → T010.
- [x] T016 [US1] `src/dk_data/services/mcp/router.py`: add the SINGLE gated pre-check before the existing `adapter.invoke()` httpx call; existing path byte-unchanged when gate off. → T007 rows 1–3.
- [x] T017 [US1] Graft the 5 refined `db_query` bodies (`ema`, `ema_labels`, `openfda_labels` + Phase-1) onto `main`'s existing `Adapter` classes per `adapter-map.md`; add NEW `src/dk_data/services/mcp/adapters/ema_labels.py`.
- [x] T018 [P] [US1] Graft the 24 placeholder-ILIKE `db_query` bodies onto their `main` `Adapter` classes; each docstring states it is generic-pending-bronze/silver and gated-backlog. (FR-005)
- [x] T019 [US1] Run T006–T010 → all GREEN.

### Wiring & gate delivery

- [x] T020 [US1] Add `MCP_DBFIRST_ENABLED=false` + `MCP_DBFIRST_SOURCES=""` to BOTH `k8s/overlays/staging` and `k8s/overlays/prod` (+ Doppler `dk-data-staging`/`dk-data-prod`), default-off, to preserve Environment Parity (Constitution II, `[GITOP]`/`[SECRT]`).
- [x] T021 [US1] `kubectl kustomize k8s/base/` and both overlays succeed; no orphaned/forbidden CRDs (Constitution VI / Quality Gates).

### US1 verification (maps to SC-001/002/003/006)

- [x] T022 [US1] Full CI-faithful test run (quickstart cmd) — no regressions vs known baseline noise; feature-015 `test_mcp_adapters` T079 normalize tests still 100% pass (SC-006).
- [x] T023 [US1] `python -c "import dk_data.api.routes"` clean.
- [x] T024 [US1] Zero-diff baseline check: with gate off, representative `invoke_tool` outputs equal `baseline-mcp.json` (SC-001).
- [x] T025 [US1] `ruff check .` (CI-faithful) clean — no `E402`/stray lint.
- [ ] T026 [US1] Open PR to `main`; `gh pr checks <#>` shows Lint+Test+SQLMesh+Manifests = pass at the verified head SHA (`gh pr view --json headRefOid`; re-verify after any force-push). **No auto-merge.** Manual merge after green (FR-008/FR-013, SC-003).

**Checkpoint US1 / SP1 complete** — the hard gate for SP2 is now satisfied.

---

## Phase 4: User Story 2 — Replace `staging` with `main` (Priority: P2) — GATED OUTLINE

**⚠️ Blocked until SP1 (Phase 3) is merged green on `main` (FR-008/FR-009). Requires its own design cycle before execution.**

- [ ] T027 [US2] Author SP2 design+plan (own `/dk.specify`→`/dk.plan` or design doc): staging-overlay deploy-target validation on `main`, CI workflow delta (`build-push.yaml` vs `build-dk-data-fe.yaml`), ArgoCD/preview impact, freeze window, announcement.
- [ ] T028 [US2] Precondition check: SP1 commit present & green on `origin/main`; otherwise ABORT.
- [ ] T029 [US2] Push immutable recovery tag `staging-pre-ws4-reconcile` at current `origin/staging` tip; verify it is fetchable (FR-009, SC-004).
- [ ] T030 [US2] Reset `staging` → `origin/main`; force-update; verify `git diff origin/main origin/staging` shows zero unintended divergence (SC-004) and staging deploy succeeds.

---

## Phase 5: User Story 3 — Data created once, shared across envs (Priority: P3) — OUTLINE

**⚠️ Follows SP2. Requires its own brainstorming→spec→plan cycle (FR-011/FR-012).**

- [ ] T031 [US3] Enumerate any genuinely environment-specific data need BEFORE dedup cut-over (FR-012).
- [ ] T032 [US3] Design single-origin ingestion (production-side once → shared warehouse; staging read-only): edit `k8s/.../cronjobs` + `deploy/` so each source is fetched ≤1×/cycle (SC-005).
- [ ] T033 [US3] Verify both environments read identical data; no duplicate external fetches observed.

---

## Phase 6: Polish & Cross-Cutting (close-out)

- [ ] T034 [P] Surface governance recommendation to stakeholder: make build/lint + test required status checks on BOTH `main` and `staging` (FR-013).
- [ ] T035 [P] Update memory: promote D009 status, update `pr415-remediation-state.md` + `MEMORY.md`, mark remediation **task #7 complete** once SP1 lands on `main`.
- [ ] T036 Write `auto-decisions.json` audit trail to `specs/211-ws4-staging-main-reconcile/auto-decisions.json` (done by `/dk.auto`).

---

## Dependencies & Execution Order

- Setup (T001–T003) → Foundational (T004–T005) → **US1 (T006–T026)**.
- US1 TDD: T006–T011 (RED) **before** T012–T019 (GREEN); T012 blocks T013/T016/T017; T020 after impl; T022–T026 last.
- **US2 (T027–T030) blocked by US1 merged on `main`.** US3 (T031–T033) after US2. Polish (T034–T036) anytime after US1; T035 task-#7 close requires US1 on `main`.

## Parallel Opportunities

- T002 ∥ T003 (setup).
- RED tests T006 ∥ T007 ∥ T008 ∥ T009 ∥ T010 (distinct test files/cases).
- T018 ∥ other GREEN tasks (different adapter files) once T012 lands.
- T034 ∥ T035 (polish).

## Implementation Strategy

MVP = **US1 only** (delivers the entire residual #415 value safely onto prod
`main`, gate-off). US1 is independently shippable and is the precondition for
US2. US2 and US3 are deliberately scoped as gated outlines — each gets its own
design cycle; do not begin their code until their preconditions and designs are
in place. Every merge is manually gated on verified-SHA green CI (no
auto-merge).
