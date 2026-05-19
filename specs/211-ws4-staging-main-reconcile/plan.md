# Implementation Plan: WS4 — `staging`/`main` Reconcile

**Branch**: `211-ws4-staging-main-reconcile` | **Date**: 2026-05-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/211-ws4-staging-main-reconcile/spec.md`
**Design source**: `docs/superpowers/specs/2026-05-19-ws4-staging-main-reconcile-design.md`

## Summary

Additively port the PR #415 DB-first serving capability and its "database
outage ≠ not-found" safety contract onto canonical `main` (SP1), behind a
per-source gate that is **off by default** so production behavior is unchanged
until explicitly enabled. Then replace the divergent `staging` branch with
canonical `main` (SP2), and deduplicate external data creation across
environments (SP3). SP1 is implementation-ready and is the hard gate for SP2;
SP2 and SP3 are scoped outlines requiring their own design cycles.

## Technical Context

**Language/Version**: Python 3.11+ (`requires-python = ">=3.11"`)
**Primary Dependencies**: FastAPI; asyncpg (already used on `main` —
`src/dk_data/api/dependencies.py`) for the DB-first path; httpx (existing
external path — unchanged); pytest (+ `responses`)
**Storage**: PostgreSQL 16.4 (CloudNativePG); adapter `raw`/`bronze`/`silver`
schemas; placeholder serving queries read `<raw_schema>.<raw_table>`
**Testing**: pytest. `main` CI runs `pytest tests/ -v -m "not integration"`
plus a separate integration leg against real CNPG postgres (tag `[TESTE]`:
no DB mocks for integration; unit H1-contract tests use an in-process fake pool)
**Target Platform**: Linux server (K3s), FastAPI `dk_data` service
**Project Type**: single (Python service under `src/dk_data/`)
**Performance Goals**: when DB-first enabled for a source, ≤1 added warehouse
round-trip before any external call; default-off path = zero added latency
**Constraints**: zero default behavior change; additive code only; reversible
by a single global env switch and by clean `git revert`; `main` is
canonical/prod and must never be overwritten by `staging` content
**Scale/Scope**: SP1 ≈ 4 core changes (`base.py` additive, new `dispatch.py`,
`router.py` single gated hook, gate config) + 34 `db_query` bodies grafted onto
`main`'s existing `Adapter` classes + 1 new adapter (`ema_labels`) + 2 new test
modules; SP2/SP3 = outlined

## Constitution Check

*GATE: evaluated against `.specify/memory/constitution.md` v1.0.0. Re-checked after Phase 1.*

| Principle | Verdict | Note |
|---|---|---|
| I. GitOps Deployment | PASS | Gate env vars delivered via Doppler + Kustomize overlays, never committed `.env` (`[SECRT]`/`[GITOP]`). |
| II. Environment Parity | PASS (gated) | DB-first env vars MUST be added to **both** staging and prod overlays/Doppler, default-off, to preserve structural parity. SP2 directly restores branch parity. |
| III. Observability by Default | PASS (action) | Add a DB-first **outcome metric** (`served`/`fallthrough`/`error`/`disabled`) + trace span; register only with the path so it is exercised by tests (no dead metric). |
| IV. Spec-Driven Development | PASS | This Speckit pipeline. |
| V. Medallion Integrity | PASS | `db_query` reads its declared `raw_schema`; 24 placeholder queries documented backlog, gated off. |
| VI. No Dead Infrastructure | PASS | Gated path is reachable (tests + opt-in), not orphaned; no Prometheus-Operator CRDs added. |

**Quality Gates**: no DB migration in SP1 (additive code → backwards-compat
trivially holds); `kubectl kustomize k8s/base/` must still succeed (only env-var
additions); CI lint/test must pass on the verified revision before merge
(FR-008/FR-013). **No constitution violations → Complexity Tracking empty.**

**Active-tag impact**: `[DSN]` — DB-first reuses `main`'s existing async DB
access, introduces **no** `psycopg2.connect(` outside the helper. `[BRKR]` — SP1
adds **no** new external HTTP calls (fallthrough uses `main`'s existing,
already-compliant path). `[ZVAL]`/`[VERSN]` — no request-schema or endpoint
version change. `[TESTE]` — unit H1 matrix (fake pool) + integration leg vs real
CNPG when enabled.

## Project Structure

### Documentation (this feature)

```text
specs/211-ws4-staging-main-reconcile/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions R1..R6
├── data-model.md        # Phase 1 — entities & dispatch state machine
├── quickstart.md        # Phase 1 — CI-faithful run/verify guide
├── contracts/           # Phase 1 — db_query / dispatch / gate contracts
│   ├── db_query-contract.md
│   ├── dispatch-decision-table.md
│   └── gate-config.md
├── memory/context.md    # feature context + active tags
└── tasks.md             # Phase 2 (/dk.tasks) — NOT created here
```

### Source Code (repository root — real paths on `main`)

```text
src/dk_data/services/mcp/
├── adapters/
│   ├── base.py                 # SP1: + async db_query() H1 contract (ADDITIVE; keep feature-015 surface)
│   ├── ema_labels.py           # SP1: NEW adapter (sole staging-only source)
│   ├── chembl.py … (33 more)   # SP1: + db_query method grafted onto EXISTING Adapter classes
│   └── __init__.py             # unchanged (router still imports the 8 *Tool classes)
├── dispatch.py                 # SP1: NEW — parallel registry-driven DB-first dispatch (H1)
├── router.py                   # SP1: + single gated pre-check before adapter.invoke()
├── tool_registry.py            # unchanged (feature-015 registry already present)
└── (gate config read)          # SP1: MCP_DBFIRST_ENABLED + MCP_DBFIRST_SOURCES

src/dk_data/observability/metrics.py  # SP1: + db_first_outcome metric

tests/
├── test_mcp_adapters.py                 # KEEP feature-015 T079 normalize tests; + db_query H1 matrix
├── test_mcp_dbfirst_dispatch.py         # SP1: NEW — dispatch decision table (fake pool, asyncio.run)
└── test_mcp_data_tools_isolation.py     # SP1: NEW — sys.modules landmine regression (file-path probe)

k8s/overlays/{staging,prod}/             # SP1: + MCP_DBFIRST_* env (default-off, BOTH overlays)
```

**Structure Decision**: Single Python service. SP1 confines code change to
`src/dk_data/services/mcp/` (+ one metrics line, + overlay env) and `tests/`.
No new top-level packages. SP2 acts on git refs only; SP3 acts on
`k8s/.../cronjobs` + `deploy/` and gets its own structure decision.

## Phases

- **Phase 0 — Research**: `research.md` (R1 DB handle, R2 gate mechanism,
  R3 SP2 reconcile strategy, R4 empty-result semantics, R5 SP3 dedup outline,
  R6 observability).
- **Phase 1 — Design**: `data-model.md` (entities + dispatch state machine),
  `contracts/` (db_query / decision table / gate config — internal contracts;
  the public `/api/v1/mcp-tools/{tool}/invoke` request/response is unchanged),
  `quickstart.md` (CI-faithful test/ruff/verify steps).
- **Phase 2 — Tasks**: produced by `/dk.tasks` (TDD-ordered; SP1 detailed,
  SP2/SP3 gated outline phases).

## Complexity Tracking

> No constitution violations. Section intentionally empty.

## Risks & Rollback

- **Prod-regression risk** mitigated by gate-default-off (FR-003) + additive-only
  change (FR-007) + zero-diff baseline test (SC-001).
- **Rollback**: set `MCP_DBFIRST_ENABLED=false` (instant, no deploy of code) or
  empty `MCP_DBFIRST_SOURCES`; clean `git revert` of the squash-merge.
- **SP2 irreversibility** mitigated by `staging-pre-ws4-reconcile` tag pushed
  before the reset, and the SP1-green-on-`main` hard precondition (FR-008/009).
- **Governance**: `main`/`staging` enforce no required checks — every merge
  manually gated on verified-SHA green; no auto-merge (FR-013). Recommend making
  build/lint + test required on both branches.
