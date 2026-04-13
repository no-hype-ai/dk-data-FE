# Decisions

> Key architectural choices that affect future work. Newest first.
> Format: ID, title, date. Then Context, Decision, Rationale, Tags.
> Only record decisions that a future developer or AI session needs to know about.

<!-- Next ID: D008 -->

<!--
  Feature-002 decisions D008-D015 were removed from global memory on 2026-04-13
  per drift-audit fix D4. They live in .dk/specs/002-external-integration-foundation/memory/decisions.md
  and will be promoted here on feature merge.
-->

## D007 — Crosswalk dedupe and conflict policy — 2026-04-11

**Context**: Hub bootstrap procedures need to be idempotent (FR-026). What happens if a re-run encounters a `(source, identifier)` that already exists but resolves to a different `hub_id` than the existing row?

**Decision**: Every crosswalk has `(source, identifier)` as `PRIMARY KEY`. Bootstrap inserts use `ON CONFLICT (source, identifier) DO NOTHING`. If a conflict is detected (existing row's `hub_id` differs from the new resolution), the bootstrap MUST log to a new audit table `meta.linkage_conflicts (detected_at, source, identifier, existing_hub_id, new_hub_id, procedure_name)` and MUST NOT silently overwrite. Operators triage conflicts manually.

**Rationale**: Idempotence + zero data loss. Conflicts are rare but corrupt downstream joins when they happen silently. The audit table makes them visible without blocking the bootstrap.

**Tags**: `[IDMPT]`

## D006 — `[PGBOU]` tag activation — 2026-04-11

**Context**: PgBouncer is deployed at `pgbouncer.infra.svc.cluster.local:5432` but most fetcher pods today connect directly to the postgres primary, eating connection slots from the shared `max_connections=200` budget.

**Decision**: Activated `[PGBOU]` tag. Long-running fetcher and short-lived transform pods MUST set both `POSTGRES_HOST` (PgBouncer) and `POSTGRES_HOST_DIRECT` (primary). SQLMesh and PL/pgSQL procedure invocations use `_DIRECT` because they need session features. Everything else uses the pooler.

**Rationale**: PgBouncer transaction mode breaks session-scoped advisory locks and prepared statements, but we already use `meta.job_locks` (D005) instead of advisory locks, so the transaction-mode constraint is acceptable for the workloads that route through it.

**Tags**: `[PGBOU]`, `[JOBLK]`

## D005 — Persistent job locks via `meta.job_locks` — 2026-04-11

**Context**: PgBouncer transaction mode breaks `pg_try_advisory_lock` (session-scoped). Cross-pod coordination needs an alternative.

**Decision**: TTL-based persistent lock table `meta.job_locks (name PRIMARY KEY, locked_by, locked_at, expires_at)`. Acquire is `INSERT ... ON CONFLICT (name) DO UPDATE WHERE expires_at < NOW()`. Release is `DELETE WHERE name = ? AND locked_by = ?`. Stale locks auto-expire.

**Rationale**: Survives PgBouncer transaction-mode multiplexing. Auto-expiration handles pod crashes without manual cleanup.

**Tags**: `[JOBLK]`

## D004 — Drug product hub at SCD/SBD level — 2026-04-11

**Context**: RxNorm Semantic Clinical Drugs (SCD/SBD) describe one clinical drug ("Sildenafil 50 MG Oral Tablet"). Each SCD has many NDCs (~47 for a generic). Should the hub be at SCD level or NDC level?

**Decision**: SCD/SBD level (one row per clinical drug). NDC moves to the crosswalk as `source = 'ndc'` rows. Hub keys on `rxcui` UNIQUE (TTY in (SCD, SBD, GPCK, BPCK) only). RxCUIs at IN/PIN/BN return NULL from `resolve_drug_product` with a hint to call `resolve_molecule` instead.

**Rationale**: NDC-level would force ~47 duplicate rows per generic clinical drug. SCD/SBD matches RxNorm's clinical concept and how clinicians and pharmacists think about products. Two-tier (SCD parent + NDC child) is overkill for v1 with no use case requiring package-level distinction.

**Tags**: `[CARRY]`

## D003 — Hub scope: all 10 hubs in one feature — 2026-04-11

**Context**: The source linkage doc enumerates 10 entity types (molecules, drug_products, targets, conditions, companies, providers, facilities, patents, trademarks, designs). Should v1 ship all 10 or a subset?

**Decision**: Ship all 10 hubs in feature 001-silver-medallion-rebuild. Bootstrap budget ≤105 min wall clock, ≤7 GB total WAL — fits the cluster's reliability ceilings.

**Rationale**: Partial scope would force consumers to wait on follow-up work and would leave silver enrichment models without targets to join to. The 10 hubs are interlinked (drug_products → molecules, patents → companies + molecules, providers → facilities) so a partial cut is incoherent.

**Tags**: `[CARRY]`

## D002 — Two-tier confidence threshold for fuzzy fallback — 2026-04-11

**Context**: `resolve_*()` functions need a Pattern D fallback (trigram fuzzy) for sources with no canonical identifier. Without a threshold, every misspelling resolves to *some* hub row.

**Decision**: Two-tier. Resolve functions return matches at `pg_trgm` similarity ≥ 0.85 alongside the computed `confidence` value; matches below 0.85 return NULL. Gold-layer consumers and any clinical-grade silver join MUST filter on `confidence ≥ 0.95`.

**Rationale**: 0.85 is the standard `pg_trgm` "probably the same word" threshold; 0.95 is the standard "same word, possibly cased differently" threshold. Two-tier lets us use fuzzy matches for discovery without polluting clinical outputs.

**Tags**: `[CARRY]`

## D001 — Structured-field linking instead of LLM extraction — 2026-04-11

**Context**: ~8 sources ship entity references in narrative text (FAERS, ClinicalTrials.gov, DailyMed, PubMed, EuropePMC, patents, news, SEC EDGAR). Original assumption was that LLM extraction via `litellm-server` was needed.

**Decision**: No LLM in v1. Read structured sibling fields the source APIs already provide:
- FAERS: `patient.drug[].openfda.unii[]` / `rxcui[]` / `product_ndc[]` / `substance_name[]`; reactions via `reactionmeddrapt` (already MedDRA PT)
- ClinicalTrials.gov: `protocolSection.derivedSection.interventionMeshList[]` and `conditionMeshList[]`
- PubMed / EuropePMC: `MeshHeadingList` and `ChemicalList` + regex `NCT\d{8}` / DOI / PMID over title+abstract
- Patents: Orange Book join on `(application_number, patent_number)` for FDA-approved drugs only
- Medical news: precompiled regex against `mol_bronze.who_inn` (~10K WHO INN entries)

**Rationale**: Source-API audit found ~80–90% coverage from structured fields alone. LLM cost analysis ($8K–30K one-time + $2.5K–10K/year) does not justify the marginal lift. Genuinely prose-only cases (DailyMed indication prose, non-FDA patent claims, SEC EDGAR Business sections) deferred to a follow-up.

**Tags**: `[CARRY]`, `[SVANT]`
