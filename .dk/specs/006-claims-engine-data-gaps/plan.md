# Implementation Plan: claims-engine-data-gaps

## Technical Context

- **Database:** PostgreSQL 16 on CNPG (CloudNativePG) in a k3s cluster.
- **Transformation layer:** SQLMesh models in `src/dk_data/sqlmesh/models/` — bronze, silver, gold tiers per domain (`mol_`, `hcs_`, `ind_`, `ip_`).
- **Ingestion layer:** Python loaders in `src/dk_data/ingestion/` — fetchers pull from upstream APIs, sources/loaders write to `*_raw` schema tables.
- **API surface:** PostgREST exposes silver/gold views. FastAPI handles `/data-platform/*/resolve` RPCs.
- **WAL constraint:** `[WALMX]` tag — no single SQL transaction may produce more than 2 GB WAL. Heavy loads use chunked procedures with `pg_current_wal_lsn()` brackets written to `meta.transform_runs`.
- **Silver architecture:** 10 canonical entity-resolution hubs. Resolve functions target <=10ms p99 (SC-004). Five banned antipatterns (S1-S5) enforced by CI.
- **Passthrough convention:** `mol_silver.drug_labels` is a full passthrough of `mol_bronze.openfda_labels`; `mol_silver.fda_drugs` is a passthrough of `mol_bronze.fda_drugs`; `mol_silver.purple_book` is a passthrough of `mol_bronze.purple_book`. Adding columns at bronze makes them appear at silver after a SELECT-list sync.

---

## Prerequisites

### WAL Circuit Breaker Gating

Large bronze rebuilds (Items 25, 26, 27, 28) will each touch tables with potentially millions of rows. Before beginning Phase 3+, the WAL circuit breaker infrastructure must be in place:

- Confirm `meta.transform_runs` WAL accounting is active for all write paths.
- For any loader backfill that will produce >500 MB WAL, use the chunked procedure pattern (<=50K rows / <=200 MB WAL per chunk, `pg_sleep(0.05)` between chunks, resumable via `meta.refresh_state.last_chunk_position`).
- If a tray pattern (UNLOGGED staging -> chunked load -> SET LOGGED -> atomic swap) is needed for the largest bronze tables (NPPES at ~7M rows, Open Payments at ~12M rows/year), model it after the existing `mol_bronze.refresh_chembl_activities_via_tray()` procedure from feature 001.

### Tray Pattern for Large Bronze Rebuilds

Items 25 and 26 require full-table backfills of expanded column sets. These tables exceed 1M rows and must use:

1. Dedicated CronJobs (not the daily SQLMesh CronJob).
2. Direct connection via `POSTGRES_HOST_DIRECT` (not PgBouncer).
3. Drop non-essential indexes before bulk load, recreate concurrently after.
4. BRIN indexes on `ingested_at` columns instead of btree.

---

## Phase 1: Week 1 -- Hotfixes + Quick Wins (P0)

### Item 24: Fix `mol_bronze.purple_book` 0-row regression (~0.5d)

**Decision: Option A -- direct `results[]` iteration, no loader change.**

The Purple Book fetcher stores raw openFDA Drugs@FDA API responses unchanged. The upstream API returns records under `results[*]`, not `_normalized_products`. Option A rewrites the bronze SQL FROM clause to iterate `response_body->'results'`, avoiding any loader-side normalization. This is preferred because:
- It keeps the loader a pure pass-through (consistent with every other fetcher).
- The fix is entirely in one SQL file -- no Python change, no re-ingestion needed.
- Existing raw data is immediately usable.

**Fix shape:**

1. Rewrite `src/dk_data/sqlmesh/models/molecules/bronze/purple_book.sql`:
   - Change FROM clause: `jsonb_array_elements(response_body->'results') AS app`, then `LATERAL jsonb_array_elements(app->'products') AS prod` to get one row per product.
   - Update all column projections to read from `app` (application-level fields) and `prod` (product-level fields).
   - Add WHERE filter: `app->>'application_number' LIKE 'BLA%'` or `prod->>'license_type' = 'BLA'` to restrict to Purple Book scope.
2. Add SQLMesh audit: `row_count_at_least(1000)` to catch future regressions.
3. `mol_silver.purple_book` inherits the fix automatically through its existing passthrough.

### Item 1: Fully unnest every openFDA drug-label field (~1d)

Six distinct field groups, each handled as a sub-task:

**1a. Fix `product_type` bug:**
- In `src/dk_data/sqlmesh/models/molecules/bronze/openfda_labels.sql`, change `label->>'product_type'` to `label->'openfda'->'product_type'->>0`.

**1b. Add 8 missing `openfda` subobject fields:**
- `substance_name`, `product_ndc`, `package_ndc`, `openfda_spl_id`, `pharm_class_pe`, `pharm_class_cs`, `original_packager_product_ndc`, `upc`.
- Arrays projected as `::JSONB`; single-value strings via `->>0`.

**1c. Add 22 Rx label sections:**
- `abuse`, `active_ingredient`, `animal_pharmacology_and_toxicology`, `carcinogenesis_mutagenesis_fertility`, `controlled_substance`, `dea_schedule`, `dependence`, `dosage_forms_and_strengths`, `drug_abuse_and_dependence`, `drug_or_lab_test_interactions`, `inactive_ingredient`, `information_for_patients`, `instructions_for_use`, `labor_and_delivery`, `laboratory_tests`, `microbiology`, `nonclinical_toxicology`, `nonteratogenic_effects`, `precautions`, `pregnancy_or_breast_feeding`, `recent_major_changes`, `label_references`, `teratogenic_effects`.
- All via `label->'<key>'->>0 AS <column_name>`.

**1d. Add 7 OTC label sections:**
- `ask_doctor`, `ask_doctor_or_pharmacist`, `do_not_use`, `keep_out_of_reach_of_children`, `purpose`, `questions`, `stop_use`.

**1e. Add 4 SPL structured sections:**
- `spl_medguide`, `spl_patient_package_insert`, `spl_product_data_elements`, `spl_unclassified_section`.

**1f. Add 14 `_table` JSONB variants:**
- `adverse_reactions_table`, `clinical_pharmacology_table`, `clinical_studies_table`, `description_table`, `dosage_and_administration_table`, `dosage_forms_and_strengths_table`, `drug_interactions_table`, `how_supplied_table`, `instructions_for_use_table`, `pharmacokinetics_table`, `recent_major_changes_table`, `spl_medguide_table`, `spl_patient_package_insert_table`, `spl_unclassified_section_table`.
- All via `label->'<key>'::JSONB AS <column_name>`.

**1g. Silver sync:**
- Update `src/dk_data/sqlmesh/models/molecules/silver/drug_labels.sql` SELECT list to include every new column (one line per column added to bronze).

### Item 2: ATC classifications hierarchy hub (~2d)

**Priority resolution order: DrugBank -> ChEMBL -> KEGG.**

1. Create SQLMesh model `mol_silver.atc_classifications` with columns: `atc_code` (VARCHAR(20) PK), `parent_atc_code` (VARCHAR(20)), `level` (INTEGER 1-5), `description` (TEXT), `source` (TEXT), `last_updated_at` (TIMESTAMPTZ).
2. Parse KEGG `brite` field from `src/dk_data/sqlmesh/models/molecules/bronze/kegg_drug.sql` (`mol_bronze.kegg_drug.raw_json`) -- KEGG publishes full ATC branch with indentation-based hierarchy.
3. Supplement with WHO-CC ATC bulk download (verify license tier).
4. Add `atc_code` (TEXT[]) on `mol_silver.drug_products`, populated by priority resolution: DrugBank -> ChEMBL -> KEGG.
5. Expose recursive CTE helper or `mol_silver.resolve_atc_ancestors()` RPC.
6. Expose via PostgREST (already in `PGRST_DB_SCHEMAS` for `mol_silver`).

---

## Phase 2: Weeks 2-3 -- Medium-Effort Internal Items (P1)

### Item 6: Publication evidence tier (~3d)

**Per-source fallback logic for evidence classification:**

The `evidence_tier` column (VARCHAR(1): A/B/C/D/U) is derived from `publication_type` strings, which vary by source:

- **PubMed:** `publication_type_list` field. Map `Systematic Review`, `Meta-Analysis` -> A; `Randomized Controlled Trial`, `Clinical Trial` -> B; `Observational Study`, `Cohort Study`, `Case-Control Study` -> C; `Case Reports`, `Editorial`, `Comment`, `Letter` -> D; anything else -> U.
- **OpenAlex:** `type` field. Map `review` (if Cochrane) -> A; `article` with RCT keywords -> B; `article` (observational) -> C; `letter`, `editorial` -> D; else -> U.
- **Cochrane:** All Cochrane-sourced records default to A (systematic reviews by definition).
- **Fallback:** Any unclassifiable source/type combination -> U (never NULL).

File: `src/dk_data/sqlmesh/models/molecules/silver/publications.sql` -- add CASE expression computing `evidence_tier`.

### Item 7: FDA designation flags (~3d)

1. Update `src/dk_data/sqlmesh/models/molecules/bronze/fda_drugs.sql` -- add five boolean flags extracted from `submissions` JSONB via `EXISTS` subqueries (SQL snippets from brief section 4, Item 7).
2. Update silver passthrough for `mol_silver.fda_drugs`.
3. Create new bronze source `mol_bronze.fda_orphan_designation` (loader + migration + SQLMesh model).
4. Add unified `has_orphan_designation` BOOLEAN on `mol_silver.drug_products`.

### Item 11: Drug label changes diff table (~1-2d)

1. Create materialized view `mol_silver.drug_label_changes` with section-level diffs between consecutive `(set_id, version)` pairs.
2. Compute at ingest time via post-ingestion hook or materialized view refresh.
3. Expose via PostgREST.

### Item 25: CMS Open Payments expansion (~2d)

**Dispute-filtering default:** Silver rollups MUST filter on `dispute_status_for_publication IS NULL OR dispute_status_for_publication = 'No'` by default. Disputed payments are excluded from competitive-intelligence rollups unless the query explicitly includes them.

1. New migration: add ~60 missing columns to `hcs_raw.cms_open_payments` DDL.
2. Update loader (`src/dk_data/ingestion/sources/cms_open_payments.py` or equivalent) to read all ~91 CMS CSV columns.
3. Extend `hcs_bronze.cms_open_payments` SQLMesh model passthrough.
4. Backfill historical program years (partitioned by `_source_year`).

### Item 26: CMS NPPES expansion (~3d)

**Dispute-filtering default for silver:** Not applicable (NPPES has no dispute concept), but deactivated providers (`npi_deactivation_date IS NOT NULL AND npi_reactivation_date IS NULL`) SHOULD be excluded from active-provider silver rollups by default.

1. New migration: add ~280 missing columns to `hcs_raw.cms_nppes` DDL.
2. Update NPPES loader to parse all ~330 columns from monthly dissemination file.
3. Consider `hcs_raw.cms_nppes_practice_locations` child table for `pl_pfile_<date>.csv`.
4. Extend bronze SQLMesh model passthrough.
5. Add index on `other_provider_identifier_type_code_N` / `other_provider_identifier_N` for DEA-number and state-license joins.
6. Use tray pattern for full backfill (~7M rows).

---

## Phase 3: Weeks 4-5 -- Short New Sources (P2)

### Item 14: EMA PRAC safety signals (~2-3d)

1. New silver model `mol_silver.ema_prac_signals` parsing PRAC records from `mol_bronze.ema` based on `action_type` / `document_type`.
2. Columns: `signal_id`, `drug_name`, `active_substance`, `signal_type`, `signal_date`, `outcome`, `document_url`.
3. Molecule crosswalk.

### Item 15: FDA Drug Shortages (~3d)

1. New fetcher + loader for openFDA Drug Shortages endpoint.
2. New bronze model `mol_bronze.fda_drug_shortages`.
3. Silver crosswalk `mol_silver.fda_drug_shortages` via normalized generic_name.
4. Daily refresh cadence.

### Item 16: FDA Companion Diagnostics (~2d)

1. New scraper for FDA CDx pairing list.
2. New bronze model `mol_bronze.fda_cdx_pairs`.
3. Silver crosswalk to molecules via drug_generic_name.

### Item 27: Other CMS/HRSA loader expansions (~4d)

Four sub-items, each following the same pattern: migration + loader patch + bronze model update.

- **27a.** `hcs_raw.cms_part_d_prescriber` (~18 -> ~25-30 columns): opioid breakouts, antibiotic breakouts, branded-vs-generic splits.
- **27b.** `hcs_raw.cms_hospital_general_info` (~14 -> ~40+ columns): 26+ per-measure quality ratings.
- **27c.** `hcs_raw.cms_physician_puf` (+per-HCPCS line items): new child table `hcs_raw.cms_physician_puf_services`.
- **27d.** `hcs_raw.hrsa` (~9 -> ~20-25 columns): `hpsa_status_code`, provider counts, MUA fields.

---

## Phase 4: Weeks 6+ -- Larger New Source Ingestion (P1 large)

### Item 8: Treatment guidelines feed (~2wk)

**Quarterly maintenance cadence:** After initial curation, guidelines are reviewed quarterly for new editions. Automated scraping is added for bodies with predictable PDF/HTML formats; others remain manual curation.

1. New bronze model `mol_bronze.guidelines` with structured fields: `id`, `body`, `title`, `publication_date`, `version`, `indication_icd11`, `indication_name`, `source_url`, `full_text`, `sections` (JSONB), `recommendations` (JSONB).
2. Initial ingestion: manual curation of top 10-15 guidelines per therapeutic area.
3. Target bodies: AAD, ACR, EADV, GINA, GOLD, NCCN, ESMO, ASCO.
4. Silver layer `mol_silver.guidelines` with molecule and condition crosswalks.
5. Quarterly review cadence for updates; automated scraping where feasible.

### Item 10: EMA SmPC parser (~2wk)

1. PDF parser for EMA SmPC canonical section structure (4.1-5.3 mapping to FDA-equivalent column names).
2. New silver model `mol_silver.drug_labels_ema` with same column structure as `mol_silver.drug_labels`.
3. Crosswalk to molecules via `mol_silver.ema_regulatory` linkage.
4. Validation: >= 90% section-header accuracy on 50-SmPC validation set.

### Item 28: IP patent/trademark loader expansions (~1wk)

Four sub-items, each following: migration + loader patch + bronze model update + new silver views.

- **28a.** `ip_raw.uspto_patents` (~10 -> ~50 columns): citations, continuity, claims text, assignment history, family members.
- **28b.** `ip_raw.epo_patents` (~9 -> ~35 columns): priority claims, family members, legal status events, designated states.
- **28c.** `ip_raw.uspto_trademarks` (~15 -> ~40 columns): case-file statements, oppositions, assignments, prosecution history.
- **28d.** `ip_raw.euipo_trademarks` (~15 -> ~35 columns): oppositions, cancellations, seniorities, priority claims, Vienna codes.

New silver views: `ip_silver.patent_families`, `ip_silver.patent_citations`, `ip_silver.trademark_oppositions`.

Deeply nested fields (citations, family members, assignment events) preserved as JSONB arrays at raw, matching the molecules-domain pattern.

### Item 9: FDA enforcement actions (~1mo)

Five new bronze sources (one week each):
1. `mol_bronze.fda_warning_letters`
2. `mol_bronze.fda_untitled_letters`
3. `mol_bronze.fda_483_observations`
4. `mol_bronze.fda_dear_hcp_letters`
5. `mol_bronze.fda_crls`

Each with silver crosswalk to molecules via normalized generic_name / brand_name matching.

### Item 13: Conference abstracts feed (~4wk)

**Embargo-aware publication timing:** `embargo_date` and `publication_date` are tracked as distinct fields. Rules fire on `publication_date` only. Embargoed abstracts MUST NOT appear in the rules engine context bag until `publication_date`. The silver model filters: `WHERE publication_date <= CURRENT_DATE OR publication_date IS NULL`.

1. New bronze source `mol_bronze.conference_abstracts` with embargo tracking.
2. Scrape top 10-15 conference programs: AAD, EADV, ACR, EULAR, ATS, AAAAI, ERS, ASCO, ESMO, ASH, AHA, ESC, ADA, EASD, DDW, UEGW.
3. Silver layer `mol_silver.conference_abstracts` with molecule and condition crosswalks.
4. Embargo filter in silver model prevents premature visibility.

---

## Phase 5: Polish

1. **PostgREST grants:** Verify all new silver/gold models are in `PGRST_DB_SCHEMAS` and have `SELECT` grants for the PostgREST role. Explicitly test each new endpoint.
2. **Post-audit queries:** Run the post-audit query from Item 1 (`SELECT jsonb_object_keys(raw_json) EXCEPT (projected_columns)`) to verify zero documented openFDA keys remain unprojected.
3. **E2E validation:** Execute every acceptance scenario from the spec against production data. Confirm row counts, specific drug lookups (Dupilumab, hydrocodone, aspirin), ATC hierarchy walks, evidence tier distribution, designation flags, shortage list, CDx pairs.
4. **Adapter cleanup:** Notify `behavior-labs-ai` team that Items 1/24 have shipped so `@repo/claims-response-dk-adapter` can remove `raw_json` JSONB-parse workarounds.

---

## Blocked Items (Not in Scope)

- **Item 18:** MedDRA hierarchy (LLT/HLT/HLGT) -- permanently blocked on MSSO license. SOC-level scoping via `mol_silver.adverse_events.meddra_soc` covers most needs.
- **Items 19-23:** Commercial contracts (IQVIA, Symphony, MMIT, Pathmatics, Optum). Not engineering problems.

---

## Risk Mitigations

| Risk | Mitigation |
|------|------------|
| WAL spike during NPPES/Open Payments backfill | Tray pattern with chunked loads; WAL accounting to `meta.transform_runs` |
| Purple Book API response shape changes | SQLMesh audit `row_count_at_least(1000)` catches silent regressions |
| WHO-CC ATC license restriction | Start with KEGG-only ATC tree; WHO-CC is supplementary |
| EMA SmPC PDF parsing accuracy | Validation set of 50 SmPCs; >= 90% section-header accuracy gate |
| Conference abstract embargo leakage | Silver model `WHERE publication_date <= CURRENT_DATE` filter enforced |
| Disputed CMS Open Payments in silver rollups | Default filter: `dispute_status_for_publication IS NULL OR = 'No'` |
