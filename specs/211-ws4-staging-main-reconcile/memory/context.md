# Feature Context — 211-ws4-staging-main-reconcile

**Feature**: WS4 — `staging`/`main` reconcile (port #415 hardening, unify
branches, dedupe ingestion).
**Created**: 2026-05-19 · **Pipeline**: `/dk.auto` (autonomous).
**Based on**: canonical `origin/main` (isolated worktree `.agents/ws4`) — NOT
`staging`, because `staging` is slated for replacement (SP2) and artifacts must
live on the surviving lineage.

## Key context

- `main` ⟂ `staging`: **unrelated git histories** (no merge-base). `main` is
  canonical/prod (feature-015 MCP, 63 HTTP-only adapters, TAVR/hydrate/prod).
  `staging` = Specify rewrite + #415 hardening (34-adapter subset).
- WS4 = 3 sequenced sub-projects: **SP1** additive gated DB-first port onto
  `main` (implementation-ready) → **SP2** replace `staging` with `main`
  (outline) → **SP3** dedupe ingestion (outline). SP1 hard-gates SP2.
- SP1 is **additive + default-off**: zero prod behavior change until a source
  is explicitly enabled; reversible by one env switch + clean revert.

## Active tags in scope (already enforced; no new tags added)

- `[DSN]` — reuse existing async DB access; no new `psycopg2.connect(`.
- `[TESTE]` — unit H1 matrix (fake pool) + integration leg vs real CNPG.
- `[GITOP]` / `[SECRT]` — gate env via Doppler + Kustomize overlays, no
  committed `.env`.
- `[ZVAL]` / `[VERSN]` — no request-schema / endpoint-version change.
- `[BRKR]` — SP1 adds no new external HTTP (fallthrough uses existing path).

Decision of record: `.dk/memory/decisions.md` **D009**.

## Governance (must surface; do not rely on automation)

Neither `main` nor `staging` enforces required status checks. Every WS4 merge
is manually gated on `gh pr checks` green at the verified head SHA; **no
auto-merge** (FR-013). Recommendation to stakeholder: make build/lint + test
required checks on both branches.

## Carry-forward / deferred (not blockers)

- 24 of 34 ported `db_query` bodies are the documented placeholder ILIKE
  serving query — present but gated off, refine per source later.
- Phase-1 deferred items (ema-search exact-match; openfda_labels `_api_lookup`
  HTTP-leg silent miss; ema_labels TTL on `ingested_at=None`; ema_mol
  pandas-fallback header; ema-labels-search 404-by-design) remain
  documented-accepted (FR-014).
