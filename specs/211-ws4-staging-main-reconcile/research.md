# Phase 0 Research — WS4

All decisions made autonomously (`/dk.auto`) from the approved design doc,
the git investigation, the constitution, and active tags.

## R1 — DB handle for the DB-first path

- **Decision**: Reuse `main`'s existing async DB access
  (`src/dk_data/api/dependencies.py`, asyncpg). The dispatch path receives a
  pool/connection acquired from the existing application DB lifecycle; no new
  pool is introduced.
- **Rationale**: Minimizes surface and risk; avoids a second connection
  lifecycle; respects active tag `[DSN]` (no new `psycopg2.connect(`; reuse the
  established helper/dependency). Honors "additive only".
- **Alternatives rejected**: a dedicated new asyncpg lifespan pool (staging's
  approach) — duplicate lifecycle, more failure modes, larger diff on the prod
  branch for no benefit.

## R2 — Gate mechanism

- **Decision**: Two environment variables — `MCP_DBFIRST_ENABLED` (global
  boolean, default **false**) and `MCP_DBFIRST_SOURCES` (comma-separated
  per-source allowlist; empty = none). Both delivered via Doppler +
  Kustomize overlays for **both** staging and prod (default-off) to preserve
  Environment Parity (Constitution II).
- **Rationale**: Simple, auditable, reversible by a single switch (FR-007);
  GitOps/Doppler compliant (`[GITOP]`/`[SECRT]`); per-source granularity lets
  each source be validated before exposure.
- **Alternatives rejected**: per-tier flags (too coarse for staged validation);
  a feature-flag service (over-engineered, new dependency); code constant
  (not reversible without deploy).

## R3 — SP2 reconcile strategy (OUTLINE; finalized in SP2's own design)

- **Decision (provisional)**: After SP1 is green on `main`: (1) push an
  immutable tag `staging-pre-ws4-reconcile` at the current `staging` tip;
  (2) reset `staging` to `origin/main`; (3) force-update `staging`. `staging`
  becomes a pure mirror of canonical `main`.
- **Rationale**: The histories are **unrelated** (no merge-base) — a merge
  would manufacture a permanent fake-merge with ~1,951-file conflicts and no
  value, since staging's content is being discarded anyway. A mirror reset is
  the only operation that achieves the stated end-state. The tag preserves full
  recoverability (FR-009).
- **Alternatives rejected**: `merge --allow-unrelated-histories -X theirs`
  (destroys `main`, violates "main canonical"); curated cherry-pick of 189
  commits (pointless — staging lineage is being retired); ours/theirs reconcile
  commit (same destruction risk).
- **Deferred to SP2 design**: staging-overlay deploy-target validation, CI
  workflow delta (`build-push.yaml` vs `build-dk-data-fe.yaml`), ArgoCD /
  preview implications, freeze window, announcement.

## R4 — Empty-result semantics (resolves a silent-bug class)

- **Decision**: A warehouse query that executes successfully but returns no
  rows / an empty payload is **"no local result" → fall through** to the
  existing external path. Only a non-empty match is "served"; only a raised
  exception is "error".
- **Rationale**: Prevents the "served an empty success" failure mode, which
  would mask data gaps as authoritative empties. Makes the three-way contract
  total and unambiguous (FR-001, edge cases, SC-002).

## R5 — SP3 ingestion-dedup approach (OUTLINE; own design cycle)

- **Decision (provisional, leading candidate)**: External ingestion runs
  **once** (production-side) into the shared production warehouse; the staging
  environment consumes the same warehouse **read-only**. Per-environment
  ingestion CronJobs/hydrate Jobs are removed from the staging overlay.
- **Rationale**: Eliminates duplicate external fetches and cross-env data
  drift (FR-011, SC-005); consistent with SP2's "staging mirrors main" outcome.
- **Open for SP3 design**: enumerate any genuinely environment-specific data
  need before cut-over (FR-012); decide shared-store boundary
  (single warehouse vs dedicated data namespace); migration/runbook.
- **Alternatives noted**: dedicated shared "data" namespace; staging keeps a
  thin subset. To be weighed in SP3 brainstorming.

## R6 — Observability of the new path (Constitution III / `[TESTE]`)

- **Decision**: Add one metric `mcp_dbfirst_outcome_total{source,outcome}` with
  `outcome ∈ {served, fallthrough, error, disabled}` and a trace span around
  the dispatch decision. Metric registered alongside the path and exercised by
  the H1 matrix tests so it is never a dead metric.
- **Rationale**: Constitution forbids dead metrics and unobservable services;
  the outcome metric also gives operators the signal to safely widen
  `MCP_DBFIRST_SOURCES` during rollout.
- **Alternatives rejected**: logging-only (not scrape-able for rollout
  decisions); no instrumentation (violates Principle III).
