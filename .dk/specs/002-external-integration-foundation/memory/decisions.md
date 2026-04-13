# Feature-Scoped Decisions — 002-external-integration-foundation

> These decisions were captured during dk.auto and subsequent audits. They are **feature-scoped** and will be **promoted to `.dk/memory/decisions.md`** at feature merge time (not before).
>
> Format: newest first. When promoting, renumber to continue from global `<!-- Next ID: D008 -->`.

## F-D008 — Activate `[ZVAL]`, `[VERSN]`, `[RBAC]`, `[AUDIT]` tags — 2026-04-13

**Context**: Feature 002 introduces JWT auth at the FastAPI layer, a SemVer-versioned client package, explicit role/permission checks, and per-request audit logging via the metering proxy.

**Decision**: Activate the four previously-dormant tags. CI enforcement:
- `[ZVAL]`: new FastAPI resolve wrapper routes declare Pydantic body/query models
- `[VERSN]`: client package uses SemVer; CI lint on `@datakinetic/dk-data-client` version bumps
- `[RBAC]`: router-level `Depends(verify_jwt)` on `/data-platform`; test: unauth → 401, missing-role → 403
- `[AUDIT]`: metering proxy audit-logs every request with consumer_id, resource, status, latency_ms

**Rationale**: Previously dormant because no prior feature required them. Feature 002 makes them load-bearing.

**Tags**: `[ZVAL]`, `[VERSN]`, `[RBAC]`, `[AUDIT]`

**Promotion target**: `.dk/memory/decisions.md` as D008; also update `.dk/memory/tags.md` Active Tags column on merge.

---

## F-D009 — FastAPI router-level `verify_jwt` dependency — 2026-04-13

**Context**: The `/data-platform/*` FastAPI surface (34 routes) has zero auth dependencies. Dropping `web_anon` from PostgREST does NOT lock down FastAPI unless FastAPI also enforces auth.

**Decision**: Add `Depends(verify_jwt)` at the router level: `APIRouter(prefix="/data-platform", dependencies=[Depends(verify_jwt)])`. Applies to all 34 current routes without per-route edits; new routes added under the router are auto-protected.

**Rationale**: Single line of code, bypass-proof for new routes. Per-route decorators are forgettable; middleware runs before path matching and complicates carve-outs.

**Tags**: `[RBAC]`, `[ZVAL]`

---

## F-D010 — Migration sequence 215 → 216 → 217 → 218 — 2026-04-13

**Context**: Four new migrations in feature 002. What order do they run in?

**Decision**: 215 rename → 216 missing views → 217 resolve grants → 218 drop web_anon. Migration 216 depends on 215 (the `mol_api.publications` view UNIONs `mol_api.pubmed_publications` and `mol_api.openalex_publications`, which only exist after 215). 218 runs last as the safety gate.

**Rationale**: Data dependency (216 → 215). Dropping `web_anon` last allows prior migrations to touch it during the transition window.

**Tags**: `[IDMPT]`, `[RBAC]`

---

## F-D011 — Client ships in TS + Python simultaneously — 2026-04-13

**Context**: Consumers span TS (behavior-labs-ai, ground-truth-charlie) and Python (trials-predictor). Should the client ship in both or phase Python?

**Decision**: Both simultaneously in v0.1.

**Rationale**: Phasing Python strands trials-predictor without a migration path and forces a second cutover window.

**Tags**: `[VERSN]`, `[TESTE]`

---

## F-D012 — Client cache L2 backend: Redis prod, SQLite dev — 2026-04-13

**Context**: The client needs an L2 cache shared across consumer app pods.

**Decision**: Redis in production (shared across pods, already deployed), SQLite in dev (no external dep).

**Rationale**: Cross-pod cache sharing is required for multi-replica consumers. SQLite keeps dev friction low.

**Tags**: `[IDMPT]`

---

## F-D013 — Client telemetry cadence: per-call in v0.1 — 2026-04-13

**Context**: ~7M events/day. Per-call immediate vs batched.

**Decision**: Per-call immediately in v0.1. Batching is a v1.1 optimization shipped only if Loki volume proves problematic.

**Rationale**: Per-call emission gives the cleanest causality for debugging. Premature optimization discouraged.

**Tags**: `[NOLOG]`

---

## F-D014 — Rollback depth for `218_drop_web_anon` — 2026-04-13

**Context**: Rollback of `DROP ROLE web_anon` could restore the full legacy grants or only a minimum.

**Decision**: Minimum only — USAGE on `api` + SELECT on `api.health` + SELECT on `api.data_catalog`. Nothing more.

**Rationale**: Restoring broad grants re-opens every hole the lockdown closed. Forward-fix (provision a consumer credential) is preferred over deep rollback.

**Tags**: `[RBAC]`, `[SECRT]`

---

## F-D015 — Deprecated alias window: 30 days telemetry-gated — 2026-04-13

**Context**: Migration 215 leaves deprecated `api.*` aliases pointing at `mol_api.*`/`ip_api.*`. How long do the aliases live?

**Decision**: 30 calendar days after the last consuming app's migration to the prefixed names is verified in telemetry.

**Rationale**: Hard deadline prevents permanence; telemetry-gating prevents dropping them while a lagging consumer still uses them.

**Tags**: `[VERSN]`

---

## F-D016 — Backfill for consolidated chembl-activities: single sequential job — 2026-04-13

**Context (drift audit D2)**: Original US-20 plan assumed the backfill orchestrator could fan out 17 parallel Jobs for chembl-activities (one per year). Code inspection found no fan-out pattern in `src/dk_data/ingestion/`. The orchestrator runs every 10 min with `max 1 concurrent`, per-source activation via SQL UPDATE — it does NOT dispatch N parallel jobs.

**Decision**: Run the consolidated `cronjob-fetch-chembl-activities.yaml` as a SINGLE SEQUENTIAL job. Each cron tick processes exactly ONE year — the next un-backfilled year from `meta.backfill_state`. Job reads state → fetches one year → updates state → exits. 17 ticks = 17 years complete. After initial backfill, subsequent ticks keep the latest year current.

**Rationale**:
- Matches the existing backfill orchestrator contract (no new orchestrator feature needed)
- Per-year WAL budget is bounded to ~1M records × reasonable row size → well under the 2 GB `[WALMX]` ceiling
- Resumable: if a year fails mid-fetch, the next tick retries from the `meta.refresh_state.last_chunk_position`
- No new capacity ask: the existing cronjob cadence (10-min orchestrator tick) drives progress
- Wall-clock: 17 ticks × 10 min = 170 min minimum for full backfill (acceptable for one-time backfill)

**Alternatives considered**:
- Fan-out parallel Jobs (original plan): requires building a new orchestrator feature (scope creep)
- Single Job processes all 17 years in one run: violates `[WALMX]` (17M records × one transaction)
- Split into 4 ranges (2010-2014, 2015-2018, 2019-2022, 2023-2026): still per-tick sequential; same as single-year but with larger chunks and worse resumability

**Tags**: `[IDMPT]`, `[WALMX]`, `[JOBLK]`

**Same pattern applies to pubchem**: the consolidated `cronjob-fetch-pubchem.yaml` runs one range per tick (6 ranges total), not all 6 in parallel.

---

## F-D017 — Adapter v0.2 lifecycle after migration 216 — 2026-04-13

**Context (drift audit D1)**: Adapter v0.1 ships in Phase 3 against the pre-cleanup PostgREST surface. After Phase 4 migrations land, `mol_api.*` surface changes. Type fingerprint in `serverInfo()` mismatches → consumers see warnings or errors.

**Decision**:
1. Immediately after migration 216 lands on prod, regenerate types and publish `@datakinetic/dk-data-client` v0.2.0
2. Client `serverInfo()` schema fingerprint check is WARN-ONLY (not throw) in v0.1 → allows graceful coexistence during the upgrade window
3. Target window: consumers upgrade to v0.2 within 7 days of migration 216 landing
4. Document the transition window in `docs/consumer-onboarding.md`

**Rationale**: Decoupling adapter release from migration land gives consumers time to upgrade without breaking them. Warn-only fingerprint avoids flag-day breaks.

**Tags**: `[VERSN]`, `[TESTE]`

---

## F-D018 — `.dk/memory/` commit discipline — 2026-04-13

**Context (drift audit D4)**: Earlier edits appended D008-D015 to global `.dk/memory/decisions.md` and activated `[ZVAL]`/`[VERSN]`/`[RBAC]`/`[AUDIT]` in global `.dk/memory/tags.md`. These are global artifacts affecting every future feature. If feature 002 is cancelled or partially shipped, the global edits hang around.

**Decision**:
1. All feature-scoped decisions live in `.dk/specs/002-external-integration-foundation/memory/decisions.md` (this file, as `F-D<N>`)
2. Tag activations stay dormant in global `.dk/memory/tags.md` until the PR that lands the feature code also lands the tag activation (same commit)
3. On feature merge: promote `F-D008`–`F-D017` to `.dk/memory/decisions.md` as `D008`–`D017`; flip the tag activation notes; bump the `<!-- Next ID -->` marker
4. On feature cancellation: nothing to revert globally; this file is deleted with the feature directory

**Rationale**: Prevents global memory drift during a multi-week implementation window. Preserves the audit history (feature memory file is committed in the feature branch).

**Tags**: `[GITOP]`

---

## F-D019 — L2 cache TTL corrected for gold-backed resources — 2026-04-13

**Context (drift audit D7)**: Original cache table set `competitive_landscape` TTL to 6 hours. The `cronjob-mol-transform-gold-ext.yaml` runs daily at 22:00 UTC, so the underlying data only updates once per day. A 6-hour TTL caches the same miss 4× per day for zero freshness benefit.

**Decision**: Set L2 TTL to 24 hours for every gold-backed resource: `molecule_profile`, `safety_signals`, `lifecycle_stages`, `competitive_landscape`, `company_pipeline`. Clinical trials stay at 6h (CT.gov changes mid-day). Drug labels stay at 24h. Identifiers stay at 30 days.

**Rationale**: Align TTL with actual refresh cadence.

**Tags**: `[TESTE]`
