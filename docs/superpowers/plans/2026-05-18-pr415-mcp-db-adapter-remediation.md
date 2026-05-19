# PR #415 Remediation — DB-backed MCP Data-Tool Layer

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use `- [ ]` checkboxes. **This document is a decision + plan: read "Premise Correction" and "Options" before any code.**

**Goal:** Land PR #415's intent — a DB-first MCP data-tool surface (EMA/openFDA label lookups, registry-driven adapters) — *keeping* the 820 lines (`tool_registry.py` + `test_mcp_adapters.py`), without breaking the production FastAPI app.

**Architecture:** Introduce the missing `adapters/base.BaseAdapter` abstraction, a registry-driven router that injects a DB pool, and the missing adapter modules + `mol_silver.ema` data model — phased so CI/import is green at every step.

**Tech Stack:** Python 3.11, FastAPI, asyncpg, psycopg2 (migrations), SQLMesh (silver), pytest, openpyxl/pymupdf.

---

## 1. Premise Correction (read first)

You asked to "remediate and include the 820 lines … intended to be working with `/Users/nick/Code/behavior-labs-ai`." Ground truth from cross-repo exploration:

- **`behavior-labs-ai` has NO MCP adapter code.** It is a TypeScript/NestJS + Next.js monorepo (`apps/`, `biome.jsonc`). There is no `BaseAdapter`, no `adapters/`, no `tool_registry` to port from. The MCP data-tool architecture exists **only** in `dk-data-FE`, and only partially.
- **`base.py`/`BaseAdapter` exists nowhere** — not in dk-data-FE, not in behavior-labs-ai, not in git history. PR #415's `ema_labels.py`/`openfda_labels.py` `from .base import BaseAdapter` references a class **that was never written**. This is the root of the 43 import failures.
- The realistic integration: **behavior-labs-ai is the intended *consumer*** of dk-data-FE's `/api/v1/data-tools/{tool}/invoke` surface (AI agents calling drug-data tools). So the objective is to make dk-data-FE's DB-first tool surface *complete and correct*, not to port code between repos.

**Implication:** "Include the 820 lines" = **design and build the `BaseAdapter` framework + missing adapters here**, in dk-data-FE. This is a feature build-out, not a bug-fix. Scope and approach decisions below need your call.

---

## 2. Ground Truth (what #415 actually is)

PR #415: base = **`staging`** (NOT `main`; the two share no merge base — `main` is 123 commits behind, `staging` 171 ahead; my earlier #408/#410/#412 are on `staging`). 7 commits, 1826+/55−. `mergeable` vs staging, but `Test` CI red.

| Area | State |
|---|---|
| `adapters/base.py` (`BaseAdapter`) | **Missing entirely.** Imported by `ema_labels.py:10`, `openfda_labels.py:10`. `adapters/__init__.py` imports `OpenFDALabelsTool` → importing the package raises `ModuleNotFoundError` → cascades to `router.py` → `dk_data.api.routes` → **whole FastAPI app fails to import** (kills pre-existing `ema-search`, `fda-drugs-search`, … too). |
| Two architectures | Working: `*Tool(BaseMCPTool)` HTTP-first, 9 live in `router.TOOL_REGISTRY`, no `db_pool`. Aspirational (#415): `Adapter(BaseAdapter)` w/ `source_name`/`raw_table`/`raw_schema`/`db_query()`, DB-first, driven by `tool_registry.ToolDefinition`. The two are unreconciled. |
| `tool_registry.py` (631 LOC) | Declares ~58 `ToolDefinition`s → adapter modules; **~10 exist**. Not imported by `router.py` (dead). |
| `tests/test_mcp_adapters.py` (192 LOC) | Parametrizes **28** adapter modules expecting `Adapter(BaseAdapter)` + `source_name/raw_table/raw_schema`; **6 exist**. Whole file red at collection (the "[pubchem]" CI line is just the alphabetically-last of 43). |
| `db_query` hook | **Not implemented.** `base_tool.BaseMCPTool` unmodified; router only calls `invoke()` (HTTP). `EmaTool.db_pool` is a class attr hardcoded `None`, never injected → EMA DB path unreachable. |
| `mol_silver.ema` | Queried by `ema.py`; **no migration/SQLMesh model creates it** on this branch (only `bronze.ema` exists; a `silver/ema.sql` exists in an unrelated worktree only). `ema_labels.py` instead reads `mol_raw.ema` (JSONB) — the two adapters disagree on the source of truth. |
| Migration 244 | `mol_raw.ema_label_cache` — **correct & clean** (idempotent, `UNIQUE(smpc_pdf_url)`, mol_raw schema). Numbering gap 076→244 is **fine** (runner does `sorted(glob("*.sql"))` by numeric prefix; gaps allowed). |
| `run_migrations.py` guard | `ensure_tracking_table()` now does a 2nd `cur.execute()` (`DO $$ … pg_get_viewdef … DROP VIEW … CASCADE …`). Breaks `test_migration_runner.py::test_executes_create_statements` (asserts on `call_args` = last call + `commit.assert_called_once`). Stale-test, **but** the DO-block has a real hazard: unconditional `DROP … CASCADE` with gated recreate → a matview/visibility edge silently destroys `api.migration_status` on every deploy. |
| `openpyxl` | Imported unconditionally at `ema_epar.py:9`; **not declared** in `pyproject.toml` (only transitive). `pymupdf` is declared. |
| Silent-failure HIGH issues | H1 DB error → silent API fallback; H2 empty/garbage SmPC PDF poisons `UNIQUE`-keyed cache forever; H3 uncaught `json.loads`/`**dict` on corrupt cache row → opaque 500; H4 XLSX parser breakage reported as "EMA source unavailable"; H5 primary-URL exception → falls to known-dead URLs. |

---

## 3. Options (DECIDED: **Option D** — phased build-out + staging→main reconcile; see §7)

### Option A — Strip the 820 lines, ship only the EMA fixes
Remove `tool_registry.py`, `test_mcp_adapters.py`, the `BaseAdapter` paths; keep the XLSX fix + migration 244 + migration guard (hardened). Smallest, green in ~½ day. **You explicitly rejected this.** (Recorded for completeness; it remains the fastest unblock if priorities change.)

### Option B — Full build-out now (all ~28 adapters + framework, one PR)
Write `BaseAdapter`, the registry-driven router with pool injection, **all ~18–22 missing adapter modules**, `mol_silver.ema`, harden everything, in one PR. Delivers the whole vision but is multi-week, high-risk, unreviewable as one unit, and blocks the EMA value behind the long tail.

### Option C — **Phased build-out (recommended).** Keep all 820 lines; land in reviewable, always-green slices
A coherent middle path that satisfies "include the 820 lines" without a multi-week monolith and without ever shipping a red/import-broken tree:

- **Phase 0 — Make it importable & CI-green (keeps the 820 lines).** Write `adapters/base.BaseAdapter`; make `tool_registry.py` import-safe and `test_mcp_adapters.py` xfail/skip the not-yet-built adapters (registry stays, marked authoritative backlog). Harden the migration DO-block; fix the migration-runner test; declare `openpyxl`. → Whole app imports, CI green, zero dead-on-import.
- **Phase 1 — Wire the real DB-first path for the two adapters #415 is actually about.** Implement `db_query()`-before-HTTP in the router with `db_pool` injected at FastAPI startup; port `ema_labels`/`openfda_labels`/`ema` onto `BaseAdapter`; build `mol_silver.ema` (SQLMesh silver from `bronze.ema`) so `ema-search` is real. Fix H1–H5 for these. → EMA/openFDA label tools genuinely DB-first; behavior-labs-ai gets working tools.
- **Phase 2..N — Adapter build-out from the registry, one slice per PR.** `tool_registry.py` becomes the authoritative backlog; each subsequent PR converts a small batch (e.g., 3–5) of registry entries into real `Adapter`s with TDD, flipping their `xfail`→pass. No phase ever leaves CI red.

Recommended because: preserves your intent (registry + matrix test stay as the contract/backlog), every PR is reviewable & green, EMA value lands fast, and the long adapter tail is incremental and parallelizable.

### Option D — Same as C but split repo-targeting
Land Phase 0+1 against `staging` (matches #415's base), then a separate forward-port to `main` (they've diverged 123/171). Pairs with C; not exclusive. Decision needed: do we keep targeting `staging` (recommended — matches the repo's actual flow and where #408/#410/#412 live) or also schedule a `staging→main` reconcile?

---

## 4. Recommended Plan — Phase 0 (unblock, keep 820 lines, CI green)

**Branch:** `fix/415-phase0-base-adapter-and-guards` off `origin/staging` (NOT main). One PR, base `staging`.

**File structure:**
- Create `src/dk_data/services/mcp/adapters/base.py` — `BaseAdapter` ABC (the contract `tool_registry.py`/`test_mcp_adapters.py` already assume).
- Modify `tests/test_mcp_adapters.py` — keep the 28-row matrix; xfail the unbuilt ones via a single source-of-truth set.
- Modify `src/dk_data/scripts/run_migrations.py` — harden the DO-block.
- Modify `tests/test_migration_runner.py` — assert on `call_args_list`, not `call_args`.
- Modify `pyproject.toml` — add `openpyxl>=3.1,<4.0`.
- Modify `src/dk_data/services/mcp/adapters/{ema_labels,openfda_labels}.py` — only the import line, so the package imports.

### Task 0.1: `BaseAdapter` contract

**Files:** Create `src/dk_data/services/mcp/adapters/base.py`; Test `tests/test_mcp_adapters_base.py`

- [ ] **Step 1 — Failing test**
```python
# tests/test_mcp_adapters_base.py
import pytest
from dk_data.services.mcp.adapters.base import BaseAdapter

def test_baseadapter_is_abstract():
    with pytest.raises(TypeError):
        BaseAdapter()  # abstract: source_name/raw_table/raw_schema/normalize required

def test_concrete_subclass_exposes_contract():
    class _A(BaseAdapter):
        source_name = "x"; raw_table = "t"; raw_schema = "mol_raw"
        def normalize(self, row): return dict(row)
        async def db_query(self, drug_name, db_pool): return None
    a = _A()
    assert a.full_table_name == "mol_raw.t"
    assert a.validate_against_bronze() is True
```
- [ ] **Step 2 — Run, expect ImportError/fail**: `.venv/bin/python -m pytest tests/test_mcp_adapters_base.py -q --no-cov`
- [ ] **Step 3 — Implement** `BaseAdapter` (ABC; abstract `source_name`/`raw_table`/`raw_schema` class attrs + `normalize`; concrete `full_table_name` property = `f"{raw_schema}.{raw_table}"`; default `validate_against_bronze()->True`; `async def db_query(self, drug_name, db_pool) -> dict|None` abstract, contract: return `None` ⇒ caller falls through to HTTP, raise ⇒ real error (NOT swallowed as miss)). The contract docstring must state the H1 rule explicitly.
- [ ] **Step 4 — Run, expect PASS**
- [ ] **Step 5 — Commit** `feat(mcp): add BaseAdapter contract (db_query None=fallthrough, raise=error)`

### Task 0.2: Package imports without the full adapter set

**Files:** Modify `adapters/ema_labels.py`, `adapters/openfda_labels.py` (import line only); Test `tests/test_mcp_import_smoke.py`

- [ ] **Step 1 — Failing test**
```python
# tests/test_mcp_import_smoke.py
def test_router_imports():
    import importlib
    importlib.import_module("dk_data.services.mcp.router")  # must not raise
def test_api_routes_import():
    import importlib
    importlib.import_module("dk_data.api.routes")
```
- [ ] **Step 2 — Run, expect FAIL** (`ModuleNotFoundError: ...adapters.base`) — confirms the prod-breaking bug.
- [ ] **Step 3 — Implement**: now that `base.py` exists (0.1), the imports resolve. Verify `ema_labels.Adapter`/`openfda_labels.Adapter` subclass the new `BaseAdapter`; fix any attribute mismatch so the module imports (do NOT wire behavior yet — Phase 1).
- [ ] **Step 4 — Run, expect PASS** (both modules import; router imports).
- [ ] **Step 5 — Commit** `fix(mcp): adapters package imports cleanly (unbreaks FastAPI app)`

### Task 0.3: Matrix test keeps the registry as backlog, green now

**Files:** Modify `tests/test_mcp_adapters.py`

- [ ] **Step 1**: Add one authoritative `BUILT_ADAPTERS: set[str]` (the modules that actually exist with a real `Adapter`). Parametrize over the full 28 (keep the contract/backlog visible) but `pytest.param(m, marks=pytest.mark.xfail(strict=True, reason="registry backlog — not yet built (Phase 2+)"))` for `m not in BUILT_ADAPTERS`.
- [ ] **Step 2 — Run**: `.venv/bin/python -m pytest tests/test_mcp_adapters.py -q --no-cov` → expected: built ones PASS, unbuilt ones XFAIL, **0 failures**.
- [ ] **Step 3**: N/A (test-only).
- [ ] **Step 4 — Run, confirm 0 failed / N xfailed**.
- [ ] **Step 5 — Commit** `test(mcp): registry matrix as xfail backlog (0 failures, contract preserved)`

### Task 0.4: Harden the migration-runner DO-block

**Files:** Modify `src/dk_data/scripts/run_migrations.py`; `tests/test_migration_runner.py`

- [ ] **Step 1 — Failing test**: add `test_ensure_tracking_table_emits_ddl_and_guard` asserting over `cursor.execute.call_args_list` (concatenated) that it contains `CREATE SCHEMA IF NOT EXISTS meta` AND the guard block; fix the existing `test_executes_create_statements` to scan `call_args_list` and drop the `commit.assert_called_once` coupling (assert `commit.called`).
- [ ] **Step 2 — Run, expect FAIL** (current code: `call_args` = last call; old assert).
- [ ] **Step 3 — Implement**: wrap the view round-trip so a failure can NEVER block migrations or silently destroy the view: detect matviews too (`pg_matviews`/`pg_class.relkind='m'`), only `DROP` after `v_def` successfully captured, `RAISE NOTICE` the captured def + an explicit warning if existence-positive but `v_def IS NULL`, wrap the `DO` body so a viewdef failure `RAISE`s (rolls back) rather than committing a destroyed view. Keep behavior identical on the happy path.
- [ ] **Step 4 — Run, expect PASS** (both tests).
- [ ] **Step 5 — Commit** `fix(migrations): harden api.migration_status guard (no silent CASCADE loss)`

### Task 0.5: Declare `openpyxl`

**Files:** Modify `pyproject.toml`; Test `tests/test_deps_declared.py`

- [ ] **Step 1 — Failing test**: parse `pyproject.toml`, assert `openpyxl` in `[project].dependencies` (mirrors the existing dep-declaration discipline).
- [ ] **Step 2 — Run, expect FAIL**.
- [ ] **Step 3 — Implement**: add `"openpyxl>=3.1,<4.0"`; `uv lock`.
- [ ] **Step 4 — Run, expect PASS**; also `.venv/bin/python -c "import openpyxl"`.
- [ ] **Step 5 — Commit** `build: declare openpyxl (used unconditionally by ema_epar)`

### Phase 0 exit gate
`.venv/bin/python -m pytest tests/ -q --no-cov` → **0 failed** (xfails allowed); `python -c "import dk_data.api.routes"` OK; `ruff check .` clean. Open PR vs **`staging`**. Phase 0 is independently shippable and unblocks every other PR (mirrors how #410 unblocked the repo-wide lint gate).

---

## 5. Phase 1 — DB-first path works end-to-end (WS2, execution-ready)

**Status:** Phase 0 merged to `staging` (`2bf123a`, #420). Branch all Phase-1 work off `origin/staging` as `fix/415-phase1-db-first-router` (one PR vs `staging`). Subagent-driven: fresh implementer per task, spec+quality review each. Each task = TDD (RED watched, minimal GREEN, commit). Run tests `.venv/bin/python -m pytest <path> --no-cov --no-header -q`; ruff via `~/.pyenv/versions/3.14.3/bin/ruff`.

**Goal:** `ema-search` / `ema-labels-search` / `openfda-labels-search` actually serve DB-first via the router (currently the DB logic is unreachable dead code), backed by a real `mol_silver.ema`, with silent-failure H1–H5 closed.

### Task 1.1 — Router consumes BaseAdapter `Adapter`s + DB pool injection
**Files:** Modify `src/dk_data/services/mcp/router.py`, `src/dk_data/services/mcp/base_tool.py` (or a new `dispatch.py`), `src/dk_data/api/app.py` (FastAPI lifespan); Test `tests/test_mcp_router_dbfirst.py`.
- RED: test that `POST /api/v1/data-tools/{slug}/invoke` for a slug whose `Adapter.db_query` returns a dict responds from DB **without** any outbound HTTP (patch httpx to assert not-called); and that `db_query` raising → router returns 5xx with a structured error (NOT a silent HTTP fallback).
- GREEN: FastAPI lifespan creates one `asyncpg` pool (reuse existing DSN/config used by other asyncpg callers; if none, psycopg pool per existing pattern) and stores it on `app.state`; the invoke handler resolves the adapter, calls `await adapter.db_query(drug_name, pool)` first — `None` ⇒ fall through to existing HTTP `invoke()`, dict ⇒ return it, exception ⇒ 502/500 structured (do not swallow). Registry-driven: map slug→Adapter via `tool_registry.TOOL_REGISTRY` for built adapters, keeping existing `*Tool` HTTP path for the rest.
- Commit `feat(mcp): registry-driven router with DB-first db_query + pool injection`.

### Task 1.2 — Build `mol_silver.ema` (SQLMesh silver)
**Files:** Create `src/dk_data/sqlmesh/models/molecules/silver/ema.sql` (adapt the worktree copy at `.claude/worktrees/agent-a3b53a1f/.../silver/ema.sql`; pattern-match `sqlmesh/models/molecules/silver/trademarks.sql`); Test `tests/test_silver_ema_model.py`.
- RED: test asserting the SQLMesh model parses/renders and yields the columns `ema.py` selects (`product_number, product_name, active_substance, inn, atc_code, marketing_authorization_holder, authorization_status, authorization_date, medicine_type, therapeutic_area, pharmacotherapeutic_group, epar_url, summary_url, molecule_id`) keyed off `bronze.ema`.
- GREEN: write the silver model selecting/normalizing from `bronze.ema` (which exists). Honor CLAUDE.md silver rules (no banned antipatterns S1–S5; entity ids via hub join/resolve, not inline fuzzy). Validate with the repo's SQLMesh validation (`Validate SQLMesh Models` CI job locally if a make target exists; else the model-render test).
- Commit `feat(silver): mol_silver.ema from bronze.ema (backs ema-search)`.

### Task 1.3 — Port `ema.py` onto BaseAdapter, single source of truth
**Files:** Modify `src/dk_data/services/mcp/adapters/ema.py`; Test `tests/test_adapter_ema.py`.
- RED: `EmaTool`/`Adapter` `db_query` returns rows from `mol_silver.ema` for a known substance via a mocked pool; the 6-way `OR` is replaced with an indexed-friendly query (no leading-wildcard LIKE — CLAUDE.md S2); `db_query` returning `None` when no row (not an error), raising on real DB error.
- GREEN: implement as a `BaseAdapter` subclass; query `mol_silver.ema`; add it to `BUILT_ADAPTERS` in `tests/test_mcp_adapters.py` and drop its xfail (strict xfail will force this).
- Commit `fix(mcp): ema adapter DB-first on mol_silver.ema (BaseAdapter)`.

### Task 1.4 — H1: openfda_labels error≠miss
**Files:** Modify `src/dk_data/services/mcp/adapters/openfda_labels.py`; Test `tests/test_adapter_openfda_labels.py`.
- RED: DB hit → `source:"openfda_local"`, no HTTP; genuine miss (`None`) → API fallback; DB **exception** → either raise OR return `{"source":"openfda","degraded":true,"degraded_reason":"local_lookup_error"}` (decide: raise unless an explicit degrade flag) and log at error — NOT a silent identical-to-miss fallback.
- GREEN: implement; remove the broad `except Exception: return None`.
- Commit `fix(mcp): openfda_labels — DB error is not a silent miss (H1)`.

### Task 1.5 — H2/H3: ema_labels cache integrity
**Files:** Modify `src/dk_data/services/mcp/adapters/ema_labels.py`; Test `tests/test_adapter_ema_labels.py`.
- RED: empty/garbage PDF extraction (`full_text` empty / `page_count`==0) is **not** written to `mol_raw.ema_label_cache`; a corrupt cached `extracted_text` row (`json.loads` raises or decodes non-dict) is skipped+logged (error id), not a 500; `_check_cache` honors a freshness TTL (stale row → re-extract). `_derive_smpc_url` pure-function unit tests (valid/invalid URLs → None).
- GREEN: guard `_save_cache` (refuse empty/garbage), wrap `json.loads`/`**` in `_check_cache`, add TTL/`ingested_at` staleness check + re-extract path.
- Commit `fix(mcp): ema_labels cache integrity — no poison, corrupt-row safe, TTL (H2,H3)`.

### Task 1.6 — H4/H5: ema_epar parser vs source-down
**Files:** Modify `src/dk_data/ingestion/fetchers/ema_epar.py`, `src/dk_data/ingestion/fetchers/ema_mol.py`; Test `tests/test_ema_epar_fetcher.py`.
- RED: a malformed/short XLSX (fixture or mocked `openpyxl.load_workbook`) → status `parse_error`/`schema_mismatch` (NOT `source_unavailable`); a primary-URL exception is logged at **error** (not warning) before any fallback; header-row detection validated against an expected column (drift → `schema_mismatch`). Replace `assert ws is not None` with an explicit raise.
- GREEN: implement the status distinction + header validation + error-level logging.
- Commit `fix(ingestion): ema_epar parser-error ≠ source-down; loud primary failure (H4,H5)`.

### Phase 1 exit gate
`tests/` no NEW failures vs the post-#420 `staging` baseline (same env-noise carve-outs as Phase 0); app imports; `ema_labels`/`openfda_labels`/`ema` real-pass in `test_mcp_adapters.py` (xfail removed for built ones, `strict` satisfied); ruff clean (tracked tree); SQLMesh validation green. PR vs `staging`; merge on green CI. Then WS3 (parallel-sub-agent adapter tail) is unblocked.

## 6. Phase 2..N (outline)
`tool_registry.py` = authoritative backlog. Each PR: pick 3–5 registry entries, TDD real `Adapter`s, flip their `xfail`→pass, register in router. Parallelizable across sub-agents. CI never red.

## 7. Decisions (LOCKED 2026-05-18)
1. **Approach: Option D** — phased (Option C) **and** a scheduled `staging→main` reconcile workstream. **Full `data-tools/` build-out is in scope** (the entire ~28-adapter registry vision is the committed end state, delivered phased — not deferred indefinitely).
2. **`mol_silver.ema`:** BUILD it as a SQLMesh silver model from `bronze.ema` (template `sqlmesh/models/molecules/silver/trademarks.sql`; adapt the worktree `silver/ema.sql`). `ema-search` becomes genuinely correct in Phase 1.
3. **Phase 2+ adapter tail:** I orchestrate **parallel sub-agents** (superpowers:dispatching-parallel-agents) building adapter batches concurrently from the registry backlog; I review + merge each green batch.
4. **#415:** review posted (`CHANGES_REQUESTED`, 2026-05-18). Open a **fresh Phase-0 PR vs `staging`** cross-linking #415; #415 is superseded, not force-pushed.

### Resulting workstreams
- **WS1 (Phase 0)** — this plan §4, branch off `origin/staging`. Unblocks import/CI. Ship first.
- **WS2 (Phase 1)** — DB-first router + pool injection + `mol_silver.ema` + H1–H5 for ema/openfda. Detail after WS1 green.
- **WS3 (Phase 2..N)** — parallel-sub-agent adapter build-out from `tool_registry.py`; one green PR per 3–5 adapters until the 28-row matrix is fully `pass` (no `xfail`).
- **WS4 (reconcile)** — `staging→main` forward-port plan (separate doc) once WS1+WS2 land on `staging`.

## 8. Self-review
- Spec coverage: every #415 defect (C1–C6, H1–H5, the 2 CI failures) maps to a phase/task. ✔
- No placeholders in Phase 0 (fully specified, TDD, exact files/commands). Phases 1–N intentionally outlined pending §7 decisions — detailing 28 adapters now would be placeholder-laden and presumptuous (writing-plans: no fake detail).
- Type consistency: `BaseAdapter` contract (0.1) is the single definition reused by 0.2/0.3 and Phase 1. ✔
