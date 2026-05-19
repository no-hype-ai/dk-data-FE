# WS4 — `staging` ↔ `main` Reconcile: Design Spec

- **Date:** 2026-05-19
- **Status:** Approved design (pending spec review) → next: implementation plan (SP1)
- **Owner:** PR #415 MCP/DB-adapter remediation, workstream WS4
- **Supersedes premise of:** the WS4 outline in `docs/superpowers/plans/2026-05-18-pr415-mcp-db-adapter-remediation.md` §"Resulting workstreams"

---

## 1. Context — the handoff premise was factually wrong

The WS4 handoff assumed a mechanical forward-port: "`main` lacks the #415 chain;
merge `staging`→`main`." Direct inspection of `origin/main` and `origin/staging`
disproved this:

| Claim in handoff | Git reality (verified 2026-05-19) |
|---|---|
| "diverged, no useful shared base" | **Zero common ancestor.** Distinct roots (`main` `3b8a4ca`; `staging` `0680aea` "Initial commit from Specify template"). `git merge-base origin/main origin/staging` → empty (unrelated histories). |
| "prod import broke: no `base.py`" / "#415 chain ONLY on staging" | `main` **has** `src/dk_data/services/mcp/adapters/base.py` + **63** adapters (feature `015-assessment-dashboard-integration`, T059/T062/T079). staging has **34**. |
| "#408/#410/#412 only on staging" | All three are in **main's** log (`9d33fe0` #412, `28fe600` #410, `5c86bc6` #408). |
| net delta | `git diff origin/main origin/staging` = **1,951 files, +17,746 / −220,052**. Adopting staging onto main would delete ~220k lines of main-only work (TAVR Phase 0/1A/1B, hydrate dispatcher, resource budget, source registry, ~30 CMS adapters, prod-promotion infra). |
| staging-unique adapters | Only **1** adapter file is staging-only (`ema_labels.py`). 30 adapter files are main-only. |

**Logical (not git) relationship:** both trees share the feature-015 MCP scaffold
by content (`tool_registry.py` near-identical). They diverged from a *logical*
common point: `staging` = feature-015 scaffold **+ #415 hardening** (rewrote
`base.py` with the load-bearing `async db_query()` H1 contract, added
`dispatch.py`, isolation tests, 34 hardened adapters); `main` = feature-015
scaffold **+ 63 adapters + TAVR/hydrate/prod**, with the *pre-#415* `base.py`
(no `db_query()` at all) and an older hardcoded 8-tool HTTP `router.py`.

The original #415 trigger ("prod FastAPI import broke — no `base.py`") **does
not exist on `main`**. So #415 fixed a *staging-lineage-only* breakage; its only
residual value to `main` is the DB-first serving capability + the H1
silent-failure contract — a net-new *feature* for `main`, not a prod bugfix.

## 2. Decisions (load-bearing — from stakeholder Q&A)

1. **`main` stays canonical / prod.** Never overwrite main's tree with staging's.
2. **End-state: replace `staging` with `main`.** staging's divergent Specify
   rewrite is not the future; staging becomes a deploy mirror of canonical main.
3. **Port the full 34 hardened adapter set's `db_query` + the H1 contract onto
   `main`** before replacing staging (otherwise the #415 work is discarded).
4. **Port mechanism = Approach A (additive + gated):** DB-first short-circuit is
   env-gated **OFF by default** → zero default prod behavior change; opt-in per
   source as each real query is validated.
5. **New scope item:** data should be created **once**, not downloaded/built
   separately for `staging` and `prod` (ingestion dedup across environments).

## 3. Sub-project decomposition & sequencing

WS4 is three independent sub-projects. **SP1 is implementation-ready in this
doc. SP2 and SP3 are outlined here but each requires its own design + plan
before implementation.**

```
SP1  port #415 db_query/H1/isolation onto main   ──(must land green on main)──┐
                                                                              ▼
SP2  replace staging with main (branch reset; staging = deploy mirror)        │
                                                                              ▼
SP3  data-created-once (ingestion dedup across environments)
```

Hard ordering: **SP1 must merge green on `main` before SP2.** If staging is
reset to main before #415 is ported, the #415 work is lost. SP3 is independent
of SP1 but logically follows SP2 (one canonical branch first).

---

## 4. SP1 — Port #415 db_query / H1 / isolation onto canonical `main`

### 4.1 Key structural facts (grounding)

- `main` already has `Adapter(BaseAdapter)` classes for the feature-015 sources
  (e.g. `chembl.py::class Adapter(BaseAdapter)` — same shape as staging's).
  `main/adapters/__init__.py` exports only the **8 `*Tool(BaseMCPTool)`**
  classes the live router uses (`FdaDrugsTool`, `PdbStructuresTool`,
  `OrcidTool`, `CmsPartDSpendingTool`, `HtaDecisionsTool`, `EmaTool`,
  `CochraneTool`, `TtdTool`). The ~55 other `Adapter(BaseAdapter)` classes are
  feature-015 **normalize-only** and already present.
- `main` already ships `tool_registry.py` (feature-015 T062, full registry) and
  uses `asyncpg` (`src/dk_data/api/dependencies.py`).
- `main`'s `router.py` dispatches a **hardcoded 8-entry `TOOL_REGISTRY` dict**
  via `adapter.invoke()` → `httpx`. It does **not** dispatch through
  `tool_registry.TOOL_REGISTRY`. staging's `dispatch.py` is what makes the
  registry the live DB-first path.
- Of staging's 34 adapters: 29 expose `db_query`; **24 use the placeholder
  ILIKE** serving query (`SELECT response_body FROM <schema>.<raw_table> WHERE
  response_body::text ILIKE '%'||$1||'%'` — documented generic-pending-model);
  ~5 are genuinely refined (`ema`, `ema_labels`, `openfda_labels`, Phase-1).
  `main` has **0/62** with `db_query`.

→ The port is genuinely **additive**: graft new behavior onto pre-existing
main structures; do not rewrite main's proven dispatch.

### 4.2 Architecture (additive, zero default-path change)

**C1 — `base.py` additive merge.** Add to main's `BaseAdapter`:
`async def db_query(self, drug_name, db_pool) -> dict | None` returning `None`
by default, with the load-bearing H1 contract docstring (return `None` →
caller falls through to HTTP; return `dict` → served from warehouse; **RAISE →
real error, caller MUST surface, not treat as miss**). **Preserve** main's
feature-015 surface (`build_url`, `build_urls_with_resolution`,
`validate_against_bronze`). Purely additive; no existing adapter contract
changes; main's `test_mcp_adapters.py` T079 stays green.

**C2 — `dispatch.py` new parallel module.** Ported from staging, adapted to
main. Registry-driven: `tool_registry.TOOL_REGISTRY[slug].adapter_module` →
lazy-import `Adapter` → `db_query`. Never raises on absent/older adapters
(returns "no DB path"). H1 dispatch order: `db_query` dict → return (no HTTP);
`None` → fall through to HTTP; **raise → HTTP 502 `{"stage":"db_query"}`,
never fall through** (DB outage ≠ cache miss).

**C3 — `router.py` single gated hook.** Before the existing `adapter.invoke()`
HTTP call in `invoke_tool`, *iff* DB-first is enabled for that source,
delegate to `dispatch`. Gate:
- `MCP_DBFIRST_ENABLED` (global bool, default **false**)
- `MCP_DBFIRST_SOURCES` (comma-separated per-source allowlist; empty = none)

Default OFF → prod `/api/v1/mcp-tools/{tool}/invoke` behaves **exactly as
today**. Enabling is opt-in per source via env once its real query is validated.

**C4 — DB handle.** Reuse main's existing `asyncpg` access
(`src/dk_data/api/dependencies.py`). No new lifespan pool. Exact wiring
(dependency vs. app-state pool) pinned in the implementation plan.

**C5 — 34 `db_query` bodies.** Graft staging's `db_query` methods onto main's
*existing* `Adapter(BaseAdapter)` classes for the name-matching sources. The 5
refined ones are eligible to enable via `MCP_DBFIRST_SOURCES`; the 24
placeholder-ILIKE bodies are present but gated and documented as backlog
(see §4.6). `ema_labels` is staging-only as a file → add as a new main
`Adapter`.

### 4.3 Data flow (gate ON for a source `S`)

```
POST /api/v1/mcp-tools/{S}/invoke {drug_name}
  └─ router.invoke_tool
       ├─ MCP_DBFIRST_ENABLED && S in MCP_DBFIRST_SOURCES ?
       │     ├─ no  → main's existing httpx adapter.invoke()  [unchanged path]
       │     └─ yes → dispatch.dispatch(S, drug_name, pool)
       │                ├─ Adapter.db_query → dict  → 200 (served from warehouse)
       │                ├─ Adapter.db_query → None  → fall through to httpx invoke()
       │                └─ Adapter.db_query raises  → 502 {"stage":"db_query"} (STOP)
```

### 4.4 Error handling

H1 is the core invariant: a raising `db_query` is a real error surfaced as
**502 `{"stage":"db_query"}`**; the dispatcher must **never** swallow it into an
HTTP fallthrough. `None` is the *only* "fall to HTTP" signal. Absent/older
adapter modules are not errors (no DB path → HTTP). All non-DB-first behavior
is byte-for-byte main's current behavior.

### 4.5 Testing & verification

- **TDD** every code change (RED → GREEN).
- Port staging's `test_mcp_data_tools_isolation.py` — the sys.modules-landmine
  regression. Use the **file-path probe under a throwaway name**, never
  `import_module("tests.…")` (that fails CI with `ModuleNotFoundError: tests`).
- Add a `db_query` **H1 contract matrix** (hit → dict; miss → None→HTTP;
  raise → 502, no fallthrough) over main's `Adapter` classes, using a
  FakePool / `asyncio.run` harness (no live DB; matches staging's pattern).
- Keep main's `test_mcp_adapters.py` T079 `ADAPTER_MODULES` normalize tests
  intact (no regression).
- Ruff CI-faithful: `ruff check .` clean (no `tests/conftest.py` sys.path hack
  — it breaks Lint via E402 and is out of scope; for local worktree runs use
  `PYTHONPATH=<worktree>/src`).

**Verification gate (ALL required before merge, no auto-merge):**
1. main CI **`Lint` = pass** AND **`Test` = pass** AND **`Validate SQLMesh
   Models` = pass** AND **`Validate Kubernetes Manifests` = pass**, confirmed
   via `gh pr checks <#>` against the verified PR head SHA
   (`gh pr view <#> --json headRefOid` — guard against reading a stale green).
2. db_query H1 contract matrix real-passes (0 xfail).
3. `python -c "import dk_data.api.routes"` clean.
4. With gate OFF: a representative `invoke_tool` call is byte-identical to
   pre-change behavior (no default-path regression).

### 4.6 Deferred carry-forwards (documented-accepted, not fixed in SP1)

- 24 placeholder-ILIKE `db_query` bodies — generic pending each source's
  bronze/silver model. Present but gated OFF; refine per source later.
- Phase-1 deferred: (1) `ema-search` exact-match-only; (2)
  `openfda_labels._api_lookup` broad `except…return None` (HTTP-leg silent
  miss; H1 fixed only for DB path); (3) `ema_labels` `ingested_at=None`
  bypasses 30-day TTL; (4) `ema_mol` pandas-fallback not header-validated;
  (5) `ema-labels-search` 404-on-miss by design.

### 4.7 Rollback

`MCP_DBFIRST_ENABLED=false` (or empty `MCP_DBFIRST_SOURCES`) disables the entire
DB-first path instantly with no code revert. Because the change is additive and
modifies no feature-015 behavior, `git revert` of the squash-merge is clean.

---

## 5. SP2 — Replace `staging` with `main` (OUTLINE — needs own spec + plan)

**Problem.** `staging` is a divergent Specify-template rewrite that is *not* the
future. After SP1 lands, `staging` should become a deploy mirror of canonical
`main` so there is one source of truth and staging inherits main's richer CI
(`integration-live`, `standards`, `enrollment-check`, `grafana-dashboards`,
`mirror-pgbouncer`, `build-dk-data-fe`, plus the gated `-m "not integration"`
test split).

**Mechanics sketch (to be designed in SP2):**
- Hard-reset `staging` to `main` (force-push) — discards 189 staging commits
  incl. the entire #415 lineage (#420–#428). Acceptable **only because SP1 has
  ported the #415 value to main first** (hard dependency).
- The staging *environment* persists: `main` already carries
  `k8s/overlays/staging`. Confirm staging overlay image-tag / Doppler / deploy
  wiring on `main` is correct for the staging cluster before the reset.
- CI: PRs to `staging` will run main's `ci.yaml`. Confirm no
  staging-only workflow (`build-push.yaml`) is load-bearing for the staging
  environment, or port its function to main's `build-dk-data-fe.yaml`.

**Open questions for SP2 design:** preserve any staging-only operational config?
ArgoCD / dk-preview implications of the branch reset? Announcement / freeze
window? Backup of the staging ref (tag `staging-pre-ws4-reset`) before
force-push (recommended).

**Risk:** irreversible force-push on a shared branch. Mitigation: tag the old
staging tip; SP1 green-on-main as a hard gate; explicit human go-ahead.

## 6. SP3 — Data created once, not per-environment (OUTLINE — needs own brainstorming + spec + plan)

**Problem (stakeholder).** Data is currently downloaded/built separately for
`staging` and `prod`; it should be created **once** and shared.

**Current-state evidence.** `main` carries a large ingestion fleet
(`k8s/apps/cronjobs/base/cronjob-fetch-*`, `cronjob-cms-all`,
`cronjob-backfill-orchestrator`, `deploy/hydrate/sources.yaml`,
`deploy/jobs/prestaged-hydrate.yaml`) parameterized through
`k8s/overlays/{prod,staging}` — so ingestion runs in **both** overlays →
external sources fetched twice and the two environments can drift.

**Option sketch (to be brainstormed/designed in SP3):**
- (a) Run ingestion CronJobs in **one** namespace/environment only; the other
  reads the same shared Postgres/object store.
- (b) A dedicated shared "data" namespace decoupled from app envs; both
  app envs are read-only consumers.
- (c) Eliminate the separate staging *data* path entirely (staging reads prod
  data read-only) — interacts with SP2's "staging = mirror" outcome.

**Out of scope here.** SP3 gets its own brainstorming → spec → plan cycle;
this section only records the problem and that it is sequenced after SP2.

---

## 7. Governance findings (surface to human; do not rely on automation)

Neither `main` nor `staging` enforces required status checks — `Test`/`Lint`
are **not** blocking (this is why #421 once merged on red CI). Every WS4 PR
merge must be **manually** gated on `gh pr checks` showing `Test` + `Lint`
(+ SQLMesh + k8s on main) = pass against the verified head SHA; **no
auto-merge**. **Recommendation to stakeholder:** make `Test` + `Lint` required
status checks on **both** `main` and `staging`.

## 8. Out of scope

- Refining the 24 placeholder-ILIKE serving queries (per-source future work).
- The Phase-1 deferred items in §4.6 (documented-accepted).
- Any modification to main's feature-015 adapter normalize() behavior.
- SP2/SP3 implementation (separate cycles).

## 9. Definition of done (WS4 overall)

- SP1 merged green on `main`; db_query H1 matrix real-pass; app import clean;
  gate OFF = zero prod behavior change verified.
- SP2 executed: `staging` reset to `main` (post-SP1), staging deploy verified.
- SP3 designed and executed in its own cycle.
- Memory (`pr415-remediation-state.md` + `MEMORY.md`) updated; remediation
  task #7 closed; #415 remediation fully closed.
