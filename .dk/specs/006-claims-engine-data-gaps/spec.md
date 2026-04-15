# Feature: claims-engine-data-gaps

## Summary

Close all remaining data gaps in `dk-data-FE` that prevent the Claims Response Rules Engine (shipped as `@repo/claims-response` in `behavior-labs-ai`) from expressing the full rule-authoring surface defined in the source Dupixent seed ruleset. The engine currently covers ~80% of rule classes against dk-data as-is; this feature closes the remaining ~20%.

The work spans three tiers:

- **Tier 1 (days each):** Internal engineering items where source data exists in bronze/raw but is not yet silverized or fully unnested. Includes Items 1, 2, 6, 7, 11, 18, 24, 25, 26, 27, 28.
- **Tier 2 (weeks each):** New source ingestion where dk-data has no feed at all. Includes Items 8, 9, 10, 13, 14, 15, 16.
- **Tier 3 (contract-blocked):** Commercial data sources requiring business contracts (IQVIA, Symphony, Pathmatics, MMIT, etc.). Items 19-23 are tracked but out of scope for engineering.

Closed/merged items retained for traceability: Items 3, 4, 5, 12, 17.

Priority order by rule impact per engineering-day:
1. **Item 24 (P0 hotfix, ~0.5d)** -- Fix `mol_bronze.purple_book` which silently produces 0 rows
2. **Item 1 (P0, ~1d)** -- Exhaustively unnest every openFDA drug-label field into typed bronze columns
3. **Item 2 (P0, ~2d)** -- ATC classifications hierarchy hub

These three items ship in under a week and unblock ~85% of rule classes.

---

## Context: How the Rules Engine Consumes dk-data

The Claims Response Rules Engine is a pure TypeScript evaluator shipped as `@repo/claims-response` in `behavior-labs-ai`. It is consumed from `apps/api` inside a BullMQ worker that runs on every new `CIAlert` (competitive intelligence alert). The adapter package `@repo/claims-response-dk-adapter` handles all dk-data I/O.

### 12-Query Per-Alert Adapter Pattern

For each `CIAlert`, the adapter makes ~12 dk-data calls:

1. **`POST /data-platform/molecules/resolve`** -- resolve the competitor text mention to molecule UUID + canonical name + aliases + ATC + modality + biosimilar status + targets.
2. **`POST /data-platform/molecules/resolve`** -- resolve the defended brand (cached per org-brand).
3. **`POST /data-platform/conditions/resolve`** -- resolve indication text to condition UUID + ICD-11 + ICD-10 + MedDRA PT + therapeutic_area + MeSH descriptor.
4. **`GET /rest/drug_labels?molecule_id=eq.<uuid>&order=effective_date.desc&limit=1`** with `Accept-Profile: mol_silver` -- competitor's most recent label. Until Item 1 ships, the adapter parses fields from `raw_json` via JSONB helpers (e.g., `raw_json->'openfda'->'dea_schedule'`, `raw_json->'recent_major_changes'->>0`). After Item 1, every openFDA field is a typed silver column.
5. **Same drug_labels query** for the defended brand (cached).
6. **`GET /rest/adverse_events?molecule_id=eq.<uuid>&meddra_soc=in.(...)`** -- FAERS events.
7. **`GET /rest/safety_signals?molecule_id=eq.<uuid>`** with `Accept-Profile: mol_gold` -- PRR/ROR/IC disproportionality (weekly cron refresh).
8. **`GET /rest/publication_evidence?molecule_id=eq.<uuid>&confidence_score=gte.0.6`** -- extracted endpoints.
9. **`GET /rest/rems_programs?molecule_id=eq.<uuid>`** -- REMS data.
10. **`GET /rest/pharmacogenomics?molecule_id=eq.<uuid>`** -- PGx annotations.
11. **`GET /rest/patents?molecule_id=eq.<uuid>&status=eq.active`** -- patent status.
12. **`GET /rest/nice_hta?molecule_id=eq.<uuid>`** and **`GET /rest/regulatory_decisions?drug_name=eq.<name>`** -- HTA decisions.

### Latency Expectations

- Resolve RPCs: target of 10ms p99 or less (SC-004).
- All other queries are single-row or small-result SELECTs with indexed WHERE clauses.
- Total per-alert cost: typically < 100ms when all queries are warm.

### Caching Strategy (24h TTL)

- Defended-brand metadata and labels: cached per `(organizationId, brandId)` at the Redis layer in `behavior-labs-ai`.
- Competitor metadata: cached per-molecule with 24h TTL.
- Safety signals and label sections: NOT cached (engine wants fresh data on every alert).

### Empty-Context-Bag Fallback

When dk-data is unreachable, the adapter falls back to an empty context bag. The rules engine returns `used_default_path: true` and the alert proceeds with LLM-only classification. Observability in `apps/api` logs dk-data latency and errors as OpenTelemetry attributes.

### Refresh Cadences

Silver tables are refreshed on their current SQLMesh cron cadences. The rules engine team is satisfied with these cadences as long as PostgREST remains available.

---

## User Scenarios and Testing

### US-01: Full openFDA label field availability (Item 1)

**As a** rule author, **I want** every openFDA drug-label field available as a typed silver column **so that** I never need to parse `raw_json` for a field the API documents.

**Acceptance scenario:**
- Query `mol_silver.drug_labels` for Dupilumab (BLA 761055): `product_type = 'HUMAN PRESCRIPTION DRUG'` (confirming the `product_type` bug fix from `openfda` subobject), `substance_name = 'DUPILUMAB'`, non-null `product_ndc` and `package_ndc` JSONB arrays, `pharm_class_cs` contains `'Antibodies, Monoclonal [CS]'`, non-null `openfda_spl_id`.
- `adverse_reactions_table` has >= 8 entries, `clinical_studies_table` has >= 30 entries, `instructions_for_use_table` has >= 20 entries for Dupilumab.
- Query for a Schedule II opioid (e.g., hydrocodone): `dea_schedule = 'CII'`, non-null `abuse`, `dependence`, `drug_abuse_and_dependence`, `controlled_substance`.
- Query for an OTC product (e.g., aspirin): non-null `purpose`, `ask_doctor`, `do_not_use`, `keep_out_of_reach_of_children`, `stop_use`.
- At least one drug has non-null `pharm_class_pe`.
- A drug with a recent label revision has non-null `recent_major_changes` and `recent_major_changes_table`.
- Post-audit: `SELECT jsonb_object_keys(raw_json) EXCEPT (projected_columns)` returns only undocumented or internal openFDA metadata keys.

### US-02: ATC hierarchy walking (Item 2)

**As a** rule author, **I want** to scope rules to "any drug whose ATC code is under D11 (dermatologicals)" **so that** therapeutic-class rules work with `within_hierarchy` operators.

**Acceptance scenario:**
- `mol_silver.atc_classifications` exists with ~6,500 rows.
- For `atc_code = 'D11AH05'` (dupilumab), walking `parent_atc_code` returns `D11AH` -> `D11A` -> `D11` -> `D`.
- `mol_silver.drug_products.atc_code` is populated for a nontrivial fraction of rows.
- PostgREST exposes `/atc_classifications` as a readable endpoint.

### US-03: Publication evidence tiers (Item 6)

**As a** rule author, **I want** a canonical `evidence_tier` column on publications **so that** methodology-triage rules do not reinvent the classification logic inline.

**Acceptance scenario:**
- `mol_silver.publications.evidence_tier` is populated for >= 95% of rows.
- A Cochrane review has `evidence_tier = 'A'`.
- A case report has `evidence_tier = 'D'`.
- An unclassifiable publication has `evidence_tier = 'U'`, not NULL.

### US-04: FDA designation flags (Item 7)

**As a** rule author, **I want** boolean designation flags on `mol_silver.fda_drugs` **so that** accelerated-pathway and rare-disease rules are expressible as `is_accelerated_approval = TRUE`.

**Acceptance scenario:**
- `mol_bronze.fda_drugs` / `mol_silver.fda_drugs` expose `is_priority_review`, `is_orphan_designation`, `is_breakthrough_designation`, `is_fast_track`, `is_accelerated_approval` as booleans.
- `mol_bronze.fda_orphan_designation` exists with >= 500 rows from the FDA Orphan Drug Designation database.
- `mol_silver.drug_products.has_orphan_designation = TRUE` for a known small-molecule orphan drug (via new bronze source).
- `mol_silver.drug_products.has_orphan_designation = TRUE` for a known biologic orphan drug (via existing Purple Book linkage).
- A known Breakthrough-designated drug has `is_breakthrough_designation = TRUE`.

### US-05: Treatment guidelines (Item 8)

**As a** rule author, **I want** structured treatment guidelines from AAD/ACR/EADV/GINA/GOLD/NCCN/ESMO/ASCO **so that** guideline-anchored rules work as structured rules rather than text-match fallbacks.

**Acceptance scenario:**
- `mol_silver.guidelines` exists with >= 50 guidelines.
- AAD, ACR, GINA, and NCCN are each represented.
- Each guideline has a parseable `sections` JSONB with individual recommendations.
- Crosswalk to molecules works for a sample query.

### US-06: FDA enforcement actions (Item 9)

**As a** rule author, **I want** Warning Letters, Untitled Letters, 483s, Dear HCP letters, and CRLs ingested **so that** enforcement-action rules fire when a competitor receives an FDA Warning Letter.

**Acceptance scenario:**
- Five bronze sources exist with >= 100 rows each.
- Each has a molecule crosswalk covering >= 50% of rows with drug mentions.
- A known recent Warning Letter for a specific drug appears and resolves to the correct molecule.

### US-07: EMA SmPC sections (Item 10)

**As a** rule author, **I want** structured EMA SmPC section text **so that** EU-jurisdictional label-section rules are expressible.

**Acceptance scenario:**
- `mol_silver.drug_labels_ema` exists with >= 500 SmPCs parsed.
- For Dupixent's EU SmPC, expected sections (4.1 through 5.3) are parsed and non-null.
- Parsing quality: >= 90% of section headers correctly identified on a validation set of 50 SmPCs.

### US-08: Drug label changes (Item 11)

**As a** rule author, **I want** a precomputed section-level diff surface **so that** label-change detection works for changes FDA does not flag in `recent_major_changes`.

**Acceptance scenario:**
- `mol_silver.drug_label_changes` exists with >= 1 row per (set_id, version) pair that has a predecessor.
- For a label with a known boxed-warning change: `section_name = 'boxed_warning'` and `change_type = 'modified'`.

### US-09: Conference abstracts (Item 13)

**As a** rule author, **I want** real-time conference abstract data **so that** competitive-intel rules fire on conference publication day rather than waiting 6-18 months for PubMed indexing.

**Acceptance scenario:**
- `mol_silver.conference_abstracts` exists with >= 500 abstracts across >= 5 conferences.
- A known AAD late-breaking abstract appears with correct `embargo_date` and `publication_date` (tracked distinctly).
- Molecule crosswalk works for abstracts mentioning specific drugs.

**Edge case:** `embargo_date` and `publication_date` must be tracked as distinct fields. Rules fire on `publication_date`, not `embargo_date`. Embargoed abstracts must not appear in the rules engine context bag until `publication_date`.

### US-10: EMA PRAC safety signals (Item 14)

**As a** rule author, **I want** EMA post-market safety signals separated from approval decisions **so that** EU post-market safety rules are expressible.

**Acceptance scenario:**
- Separate silver surface for PRAC signals with >= 50 rows.
- A known EMA safety review for a specific drug appears in the feed.

### US-11: FDA drug shortages (Item 15)

**As a** rule author, **I want** the FDA shortage list ingested **so that** supply-positioning rules fire when a competitor's drug is on the shortage list.

**Acceptance scenario:**
- `mol_silver.fda_drug_shortages` exists with the current shortage list.
- A known active shortage appears with correct status and start date.

### US-12: FDA companion diagnostics (Item 16)

**As a** rule author, **I want** the FDA CDx pairing list **so that** biomarker-gated rules frame a broader label advantage.

**Acceptance scenario:**
- `mol_bronze.fda_cdx_pairs` exists with >= 50 rows.
- A known CDx pair (e.g., any FDA-approved targeted therapy with a required IVD) appears.

### US-13: Purple Book fix (Item 24)

**As a** rule author, **I want** `mol_bronze.purple_book` to actually produce rows **so that** every biosimilar / interchangeable / orphan-exclusivity rule reads real data instead of empty sets.

**Acceptance scenario:**
- `SELECT COUNT(*) FROM mol_bronze.purple_book` returns >= 1,000 rows.
- Dupilumab (BLA 761055) has a row with `brand_name = 'Dupixent'`, `license_type = 'BLA'`, non-null `applicant`.
- A known biosimilar (e.g., a Humira biosimilar BLA) has `is_biosimilar = TRUE` and populated `reference_product_name`.
- `mol_silver.purple_book` inherits the fix automatically through the existing passthrough.
- A new SQLMesh audit (`row_count_at_least(1000)` or equivalent) catches future regressions.

**Edge case:** The Purple Book fix must filter on `license_type = 'BLA'` (or application number starting with `BLA`). The upstream Drugs@FDA API returns all application types; only BLA records belong in the Purple Book view.

### US-14: CMS Open Payments expansion (Item 25)

**As a** rule author, **I want** all ~91 CMS Sunshine Act columns loaded **so that** dispute-aware rollups, KOL NPI linkage, and teaching-hospital attribution are possible.

**Acceptance scenario:**
- `hcs_raw.cms_open_payments` has >= 85 columns.
- Every column the CMS public CSV publishes for program year 2023 is loaded for at least one row.
- `physician_npi` populated for all physician-recipient rows.
- `teaching_hospital_ccn` populated for all teaching-hospital-recipient rows.
- `dispute_status_for_publication` loaded and used to filter silver rollups by default.

### US-15: CMS NPPES expansion (Item 26)

**As a** rule author, **I want** all ~330 NPPES columns loaded **so that** provider entity-linkage, multi-taxonomy physician rules, and deactivated-provider filters work.

**Acceptance scenario:**
- `hcs_raw.cms_nppes` has >= 300 columns.
- A physician with 5+ board certifications has `healthcare_provider_taxonomy_code_5` populated.
- A physician with a DEA number has it visible via `other_provider_identifier_type_code_N = '05'`.
- Practice-location address fields are non-null for every active provider.
- `last_update_date` is loaded and exposed for change-detection.

### US-16: Other CMS/HRSA loader expansions (Item 27)

**As a** rule author, **I want** the remaining CMS and HRSA loader gaps closed **so that** opioid prescribing breakouts, per-measure quality ratings, per-HCPCS line items, and provider-shortage fields are available.

**Acceptance scenario:**
- `hcs_raw.cms_part_d_prescriber` column count >= 25.
- `hcs_raw.cms_hospital_general_info` carries at least 20 per-measure quality rating columns.
- `hcs_raw.cms_physician_puf` has per-HCPCS line items (new child table `hcs_raw.cms_physician_puf_services` acceptable).
- `hcs_raw.hrsa` has `hpsa_status_code`, `provider_count`, `primary_care_physician_count` columns.

### US-17: IP patent/trademark loader expansions (Item 28)

**As a** rule author, **I want** patent citations, family members, continuity chains, oppositions, cancellations, priority claims, and assignment events loaded **so that** patent-family, prior-art, opposition-in-flight, and assignment-change rules are expressible.

**Acceptance scenario:**
- `ip_raw.uspto_patents` has `cited_patents`, `citing_patents`, `parent_application`, `claims_full_text` populated.
- `ip_raw.epo_patents` has `family_members`, `priority_claims`, `legal_status_events` populated.
- `ip_raw.uspto_trademarks` has `case_file_statements`, `oppositions`, `assignments` populated.
- `ip_raw.euipo_trademarks` has `oppositions`, `cancellations`, `seniorities` populated.
- Bronze models pass through every new column; new silver views exist for `ip_silver.patent_families`, `ip_silver.patent_citations`, `ip_silver.trademark_oppositions`.
- A known patent family (e.g., the dupilumab composition-of-matter family) returns every member patent through `ip_silver.patent_families`.

---

## Requirements

### FR-001: Fix `mol_bronze.purple_book` silent 0-row regression (Item 24)

**Priority:** P0 (hotfix). **Effort:** ~0.5 day.

The SQLMesh model iterates `response_body->'_normalized_products'` which does not exist. The Purple Book fetcher stores raw openFDA Drugs@FDA responses unchanged; no `_normalized_products` transformation is applied. The upstream API returns records under `results[*]` with fields at the top level.

**Requirements:**
1. Rewrite the bronze `FROM` clause to iterate over `response_body->'results'`, unnesting `app->'products'` to get one row per product.
2. Filter to `license_type = 'BLA'` or application numbers starting with `BLA` (Purple Book is a BLA-only subset of Drugs@FDA).
3. Add a SQLMesh audit `row_count_at_least(1000)` to prevent future silent regressions.
4. `mol_silver.purple_book` inherits the fix automatically through the existing passthrough.

### FR-002: Fully unnest every openFDA drug-label field (Item 1)

**Priority:** P0. **Effort:** ~1 day.

**Design principle:** Nothing in the openFDA drug-label JSON response should remain nested in bronze. Every key of the `openfda` metadata subobject and every top-level label-section key the API can return must be projected as a typed bronze column.

**Requirements:**
1. Fix the `product_type` bug: change `label->>'product_type'` to `label->'openfda'->'product_type'->>0`.
2. Add 8 missing `openfda` subobject fields (see Appendix A: Table A1).
3. Add 22 missing Rx label sections (see Appendix A: Table A2).
4. Add 7 missing OTC label sections (see Appendix A: Table A3).
5. Add 4 missing SPL structured sections (see Appendix A: Table A4).
6. Add 14 `_table` JSONB variants (see Appendix A: Table A5). These are arrays of HTML-fragment strings; preserve as JSONB.
7. Sync `mol_silver.drug_labels` SELECT list to include every new column (one line per column).

**Not gaps (do not re-add):**
- `renal_impairment` and `hepatic_impairment` are NOT distinct top-level openFDA fields. Their content lives inside `use_in_specific_populations`, which is already extracted. Rules scope on `use_in_specific_populations` directly.

### FR-003: ATC classifications hierarchy hub (Item 2)

**Priority:** P0. **Effort:** ~2 days.

**Requirements:**
1. Create `mol_silver.atc_classifications` with columns: `atc_code` (VARCHAR(20) PK), `parent_atc_code` (VARCHAR(20)), `level` (INTEGER 1-5), `description` (TEXT), `source` (TEXT -- `'kegg'` | `'who_cc'`), `last_updated_at` (TIMESTAMPTZ).
2. Populate from KEGG `brite` field (`mol_bronze.kegg_drug.raw_json`) and supplement with WHO-CC ATC bulk download.
3. Add `atc_code` column (TEXT[]) on `mol_silver.drug_products`, populated by priority resolution: DrugBank -> ChEMBL -> KEGG.
4. Expose recursive CTE helper or `mol_silver.resolve_atc_ancestors()` RPC.
5. Expose via PostgREST.

### FR-004: Publication evidence tier (Item 6)

**Priority:** P1. **Effort:** ~3 days.

**Requirements:**
1. Add derived column `evidence_tier` (VARCHAR(1) -- `A`/`B`/`C`/`D`/`U`) to `mol_silver.publications`.
2. Classification rules (Oxford CEBM-inspired):
   - `A` -- systematic reviews / meta-analyses of RCTs, Cochrane reviews
   - `B` -- individual RCTs, non-randomized controlled trials
   - `C` -- observational studies (cohort, case-control), real-world evidence
   - `D` -- case series, case reports, expert opinion, editorials
   - `U` -- unknown / unclassifiable
3. Map from `publication_type` strings (varies by source: PubMed, OpenAlex, Cochrane) with fallbacks per source.
4. Fixture tests: 50 publications per tier covering each source.

### FR-005: FDA designation flags (Item 7)

**Priority:** P1. **Effort:** ~3 days.

**Requirements:**
1. Update `mol_bronze.fda_drugs` to extract five boolean flags from `submissions` JSONB array via `EXISTS` subqueries: `is_priority_review`, `is_orphan_designation`, `is_breakthrough_designation`, `is_fast_track`, `is_accelerated_approval`.
2. Update `mol_silver.fda_drugs` passthrough to include the five flags.
3. Create new bronze source `mol_bronze.fda_orphan_designation` from the FDA Orphan Drug Designation database with columns: `designation_number` (TEXT), `generic_name` (TEXT), `trade_name` (TEXT), `sponsor` (TEXT), `designation_date` (DATE), `designated_indication` (TEXT), `marketing_approval_date` (DATE, nullable).
4. Add unified `has_orphan_designation` BOOLEAN on `mol_silver.drug_products` combining Purple Book `orphan_exclusivity_end IS NOT NULL` (biologics) with `mol_bronze.fda_orphan_designation` linkage (small molecules).

### FR-006: Treatment guidelines feed (Item 8)

**Priority:** P0 (single largest functionality gap). **Effort:** ~2 weeks initial + ongoing.

**Requirements:**
1. Create `mol_bronze.guidelines` with columns: `id` (UUID), `body` (TEXT -- e.g., `'AAD'`), `title` (TEXT), `publication_date` (DATE), `version` (TEXT), `indication_icd11` (TEXT), `indication_name` (TEXT), `source_url` (TEXT), `full_text` (TEXT -- parsed PDF), `sections` (JSONB -- structured sections with recommendations), `recommendations` (JSONB -- individual graded recommendations with strength and evidence quality).
2. Initial ingestion: manual curation of top 10-15 guideline bodies per therapeutic area.
3. Silver layer `mol_silver.guidelines` with crosswalks to molecules and indications.
4. Ongoing maintenance cadence: quarterly manual review, automated scraping where feasible.
5. Target bodies: AAD, ACR, EADV, GINA, GOLD, NCCN, ESMO, ASCO.

### FR-007: FDA enforcement actions (Item 9)

**Priority:** P0. **Effort:** ~1 month (1 week per source).

**Requirements -- five new bronze sources:**

1. **`mol_bronze.fda_warning_letters`**: `letter_id`, `letter_date`, `company_name`, `company_address`, `subject`, `issuing_office`, `response_letter_url`, `closeout_letter_url`, `full_text`, `drug_mentions` (JSONB).
2. **`mol_bronze.fda_untitled_letters`**: same structure as warning letters.
3. **`mol_bronze.fda_483_observations`**: `observation_id`, `inspection_date`, `company_name`, `facility`, `observations` (JSONB), `full_text`.
4. **`mol_bronze.fda_dear_hcp_letters`**: Dear Healthcare Provider letters from FDA Drug Safety Communications.
5. **`mol_bronze.fda_crls`**: Complete Response Letters where publicly disclosed (via 8-K filings or FOIA).

Each feed gets its own silver crosswalk to molecules via normalized generic_name / brand_name matching.

**Partial mitigation note:** `mol_silver.web_content` (columns: `id`, `molecule_id`, `search_query`, `search_engine`, `search_type`, `result_url`, `result_title`, `result_snippet`, `result_rank`, `result_domain`, `publication_date`, `authors`, `source_name`, `relevance_score`, `source`, `ingested_at`, `created_at`) partially mitigates enforcement-action coverage for news-based enforcement mentions, but does not replace structured ingestion of the actual FDA enforcement databases.

### FR-008: EMA SmPC parser (Item 10)

**Priority:** P0 for EU-scoped rules. **Effort:** ~2 weeks.

**Requirements:**
1. Create `mol_silver.drug_labels_ema` with the same column structure as `mol_silver.drug_labels`, sourced from EMA SmPC PDFs.
2. PDF parser mapping EMA SmPC sections to FDA-equivalent columns:
   - 4.1 Therapeutic indications -> `indications_and_usage`
   - 4.2 Posology and method of administration -> `dosage_and_administration`
   - 4.3 Contraindications -> `contraindications`
   - 4.4 Special warnings and precautions -> `warnings_and_cautions`
   - 4.5 Interaction with other medicinal products -> `drug_interactions`
   - 4.6 Fertility, pregnancy and lactation -> `pregnancy` + `nursing_mothers`
   - 4.7 Effects on ability to drive and use machines -> `use_in_specific_populations`
   - 4.8 Undesirable effects -> `adverse_reactions`
   - 4.9 Overdose -> `overdosage`
   - 5.1 Pharmacodynamic properties -> `pharmacodynamics`
   - 5.2 Pharmacokinetic properties -> `pharmacokinetics`
   - 5.3 Preclinical safety data -> `nonclinical_toxicology`
3. Crosswalk to molecules via `mol_silver.ema_regulatory` linkage.

**Important note:** `ema_regulatory_docs.summary` contains document metadata (brief synopsis), NOT parsed SmPC text. It does NOT mitigate this item.

### FR-009: Drug label changes diff table (Item 11)

**Priority:** P2. **Effort:** ~1-2 days.

**Requirements:**
1. Create materialized view `mol_silver.drug_label_changes` with columns: `set_id` (TEXT), `from_version` (INTEGER), `to_version` (INTEGER), `section_name` (TEXT), `change_type` (TEXT -- `'added'` | `'removed'` | `'modified'`), `diff_text` (TEXT), `detected_at` (TIMESTAMPTZ).
2. Compute diffs at ingest time when a new label version lands.
3. Expose via PostgREST.

### FR-010: Conference abstracts feed (Item 13)

**Priority:** P1. **Effort:** ~4 weeks.

**Requirements:**
1. Create `mol_bronze.conference_abstracts` with columns: `abstract_id` (TEXT), `conference_name` (TEXT), `conference_body` (TEXT), `conference_date` (DATE), `presentation_date` (DATE), `presentation_type` (TEXT -- oral, poster, late-breaking), `title` (TEXT), `authors` (JSONB), `affiliations` (JSONB), `abstract_text` (TEXT), `embargo_date` (DATE), `publication_date` (DATE), `session_title` (TEXT), `track` (TEXT), `source_url` (TEXT).
2. Scrape top 10-15 conference programs: AAD, EADV (Dermatology); ACR, EULAR (Rheumatology); ATS, AAAAI, ERS, ESMO (Respiratory/Allergy); DDW, UEGW (Gastroenterology); ASCO, ESMO, ASH (Oncology); AHA, ESC (Cardiology); ADA, EASD (Endocrinology).
3. Silver layer `mol_silver.conference_abstracts` with molecule and condition crosswalks.

**Edge case:** `embargo_date` vs `publication_date` must be tracked distinctly. Rules fire on `publication_date`. Embargoed abstracts must not appear in the rules engine context bag until `publication_date`.

**Partial mitigation note:** `mol_silver.web_content` partially mitigates web-scraped conference abstract coverage but does not replace dedicated structured ingestion with embargo tracking.

### FR-011: EMA PRAC safety signals split (Item 14)

**Priority:** P2. **Effort:** ~2-3 days.

**Requirements:**
1. Create `mol_silver.ema_prac_signals` with columns: `signal_id`, `drug_name`, `active_substance`, `signal_type` (e.g., `'periodic safety update'`, `'referral'`, `'safety review'`), `signal_date`, `outcome`, `document_url`.
2. Parse from `mol_bronze.ema` based on `action_type` / `document_type` field.
3. Crosswalk to molecules.

### FR-012: FDA Drug Shortages (Item 15)

**Priority:** P2. **Effort:** ~3 days.

**Requirements:**
1. Create `mol_bronze.fda_drug_shortages` with columns: `shortage_id` (TEXT), `generic_name` (TEXT), `brand_name` (TEXT), `company` (TEXT), `status` (TEXT -- `'Currently in Shortage'` | `'Resolved'`), `shortage_reason` (TEXT), `shortage_start_date` (DATE), `shortage_end_date` (DATE, nullable), `affected_products` (JSONB), `notes` (TEXT).
2. Silver crosswalk to molecules via normalized generic_name.
3. Daily refresh cadence.

### FR-013: FDA Companion Diagnostics list (Item 16)

**Priority:** P2. **Effort:** ~2 days.

**Requirements:**
1. Create `mol_bronze.fda_cdx_pairs` with columns: `cdx_id` (TEXT), `device_name` (TEXT), `manufacturer` (TEXT), `intended_use` (TEXT), `drug_trade_name` (TEXT), `drug_generic_name` (TEXT), `approval_date` (DATE), `submission_type` (TEXT -- PMA, 510(k), De Novo), `source_url` (TEXT).
2. Silver crosswalk to molecules via drug_generic_name.

### FR-014: MedDRA hierarchy depth (Item 18)

**Priority:** P3. **Effort:** Depends on MSSO license. **Status:** Permanently blocked.

dk-data does NOT hold a MedDRA license. `soc_distribution` in `mol_gold.safety_signals` is NULL by design. This item is permanently blocked unless a license is procured. SOC-level scoping via `mol_silver.adverse_events.meddra_soc` covers most safety-signal rule needs.

### FR-015: CMS Open Payments loader expansion (Item 25)

**Priority:** P1. **Effort:** ~2 days.

**Requirements:**
1. Add missing columns to DDL via new migration.
2. Update loader to read every column the public CSV publishes (~91 total).
3. Extend bronze SQLMesh model passthrough.
4. Re-run backfill for historical program years.

**Missing columns by category (see Appendix B: Table B1 for full list):**
- **Physician identity:** `physician_npi`, `physician_middle_name`, `physician_name_suffix`, `physician_primary_type`, `physician_specialty_2`
- **Teaching hospitals:** `teaching_hospital_ccn`, `teaching_hospital_id`, `teaching_hospital_name`
- **Recipient geography:** `recipient_country`, `recipient_primary_business_street_address_line_1`, `recipient_primary_business_street_address_line_2`, `recipient_postal_code`, `recipient_province`
- **Publication/dispute metadata:** `dispute_status_for_publication`, `delay_in_publication_indicator`, `change_type` (NEW/ADD/CHANGE), `payment_publication_date`
- **Manufacturer identity:** `applicable_manufacturer_or_applicable_gpo_making_payment_id`, `applicable_manufacturer_or_applicable_gpo_making_payment_state`, `applicable_manufacturer_or_applicable_gpo_making_payment_country`
- **Product category/indication slots:** `product_category_or_therapeutic_area_1..5`, `product_indication_1..5`
- **Travel details:** `city_of_travel`, `state_of_travel`, `country_of_travel`
- **Flags:** `physician_ownership_indicator`, `third_party_payment_recipient_indicator`, `charity_indicator`, `contextual_information`

### FR-016: CMS NPPES loader expansion (Item 26)

**Priority:** P1. **Effort:** ~3 days.

**Requirements:**
1. Add all missing columns to DDL via new migration.
2. Update NPPES loader to parse every column from the monthly dissemination file.
3. Consider ingesting `pl_pfile_<date>.csv` (secondary practice locations) as `hcs_raw.cms_nppes_practice_locations`.
4. Extend bronze SQLMesh model passthrough.
5. Add index on `other_provider_identifier_type_code_N` / `other_provider_identifier_N` for DEA-number and state-license joins.

**Missing columns by category (see Appendix B: Table B2 for full list):**
- **Taxonomies 3-15:** `healthcare_provider_taxonomy_code_3..15`, `healthcare_provider_primary_taxonomy_switch_3..15`, `provider_license_number_3..15`, `provider_license_number_state_code_3..15` (4 columns x 13 slots = 52 columns)
- **Other provider identifiers 1-50:** `other_provider_identifier_1..50`, `other_provider_identifier_type_code_1..50`, `other_provider_identifier_state_1..50`, `other_provider_identifier_issuer_1..50` (4 columns x 50 slots = 200 columns)
- **Practice location addresses:** `provider_first_line_business_practice_location_address`, `provider_business_practice_location_address_city_name`, and corresponding state, postal code, country, telephone, fax fields for both mailing and practice locations
- **Authorized official details:** `authorized_official_last_name`, `authorized_official_first_name`, `authorized_official_title_or_position`, `authorized_official_telephone_number`, `authorized_official_name_prefix_text`, `authorized_official_name_suffix_text`, `authorized_official_credential_text`
- **Deactivation/reactivation:** `npi_deactivation_reason_code`, `npi_deactivation_date`, `npi_reactivation_date`
- **Entity-type-specific:** `is_sole_proprietor`, `is_organization_subpart`, `parent_organization_lbn`, `parent_organization_tin`
- **Other:** `last_update_date`, `certification_date`

### FR-017: Other CMS/HRSA loader expansions (Item 27)

**Priority:** P2. **Effort:** ~4 days total (~1 day each).

**27a. `hcs_raw.cms_part_d_prescriber`** (~18 -> ~25-30 columns)
Missing: `opioid_prescriber_rate`, `opioid_day_supply`, `long_acting_opioid_*`, antibiotic breakouts, branded-vs-generic splits per beneficiary cohort, beneficiary-demographic splits.

**27b. `hcs_raw.cms_hospital_general_info`** (~14 -> ~40+ columns)
Missing: 26+ per-measure quality ratings (mortality for heart attack/heart failure/pneumonia/stroke/COPD, readmission rates, safety-of-care rating, patient-experience rating, timeliness-of-care rating, efficient-use-of-imaging rating, healthcare-associated-infection rates).

**27c. `hcs_raw.cms_physician_puf`** (~21 -> per-HCPCS line items)
Missing per-HCPCS service line items: `hcpcs_code`, `hcpcs_description`, `place_of_service`, `number_of_services`, `number_of_medicare_beneficiaries`, `number_of_distinct_medicare_beneficiary_per_day_services`, `average_medicare_allowed_amt`, `average_submitted_charge_amt`, `average_medicare_payment_amt`, `average_medicare_standardized_amt`, plus beneficiary age/gender/ethnicity breakouts.

**27d. `hcs_raw.hrsa`** (~9 -> ~20-25 columns)
Missing: `hpsa_status_code`, `designation_history` (JSONB), `provider_count`, `primary_care_physician_count`, `dental_provider_count`, `mental_health_provider_count`, `mua_status`, `mua_score`, `withdrawn_date`.

### FR-018: IP patent/trademark loader expansions (Item 28)

**Priority:** P1. **Effort:** ~1 week.

**28a. `ip_raw.uspto_patents`** (~10 -> ~50 columns)

Currently loaded: `patent_number`, `title`, `abstract`, `inventors` (JSONB), `assignees` (JSONB), `filing_date`, `grant_date`, `cpc_codes[]`, `claims_count`, `patent_type`.

Missing:
- **Citations:** `cited_patents`, `citing_patents`, `npl_citations` (non-patent literature references)
- **Continuity:** `parent_application`, `child_applications`, `continuation_type` (CON/DIV/CIP/REISSUE)
- **Claims text:** `claims_full_text`
- **Assignment history:** `assignment_events[]` (date, old_assignee, new_assignee, conveyance_type)
- **Examiner data:** `examiner_first_name`, `examiner_last_name`, `examiner_art_unit`
- **International family:** `family_id`, `equivalent_foreign_patents[]`
- **Publication/priority:** `application_number`, `publication_number`, `priority_date`
- **IPC codes** in addition to CPC codes

**28b. `ip_raw.epo_patents`** (~9 -> ~35 columns)

Currently loaded: `publication_id`, `title`, `abstract`, `applicants` (JSONB), `inventors` (JSONB), `filing_date`, `publication_date`, `ipc_codes[]`, `family_id`.

Missing:
- **Priority claims:** `priority_claims[]` (each with country, number, date)
- **Full family members:** `family_members[]` (DOCDB simple family)
- **Multilingual abstracts:** `abstract_en`, `abstract_fr`, `abstract_de`
- **Legal-status history:** `legal_status_events[]` (lapse, restoration, opposition filed/decided)
- **Designated states:** `designated_states[]` (EPC member states)
- **Grant date** (distinct from publication date)
- **Cited documents:** `cited_patents[]` via biblio endpoint

**28c. `ip_raw.uspto_trademarks`** (~15 -> ~40 columns)

Missing:
- **Case-file statements:** time-ordered status changes, office actions, responses, notices of allowance
- **Owner change history:** `owner_events[]` with assignment dates
- **Assignment records:** `assignments[]` from USPTO Assignment database
- **Prosecution events:** `prosecution_history[]`
- **Oppositions/cancellations:** `tta_proceedings[]`
- **Renewal history:** `renewal_events[]`
- **International registrations** (Madrid Protocol linkage)
- **Mark image URL** (for trade-dress rules)

**28d. `ip_raw.euipo_trademarks`** (~15 -> ~35 columns)

Missing:
- **Oppositions:** `oppositions[]` with opponent, filing date, decision
- **Cancellations:** `cancellations[]` with grounds, decision date
- **Seniorities:** `seniorities[]` (prior national rights under EUIPO seniority mechanism)
- **Priority claims:** `priority_claims[]`
- **Vienna classifications:** `vienna_codes[]` (figurative-element classification, distinct from Nice classes)
- **Publication history:** `publication_events[]` with dates
- **Owner change history**
- **Acquired-distinctiveness flag** (for descriptive marks registered on proof)

**New silver views required:**
- `ip_silver.patent_families` -- one row per family_id with member patents
- `ip_silver.patent_citations` -- edge list
- `ip_silver.trademark_oppositions` -- one row per opposition event

### FR-019: Tier 3 items -- tracked, contract-blocked, out of scope

The following items are not dk-data engineering problems. They depend on commercial contracts:

| Item | Source | Resolution |
|------|--------|------------|
| 19 | DTC advertising feed (iSpot/Kantar/Pathmatics) | `CIAlertCategory.COMPETITOR_DTC` declared out of scope for first port |
| 20 | Commercial payer formulary (MMIT/Decision Resources) | Rules engine scopes payer rules to Medicare only |
| 21 | Commercial prescription/sales (IQVIA/Symphony/Komodo) | `CIAlertCategory.COMMERCIAL_PERFORMANCE` declared out of scope |
| 22 | KOL social voice / sentiment | KOL rules scoped to authorship and publications only |
| 23 | Private insurance claims (Optum/MarketScan/Truven) | RWE rules scoped to Medicare via `hcs_silver.cms_*` only |

---

## Key Entities

### Modified bronze/silver models

| Entity | Schema.Table | Change |
|--------|-------------|--------|
| openFDA drug labels | `mol_bronze.openfda_labels` / `mol_silver.drug_labels` | +8 openfda subobject fields, +22 Rx sections, +7 OTC sections, +4 SPL sections, +14 `_table` variants, `product_type` bug fix |
| Purple Book | `mol_bronze.purple_book` / `mol_silver.purple_book` | Fix 0-row regression; rewrite FROM clause |
| FDA drugs | `mol_bronze.fda_drugs` / `mol_silver.fda_drugs` | +5 designation boolean flags |
| Drug products | `mol_silver.drug_products` | +`atc_code` (TEXT[]), +`has_orphan_designation` (BOOLEAN) |
| Publications | `mol_silver.publications` | +`evidence_tier` (VARCHAR(1)) |
| CMS Open Payments | `hcs_raw.cms_open_payments` / `hcs_bronze.cms_open_payments` | ~31 -> ~91 columns |
| CMS NPPES | `hcs_raw.cms_nppes` / `hcs_bronze.cms_nppes` | ~48 -> ~330+ columns |
| Part D Prescriber | `hcs_raw.cms_part_d_prescriber` | ~18 -> ~25-30 columns |
| Hospital General Info | `hcs_raw.cms_hospital_general_info` | ~14 -> ~40+ columns |
| Physician PUF | `hcs_raw.cms_physician_puf` | +per-HCPCS line items |
| HRSA | `hcs_raw.hrsa` | ~9 -> ~20-25 columns |
| USPTO Patents | `ip_raw.uspto_patents` | ~10 -> ~50 columns |
| EPO Patents | `ip_raw.epo_patents` | ~9 -> ~35 columns |
| USPTO Trademarks | `ip_raw.uspto_trademarks` | ~15 -> ~40 columns |
| EUIPO Trademarks | `ip_raw.euipo_trademarks` | ~15 -> ~35 columns |

### New models

| Entity | Schema.Table | Description |
|--------|-------------|-------------|
| ATC Classifications | `mol_silver.atc_classifications` | ATC hierarchy with parent-child pointers (~6,500 rows) |
| FDA Orphan Designations | `mol_bronze.fda_orphan_designation` | Small-molecule orphan designations |
| Guidelines | `mol_bronze.guidelines` / `mol_silver.guidelines` | Treatment guidelines with structured recommendations |
| FDA Warning Letters | `mol_bronze.fda_warning_letters` | Enforcement actions |
| FDA Untitled Letters | `mol_bronze.fda_untitled_letters` | Enforcement actions |
| FDA 483 Observations | `mol_bronze.fda_483_observations` | Inspection observations |
| FDA Dear HCP Letters | `mol_bronze.fda_dear_hcp_letters` | Safety communications |
| FDA CRLs | `mol_bronze.fda_crls` | Complete Response Letters |
| EMA SmPC Labels | `mol_silver.drug_labels_ema` | Parsed EMA SmPC sections |
| Drug Label Changes | `mol_silver.drug_label_changes` | Section-level diff surface |
| Conference Abstracts | `mol_bronze.conference_abstracts` / `mol_silver.conference_abstracts` | Conference abstracts with embargo tracking |
| EMA PRAC Signals | `mol_silver.ema_prac_signals` | EU post-market safety signals |
| FDA Drug Shortages | `mol_bronze.fda_drug_shortages` / `mol_silver.fda_drug_shortages` | Drug shortage list |
| FDA CDx Pairs | `mol_bronze.fda_cdx_pairs` | Companion diagnostics pairings |
| NPPES Practice Locations | `hcs_raw.cms_nppes_practice_locations` | Secondary practice locations (optional child table) |
| Physician PUF Services | `hcs_raw.cms_physician_puf_services` | Per-HCPCS line items (optional child table) |
| Patent Families | `ip_silver.patent_families` | One row per family_id with member patents |
| Patent Citations | `ip_silver.patent_citations` | Patent citation edge list |
| Trademark Oppositions | `ip_silver.trademark_oppositions` | One row per opposition event |

---

## Success Criteria

1. **Item 24 (Purple Book fix):** `SELECT COUNT(*) FROM mol_bronze.purple_book` >= 1,000 rows. Dupilumab BLA 761055 has a row with `brand_name = 'Dupixent'` and `license_type = 'BLA'`. A Humira biosimilar has `is_biosimilar = TRUE`.
2. **Item 1 (Label unnesting):** All 56 new columns (8 openfda + 22 Rx + 7 OTC + 4 SPL + 14 _table + 1 product_type fix) exist on bronze and silver. Dupilumab's `product_type = 'HUMAN PRESCRIPTION DRUG'`, hydrocodone's `dea_schedule = 'CII'`, aspirin's OTC fields non-null.
3. **Item 2 (ATC):** ~6,500 rows in `mol_silver.atc_classifications`. D11AH05 ancestor walk returns D11AH, D11A, D11, D.
4. **Item 6 (Evidence tier):** >= 95% of publications have `evidence_tier` populated. Cochrane = `'A'`, case report = `'D'`.
5. **Item 7 (Designations):** Five boolean flags on `mol_silver.fda_drugs`. `mol_bronze.fda_orphan_designation` >= 500 rows.
6. **Item 8 (Guidelines):** >= 50 guidelines across AAD, ACR, GINA, NCCN in `mol_silver.guidelines`.
7. **Item 9 (Enforcement):** Five bronze sources each >= 100 rows, >= 50% molecule crosswalk coverage.
8. **Item 10 (SmPC):** >= 500 parsed SmPCs, >= 90% section-header accuracy.
9. **Item 11 (Label changes):** Diff table exists with change rows for known label revisions.
10. **Item 13 (Conferences):** >= 500 abstracts across >= 5 conferences, embargo vs publication dates tracked.
11. **Item 14 (PRAC):** >= 50 PRAC signal rows.
12. **Item 15 (Shortages):** Current shortage list loaded with correct statuses.
13. **Item 16 (CDx):** >= 50 CDx pairs.
14. **Item 24 audit:** SQLMesh `row_count_at_least(1000)` audit on Purple Book.
15. **Item 25 (Open Payments):** >= 85 columns, `physician_npi` populated for physician rows.
16. **Item 26 (NPPES):** >= 300 columns, taxonomy slots 3-15 populated, DEA numbers visible.
17. **Item 27 (CMS/HRSA):** Part D >= 25 columns, Hospital >= 20 quality ratings, Physician PUF per-HCPCS, HRSA has `hpsa_status_code`.
18. **Item 28 (IP):** Citations, family members, oppositions populated across all four IP raw tables. Silver views for patent_families, patent_citations, trademark_oppositions exist.

---

## Assumptions

1. `mol_silver.drug_labels` is a full passthrough of `mol_bronze.openfda_labels`. Every column added to bronze is automatically available at silver after a one-line SELECT list sync.
2. `mol_silver.fda_drugs` is a thin passthrough of `mol_bronze.fda_drugs`. Same pattern as above.
3. `mol_silver.purple_book` is a passthrough of `mol_bronze.purple_book`. Fixing the bronze model fixes silver automatically.
4. The openFDA drug-label JSON schema is the ground-truth source for Item 1. The field list was verified by querying the live API for Dupixent plus 8 reference drugs (aspirin, metformin, warfarin, hydrocodone, levothyroxine, atorvastatin, and others) spanning prescription biologics, small molecules, OTC, and controlled substances.
5. All `_table` fields in openFDA responses are arrays of HTML-fragment strings. They must be preserved as JSONB rather than extracting a single element (e.g., Dupixent's `adverse_reactions_table` has 8 entries, `clinical_studies_table` has 30, `instructions_for_use_table` has 21).
6. KEGG publishes the full ATC branch for each drug in the `brite` field with indentation-based hierarchy; this is parseable for hierarchy reconstruction.
7. The WHO-CC ATC bulk download is free for research use; commercial redistribution requires a separate license tier -- verify before relying on it.
8. CMS and HRSA datasets are publicly available CSV/API downloads with stable column names. Loader changes are mechanical.
9. USPTO PatentsView API, EPO OPS API, and EUIPO/TMview JSON APIs are all well-documented and accessible.
10. `mol_silver.publication_evidence` uses `confidence_score >= 0.40` as the production filter threshold. Rules that trust extracted endpoints should be aware of this threshold.
11. The rules engine's adapter (`@repo/claims-response-dk-adapter`) currently works around missing fields by parsing `raw_json` via JSONB helpers. Once Item 1 ships, these workarounds can be removed.
12. Deeply nested fields in IP sources (citations, family members, assignment events) are preserved as JSONB arrays at raw, matching the existing molecules-domain pattern.

---

## Resolved Open Questions

These questions were raised by the rules engine team in the source brief (section 7). Answers are integrated into the requirements above but documented here for traceability.

### Q1: MedDRA license tier

**Question:** What MedDRA license tier does dk-data hold?

**Answer:** dk-data does NOT hold a MedDRA license. `soc_distribution` in `mol_gold.safety_signals` is NULL by design. Item 18 (MedDRA hierarchy depth -- LLT/HLT/HLGT) is **permanently blocked** unless a license is procured. SOC-level scoping via `mol_silver.adverse_events.meddra_soc` + `meddra_soc_code` covers most safety-signal rule needs. HLT/HLGT layers are intermediate groupings that rule authors rarely use.

### Q2: News signals sentiment

**Question:** Are `mol_silver.news_signals.sentiment_polarity` and `sentiment_score` actually populated?

**Answer:** `sentiment_polarity` is hardcoded to `'neutral'` and `sentiment_score` is hardcoded to `NULL` in the current SQLMesh SELECT. No sentiment classifier is wired in. The `mol_gold.advocacy_sentiment` model consumes these columns but produces only neutral sentiment. This is a known limitation, not a data gap to fix in this feature.

### Q3: `mol_silver.web_content` columns

**Question:** What are the columns of `mol_silver.web_content`?

**Answer:** `mol_silver.web_content` exists with columns: `id`, `molecule_id`, `search_query`, `search_engine`, `search_type`, `result_url`, `result_title`, `result_snippet`, `result_rank`, `result_domain`, `publication_date`, `authors`, `source_name`, `relevance_score`, `source`, `ingested_at`, `created_at`. This partially mitigates Items 9 (enforcement actions via news-based mentions) and 13 (conference abstracts via web-scraped results) but does not replace structured ingestion of the actual data sources.

### Q4: EMA regulatory docs summary content

**Question:** Does `ema_regulatory_docs.summary` contain parsed SmPC section text, or just document metadata?

**Answer:** `ema_regulatory_docs.summary` contains document metadata (brief synopsis), NOT parsed SmPC text. This does NOT mitigate Item 10 (EMA SmPC parser). A dedicated PDF parser is required.

### Q5: ICD-11 ontology PostgREST exposure

**Question:** Are `ind_silver.icd11_ontology` and `ind_silver.indication_ontology` exposed via PostgREST?

**Answer:** YES. `ind_silver` is in `PGRST_DB_SCHEMAS`, so both `ind_silver.icd11_ontology` and `ind_silver.indication_ontology` are directly queryable via PostgREST. Hierarchy walks work via PostgREST. The rules engine adapter does not need to route hierarchy walks through `conditions`.

### Q6: Publication evidence confidence threshold

**Question:** What confidence threshold does `mol_silver.publication_evidence` use in production?

**Answer:** The SQLMesh model filters at `confidence_score >= 0.40`. Rules that trust extracted endpoints (hazard ratios, p-values) should be aware that this is the floor threshold. The adapter queries with `confidence_score=gte.0.6` for higher-confidence results.

---

## Clarifications

### Closed/Merged Items

The following items from the source brief are closed or merged and require no new work:

- **Item 3:** Merged into Item 1. `recent_major_changes` extraction is a sub-item of the label-field extraction.
- **Item 4:** Closed. `mol_gold.safety_signals` is an active SQLMesh model (`cron '@weekly'`) populated from FAERS + drug labels. Safety-signal rules with statistical thresholds (PRR, ROR, IC, signal_strength) are expressible today.
- **Item 5:** Merged into Item 1 for `dea_schedule` and `drug_abuse_and_dependence`. `renal_impairment` and `hepatic_impairment` are NOT gaps -- they live inside `use_in_specific_populations`, already extracted.
- **Item 12:** Schema-closed but data-empty. `is_interchangeable` columns exist on `mol_silver.purple_book` and `ip_silver.patent_exclusivities`, but because `mol_bronze.purple_book` is broken (Item 24), silver currently has zero rows. Item 24 is the actual fix.
- **Item 17:** Merged into Item 1. All text sections and `_table` variants previously scoped here are covered by the exhaustive Item 1 unnesting.

### Not Gaps

- **`renal_impairment` and `hepatic_impairment`:** Not distinct top-level openFDA label fields. Content lives inside `use_in_specific_populations`, already extracted as a typed column on bronze and silver. Rules scope on `use_in_specific_populations` directly.
- **`spl_medguide`, `spl_patient_package_insert` as duplicates:** These are FDA-structured sections carrying patient-facing summaries. They are NOT duplicates of warnings/adverse_reactions and are worth keeping distinct.

### Sequencing

The suggested implementation order optimizes for rule impact per engineering day:

**Week 1 (hotfixes + quick wins):**
1. Item 24 -- Purple Book fix (~0.5d)
2. Item 1 -- Label unnesting (~1d)
3. Item 2 -- ATC hierarchy (~2d)

**Weeks 2-3 (medium-effort internal):**
4. Item 6 -- Evidence tier (~3d)
5. Item 7 -- FDA designations (~3d)
6. Item 11 -- Label diff table (~1-2d)
7. Item 25 -- CMS Open Payments expansion (~2d)
8. Item 26 -- CMS NPPES expansion (~3d)

**Weeks 4-5 (short new sources):**
9. Item 14 -- PRAC signals (~2-3d)
10. Item 15 -- Drug shortages (~3d)
11. Item 16 -- CDx pairs (~2d)
12. Item 27 -- Other CMS/HRSA expansions (~4d)

**Weeks 6+ (larger new sources):**
13. Item 8 -- Guidelines feed (~2wk)
14. Item 10 -- EMA SmPC parser (~2wk)
15. Item 28 -- IP loader expansions (~1wk)
16. Item 9 -- FDA enforcement actions (~1mo)
17. Item 13 -- Conference abstracts (~4wk)

**Blocked:**
18. Item 18 -- MedDRA hierarchy (MSSO license -- permanently blocked)
19. Items 19-23 -- Commercial contracts

---

## Appendix A: openFDA Drug-Label Field Enumerations (Item 1)

### Table A1: Missing `openfda` Subobject Fields (8 new columns)

| # | Field | Type | Bronze Column Name | Example Value | Rule Impact |
|---|-------|------|--------------------|---------------|-------------|
| 1 | `substance_name` | array of strings | `substance_name` | `["DUPILUMAB"]` | Active-ingredient identifier, distinct from `generic_name`. Ingredient-level and combination-product rule scoping. |
| 2 | `product_ndc` | array of strings | `product_ndc` | `["0024-5911", "0024-5914"]` | Product-level NDC codes. |
| 3 | `package_ndc` | array of strings | `package_ndc` | `["0024-5914-00", ...]` | Package-level NDC codes. |
| 4 | `spl_id` (openfda subobject) | array of strings | `openfda_spl_id` | `["83d4e019-8348-..."]` | Distinct from top-level `id`. Projected as `openfda_spl_id` to avoid name collision. |
| 5 | `pharm_class_pe` | array of strings | `pharm_class_pe` | `["Cell-mediated Immunity [PE]"]` | Physiologic Effect -- third FDA pharmacologic-class axis. |
| 6 | `pharm_class_cs` | array of strings | `pharm_class_cs` | `["Antibodies, Monoclonal [CS]"]` | Chemical Substance -- fourth FDA pharmacologic-class axis. |
| 7 | `original_packager_product_ndc` | array of strings | `original_packager_product_ndc` | `["0024-5911"]` | Repackager/relabeler provenance. |
| 8 | `upc` | array of strings | `upc` | `["3-00240000..."]` | UPC codes for OTC products. |

**Note:** `dea_schedule` is a top-level field, not an `openfda` subobject field. Listed in Table A2.

### Table A2: Missing Rx Drug-Label Sections (22 new columns)

| # | openFDA Key | Bronze Column Name | Type | Example Context |
|---|-------------|-------------------|------|-----------------|
| 1 | `abuse` | `abuse` | TEXT | Abuse potential sections for controlled substances |
| 2 | `active_ingredient` | `active_ingredient` | TEXT | Active ingredient declaration |
| 3 | `animal_pharmacology_and_or_toxicology` | `animal_pharmacology_and_toxicology` | TEXT | ~10,900 labels carry this section |
| 4 | `carcinogenesis_and_mutagenesis_and_impairment_of_fertility` | `carcinogenesis_mutagenesis_fertility` | TEXT | Reproductive toxicology data |
| 5 | `controlled_substance` | `controlled_substance` | TEXT | Controlled substance classification |
| 6 | `dea_schedule` | `dea_schedule` | TEXT | `"CII"` / `"CIII"` / `"CIV"` / `"CV"` / null |
| 7 | `dependence` | `dependence` | TEXT | Physical/psychological dependence |
| 8 | `dosage_forms_and_strengths` | `dosage_forms_and_strengths` | TEXT | Available dosage forms |
| 9 | `drug_abuse_and_dependence` | `drug_abuse_and_dependence` | TEXT | Combined abuse/dependence section |
| 10 | `drug_and_or_laboratory_test_interactions` | `drug_or_lab_test_interactions` | TEXT | Lab test interference |
| 11 | `inactive_ingredient` | `inactive_ingredient` | TEXT | Inactive ingredient declaration |
| 12 | `information_for_patients` | `information_for_patients` | TEXT | Patient counseling information |
| 13 | `instructions_for_use` | `instructions_for_use` | TEXT | Device/administration instructions |
| 14 | `labor_and_delivery` | `labor_and_delivery` | TEXT | Labor/delivery considerations |
| 15 | `laboratory_tests` | `laboratory_tests` | TEXT | Recommended monitoring labs |
| 16 | `microbiology` | `microbiology` | TEXT | ~5,200 labels; antimicrobial spectrum, susceptibility |
| 17 | `nonclinical_toxicology` | `nonclinical_toxicology` | TEXT | Nonclinical toxicology data |
| 18 | `nonteratogenic_effects` | `nonteratogenic_effects` | TEXT | Non-teratogenic reproductive effects |
| 19 | `precautions` | `precautions` | TEXT | General precautions |
| 20 | `pregnancy_or_breast_feeding` | `pregnancy_or_breast_feeding` | TEXT | Pregnancy/breastfeeding combined section |
| 21 | `recent_major_changes` | `recent_major_changes` | TEXT | FDA-flagged recent label changes |
| 22 | `references` | `label_references` | TEXT | Literature references (aliased to avoid SQL keyword) |
| 23 | `teratogenic_effects` | `teratogenic_effects` | TEXT | Teratogenic risk data |

**Note:** The brief lists 22 Rx sections. `references` is aliased as `label_references` in the bronze column to avoid SQL reserved-word conflicts. The count of 22 in the brief treats `references`/`teratogenic_effects` as the 22nd entry; the table above lists 23 rows because `dea_schedule` was counted in the brief's "22 Rx sections" but is technically a standalone top-level field, not a label-text section. The total new Rx column count is 22 (excluding `dea_schedule` which was counted in the 8 openfda subobject fields by some itemizations) or 23 depending on how `dea_schedule` is categorized. For implementation purposes, all are in this table.

### Table A3: Missing OTC Drug-Label Sections (7 new columns)

| # | openFDA Key | Bronze Column Name | Type |
|---|-------------|-------------------|------|
| 1 | `ask_doctor` | `ask_doctor` | TEXT |
| 2 | `ask_doctor_or_pharmacist` | `ask_doctor_or_pharmacist` | TEXT |
| 3 | `do_not_use` | `do_not_use` | TEXT |
| 4 | `keep_out_of_reach_of_children` | `keep_out_of_reach_of_children` | TEXT |
| 5 | `purpose` | `purpose` | TEXT |
| 6 | `questions` | `questions` | TEXT |
| 7 | `stop_use` | `stop_use` | TEXT |

### Table A4: Missing SPL Structured Sections (4 new columns)

| # | openFDA Key | Bronze Column Name | Type |
|---|-------------|-------------------|------|
| 1 | `spl_medguide` | `spl_medguide` | TEXT |
| 2 | `spl_patient_package_insert` | `spl_patient_package_insert` | TEXT |
| 3 | `spl_product_data_elements` | `spl_product_data_elements` | TEXT |
| 4 | `spl_unclassified_section` | `spl_unclassified_section` | TEXT |

**Note:** The source brief lists 5 SPL sections but one (`spl_unclassified_section`) is sometimes counted with the `_table` variants. Implementation treats these as 4 text columns. The `_table` variants of these sections are in Table A5.

### Table A5: `_table` JSONB Variants (14 new columns)

All `_table` fields are arrays of HTML-fragment strings. Preserve as JSONB, not single-element extraction.

| # | openFDA Key | Bronze Column Name | Type | Note |
|---|-------------|-------------------|------|------|
| 1 | `adverse_reactions_table` | `adverse_reactions_table` | JSONB | Dupixent has >= 8 entries |
| 2 | `clinical_pharmacology_table` | `clinical_pharmacology_table` | JSONB | |
| 3 | `clinical_studies_table` | `clinical_studies_table` | JSONB | High value for efficacy claims; Dupixent has >= 30 entries |
| 4 | `description_table` | `description_table` | JSONB | |
| 5 | `dosage_and_administration_table` | `dosage_and_administration_table` | JSONB | |
| 6 | `dosage_forms_and_strengths_table` | `dosage_forms_and_strengths_table` | JSONB | |
| 7 | `drug_interactions_table` | `drug_interactions_table` | JSONB | |
| 8 | `how_supplied_table` | `how_supplied_table` | JSONB | |
| 9 | `instructions_for_use_table` | `instructions_for_use_table` | JSONB | Dupixent has >= 21 entries |
| 10 | `pharmacokinetics_table` | `pharmacokinetics_table` | JSONB | |
| 11 | `recent_major_changes_table` | `recent_major_changes_table` | JSONB | |
| 12 | `spl_medguide_table` | `spl_medguide_table` | JSONB | |
| 13 | `spl_patient_package_insert_table` | `spl_patient_package_insert_table` | JSONB | |
| 14 | `spl_unclassified_section_table` | `spl_unclassified_section_table` | JSONB | |

---

## Appendix B: Loader Expansion Field Enumerations (Items 25-28)

### Table B1: CMS Open Payments Missing Columns (Item 25)

**Category: Physician Identity**
- `physician_npi` -- direct NPI, critical for NPPES join and publication ORCID linkage
- `physician_middle_name`
- `physician_name_suffix`
- `physician_primary_type`
- `physician_specialty_2` -- secondary specialty

**Category: Teaching Hospitals**
- `teaching_hospital_ccn`
- `teaching_hospital_id`
- `teaching_hospital_name`

**Category: Recipient Geography**
- `recipient_country`
- `recipient_primary_business_street_address_line_1`
- `recipient_primary_business_street_address_line_2`
- `recipient_postal_code`
- `recipient_province`

**Category: Publication / Dispute Metadata**
- `dispute_status_for_publication`
- `delay_in_publication_indicator`
- `change_type` (NEW / ADD / CHANGE)
- `payment_publication_date`

**Category: Manufacturer Identity**
- `applicable_manufacturer_or_applicable_gpo_making_payment_id`
- `applicable_manufacturer_or_applicable_gpo_making_payment_state`
- `applicable_manufacturer_or_applicable_gpo_making_payment_country`

**Category: Product Category / Indication Slots**
- `product_category_or_therapeutic_area_1`
- `product_category_or_therapeutic_area_2`
- `product_category_or_therapeutic_area_3`
- `product_category_or_therapeutic_area_4`
- `product_category_or_therapeutic_area_5`
- `product_indication_1`
- `product_indication_2`
- `product_indication_3`
- `product_indication_4`
- `product_indication_5`

**Category: Travel Details**
- `city_of_travel`
- `state_of_travel`
- `country_of_travel`

**Category: Flags**
- `physician_ownership_indicator`
- `third_party_payment_recipient_indicator`
- `charity_indicator`
- `contextual_information`

### Table B2: CMS NPPES Missing Columns (Item 26)

**Category: Healthcare Provider Taxonomies 3-15** (52 columns)
- `healthcare_provider_taxonomy_code_3` through `healthcare_provider_taxonomy_code_15`
- `healthcare_provider_primary_taxonomy_switch_3` through `healthcare_provider_primary_taxonomy_switch_15`
- `provider_license_number_3` through `provider_license_number_15`
- `provider_license_number_state_code_3` through `provider_license_number_state_code_15`

**Category: Other Provider Identifiers 1-50** (200 columns)
- `other_provider_identifier_1` through `other_provider_identifier_50`
- `other_provider_identifier_type_code_1` through `other_provider_identifier_type_code_50`
- `other_provider_identifier_state_1` through `other_provider_identifier_state_50`
- `other_provider_identifier_issuer_1` through `other_provider_identifier_issuer_50`

**Category: Practice Location Addresses**
- `provider_first_line_business_practice_location_address`
- `provider_second_line_business_practice_location_address`
- `provider_business_practice_location_address_city_name`
- `provider_business_practice_location_address_state_name`
- `provider_business_practice_location_address_postal_code`
- `provider_business_practice_location_address_country_code`
- `provider_business_practice_location_address_telephone_number`
- `provider_business_practice_location_address_fax_number`

**Category: Authorized Official Details**
- `authorized_official_last_name`
- `authorized_official_first_name`
- `authorized_official_title_or_position`
- `authorized_official_telephone_number`
- `authorized_official_name_prefix_text`
- `authorized_official_name_suffix_text`
- `authorized_official_credential_text`

**Category: Deactivation / Reactivation**
- `npi_deactivation_reason_code`
- `npi_deactivation_date`
- `npi_reactivation_date`

**Category: Entity-Type-Specific**
- `is_sole_proprietor` (Y/N)
- `is_organization_subpart` (Y/N)
- `parent_organization_lbn`
- `parent_organization_tin`

**Category: Other**
- `last_update_date`
- `certification_date`

### Table B3: USPTO Patents Missing Fields (Item 28a)

**Currently loaded (10 columns):** `patent_number`, `title`, `abstract`, `inventors` (JSONB), `assignees` (JSONB), `filing_date`, `grant_date`, `cpc_codes[]`, `claims_count`, `patent_type`.

**Missing fields:**

| Category | Field | Type | Purpose |
|----------|-------|------|---------|
| Citations | `cited_patents` | JSONB | Patent-to-patent citation graph (forward) |
| Citations | `citing_patents` | JSONB | Backward citations |
| Citations | `npl_citations` | JSONB | Non-patent literature references |
| Continuity | `parent_application` | TEXT | Parent application number |
| Continuity | `child_applications` | JSONB | Child application numbers |
| Continuity | `continuation_type` | TEXT | CON / DIV / CIP / REISSUE |
| Claims | `claims_full_text` | TEXT | Full claim language (not just count) |
| Assignment | `assignment_events` | JSONB | date, old_assignee, new_assignee, conveyance_type |
| Examiner | `examiner_first_name` | TEXT | Examining patent officer |
| Examiner | `examiner_last_name` | TEXT | Examining patent officer |
| Examiner | `examiner_art_unit` | TEXT | Art unit assignment |
| Family | `family_id` | TEXT | International patent family ID |
| Family | `equivalent_foreign_patents` | JSONB | Foreign equivalents |
| Publication | `application_number` | TEXT | Application number |
| Publication | `publication_number` | TEXT | Publication number |
| Priority | `priority_date` | DATE | Priority filing date |
| Classification | IPC codes | TEXT[] | In addition to existing CPC codes |

### Table B4: EPO Patents Missing Fields (Item 28b)

**Currently loaded (9 columns):** `publication_id`, `title`, `abstract`, `applicants` (JSONB), `inventors` (JSONB), `filing_date`, `publication_date`, `ipc_codes[]`, `family_id`.

**Missing fields:**

| Category | Field | Type | Purpose |
|----------|-------|------|---------|
| Priority | `priority_claims` | JSONB | Each with country, number, date |
| Family | `family_members` | JSONB | DOCDB simple family -- every filing country |
| Abstracts | `abstract_en` | TEXT | English abstract |
| Abstracts | `abstract_fr` | TEXT | French abstract |
| Abstracts | `abstract_de` | TEXT | German abstract |
| Legal status | `legal_status_events` | JSONB | Lapse, restoration, opposition filed/decided |
| Designation | `designated_states` | JSONB | EPC member states designated |
| Dates | `grant_date` | DATE | Distinct from publication date |
| Citations | `cited_patents` | JSONB | Via biblio endpoint |

### Table B5: USPTO Trademarks Missing Fields (Item 28c)

**Missing fields:**

| Category | Field | Type | Purpose |
|----------|-------|------|---------|
| Prosecution | `case_file_statements` | JSONB | Time-ordered status changes, office actions, responses |
| Ownership | `owner_events` | JSONB | Assignment dates and ownership changes |
| Assignment | `assignments` | JSONB | From USPTO Assignment database (distinct from owner_events) |
| Prosecution | `prosecution_history` | JSONB | Full prosecution timeline |
| Disputes | `tta_proceedings` | JSONB | Oppositions and cancellations |
| Maintenance | `renewal_events` | JSONB | Renewal history |
| International | Madrid Protocol linkage | TEXT | International registration number |
| Visual | `mark_image_url` | TEXT | For trade-dress rules |

### Table B6: EUIPO Trademarks Missing Fields (Item 28d)

**Missing fields:**

| Category | Field | Type | Purpose |
|----------|-------|------|---------|
| Disputes | `oppositions` | JSONB | Opponent, filing date, decision |
| Disputes | `cancellations` | JSONB | Grounds, decision date |
| Priority | `seniorities` | JSONB | Prior national rights under seniority mechanism |
| Priority | `priority_claims` | JSONB | Priority claim details |
| Classification | `vienna_codes` | JSONB | Figurative-element classification (distinct from Nice) |
| History | `publication_events` | JSONB | Publication dates and events |
| Ownership | Owner change history | JSONB | Same as USPTO pattern |
| Registration | `acquired_distinctiveness_flag` | BOOLEAN | For descriptive marks |

---

*Generated by dk on 2026-04-15T13:30:38Z*
