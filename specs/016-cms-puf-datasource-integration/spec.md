# Feature Specification: CMS PUF Data Source Integration

**Feature Branch**: `016-cms-puf-datasource-integration`
**Created**: 2026-03-01
**Status**: Draft
**Input**: `behavior-labs-ai/specs/036-reverse-engineering/TODO/05-data-source-availability.md` — Integrate ~54 free CMS/FDA/NLM/academic public-use files, APIs, and enrichment pipelines to replace $232K–$818K/yr in vendor data (IQVIA, Definitive Healthcare, Komodo Health, Veeva). These data sources power four DocNexus products: HCP Compass, HCO Navigator, Lumina, SageAI. Engineering effort: ~20-27 weeks.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Provider Lookup by NPI (Priority: P1)

An HCP Compass user needs to look up a provider by NPI and see a unified profile combining demographics, prescribing patterns, procedures, quality scores, and industry payments from 5+ CMS data sources.

**Why this priority**: Provider lookup is the most common query pattern for HCP Compass. Every downstream feature depends on unified provider profiles being available. Without this, the core product use case is unmet.

**Independent Test**: Can be tested by invoking the `cms-nppes-search` MCP tool with a known NPI and verifying all 5 data facets appear in the response and persist to `gold.provider_profile`.

**Acceptance Scenarios**:

1. **Given** a user searches for NPI `1234567890`, **When** the MCP tool `cms-nppes-search` is invoked, **Then** the system returns provider demographics (name, specialty, address, phone) from NPPES.
2. **Given** a valid NPI with prescribing history, **When** the provider profile is retrieved, **Then** it includes top prescribed drugs (generic name, total claims, total cost, beneficiary count) from Part D Prescribers.
3. **Given** a valid NPI with procedure history, **When** the provider profile is retrieved, **Then** it includes top procedures (HCPCS code, description, services, charges) from Physician PUF.
4. **Given** a valid NPI enrolled in MIPS, **When** the provider profile is retrieved, **Then** it includes quality scores (MIPS final score, attestation status) from Care Compare.
5. **Given** a valid NPI with Open Payments records, **When** the provider profile is retrieved, **Then** it includes industry payments (payer, amount, nature of payment) from Open Payments.
6. **Given** a cached NPI, **When** the lookup completes, **Then** response latency is < 3s. For cold lookups, latency is < 8s.
7. **Given** an invalid NPI (non-10-digit or non-numeric), **When** the tool is invoked, **Then** the system returns a validation error without making an API call.

---

### User Story 2 - Provider Search by Name and State (Priority: P1)

An HCP Compass user searches for providers by name and state, receiving a ranked list of matching providers with key demographics.

**Why this priority**: Name-based search is the second most common provider query pattern. Users often don't have an NPI and search by name instead.

**Independent Test**: Can be tested by searching for `provider_name: "Smith"` and `state: "CA"` and verifying a paginated result set of matching providers is returned.

**Acceptance Scenarios**:

1. **Given** a search for `provider_name: "Smith"` and `state: "CA"`, **When** the MCP tool `cms-nppes-search` is invoked with name parameters, **Then** the system returns a ranked list of matching providers with NPI, full name, credential, specialty taxonomy description, practice address, and entity type.
2. **Given** a name search, **When** results are returned, **Then** deactivated NPIs are excluded by default.
3. **Given** a name search, **When** results are returned, **Then** they are capped at 100 per query.
4. **Given** a partial name, **When** the search is executed, **Then** prefix matching is supported.

---

### User Story 3 - Facility Profile by CCN (Priority: P1)

An HCO Navigator user queries a facility by CCN and sees a unified profile combining demographics, DRG volumes, quality ratings, system affiliation, service lines, and Magnet status.

**Why this priority**: Facility profiles are the core HCO Navigator feature. Without unified facility data, the product cannot serve hospital analytics use cases.

**Independent Test**: Can be tested by querying `gold.facility_profile?ccn=eq.050454` via PostgREST and verifying demographics, DRG volumes, quality ratings, and system affiliation are present.

**Acceptance Scenarios**:

1. **Given** a user queries facility CCN `050454`, **When** the facility profile is retrieved from `gold.facility_profile`, **Then** the system returns facility demographics (name, address, type, bed count, ownership) from Provider of Services.
2. **Given** a valid CCN with inpatient data, **When** the facility profile is retrieved, **Then** it includes top DRGs by volume (DRG code, description, discharges, avg charges, avg payment) from Inpatient PUF.
3. **Given** a valid CCN with quality data, **When** the facility profile is retrieved, **Then** it includes quality ratings (overall star rating, mortality, readmission, patient experience) from Hospital Quality.
4. **Given** a valid CCN in a health system, **When** the facility profile is retrieved, **Then** it includes health system affiliation (parent organization, IDN name) from PECOS/CHOW.
5. **Given** a valid CCN, **When** the facility profile is retrieved, **Then** service lines inferred from DRG volumes are documented as "modeled" vs "reported" data.
6. **Given** an invalid CCN (not 6-character alphanumeric), **When** the query is executed, **Then** the system returns a validation error.

---

### User Story 4 - Drug Market Analysis (Priority: P1)

A Lumina user queries a drug name and sees a unified market profile combining Medicare spending, formulary coverage, drug classification, NDC details, and top prescribers.

**Why this priority**: Drug market analysis is Lumina's core feature. Medicare spending data combined with formulary coverage provides the market intelligence that replaces IQVIA subscription data.

**Independent Test**: Can be tested by querying `gold.drug_market_profile?drug_name=eq.atorvastatin` via PostgREST and verifying spending, formulary, and classification data are present.

**Acceptance Scenarios**:

1. **Given** a user queries drug `atorvastatin`, **When** the drug market profile is retrieved from `gold.drug_market_profile`, **Then** the system returns total Medicare Part D spending (total cost, beneficiary count, claims, cost per unit).
2. **Given** a drug with Part B coverage, **When** the profile is retrieved, **Then** it includes Part B spending (avg payment per dose, utilization).
3. **Given** a drug covered by Part D plans, **When** the profile is retrieved, **Then** it includes formulary coverage (number of plans covering drug, tier distribution) expressed as percentage of total Part D plans.
4. **Given** a drug with NDC entries, **When** the profile is retrieved, **Then** it includes NDC details (manufacturer, package forms, strengths) and drug classification (USP class, ATC code, RBCS category).
5. **Given** a drug with historical data, **When** the profile is retrieved, **Then** spending data includes year-over-year trend for all available years (~10 years of history).
6. **Given** a drug name, **When** matched, **Then** the system uses the existing molecule resolution pipeline for name matching.

---

### User Story 5 - Geographic Market Analytics (Priority: P2)

A SageAI user queries a geographic region and sees population demographics, spending patterns, chronic condition prevalence, and provider density.

**Why this priority**: Geographic analytics power SageAI's cross-domain query engine. This is a differentiated capability that vendor data makes expensive.

**Independent Test**: Can be tested by querying `gold.market_analytics?geo_code=eq.TX&year=eq.2024` via PostgREST and verifying population, spending, and condition data are present.

**Acceptance Scenarios**:

1. **Given** a user queries `state: "TX"`, **When** the market analytics view is retrieved from `gold.market_analytics`, **Then** the system returns population demographics (total beneficiaries, age/sex/race distribution).
2. **Given** a valid geographic query, **When** analytics are retrieved, **Then** they include spending per capita (total, IP, OP, SNF, HHA, hospice, DME).
3. **Given** a valid geographic query, **When** analytics are retrieved, **Then** they include chronic condition prevalence (diabetes, heart failure, COPD, etc.) expressed as percentages of Medicare beneficiaries.
4. **Given** a valid geographic query, **When** analytics are retrieved, **Then** they include provider density (NPIs per 100K beneficiaries by specialty) and facility landscape (hospitals, beds, avg quality rating).
5. **Given** geographic analytics, **When** data is available, **Then** it is accessible at state, HRR, and county levels.
6. **Given** per-capita calculations, **When** computed, **Then** they use CMS standardized methodology.

---

### User Story 6 - Open Payments Transparency (Priority: P2)

An HCP Compass user queries industry payments for a specific provider or company and sees general payments, research payments, ownership interests, and aggregate totals.

**Why this priority**: Open Payments data provides transparency into provider-industry financial relationships, a key HCP Compass differentiator.

**Independent Test**: Can be tested by invoking the `cms-open-payments-search` MCP tool with an NPI and verifying payment records are returned with correct categorization.

**Acceptance Scenarios**:

1. **Given** a user queries payments for NPI `1234567890`, **When** the MCP tool `cms-open-payments-search` is invoked, **Then** the system returns general payments (date, amount, nature of payment, payer name).
2. **Given** a provider with research funding, **When** payments are queried, **Then** research payments (study name, amount, PI status) are included.
3. **Given** a provider with investment interests, **When** payments are queried, **Then** ownership/investment interests are included.
4. **Given** payment results, **When** returned, **Then** aggregate totals by year, by payer, and by payment type are available.
5. **Given** payment amounts, **When** displayed, **Then** they are rounded to 2 decimal places.
6. **Given** disputed/contested payments, **When** returned, **Then** they are flagged with `dispute_status` and excluded from aggregate totals by default.
7. **Given** payment results, **When** filtered, **Then** they are filterable by year range.

---

### User Story 7 - Health System Hierarchy (Priority: P2)

An HCO Navigator user queries a health system and sees the parent organization, affiliated facilities, M&A history, and system-level aggregates.

**Why this priority**: Health system hierarchies enable HCO Navigator to show organizational context. This is data that currently requires a Definitive Healthcare subscription.

**Independent Test**: Can be tested by querying `silver.health_systems` for a known system like "HCA Healthcare" and verifying the hierarchy includes parent org, facilities, and CHOW events.

**Acceptance Scenarios**:

1. **Given** a user queries for health system "HCA Healthcare", **When** the system hierarchy is retrieved from `silver.health_systems`, **Then** the system returns the parent organization (legal business name, organizational NPI).
2. **Given** a valid health system, **When** the hierarchy is retrieved, **Then** it includes affiliated facilities (CCNs, names, types, locations).
3. **Given** a system with M&A history, **When** the hierarchy is retrieved, **Then** it includes change of ownership history (CHOW events with dates, buyer/seller).
4. **Given** a system with multiple facilities, **When** the hierarchy is retrieved, **Then** it includes system-level aggregates (total beds, total facilities, geographic footprint).
5. **Given** IDN hierarchy construction, **When** built from PECOS + CHOW + Facility Affiliation data, **Then** the hierarchy supports at least 3 levels (system → sub-system → facility).

---

### User Story 8 - Drug Interaction Check (Priority: P3)

A clinical user queries interactions between two drugs and sees severity, mechanism, clinical recommendation, and evidence level from DDInter 2.0.

**Why this priority**: Drug interaction data is a clinical decision support feature. It adds clinical depth but is not a core analytics use case.

**Independent Test**: Can be tested by invoking the `ddinter-interaction-search` MCP tool with `warfarin` and `aspirin` and verifying interaction severity is returned.

**Acceptance Scenarios**:

1. **Given** a user queries interactions between `warfarin` and `aspirin`, **When** the MCP tool `ddinter-interaction-search` is invoked, **Then** the system returns interaction severity (major/moderate/minor) from DDInter 2.0.
2. **Given** a valid interaction, **When** returned, **Then** it includes mechanism description, clinical recommendation, and evidence level.
3. **Given** 302K severity-graded interactions from DDInter 2.0, **When** a bidirectional lookup is performed, **Then** drug A→B returns the same interaction as drug B→A.
4. **Given** severity levels from DDInter, **When** returned, **Then** they are normalized to a standard scale.

---

### User Story 9 - Bulk Data Refresh Pipeline (Priority: P1)

A platform operator runs scheduled CronJobs that refresh all ~47 data sources through the full medallion pipeline (raw → bronze → silver → gold) with observability at each stage.

**Why this priority**: Without automated bulk refresh, data goes stale. This is the operational backbone that keeps all 4 products current.

**Independent Test**: Can be tested by triggering the `fetch-cms-part-d` CronJob and verifying records flow through all pipeline layers with metrics updated at each stage.

**Acceptance Scenarios**:

1. **Given** CMS releases the annual Part D Prescriber PUF update, **When** the scheduled CronJob `fetch-cms-part-d` executes, **Then** the system downloads the new dataset via data.cms.gov API.
2. **Given** downloaded data, **When** the loader runs, **Then** records are loaded into `raw.cms_part_d_prescribers` as JSONB.
3. **Given** raw records, **When** the bronze transformer runs, **Then** typed columns are extracted into `bronze.cms_part_d_prescribers`.
4. **Given** bronze records, **When** the SQLMesh incremental model runs, **Then** `silver.prescribing_profiles` is updated.
5. **Given** silver records, **When** the gold refresh runs, **Then** `gold.provider_profile` is updated for affected NPIs.
6. **Given** a successful refresh, **When** the pipeline completes, **Then** `meta.data_sources` freshness timestamp is updated and Prometheus metrics are emitted.
7. **Given** 25M records/year for Part D, **When** processed, **Then** the pipeline completes without OOM (batch inserts with 10K commit interval) within 4 hours.
8. **Given** a failed run, **When** an error occurs, **Then** partial failures do not corrupt existing data (transaction rollback) and an alert is triggered via staleness metrics.

---

### Edge Cases

- **EC-1: Deactivated NPI** — An NPI that was active but has been deactivated by CMS. System MUST flag `npi_deactivation_date` and exclude from default search results. Deactivated records retained in silver for historical queries.
- **EC-2: Duplicate Provider Records Across Sources** — Same provider appears in NPPES, Care Compare, and Physician PUF with slightly different addresses. Silver-layer entity resolution uses NPI as canonical key — NPPES is the authoritative source for demographics, other sources supplement with specialty-specific data.
- **EC-3: NPPES Bulk File Size (9.3 GB) + V2 Format Transition** — Monthly NPPES CSV is 9.3 GB uncompressed. Fetcher MUST use chunked reading (`chunksize=50000`) to avoid memory exhaustion. MUST support resume-on-failure for partial downloads. **CRITICAL**: CMS mandates NPPES Version 2 CSV format starting 2026-03-03. Fetcher MUST detect and parse V2 column layout (different header names and field ordering from V1). Implementation MUST verify V2 schema before production deployment.
- **EC-4: Missing or Suppressed Data** — CMS suppresses cells with fewer than 11 beneficiaries for privacy. Part D Prescriber rows with suppressed claim counts MUST be stored with `NULL` numeric fields and a `suppressed=true` flag, not discarded.
- **EC-5: Annual vs. Monthly Refresh Cadence Mismatch** — Some sources update monthly (NPPES, Care Compare) while others are annual (Part D, Physician PUF). Gold-layer profiles MUST display the most recent data from each source with per-source freshness timestamps, not a single "last updated" date.
- **EC-6: Historical Data Gaps** — Not all years of PUF data may be available at initial load. System MUST handle missing years gracefully in trend calculations (e.g., "2019–2023 available, 2020 missing" should not produce divide-by-zero or misleading averages).
- **EC-7: CMS API Rate Limiting** — data.cms.gov Socrata-style APIs have stated rate limits of ~10K requests/second (per CMS documentation). Practical sustained throughput is ~1-5K req/sec depending on query complexity. Fetchers MUST use exponential backoff and respect `Retry-After` headers. Bulk CSV download preferred over API pagination for large datasets (>100K rows). openFDA APIs have a separate limit of 240 requests/minute without an API key.
- **EC-8: Open Payments Dispute Period** — Open Payments data includes records under dispute. These MUST be flagged with `dispute_status` and excluded from aggregate totals by default.
- **EC-9: Health System Mergers Mid-Year** — When a CHOW event transfers facility ownership mid-year, the facility's DRG data may span two owners. Gold-layer system-level aggregates MUST be calculated based on ownership at time of discharge, not current ownership.
- **EC-10: DDInter Academic API Availability** — DDInter 2.0 is an academic resource. API may be unavailable or rate-limited. Fetcher MUST cache full dataset locally and operate in offline mode when API is unreachable.
- **EC-11: POS Chain ID Limitation** — CMS POS file's Chain ID identifies chain ownership (binary yes/no + chain ID) but does NOT provide full parent-child hierarchy. IDN hierarchy MUST be constructed from PECOS reassignment + CHOW + Facility Affiliation + SEC EDGAR — not from POS Chain ID alone.
- **EC-12: State APCD ERISA Exemption** — State APCDs are missing self-insured employer plans (30-60% of commercially insured) due to ERISA preemption. APCD data MUST be flagged with coverage limitations. Geographic fragmentation means APCD data is only available for specific states, not nationally.
- **EC-13: PBM Formulary Format Heterogeneity** — PBM public formulary lists (CVS Caremark, Express Scripts, OptumRx) are published in varying formats and may change without notice. Fetchers MUST handle format variations and gracefully degrade if a PBM changes its publishing format.
- **EC-14: Conference Abstract NPI Linking** — Conference abstracts (ASCO, AHA, ESMO, ASH) do not contain NPIs. Author-to-NPI linking MUST use name + institutional affiliation matching against NPPES, with confidence scoring. Ambiguous matches (common names, multiple affiliations) MUST be flagged as `needs_review`.

---

## Medallion Architecture Constraints *(mandatory)*

This section defines hard constraints to prevent architectural drift. All changes in this feature MUST preserve the existing medallion pipeline: raw → bronze → silver → gold.

### Constraint 1: Extend Existing Schemas

All new data sources MUST use existing `raw`, `bronze`, `silver`, `gold` schemas rather than creating separate schemas (e.g., `prov_raw`, `fac_raw`). CMS sources like `inpatient`, `hospital_info`, and `cost_reports` already use `raw.*`. Creating separate schemas would fragment the pipeline.

### Constraint 2: Dual Ingestion, Single Raw Tables

Two parallel ingestion systems feed the same raw tables:
- **MCP Tools** (real-time, on-demand): API adapters invoked via `POST /mcp/invoke`, immediate bronze transform via `BronzeTransformer`
- **Data Loaders** (batch, scheduled): CronJob fetchers + CLI loaders, SQLMesh daily transforms

Both paths MUST write to the same `raw.*` table for each source. MCP path uses the standard JSONB envelope (`response_body`, `request_params`, `processed_to_bronze`). Loader path may use direct typed columns in addition to the JSONB envelope.

### Constraint 3: Raw Layer JSONB-First Pattern

All new raw tables MUST follow the established MCP raw pattern: `id UUID PK`, `request_id`, `request_timestamp TIMESTAMPTZ`, `api_endpoint`, `request_params JSONB`, `response_status INTEGER`, `response_body JSONB NOT NULL`, `processed_to_bronze BOOLEAN DEFAULT FALSE`, `ingested_at TIMESTAMPTZ`.

Source-specific columns (e.g., `npi`, `entity_type`, `provider_name`) MAY be added for the direct loader path alongside the JSONB envelope.

**Partitioning**: `raw.cms_part_d_prescribers`, `raw.cms_part_d_prescribers_summary`, `raw.cms_physician_puf`, `raw.cms_physician_puf_summary` MUST use PostgreSQL range partitioning by year. This enables efficient partition-swap on annual refresh and prevents query degradation at 25M+ rows/year.

### Constraint 4: Gold Schema Access Control

Gold tables MUST be exposed via PostgREST by adding `gold` to `PGRST_DB_SCHEMAS`. Access control:
- `analyst` role: GRANT USAGE ON SCHEMA gold, GRANT SELECT ON ALL TABLES IN SCHEMA gold
- `web_anon` role: NO access to gold (analyst JWT required)
- Raw/bronze/silver tables: Internal only — NOT exposed via PostgREST API

### Constraint 5: Generation Source Provenance

Every gold row MUST track provenance via `_generation_source TEXT`:
- `'sql_aggregate'` — produced by SQLMesh gold model
- `'agent:service_line_inference'` — produced/enriched by agent
- `'sql_aggregate+agent:service_line_inference'` — SQL base + agent enrichment

All gold tables MUST include: `_generation_source TEXT`, `_refreshed_at TIMESTAMPTZ`, `_source_freshness JSONB`.

### Constraint 6: Backward Compatibility

Existing molecule pipeline (DrugBank, openFDA labels, ClinicalTrials, WHO ICD-11, etc.) MUST continue to function without regression. No existing MCP tools may break or change behavior. The `base_tool.py` parameter handling change MUST be backward-compatible (existing adapters that use `drug_name` continue to work).

---

### Raw Layer Tables

| Table | Source | Key Column(s) | Partitioned |
|-------|--------|----------------|-------------|
| `raw.cms_nppes` | NPPES monthly CSV / NPI Registry API | npi | No |
| `raw.cms_part_d_prescribers` | Part D Provider+Drug PUF | npi, drug_name, year | **Yes (by year)** |
| `raw.cms_part_d_prescribers_summary` | Part D Provider Summary PUF | npi, year | **Yes (by year)** |
| `raw.cms_physician_puf` | Physician/Supplier PUF (Provider+Service) | npi, hcpcs_code, year | **Yes (by year)** |
| `raw.cms_physician_puf_summary` | Physician/Supplier PUF (Provider summary) | npi, year | **Yes (by year)** |
| `raw.cms_open_payments` | Open Payments | record_id | No |
| `raw.cms_care_compare` | Care Compare Provider Data | npi | No |
| `raw.cms_provider_of_services` | Provider of Services File | ccn | No |
| `raw.cms_pecos` | PECOS Enrollment | enrollment_id | No |
| `raw.cms_chow` | Change of Ownership | chow_id | No |
| `raw.cms_facility_affiliation` | Facility Affiliation | affiliation_id | No |
| `raw.cms_inpatient_puf_detail` | Inpatient PUF (Provider+Service) | ccn, drg_code, year | No |
| `raw.cms_outpatient_puf` | Outpatient PUF | ccn, apc_code, year | No |
| `raw.cms_hospital_quality` | Hospital Quality Star Ratings | ccn | No |
| `raw.cms_drg_weights` | DRG Relative Weights | drg_code, year | No |
| `raw.ancc_magnet` | ANCC Magnet Recognition | facility_id | No |
| `raw.cms_hcpcs_level2` | HCPCS Level II Codes | hcpcs_code | No |
| `raw.fda_ndc` | FDA NDC Directory | ndc_code | No |
| `raw.cms_part_d_spending` | Part D Spending by Drug | drug_name, year | No |
| `raw.cms_part_b_spending` | Part B Spending by Drug | drug_name, year | No |
| `raw.cms_formulary` | Part D Formulary Files | plan_id, drug_name, year | No |
| `raw.cms_rbcs` | Restructured BETOS Classification | hcpcs_code | No |
| `raw.cms_price_lookup` | Medicare Procedure Price Lookup | hcpcs_code, modifier, area | No |
| `raw.usp_drug_class` | USP Drug Classification | usp_id | No |
| `raw.cms_nucc_taxonomy` | NUCC Taxonomy Codes | taxonomy_code | No |
| `raw.cms_geographic_variation` | Geographic Variation PUF | geo_level, geo_code, year | No |
| `raw.cms_chronic_conditions` | Chronic Conditions PUF | geo_code, condition, year | No |
| `raw.cms_post_acute` | Post-Acute Care PUFs | ccn, type, year | No |
| `raw.cms_dmepos` | DMEPOS by Supplier | npi, hcpcs_code, year | No |
| `raw.ddinter` | DDInter 2.0 | interaction_id | No |
| `raw.stabilis` | Stabilis 4.0 | entry_id | No |
| `raw.cms_medicaid_pdl` | Medicaid Preferred Drug Lists | state, drug_name, year | No |
| `raw.cms_cost_reports` | HCRIS Cost Reports (Worksheet S-3/A) | ccn, report_year | No |
| `raw.cms_inpatient_puf_summary` | Inpatient Hospitals Summary PUF (by Provider) | ccn, year | No |
| `raw.nlm_rxnorm` | NLM RxNorm Bulk Files | rxcui | No |
| `raw.cms_synpuf` | CMS DE-SynPUF Synthetic Claims | beneficiary_id | No |
| `raw.pbm_formulary` | PBM Public Formularies (CVS/Express/Optum) | pbm, drug_name, year | No |
| `raw.insurer_directories` | Insurer Provider Directories (Aetna/BCBS/UHC) | npi, insurer | No |
| `raw.conference_abstracts` | Conference Abstracts (ASCO/AHA/ESMO/ASH) | abstract_id | No |
| `raw.pharmgkb` | PharmGKB Pharmacogenomics | gene, drug | No |
| `raw.psyhamm_offlabel` | PSYHAMM/HeTOP Off-Label Indications | drug, indication | No |
| `raw.drug_allergy_crossref` | Drug-Allergy Cross-Sensitivity Tables | drug_class, allergen | No |
| `raw.state_apcd` | State APCD Claims (pilot states) | state, claim_id | No |

### Silver Layer Tables

| Table | Unique Key | Sources |
|-------|-----------|---------|
| `silver.providers` | `npi` | NPPES + Care Compare + Physician PUF Summary |
| `silver.healthcare_facilities` | `ccn` | Provider of Services + Hospital Quality + ANCC Magnet |
| `silver.prescribing_profiles` | `(npi, drug_name, year)` | Part D Prescribers |
| `silver.procedure_profiles` | `(npi, hcpcs_code, year)` | Physician PUF |
| `silver.open_payments` | `(record_id)` | Open Payments |
| `silver.health_systems` | `(organization_npi)` | PECOS + CHOW + Facility Affiliation |
| `silver.facility_service_lines` | `(ccn, service_line, year)` | Inpatient PUF DRG volumes + POS |
| `silver.drug_market` | `(drug_name, year)` | Part D Spending + Part B Spending + NDC + Formulary + USP + RBCS |
| `silver.geographic_analytics` | `(geo_level, geo_code, year)` | Geographic Variation + Chronic Conditions |
| `silver.drug_allergy_crossref` | `(drug_class, allergen_class)` | Published cross-reactivity tables + ATC hierarchy + ChEMBL similarity |
| `silver.dose_ranges` | `(drug_name, indication)` | DailyMed SPL XML + FDA label LLM extraction |
| `silver.offlabel_indications` | `(drug_name, indication)` | PSYHAMM/HeTOP + NCCN + ClinicalTrials.gov |
| `silver.pharmacogenomics` | `(gene, drug)` | PharmGKB + DrugBank |
| `silver.alert_rules` | `(rule_id)` | ONCHigh (15 rules) + Phansalkar (33 rules) + FAERS signals |
| `silver.equipment_inventory` | `(ccn, equipment_type)` | POS capability flags + DRG inference |
| `silver.conference_activity` | `(npi, abstract_id)` | ASCO/AHA/ESMO/ASH abstracts linked to NPIs |

**Reference Tables** (ontology-replacement lookup tables — see Integration Audit § Ontology Assessment):

| Table | Unique Key | Sources |
|-------|-----------|---------|
| `silver.drg_service_line_mapping` | `(drg_code)` | CMS DRG weights → ~30 service line categories (ServiceLineInferenceAgent context) |
| `silver.hcpcs_equipment_mapping` | `(hcpcs_code)` | HCPCS codes → equipment categories (EquipmentInventoryAgent context) |
| `silver.nucc_taxonomy` | `(taxonomy_code)` | ~900 NUCC codes → specialty descriptions (provider specialty normalization) |

### Gold Layer Tables

| Table | Product | Description |
|-------|---------|-------------|
| `gold.provider_profile` | HCP Compass | Provider demographics + top drugs + top procedures + MIPS scores + payments. Includes both `individual` and `organization` entity types via `entity_type TEXT`. |
| `gold.facility_profile` | HCO Navigator | Facility demographics + DRG volumes + quality ratings + system affiliation + service lines + Magnet status |
| `gold.drug_market_profile` | Lumina | Drug spending + formulary coverage + classification + top prescribers |
| `gold.market_analytics` | SageAI | Geographic population + spending + conditions + provider density |
| `gold.provider_network` | All products | Organizational affiliations + inferred referral pairs. Columns: `source_npi`, `dest_npi`, `relationship_type`, `confidence_score`. Filter `WHERE confidence_score >= 0.50` for downstream. |

---

## Requirements *(mandatory)*

### Functional Requirements

**Provider Data (FR-001 through FR-005)**

- **FR-001**: System MUST ingest the full CMS NPPES monthly dataset (8M+ NPIs) via bulk CSV download. System MUST support real-time single-NPI lookups via the NPI Registry REST API (`https://npiregistry.cms.hhs.gov/api/`, no authentication required). Chunked reading MUST be used for the 9.3 GB CSV file (`chunksize=50000`).
- **FR-002**: System MUST ingest CMS Part D Prescriber PUF (Provider+Drug level, ~25M records/year) and Provider Summary PUF (~1.2M/year). System MUST support queries by NPI or drug name. Data available via data.cms.gov Socrata-style API and bulk CSV. Raw and bronze tables MUST use PostgreSQL range partitioning by year.
- **FR-003**: System MUST ingest CMS Physician/Supplier PUF (Provider+Service level, ~10M records/year) and Provider Summary (~1.2M/year). System MUST support queries by NPI or HCPCS code. Raw and bronze tables MUST use PostgreSQL range partitioning by year.
- **FR-004**: System MUST ingest CMS Open Payments data (80M+ total records). System MUST support queries by physician NPI or company name. Annual release in June. MUST include general payments, research payments, and ownership interests.
- **FR-005**: System MUST ingest CMS Care Compare provider-level data (1M+ records). MUST include MIPS scores, quality attestation, and patient experience measures. Bi-monthly refresh cadence.

**Facility Data (FR-006 through FR-015)**

- **FR-006**: System MUST ingest CMS Provider of Services (POS) file containing ~6K hospitals with detailed facility characteristics: bed count, ownership type, service capabilities, teaching status, and accreditor field (TJC/DNV/HFAP — serves as Joint Commission workaround for accreditation status without requiring separate TJC API). Chain ID field identifies chain ownership but does NOT provide full parent-child hierarchy. Quarterly refresh.
- **FR-007**: System MUST ingest CMS PECOS enrollment data (1.5M enrollments) to establish provider-to-organization affiliations and build IDN hierarchies. Quarterly refresh.
- **FR-008**: System MUST ingest CMS CHOW data tracking hospital mergers, acquisitions, and ownership transfers. Used to build temporal ownership timelines for health systems.
- **FR-009**: System MUST ingest CMS Facility Affiliation data linking facilities to parent organizations. Combined with PECOS and CHOW for complete IDN hierarchy construction.
- **FR-010**: System MUST ingest CMS Inpatient PUF at provider+DRG level (~200K records/year). MUST provide DRG-level discharge volumes, average charges, and average Medicare payments per hospital.
- **FR-011**: System MUST ingest CMS Outpatient PUF at provider+APC level. MUST provide outpatient procedure volumes and charges per facility.
- **FR-012**: System MUST ingest CMS Hospital Quality Star Ratings for 4K+ hospitals. MUST include overall star rating and domain scores (mortality, readmission, safety, patient experience, timely care). Quarterly refresh.
- **FR-013**: System MUST ingest CMS DRG relative weight table (772 DRGs). MUST provide case mix index components and average length of stay. Annual refresh aligned with CMS fiscal year.
- **FR-014**: System MUST ingest ANCC Magnet-designated hospital list (~600 hospitals) via web scraping of the ANCC public listing, with monthly verification. MUST enrich `gold.facility_profile` with Magnet designation status. Web scrape approach may require maintenance if ANCC changes site structure.
- **FR-015**: System MUST ingest CMS HCPCS Level II code descriptions for non-physician services (DME, ambulance, prosthetics). Reference table for procedure code lookups.

**Drug & Market Data (FR-016 through FR-025)**

- **FR-016**: System MUST ingest FDA National Drug Code Directory (300K+ products) via openFDA API (`https://api.fda.gov/drug/ndc.json`). MUST provide drug product details: manufacturer, dosage form, route, strength, package descriptions. OPENFDA_API_KEY optional.
- **FR-017**: System MUST ingest CMS Part D Spending by Drug dataset (~5K drugs). MUST provide aggregate Medicare spending, utilization, and cost-per-unit at the drug level. Annual release.
- **FR-018**: System MUST ingest CMS Part B Spending by Drug dataset (~500 drugs). MUST cover physician-administered drugs with average payment per dose. Annual release.
- **FR-019**: System MUST ingest CMS Part D Formulary Files covering all Part D plan formularies. MUST enable formulary coverage analysis (which plans cover which drugs, at what tier). Annual release.
- **FR-020**: System MUST ingest CMS Restructured BETOS Classification System mapping all HCPCS/CPT codes to standardized service categories. Reference table for procedure analytics.
- **FR-021**: System MUST ingest CMS Procedure Price Lookup providing Medicare reimbursement rates by HCPCS code, modifier, and geographic area. Annual release.
- **FR-022**: System MUST ingest USP Drug Classification System (2,055 drugs) providing therapeutic class hierarchy. Supplements ATC classification for drug market segmentation.
- **FR-023**: System MUST ingest NUCC Healthcare Provider Taxonomy codes (~900 codes). MUST provide specialty/sub-specialty descriptions for taxonomy codes found in NPPES. Semi-annual refresh.
- **FR-024**: System MUST ingest CMS Geographic Variation PUF with 200+ variables at state, HRR, and county levels. MUST cover spending, utilization, and quality metrics per geography. Annual release.
- **FR-025**: System MUST ingest CMS Chronic Conditions PUF providing disease prevalence rates by geography and demographic group. MUST cover 21 chronic conditions. Annual release.

**Population & Clinical Data (FR-026 through FR-031)**

- **FR-026**: System MUST ingest CMS Post-Acute PUFs covering SNF, HHA, and Hospice facilities. MUST provide quality measures and utilization data. Annual release.
- **FR-027**: System MUST ingest CMS DMEPOS Utilization by Referring Provider dataset. MUST provide DME referral volumes by NPI. Annual release.
- **FR-028**: System MUST ingest DDInter 2.0 database (302K severity-graded drug-drug interactions). MUST cache full dataset locally and operate in offline mode when API is unreachable. MUST support bidirectional interaction lookup.
- **FR-029**: System MUST ingest Stabilis 4.0 database (11.5K IV compatibility entries). MUST provide IV drug compatibility/incompatibility data for clinical decision support.
- **FR-030**: System MUST ingest CMS State Medicaid PDLs providing state-level formulary/preferred drug lists. Supplements Part D formulary data with Medicaid coverage.
- **FR-031**: System MUST extend existing `journal_rss` and `medical_news` fetchers to include Becker's Hospital Review, FierceHealthcare, Modern Healthcare, and Google News RSS (healthcare topic filter) feeds. No new fetchers — add feed URLs to existing configuration.

**HCRIS Cost Reports (FR-042)**

- **FR-042**: System MUST ingest CMS HCRIS cost report data (Worksheet S-3/A staffing sections) for ~3K hospitals. MUST provide raw staffing line items (FTE counts by cost center) as input for the StaffingDecomposition Agent (FR-038). Available as bulk CSV from CMS. Annual release. Raw table: `raw.cms_cost_reports`.

**Additional Data Sources (FR-043 through FR-059)**

- **FR-043**: System MUST ingest CMS Inpatient Hospitals Summary PUF (one row per CCN, ~3K+ hospitals/year). MUST provide hospital-level total discharges, patient demographics (age, sex, race), chronic condition prevalence, and average HCC risk scores. Separate from the detail PUF (FR-010) which provides DRG-level data. Available via data.cms.gov Socrata API. Annual release. Raw table: `raw.cms_inpatient_puf_summary`. Feeds into `silver.healthcare_facilities` and `gold.facility_profile`.
- **FR-044**: System MUST ingest NLM RxNorm bulk files (free UMLS account required) for comprehensive drug normalization and ATC cross-walk. MUST provide RxCUI-to-NDC mapping, RxCUI-to-ATC classification, and ingredient-level normalization. Supplements the RxNorm REST API path used for WHO ATC (source #26). Monthly refresh. Raw table: `raw.nlm_rxnorm`.
- **FR-045**: System MUST geocode provider practice addresses from NPPES using a free geocoding service (Nominatim/OpenStreetMap or Google Geocoding API free tier). MUST produce latitude/longitude coordinates for provider practice locations. Required as input for the ReferralNetwork agent's (FR-037) geographic proximity calculations. Batch geocoding during monthly NPPES refresh. Output updates `silver.providers` with `latitude` and `longitude` columns.
- **FR-046**: System MUST ingest PBM public formulary lists from CVS Caremark, Express Scripts, and OptumRx standard commercial formularies. MUST provide commercial (non-Medicare) formulary tier status to supplement CMS Part D Formulary Files (FR-019, Medicare only). Quarterly refresh. Raw table: `raw.pbm_formulary`. Feeds into `silver.drug_market` and `gold.drug_market_profile`.
- **FR-047**: System MUST implement an Equipment Inventory Inference pipeline using CMS POS service capability flags (MRI/CT/PET capability codes) combined with DRG volume inference (high-volume cardiac DRGs → cath lab presence, high-volume neuro DRGs → MRI availability) to estimate binary equipment presence (has/doesn't have) for major medical equipment categories. Target ~50-60% binary presence accuracy for: MRI, CT, PET, cath lab, linear accelerator, surgical robot. Output populates `silver.equipment_inventory` and enriches `gold.facility_profile`.
- **FR-048**: System MUST ingest conference abstracts from ASCO Meeting Library (free account required, 10K+ abstracts/year), AHA Scientific Sessions, ESMO Congress, and ASH Annual Meeting. MUST link abstracts to provider NPIs using author name + institutional affiliation matching against NPPES (with confidence scoring per EC-14). Extends existing PubMed conference proceedings pipeline in dk-data-fe. Annual refresh per conference. Raw table: `raw.conference_abstracts`. Output populates `silver.conference_activity` for KOL identification in HCP Compass.
- **FR-049**: System MUST ingest CMS DE-SynPUF synthetic Medicare claims data (2008-2010, also available in OMOP format on AWS Marketplace, free). MUST provide synthetic patient-level claims for development, testing, and demo environments. Static dataset — one-time load. Raw table: `raw.cms_synpuf`. Used for end-to-end pipeline testing and SageAI patient journey demos before real PUF data is loaded.
- **FR-050**: System MUST cross-reference provider contact information against publicly available insurer provider directories (Aetna, BCBS, UHC public provider search pages). MUST provide phone number and address triangulation as an additional verification source for the ContactVerification pipeline (FR-036). Multi-source triangulation (NPPES + Google Places + USPS + insurer directories) flags stale numbers with higher confidence. Monthly verification cadence. Raw table: `raw.insurer_directories`.
- **FR-051**: System MUST extract provider email addresses from PubMed author correspondence fields for academic physicians. MUST link emails to NPIs via author name + institutional affiliation matching against NPPES. Expected coverage: ~25-35% of all providers, ~80%+ of academic/research physicians. Extends existing PubMed pipeline in dk-data-fe. Monthly refresh. Output updates `silver.providers` with `email` and `email_source` columns.
- **FR-052**: System MUST build drug-allergy cross-sensitivity mappings from published cross-reactivity tables (UC Davis, Vancouver Coastal Health, UNMC — all freely available), ATC hierarchy for class-level allergies (e.g., penicillins → all beta-lactams), and ChEMBL structural similarity (Tanimoto coefficient, free API). MUST map cross-sensitivity relationships with SNOMED-to-ICD-10-CM crosswalk (free from NLM). Target ~80-90% coverage of clinically relevant drug-allergy mappings. Raw table: `raw.drug_allergy_crossref`. Output populates `silver.drug_allergy_crossref`.
- **FR-053**: System MUST extract computable dose range tables from DailyMed SPL XML structured dosing sections (existing Tier 3 code in dk-data-fe — enable and extend in this feature). For drugs where structured data is unavailable, MUST use LLM extraction (Claude Haiku) of min/max/unit from FDA label DOSAGE AND ADMINISTRATION text. Target ~70% coverage of approved indications. Output populates `silver.dose_ranges`.
- **FR-054**: System MUST ingest off-label drug indication data from PSYHAMM/HeTOP (18,000+ off-label drug-indication entries, free academic database) and NCCN Compendium (oncology off-label, free summaries). MUST cross-reference with ClinicalTrials.gov (AACT, already in dk-data-fe) for investigational dosing context. Target ~70-80% coverage for common off-label uses. Raw table: `raw.psyhamm_offlabel`. Output populates `silver.offlabel_indications`.
- **FR-055**: System MUST implement alert fatigue filtering using the ONCHigh list (15 high-priority DDI rules from published expert consensus) and Phansalkar list (33 non-interruptive DDI rules). Combined lists cover ~80% of high-value clinical alert curation decisions. MUST integrate FDA FAERS signal detection for emerging safety concerns (FAERS data available free via openFDA API, already partially in dk-data-fe). Output populates `silver.alert_rules`.
- **FR-056**: System MUST ingest PharmGKB pharmacogenomics data (free academic license) covering clinically actionable gene-drug interactions (CYP2D6, CYP2C19, CYP3A4, DPYD, UGT1A1, etc.). MUST provide variant-level drug response annotations and clinical guideline recommendations. Supplements existing DrugBank pipeline. Quarterly refresh. Raw table: `raw.pharmgkb`. Output populates `silver.pharmacogenomics`.
- **FR-057**: System MUST re-enable the existing ORCID pipeline in dk-data-fe (currently disabled). MUST provide academic researcher profiles with publication counts, institutional affiliations, and ORCID identifiers. MUST link ORCID profiles to provider NPIs for KOL identification in HCP Compass. Free API, no authentication required for public profiles.
- **FR-058**: System MUST design and implement the State APCD ingestion framework for all-payer claims data from 10+ states: Massachusetts (CHIA), Colorado (CIVHC), Oregon, Vermont (VHCURES), New Hampshire, Maine, Maryland (HSCRC), Minnesota, Connecticut, Utah. Initial implementation: generic framework + 2-3 pilot states. Each state requires a separate Data Use Agreement (DUA). MUST handle ERISA exemption gaps (see EC-12). Provides all-payer patient-level claims as a partial free alternative to commercial claims vendors ($25K-$5.5M/yr). Raw table: `raw.state_apcd` (partitioned by state).
- **FR-059**: System MUST include POS accreditor field (TJC/DNV/HFAP) in `bronze.cms_provider_of_services` extraction as a Joint Commission workaround. CMS POS file's accreditor field identifies accreditation body (The Joint Commission, DNV GL, Healthcare Facilities Accreditation Program) without requiring separate Joint Commission bulk API access. This field enriches `gold.facility_profile` with accreditation status.

**Platform Infrastructure (FR-032 through FR-041)**

- **FR-032**: System MUST extend `BaseMCPTool._fetch_external()` to support query parameters beyond `drug_name`. Each adapter's `build_url()` MUST handle parameter extraction (`npi`, `provider_name`, `facility_id`, etc.) from the generic `params` dict. The change MUST be backward-compatible with existing adapters.
- **FR-033**: System MUST add `refresh_provider(npi, source_name, api_response)` and `refresh_facility(ccn, source_name, api_response)` methods to `SilverGoldRefresher`. Provider resolution MUST use NPI (canonical, no fuzzy matching needed). Facility resolution MUST use CCN.
- **FR-034**: System MUST implement a Service Line Inference Agent using Claude SDK that infers hospital service lines from DRG discharge volumes and POS service capability codes. MUST run monthly on ~6K hospitals. MUST use `claude-haiku-4-5-20251001` via the cluster LiteLLM proxy (`http://litellm.infra.svc.cluster.local:4000`) for cost efficiency and unified LLM access. Output MUST populate `silver.facility_service_lines`.
- **FR-035**: System MUST implement an IDN Hierarchy Construction Agent using Claude SDK that builds Integrated Delivery Network hierarchies from PECOS enrollment + CHOW M&A events + Facility Affiliation data + SEC EDGAR public filings (already in dk-data-fe, used for public health system executive listings and organizational structure). MUST resolve conflicting parent organizations and construct multi-level system trees. Output MUST populate `silver.health_systems`.
- **FR-036**: System MUST implement a Contact Verification Pipeline that verifies provider contact information from NPPES against Google Places API (phone verification, free tier) and USPS Address Validation API (address standardization). MUST update `silver.providers` with verification status and confidence scores.
- **FR-037**: System MUST implement a Referral Network Inference Agent using Claude SDK that infers provider-to-provider referral relationships from: (1) geographic proximity of providers sharing diagnosis patterns, (2) Post-Acute PUF facility-level referral volumes, (3) DMEPOS referring provider NPI data, (4) PECOS/Facility Affiliation organizational linkages. MUST produce `confidence_score` (0-1) per inferred edge. Monthly cadence. Output MUST populate `gold.provider_network`. MUST use `claude-haiku-4-5-20251001`.
- **FR-038**: System MUST implement a Staffing Decomposition Agent using Claude SDK that decomposes HCRIS staffing data (Worksheet S-3/A) into structured staffing categories, supplemented by BLS Occupational Employment and Wage Statistics (OEWS) occupational mix ratios for staffing decomposition. HCRIS provides ~60-70% overall coverage (~80% nursing); BLS OEWS improves departmental breakdown accuracy. Monthly cadence. Output MUST enrich silver-layer facility staffing fields.
- **FR-039**: System MUST register all ~47 new data sources in `meta.data_sources` with: source name, description, URL, refresh cadence, last fetch timestamp, record count, data quality score. MUST enable freshness monitoring via existing Prometheus metrics.
- **FR-040**: System MUST add entity-level Prometheus gauges: `dk_providers_total` (by entity_type), `dk_facilities_total` (by facility_type), `dk_provider_verification_rate` (by verification_type), `dk_idn_systems_total`. Existing `dk_data_source_*` freshness/staleness metrics MUST auto-cover new sources when registered.
- **FR-041**: System MUST create CronJob manifests for all data sources with appropriate refresh cadences: monthly (NPPES, Magnet), quarterly (POS, PECOS, CHOW, Hospital Quality), annual (Part D, Physician PUF, Open Payments, Drug/Market sources), bi-monthly (Care Compare), daily (FDA NDC via openFDA).

### Key Entities

- **Provider**: Canonical key: NPI (National Provider Identifier, 10-digit, Luhn-validated). Source of truth: NPPES (demographics), supplemented by Care Compare (quality), Physician PUF (procedures), Part D (prescribing), Open Payments (industry payments). Entity types: `individual` (Type 1 NPI), `organization` (Type 2 NPI) — stored as text values in `entity_type` column.
- **Facility**: Canonical key: CCN (CMS Certification Number, 6-character alphanumeric). Source of truth: Provider of Services (demographics), supplemented by Hospital Quality (ratings), Inpatient PUF (DRG volumes), ANCC (Magnet status). Types: short-term acute care, critical access, long-term care, psychiatric, rehabilitation, children's.
- **Health System (IDN)**: Canonical key: Organization NPI (Type 2). Constructed from PECOS enrollments + CHOW ownership transfers + Facility Affiliation links. Hierarchy: System → Sub-system → Individual facility.
- **Drug Product**: Canonical key: NDC (National Drug Code, 10-digit). Cross-references: generic name (links to existing molecule pipeline), ATC code, USP class, RBCS category. Market data: Part D spending, Part B spending, formulary coverage, prescriber volumes.
- **Geographic Unit**: Levels: State (FIPS code), Hospital Referral Region (Dartmouth HRR), County (FIPS). Data: population demographics, spending per capita, chronic condition prevalence, provider/facility density.
- **Agent Execution Log**: Audit record for every Claude SDK agent invocation. Tracks agent name, execution timestamps, records processed/written/quarantined, model used, token count, estimated cost, and status.
- **Agent Quarantine**: Low-confidence agent outputs routed for human review. Entity key, entity type, raw LLM output, confidence score, rejection reason, review status.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All ~47 data sources enumerated in this spec have operational fetchers, source loaders, raw/bronze tables, and catalog entries in `meta.data_sources`.
- **SC-002**: `gold.provider_profile` contains records for 1M+ active NPIs with at least 3 of 5 data facets populated (demographics, prescribing, procedures, quality, payments).
- **SC-003**: `gold.facility_profile` contains records for 4K+ hospitals with demographics, DRG volumes, quality ratings, and system affiliation.
- **SC-004**: `gold.drug_market_profile` contains records for 5K+ drugs with spending data, formulary coverage, and at least one classification (USP, ATC, or RBCS).
- **SC-005**: Provider/facility MCP tool invocations return within 3s (cached) / 8s (cold) for single-entity queries, consistent with existing molecule tool SLAs.
- **SC-006**: Annual PUF ingestion CronJobs (Part D: 25M rows, Physician PUF: 10M rows, Open Payments: 15M rows/year) complete without OOM errors or data corruption. Initial historical backfill loads all available years (~10 years; ~250M Part D rows, ~100M Physician PUF rows total) using year-partitioned tables.
- **SC-007**: All data sources maintain freshness within their documented cadence (monthly sources < 35 days stale, quarterly < 100 days, annual < 400 days) as measured by `dk_data_source_freshness_seconds` Prometheus metric.
- **SC-008**: `silver.health_systems` correctly represents IDN hierarchies for the top 50 US health systems (by bed count) with at least 2 levels of hierarchy (system → facility).
- **SC-009**: `silver.providers` achieves >50% phone verification and >70% address verification for providers with active NPIs in the top 10 states by provider count, within 6 months of pipeline deployment.
- **SC-010**: All data powering HCP Compass, HCO Navigator, Lumina, and SageAI product features is sourced exclusively from free public data — no IQVIA, Definitive Healthcare, Komodo Health, or Veeva subscriptions required for core functionality.
- **SC-011**: All new data sources emit `dk_data_source_freshness_seconds` and `dk_data_source_staleness_seconds` metrics. Entity-level gauges (`dk_providers_total`, `dk_facilities_total`) are visible in Prometheus.
- **SC-012**: Existing molecule pipeline (DrugBank, openFDA labels, ClinicalTrials, WHO ICD-11, etc.) continues to function without regression. No existing MCP tools break or change behavior.

---

## Product Coverage Estimates

These estimates quantify how much of each product's data needs are covered by free public sources (no vendor subscriptions). Based on cross-product analysis from the original data source availability study.

| Product | Free Coverage | What's Covered | What's Missing (requires commercial claims) |
|---------|-------------|----------------|----------------------------------------------|
| **HCP Compass** | **~80%** | NPI-level prescribing (Part D) + procedure volumes (Physician PUF) per-drug, per-CPT. MIPS quality, industry payments, KOL profiles, publications, trials. | Commercial claims (<65 population): non-Medicare prescribing + procedure volumes (~35% of population). |
| **HCO Navigator** | **~90%** | CCN-level DRG volumes (Inpatient PUF) + financials (HCRIS) + outpatient APC volumes. System hierarchy via PECOS/CHOW. Quality ratings, Magnet status, service lines. | Commercial payer mix at facility level. |
| **Lumina** | **~50%** | Medicare drug spending (Part D/B) + formulary coverage (Part D plans) + geographic variation. Drug classification (USP, ATC, RBCS). NDC details. | Commercial formulary data, non-Medicare drug market volumes. PBM formularies (FR-046) partially address this gap. |
| **SageAI** | **~75%** | 18 of 24 query types answerable. All PUFs queryable via PostgREST. Drug, publication, trial, KOL, safety, regulatory, patent, financial, news. | Patient-level longitudinal queries, commercial claims cross-setting analytics. State APCDs (FR-058) partially address this gap. |

**Key insight**: The only truly irreplaceable paid data is commercial claims for the <65 population. Everything else — provider contacts, hospital data, clinical drug content, formulary tiers — is buildable from free sources.

---

## Scope

### In Scope

- ~54 free CMS/FDA/NLM/academic data sources across 9 phases (Provider, Facility, Drug/Market, Population, Clinical, News, Advanced Clinical, Contact Enrichment, Workforce Data) — ~36 new data sources requiring new fetchers/adapters + ~7 extensions to existing fetchers/pipelines + ~5 re-enablements of existing dk-data-fe pipelines + ~6 RSS/reference-only integrations
- 6 SQL migrations creating silver entity tables, gold aggregate tables, raw/bronze tables, and agent infrastructure
- ~40 MCP adapters, ~35 fetchers, ~35 source loaders
- ~35 bronze SQLMesh models, 16 silver models, 5 gold models
- ~35 bronze transformer handlers
- `BaseMCPTool` generic parameter handling (backward-compatible)
- `SilverGoldRefresher` provider/facility refresh methods
- `config/cms_datasets.py` shared CMS Socrata dataset ID constants (prevents duplication between MCP adapters and batch fetchers)
- `CMSSocrataFetcher` shared base class for Socrata-pattern sources
- `BaseAgent` + `AgentRegistry` + `Runner` CLI for agentic processing
- 6 Claude SDK agents (ServiceLineInference, IDNHierarchy, ReferralNetwork, ContactVerification, StaffingDecomposition, EquipmentInventoryInference)
- PostgREST `gold` schema exposure with analyst JWT
- ~47 Kubernetes CronJob manifests (~41 data sources + 6 agents)
- `tool_registry.py` Tiers 4-6 (~40 ToolDefinitions)
- Prometheus metrics for providers, facilities, agents
- `meta.data_sources` catalog entries for all new sources
- Rate limits configuration for all new sources
- Tests for adapters, fetchers, agents
- Provider address geocoding pipeline
- NPPES V2 format support (mandatory from 2026-03-03)

### Out of Scope

- Commercial data vendor integrations (IQVIA, Definitive Healthcare, Komodo Health, Veeva) — the entire purpose of this feature is to replace these
- ML/computed data sources (ESM-2, Chemprop, PubMedBERT, ADMET-AI)
- Admin App UI for managing CMS data sources
- Real-time streaming ingestion (all sources are batch/API)
- Changes to existing molecule pipeline behavior
- PostgREST API changes beyond adding `gold` to schemas
- Procurement of commercial API keys (Google Places, USPS registrations are free-tier)
- ZoomInfo web scraping (admin/exec contacts, not clinical data — ToS concerns)
- Social media data extraction (Twitter/X, LinkedIn, ResearchGate — ToS restrictions, low value)
- Full Trissel's IV compatibility replacement (Stabilis 4.0 covers ~40-60%)
- National all-payer claims aggregation (State APCDs are per-state with ERISA gaps)

### Engineering Effort Estimate

Total estimated engineering effort: **~20-27 weeks** (based on original data source availability analysis). Breakdown by reverse-engineering target:

| Build Target | Effort | Coverage |
|---|---|---|
| CMS PUF ingestion pipeline (12+ PUFs) | 2-3 weeks | 100% for our products |
| AHA Survey replacement (~80-85%) | 3-4 weeks | Service lines, staffing, equipment |
| Definitive HC provider intel (~60-70%) | 4-6 weeks | Provider/facility profiles, IDN hierarchy |
| CarePrecise replacement | 1-2 weeks | Enriched NPPES + geocoding |
| News aggregation (RSS + NLP) | 1 week | Same-day coverage from top 20 publications |
| Formulary + clinical drug content (~90-95%) | 2-3 weeks | DDInter + FDA labels + Stabilis + formulary |
| Contact verification ("Poor Man's Veeva", ~65-85%) | 3-4 weeks | Phones 65-70%, addresses 80-85%, affiliations 75-80% |
| Advanced clinical features | 2-3 weeks | Drug-allergy, dose ranges, off-label, pharmacogenomics |
| State APCD framework | 2-3 weeks | Framework + 2-3 pilot states |

---

## Clarifications

### Session: 2026-03-01

- Q: Should new sources use separate schemas (e.g., `prov_raw`, `fac_raw`) or extend existing `raw`/`bronze`/`silver`/`gold`? → A: Extend existing schemas. CMS sources like `inpatient`, `hospital_info`, and `cost_reports` already use `raw.*`. Creating separate schemas would fragment the pipeline. One set of schemas, many tables.
- Q: How should the system handle the 9.3 GB NPPES CSV file? → A: Chunked pandas reading with `chunksize=50000`. Fetcher must support resume-on-failure. Monthly CronJob with a generous timeout (8h). Bulk CSV download preferred over paginated API calls for initial load.
- Q: What is the entity resolution strategy for providers? → A: NPI is a government-issued unique identifier — no fuzzy matching needed (unlike molecules). Simple lookup by NPI. For name-based searches, use NPPES first/last name fields with prefix matching. Deactivated NPIs tracked but excluded from default results.
- Q: How should the Part D PUF's 25M records/year be handled? → A: Batch inserts with `executemany()`, commit every 10K rows. Table partitioning by year for query performance. Annual refresh — full year replacement, not incremental updates within a year.
- Q: What is the refresh strategy for gold-layer profiles? → A: Gold tables refreshed via `silver_gold_refresher.py`, triggered either by MCP tool invocations (on-demand for specific NPI/CCN) or by post-ingestion batch refresh (after CronJob loads new data). Each gold record tracks `_refreshed_at` and per-source freshness timestamps.
- Q: How do agentic processing tasks fit into the pipeline? → A: Claude SDK agents run as post-processing steps, NOT in the hot MCP invoke path. Monthly CronJobs. Use `claude-haiku-4-5-20251001` via the cluster LiteLLM proxy (`http://litellm.infra.svc.cluster.local:4000`) for cost efficiency and unified LLM management. ~6K hospitals per service line inference run. Results written to silver tables, then propagated to gold.
- Q: Should DDInter/Stabilis be treated as real-time APIs or cached datasets? → A: Cached datasets. Both are academic resources with unreliable API availability. Full dataset downloaded and cached locally. Fetcher operates in offline mode when API is unreachable. Refresh quarterly or when new versions are published.
- Q: What is the data access control model for CMS PUF provider/payment data exposed via PostgREST? → A: Raw/bronze/silver internal only; gold tables exposed via PostgREST with existing RBAC (analyst JWT required).
- Q: Should large PUF tables (Part D, Physician PUF) use PostgreSQL range partitioning by year? → A: Yes, partition by year at raw + bronze layer for Part D and Physician PUF.
- Q: Should `gold.provider_profile` include both Type 1 and Type 2 NPIs? → A: Both types, distinguished by `entity_type` column using text values (`individual`, `organization`).
- Q: Why do annual PUF sources (Part D, Physician PUF) have weekly CronJob schedules? → A: Weekly schedule checks CMS for new annual releases; downloads only when new data is detected. Annual PUFs are full-year replacement, not incremental within-year updates. Weekly polling ensures fast detection of new releases.
- Q: Why do hospital counts vary across sources (~6K, ~4K, ~3K)? → A: Hospital counts are source-dependent. Provider of Services (POS) lists ~6K hospitals total. Hospital Quality covers ~4K with star ratings. HCRIS cost reports cover ~3K with detailed staffing data. Not all hospitals appear in all sources.
- Q: How many years of historical PUF data should be loaded at initial deployment? → A: All available (~10 years). Complete history for maximum trend depth.
- Q: What is the NPPES V2 format transition? → A: CMS mandates Version 2 CSV format starting 2026-03-03. V2 has different column headers and field ordering from V1. The NPPES fetcher MUST detect the format version and parse accordingly. Test with V2 files before deployment.
- Q: What is the actual CMS data.cms.gov API rate limit? → A: CMS/Socrata documentation states ~10K req/sec. Practical sustained throughput is ~1-5K req/sec depending on query complexity. The original EC-7 figure of "~1000 req/hr" was incorrect. openFDA APIs have a separate limit of 240 req/min without an API key.
- Q: What data does the POS Chain ID field provide? → A: Chain ID indicates chain ownership (binary has-chain/no-chain + chain ID number). It does NOT provide full parent-child IDN hierarchy. Full hierarchy requires PECOS reassignment + CHOW + Facility Affiliation + SEC EDGAR.
- Q: What is the Joint Commission data workaround? → A: No Joint Commission bulk API is available. However, the CMS POS file contains an accreditor field that identifies TJC/DNV/HFAP accredited facilities. This field is extracted in bronze.cms_provider_of_services (FR-059) as a free alternative.
- Q: Why are advanced clinical features (drug-allergy, dose ranges, off-label, pharmacogenomics) included? → A: While the original analysis notes "for our products, we don't need even this" (referring to EHR-level clinical decision support), these features add clinical depth to Lumina and SageAI. Prioritized as P3 — implement after core sources. DDInter 2.0 provides 302K severity-graded DDI pairs (25x more than FDB's 12K monographs), and free academic databases cover ~90-95% of FDB/Elsevier/Medi-Span capabilities.
- Q: What are State APCDs and why are they included? → A: State All-Payer Claims Databases provide real all-payer claims (commercial + Medicaid + Medicare) for individual states. Available free or low-cost with Data Use Agreements. 10+ states have programs. ERISA exemption means self-insured employer plans (30-60% of commercially insured) may be missing. Included as a partial free alternative to commercial claims vendors before committing to national vendor contracts.
- Q: Which existing dk-data-fe pipelines are re-enabled or extended? → A: SEC EDGAR (IDN hierarchy input), PubMed (author emails, conference abstracts), ORCID (re-enable disabled pipeline), journal_rss (add Google News + Modern Healthcare feeds), medical_news (add Becker's + FierceHealthcare feeds), DailyMed SPL XML (enable Tier 3 for dose range extraction).
- Q: How should `gold.provider_network` be scoped? → A: Phase 1: affiliations (PECOS/Facility Affiliation/Care Compare) + inferred referrals (geographic proximity + Post-Acute PUF volumes + DMEPOS referring NPI). Add `ReferralNetworkAgent` to Claude SDK agents. ~70-80% coverage from free data.

---

## Assumptions

1. All CMS data.cms.gov APIs remain publicly accessible without authentication (Socrata-style endpoints).
2. openFDA API continues to provide NDC directory data without API key requirements.
3. NPPES bulk CSV download URL format remains stable across monthly releases.
4. Google Places API free tier (Basic plan, no billing required) provides sufficient quota for monthly contact verification (~8M providers, but verify in batches over time, not all at once).
5. USPS Address Validation API is available for address standardization (requires free registration).
6. DDInter 2.0 and Stabilis 4.0 datasets remain publicly accessible for academic/research use.
7. Existing `BaseFetcher`, `BaseAdapter`, `BaseMCPTool` base classes and `raw→bronze→silver→gold` pipeline are stable and do not require architectural changes.
8. PostgreSQL 16.4 `JSONB` column with GIN index provides sufficient query performance for raw-layer lookups.
9. CMS data suppression rules (cells with <11 beneficiaries) remain consistent across all PUF datasets.
10. Existing Prometheus metrics infrastructure (`dk_data_source_freshness_seconds`, `dk_data_source_staleness_seconds`) auto-covers new sources when registered in `meta.data_sources`.
11. NPPES Version 2 CSV format (mandatory from 2026-03-03) column layout is documented by CMS before the transition date.
12. NLM UMLS account (free) provides sufficient access for RxNorm bulk file downloads.
13. PharmGKB academic license (free) permits use for commercial healthcare analytics platforms.
14. State APCD Data Use Agreements can be obtained within reasonable timeframes (weeks, not months) for pilot states.
15. PBM public formulary formats remain stable enough for automated parsing between quarterly refreshes.
16. BLS OEWS data (annual, free) is available in machine-readable format suitable for automated ingestion.

---

## Dependencies

| Dependency | Type | Status |
|-----------|------|--------|
| `raw`/`bronze`/`silver`/`gold` schema infrastructure | Internal | Exists |
| `BaseFetcher` / `BaseAdapter` / `BaseMCPTool` base classes | Internal | Exists |
| `SilverGoldRefresher` pipeline | Internal | Exists (needs extension for provider/facility) |
| `BronzeTransformer` pipeline | Internal | Exists (needs new handler methods) |
| SQLMesh `INCREMENTAL_BY_UNIQUE_KEY` pattern | Internal | Exists |
| Prometheus metrics infrastructure | Internal | Exists |
| `meta.data_sources` catalog table | Internal | Exists |
| CMS data.cms.gov public APIs | External | Available |
| openFDA API | External | Available |
| NPPES bulk CSV distribution | External | Available |
| DDInter 2.0 academic API | External | Available (reliability varies) |
| Stabilis 4.0 dataset | External | Available |
| Google Places API (free tier) | External | Available (registration required) |
| USPS Address Validation API | External | Available (registration required) |
| LiteLLM proxy (`litellm.infra.svc.cluster.local:4000`) | Internal | Exists (dk-alchemy infra namespace) |
| Claude Haiku model access (via LiteLLM) | Internal | Exists |
| Kubernetes CronJob scheduling | Internal | Exists |
| SEC EDGAR pipeline | Internal | Exists in dk-data-fe (reference for IDN hierarchy) |
| PubMed pipeline | Internal | Exists in dk-data-fe (extend for emails + conferences) |
| ORCID pipeline | Internal | Exists in dk-data-fe (disabled, re-enable) |
| DailyMed SPL XML pipeline | Internal | Exists in dk-data-fe (Tier 3, enable for dose ranges) |
| NLM UMLS account | External | Required for RxNorm bulk (free registration) |
| PharmGKB academic license | External | Required (free for academic/research) |
| BLS OEWS annual data | External | Available (free, public) |
| State APCD DUAs | External | Required per state (2-3 pilot states initially) |

---

## Integration Audit — Drift & Duplication Prevention

This section documents the results of a comprehensive codebase audit to ensure the 016 implementation integrates cleanly with the existing dk-data-FE codebase. Every recommendation is grounded in specific file references and existing code patterns.

### Critical Integration Points (Must-Fix Before Implementation)

#### A. `ToolInvokeRequest` requires `drug_name` — API route must change

**File**: `src/dk_data/api/routes/mcp.py:45-48`

**Problem**: `drug_name: str = Field(..., min_length=1)` is REQUIRED. New NPI/CCN tools cannot be invoked via the existing route.

**Fix**: Make `drug_name` Optional, add `npi` (regex `^\d{10}$`), `ccn` (regex `^[A-Z0-9]{6}$`), and generic `params: Dict[str, Any]` fields. Add `@model_validator` requiring at least one query key. Route handler builds `input_params` dict from all fields.

**Backward compat**: Existing callers sending `{"drug_name": "atorvastatin"}` still work — `params.get("drug_name")` returns value as before.

#### B. `base_tool.py._fetch_external()` hardcodes `drug_name`

**File**: `src/dk_data/services/mcp/base_tool.py:143`

**Problem**: `drug_name = params.get("drug_name", "")` then `_build_url(drug_name, params)`.

**Fix**: Change to `drug_name = params.get("drug_name") or params.get("npi") or params.get("ccn") or ""`. New adapters ignore the `drug_name` positional in `build_url()` and pull typed keys from `params` dict.

**Why not change `build_url` signature**: 28 existing adapters implement `build_url(self, base_url, drug_name, params)`. Changing the signature would require modifying all 28.

#### C. `SilverGoldRefresher` is molecule-only

**File**: `src/dk_data/services/mcp/silver_gold_refresher.py`

**Problem**: Only has `refresh(drug_name, source_name, api_response)` → `_resolve_molecule()`.

**Fix**: Add `refresh_provider(npi, source_name, api_response)` and `refresh_facility(ccn, source_name, api_response)`. In `base_tool.py._refresh_silver_gold()`, dispatch by source category using `_PROVIDER_SOURCES` / `_FACILITY_SOURCES` / default-molecule frozensets.

**Entity resolution**: `_resolve_provider(npi)` does NOT use fuzzy matching (unlike `_resolve_molecule`). NPI is a deterministic 10-digit identifier — simple lookup + stub creation if missing.

#### D. `ToolDefinition.input_schema` defaults to `{"required": ["drug_name"]}`

**File**: `src/dk_data/services/mcp/tool_registry.py:26-33`

**Fix**: New tools override `input_schema` with custom `properties` and `anyOf`/`required` for npi/ccn/drug_name. No change to the ToolDefinition dataclass itself needed.

#### E. Existing `silver.healthcare_facilities` uses `(provider_id, source)` as unique key

**File**: `src/dk_data/sqlmesh/models/molecules/silver/healthcare_facilities.sql`

**Problem**: Spec redefines this table with `ccn` as canonical key — this is a breaking change.

**Fix**: Migration 083 creates `silver.healthcare_facilities` with CCN-based schema. The existing `provider_id` values from CMS sources ARE CCNs (6-character), so this is mostly a rename + schema evolution. The existing SQLMesh model is updated to add new source CTEs.

### Reuse Opportunities (Don't Reinvent)

| Existing Code | Location | Reuse For |
|---------------|----------|-----------|
| `CMSMedicareClient` Socrata URL pattern | `services/external_apis/cms_medicare_client.py` | Dataset IDs, filter syntax. **Do NOT import** (different async model). Extract shared constants to `config/cms_datasets.py`. |
| `BaseFetcher` retry strategy | `ingestion/fetchers/base.py` | All new fetchers MUST subclass this. HTTPAdapter with backoff on [429,500,502,503,504]. |
| `_parse_date()`, `_join_text()` helpers | `services/mcp/bronze_transformer.py` | Reuse in new bronze handler methods. |
| `silver.identifier_mappings` UNION ALL pattern | `sqlmesh/models/molecules/silver/identifier_mappings.sql` | New `silver.provider_identifier_mappings` for NPI→org_npi, NPI→CCN cross-references. |
| `gold.molecule_profile` multi-CTE pattern | `sqlmesh/models/molecules/gold/molecule_profile.sql` | Template for `gold.provider_profile` and `gold.facility_profile`. |
| `_ensure_client()` + JSON extraction | `claude_sdk/enrichment.py`, `claude_sdk/scoring_agent.py` | Extract into `BaseAgent` ABC. Replace direct Anthropic client init with `litellm.completion()` via cluster LiteLLM proxy. Same JSON extraction pattern. |
| `tool_registry.py` ToolDefinition pattern | `services/mcp/tool_registry.py` | Mirror for `agent_registry.py` AgentDefinition dataclass. |
| `record_job_duration()`, `@timed_job` | `observability/metrics.py` | Reuse for agent execution timing. Add `dk_providers_total`, `dk_facilities_total` gauges. |
| `upsert_records()`, ThreadedConnectionPool | `utils/database.py` | All new loaders use existing DB utilities. |
| Pydantic validators | `utils/validators.py` | Reuse for new source-specific validation. |
| CronJob template | `k8s/base/ingestion/cronjob-fetch-pubmed.yaml` | All new CronJobs follow identical structure: concurrencyPolicy Forbid, backoffLimit 2, individual `secretKeyRef` per DB key (NOT `envFrom`), `imagePullSecrets: ghcr-credentials`, K8s recommended labels, OTEL env vars, `successfulJobsHistoryLimit: 3`, `failedJobsHistoryLimit: 3`. See § CronJob Manifest Template below. |

### Pattern Compliance Rules (Zero-Drift Checklist)

| Pattern | Rule | Existing Reference |
|---------|------|--------------------|
| **Raw tables** | UUID PK via `gen_random_uuid()`, 4 mandatory indexes (request_id, timestamp, processed, hash), standard request context columns | Migration 020 |
| **Bronze SQLMesh** | `INCREMENTAL_BY_TIME_RANGE`, `time_column=request_timestamp`, `batch_size 200-500`, `cron '@daily'`, standard columns (id, raw_json, raw_source_id, source, request_timestamp, processed_to_silver, created_at) | `bronze/pubmed.sql` |
| **Silver SQLMesh** | `INCREMENTAL_BY_UNIQUE_KEY`, `DISTINCT ON (key) ORDER BY source_precedence ASC`, `cron '@daily'` | `silver/molecules.sql` |
| **Gold SQLMesh** | `INCREMENTAL_BY_UNIQUE_KEY`, multi-CTE with LEFT JOINs, JSONB aggregations, must include `_generation_source TEXT`, `_refreshed_at TIMESTAMPTZ`, `_source_freshness JSONB` | `gold/molecule_profile.sql` |
| **UUID function** | `gen_random_uuid()` exclusively (30+ existing uses vs 2 outliers using `uuid_generate_v4()`) | Migration 020, all SQLMesh models |
| **MCP adapter** | Subclass `BaseAdapter`, implement `source_name`, `raw_table`, `raw_schema`, `build_url()`, `normalize()` | `adapters/chembl.py` |
| **Fetcher** | Subclass `BaseFetcher`, override `SOURCE_NAME`, `BASE_URL`, `fetch()`, `get_latest_url()` | `fetchers/cms_inpatient.py` |
| **Loader** | Function `load_*_data(records, source_hash, batch_size)` → `{status, records_inserted, ...}` | `sources/cms_inpatient.py` |
| **Metrics** | `dk_*` prefix, use Gauge/Counter from prometheus_client | `observability/metrics.py` |
| **Rate limits** | Add to `config/rate_limits.yaml` under `sources:` section. Defaults: 5 req/s, 30s timeout | Existing YAML structure |
| **Catalog seeds** | Add to `sql/seed_data_sources.sql` in `meta.data_sources` table | Existing seed entries |
| **CronJob YAML** | concurrencyPolicy Forbid, backoffLimit 2, restartPolicy Never, individual `secretKeyRef` per DB key (POSTGRES_HOST/PORT/USER/PASSWORD/DB), `imagePullSecrets: [{name: ghcr-credentials}]`, `successfulJobsHistoryLimit: 3`, `failedJobsHistoryLimit: 3`, K8s labels (`app.kubernetes.io/name`, `/component: ingestion`, `/part-of: dk-data`), OTEL env as static `value:`, image `ghcr.io/data-kinetic/dk-data-fe/job-trigger:BRANCH-SHA` (exact name required for kustomize image transformer). See § CronJob Manifest Template. | `cronjob-fetch-pubmed.yaml` |

### Ontology Assessment

**Current state**: The ontology layer (`services/ground_truth/ontology_loader.py`) is 100% drug/molecule focused:
- `OntologyMappings` dataclass: `abbreviations`, `indication_to_icd10`, `fda_epc_to_indications`, `biologic_moa_to_indications`
- Loads from `config/ontology_mappings.yaml`
- `IndicationResolver`: 4-layer resolution with confidence thresholds (0.90/0.75/0.50/0.30)

**Decision: Do NOT extend the ontology YAML for healthcare taxonomies. Use PostgreSQL lookup tables instead.**

**Rationale**:
1. DRG→service line, HCPCS→equipment, and NUCC→specialty are structured reference data, not semantic ontology mappings.
2. The reference data is already available as CMS downloadable files (DRG weights, HCPCS Level II, NUCC taxonomy CSV).
3. These become natural raw→bronze→silver reference tables in the data pipeline.

**New reference tables** (in migration 083):
- `silver.drg_service_line_mapping` — 772 DRGs → ~30 service lines (used by ServiceLineInferenceAgent as context)
- `silver.hcpcs_equipment_mapping` — HCPCS codes → equipment categories (used by EquipmentInventoryAgent as context)
- `silver.nucc_taxonomy` — ~900 NUCC codes → specialty descriptions (used for provider specialty normalization)

**What CAN be reused**: The `IndicationResolver` confidence threshold pattern (0.90/0.75/0.50/0.30) is replicated in the agent validation pipeline (>=0.80 direct, 0.50-0.79 review, <0.50 quarantine).

### New Shared Infrastructure

#### `config/cms_datasets.py` (NEW — shared dataset constants)

Centralizes CMS Socrata dataset IDs used by both MCP adapters (async) and batch fetchers (sync). Prevents ID duplication between `CMSMedicareClient` and `CMSSocrataFetcher` subclasses.

#### `ingestion/fetchers/cms_socrata_base.py` (NEW — shared fetcher base)

`CMSSocrataFetcher(BaseFetcher)` for ~15 CMS sources using Socrata V1 API. Handles pagination (`offset`+`size`), year filtering, `Retry-After` headers. Follows existing `CMSInpatientFetcher` + `CMSCatalogService` patterns.

#### `claude_sdk/base_agent.py` (NEW — agent ABC)

Extracts duplicated patterns from `enrichment.py` + `scoring_agent.py`: `_ensure_client()`, `_extract_json()`, `process_single()`, `process_batch()`, `_log_execution()`, `_check_quarantine()`. Existing agents remain untouched (opt-in inheritance).

#### `claude_sdk/agent_registry.py` (NEW — mirrors tool_registry.py)

`AgentDefinition` dataclass + `AGENT_REGISTRY` dict, following `ToolDefinition`/`TOOL_REGISTRY` pattern.

#### `claude_sdk/runner.py` (NEW — CLI entry point for agent CronJobs)

`python -m dk_data.claude_sdk.runner --agent {name} --batch-size {n} --dry-run`

### Range Partitioning (New Pattern Introduction)

No existing migration uses `PARTITION BY RANGE`. Introduced cleanly in migration 084 for four high-volume tables:
- `raw.cms_part_d_prescribers` (25M rows/year)
- `raw.cms_part_d_prescribers_summary`
- `raw.cms_physician_puf` (10M rows/year)
- `raw.cms_physician_puf_summary`

Pattern: Parent table with `year INTEGER NOT NULL` as partition key. PK is `(id, year)` (PostgreSQL requires partition key in unique constraints). Partitions created via DO block for years 2015-2025. Indexes on parent auto-propagate. SQLMesh queries the parent table transparently.

### Model Consistency Note

Existing agents use `claude-sonnet-4-20250514` via direct Anthropic SDK. New agents intentionally use `claude-haiku-4-5-20251001` for cost optimization ($0.80/$4.00 per 1M tokens vs ~$3/$15 for Sonnet). This is by design — the enrichment tasks in feature 016 are higher-volume, lower-complexity than the existing hospital enrichment (which requires deeper reasoning). Both model choices are valid for their respective use cases.

**LLM Access Pattern**: All new agents MUST use the cluster LiteLLM proxy (`http://litellm.infra.svc.cluster.local:4000`) instead of direct Anthropic SDK calls. The LiteLLM proxy (hosted in dk-alchemy infra namespace) provides unified LLM access with centralized API key management, rate limiting, retries, and cost tracking. `BaseAgent` uses `litellm.completion()` with `LITELLM_API_BASE` env var (defaulting to `http://litellm.infra.svc.cluster.local:4000`). Agent CronJobs do NOT need `ANTHROPIC_API_KEY` — the proxy manages API keys centrally. This aligns with the dk-alchemy RECOMMENDATIONS.md pattern and resolves GitHub Issue #95 (LiteLLM evaluation) for this feature.

---

## Implementation Plan

> **Note**: See [plan.md](./plan.md) for detailed design artifacts including research decisions, data model, API contracts, and agent pipeline contracts.

### Architecture Overview

```
                    ┌────────────────────┐     ┌────────────────────┐
                    │  MCP Tools (API)   │     │  Data Loaders      │
                    │  POST /mcp/invoke  │     │  CronJob → CLI     │
                    │  28 existing +     │     │  26 existing +     │
                    │  ~40 new adapters  │     │  ~35 new fetchers  │
                    └────────┬───────────┘     └────────┬───────────┘
                             │                          │
                             ▼                          ▼
                    ┌────────────────────────────────────────────┐
                    │  raw.* tables (JSONB)                      │
                    │  Same tables regardless of ingestion path  │
                    └────────────────────┬──────────────────────┘
                                         │
              ┌──────────────────────────┼──────────────────────┐
              │                          │                      │
              ▼                          ▼                      ▼
     [MCP Path: immediate]    [SQLMesh: @daily/@weekly]   [Transform API]
     BronzeTransformer         bronze/*.sql models        POST /transform
              │                          │                      │
              └──────────────────────────┼──────────────────────┘
                                         │
                    ┌────────────────────▼───────────────────────┐
                    │  bronze.* tables (typed columns)           │
                    └────────────────────┬──────────────────────┘
                                         │ SQLMesh @daily
                    ┌────────────────────▼───────────────────────┐
                    │  silver.* tables (entity-resolved)         │
                    │  providers, prescribing_profiles, etc.     │
                    └────────────────────┬──────────────────────┘
                                         │ SQLMesh @daily + Agent enrichment
                    ┌────────────────────▼───────────────────────┐
                    │  gold.* tables (pre-aggregated)            │
                    │  provider_profile, facility_profile, etc.  │
                    │  Agent-produced data validated here         │
                    └────────────────────┬──────────────────────┘
                                         │
                    ┌────────────────────▼───────────────────────┐
                    │  PostgREST API (port 3000)                 │
                    │  PGRST_DB_SCHEMAS += "gold"                │
                    │  GET /gold/provider_profile?npi=eq.X       │
                    │  analyst JWT required                      │
                    └───────────────────────────────────────────┘
```

### Critical Changes to Existing Files

> **See also**: [Integration Audit § Critical Integration Points](#critical-integration-points-must-fix-before-implementation) for file:line references, BEFORE/AFTER code patterns, and backward compatibility analysis for each change below.

| File | Change | Audit Ref |
|------|--------|-----------|
| `src/dk_data/api/routes/mcp.py` | Make `drug_name` Optional, add `npi`/`ccn`/`params` fields, add `@model_validator` requiring at least one query key | §A |
| `src/dk_data/services/mcp/base_tool.py` | Generic param handling — extract `npi`/`ccn` alongside `drug_name`; dispatch to provider/facility refreshers | §B |
| `src/dk_data/services/mcp/adapters/base.py` | `build_url()` backward-compatible update for generic `primary_query` | §B |
| `src/dk_data/services/mcp/tool_registry.py` | +~40 ToolDefinitions in Tiers 4 (provider_claims), 5 (facility_hospital), 6 (drug_market_population) | §D |
| `src/dk_data/services/mcp/bronze_transformer.py` | +~35 handlers + `_RAW_SCHEMA_MAP` entries | — |
| `src/dk_data/services/mcp/silver_gold_refresher.py` | `refresh_provider()`, `refresh_facility()`, `_resolve_provider()`, `_resolve_facility()`, per-source silver handlers, gold provider/facility refresh | §C |
| `src/dk_data/sqlmesh/models/molecules/silver/healthcare_facilities.sql` | Schema evolution from `(provider_id, source)` to `ccn` as canonical key + new source CTEs | §E |
| `src/dk_data/ingestion/main.py` | +~35 `SOURCES` dict entries with fetcher class + loader function | — |
| `src/dk_data/ingestion/fetchers/__init__.py` | Export ~35 new fetcher classes | — |
| `src/dk_data/ingestion/sources/__init__.py` | Export ~35 new loader functions | — |
| `src/dk_data/observability/metrics.py` | Provider/facility/agent Prometheus metrics | — |
| `src/dk_data/config/rate_limits.yaml` | +~45 source rate limits | — |
| `src/dk_data/sql/seed_data_sources.sql` | +~45 catalog entries | — |
| `src/dk_data/claude_sdk/__init__.py` | Export BaseAgent + 6 new agents | — |
| `k8s/base/postgrest/configmap.yaml` | Add `gold` to `PGRST_DB_SCHEMAS` | — |
| `k8s/base/kustomization.yaml` | Add ~48 new CronJob resources (~33 data sources + 6 agents + 9 phases 12-14) | — |

#### Code-Level Integration Details

**`base_tool.py` — Generic Parameter Handling** (`src/dk_data/services/mcp/base_tool.py`):

Current `_fetch_external()` hardcodes `drug_name = params.get("drug_name", "")`. Change to let adapters extract their own params:

```python
# BEFORE (line ~143):
drug_name = params.get("drug_name", "")
url = self._build_url(drug_name, params)

# AFTER:
primary_query = params.get("drug_name", "") or params.get("npi", "") or params.get("ccn", "")
url = self.adapter.build_url(self.api_base_url, primary_query, params)
```

**`silver_gold_refresher.py` — Source Category Dispatch** (`src/dk_data/services/mcp/silver_gold_refresher.py`):

In `base_tool.py._refresh_silver_gold()`, dispatch by source category:

```python
_PROVIDER_SOURCES = frozenset({"cms_nppes", "cms_care_compare", "cms_physician_puf", ...})
_FACILITY_SOURCES = frozenset({"cms_provider_of_services", "cms_hospital_quality", ...})

# In _refresh_silver_gold():
if source_name in _PROVIDER_SOURCES:
    refresher.refresh_provider(params.get("npi"), source_name, api_response)
elif source_name in _FACILITY_SOURCES:
    refresher.refresh_facility(params.get("ccn"), source_name, api_response)
else:
    refresher.refresh(params.get("drug_name"), source_name, api_response)  # existing molecule path
```

**`tool_registry.py` — New Tiers** (`src/dk_data/services/mcp/tool_registry.py`):

Add 3 new tiers after existing Tier 3:
- **Tier 4: `provider_claims`** — NPPES, Part D, Physician PUF, Open Payments, Care Compare (7 tools)
- **Tier 5: `facility_hospital`** — POS, PECOS, CHOW, Affiliation, Inpatient, Outpatient, Quality, DRG, Magnet, HCPCS (10 tools)
- **Tier 6: `drug_market_population`** — NDC, Part D/B Spending, Formulary, RBCS, Price Lookup, USP, NUCC, Geographic, Chronic, Post-Acute, DMEPOS, DDInter, Stabilis (13 tools)

**PostgREST ConfigMap** (`k8s/base/postgrest/configmap.yaml`):

```yaml
# BEFORE:
PGRST_DB_SCHEMAS: "api,mol_api,mol_gold,mol_silver,xenon,meta"
# AFTER:
PGRST_DB_SCHEMAS: "api,mol_api,mol_gold,mol_silver,xenon,meta,gold"
```

### CronJob Manifest Template

All new CronJob YAMLs MUST follow the established pattern from `cronjob-fetch-pubmed.yaml`. The codebase uses **individual `secretKeyRef`** entries for secrets (NOT `envFrom` with a secret ref). The `envFrom` keyword in existing YAMLs is only used for ConfigMap references (e.g., `molecule-pipeline-config`).

**Mandatory elements** (verified against all existing CronJobs):

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: fetch-{source}
  labels:
    app: fetch-{source}
    app.kubernetes.io/name: fetch-{source}
    app.kubernetes.io/component: ingestion
    app.kubernetes.io/part-of: dk-data
spec:
  schedule: "{cron expression}"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 2
      activeDeadlineSeconds: {timeout}
      template:
        metadata:
          labels:
            app: fetch-{source}
            app.kubernetes.io/component: batch-job
            app.kubernetes.io/part-of: dk-data
        spec:
          restartPolicy: Never
          imagePullSecrets:
            - name: ghcr-credentials
          containers:
            - name: fetch-{source}
              image: ghcr.io/data-kinetic/dk-data-fe/job-trigger:main-{sha}  # exact name for kustomize
              command: ["python", "-m", "dk_data.ingestion.main"]
              args: ["{source_name}"]
              env:
                # DB credentials — individual secretKeyRef (NOT envFrom)
                - name: POSTGRES_HOST
                  valueFrom:
                    secretKeyRef:
                      name: dk-data-secrets
                      key: POSTGRES_HOST
                - name: POSTGRES_PORT
                  valueFrom:
                    secretKeyRef:
                      name: dk-data-secrets
                      key: POSTGRES_PORT
                - name: POSTGRES_USER
                  valueFrom:
                    secretKeyRef:
                      name: dk-data-secrets
                      key: POSTGRES_USER
                - name: POSTGRES_PASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: dk-data-secrets
                      key: POSTGRES_PASSWORD
                - name: POSTGRES_DB
                  valueFrom:
                    secretKeyRef:
                      name: dk-data-secrets
                      key: POSTGRES_DB
                # Source-specific API keys (optional)
                - name: {API_KEY_NAME}
                  valueFrom:
                    secretKeyRef:
                      name: dk-data-secrets
                      key: {API_KEY_NAME}
                      optional: true
                # Observability — static values
                - name: OTEL_EXPORTER_OTLP_ENDPOINT
                  value: "http://alloy.infra.svc.cluster.local:4317"
                - name: OTEL_ENABLED
                  value: "true"
              resources:
                requests:
                  memory: "256Mi"
                  cpu: "100m"
                limits:
                  memory: "512Mi"
                  cpu: "300m"
```

**Agent CronJob variant** — uses different command/args split:
```yaml
command: ["python", "-m", "dk_data.claude_sdk.runner"]
args: ["--agent", "{agent_name}", "--batch-size", "100"]
env:
  # ... same DB secretKeyRef block as above ...
  # LiteLLM proxy — static cluster-internal URL (NOT from DopplerSecret)
  - name: LITELLM_API_BASE
    value: "http://litellm.infra.svc.cluster.local:4000"
```

**Image name requirement**: All CronJob YAMLs MUST use the exact base image name `ghcr.io/data-kinetic/dk-data-fe/job-trigger` (with any tag). The kustomize `images:` block in staging/prod overlays automatically replaces the tag via image transformer matching. Using a different image name will cause the CronJob to reference a stale or missing tag.

### Deployment Flow (ArgoCD GitOps)

New CronJobs deploy automatically via the existing ArgoCD GitOps pipeline:

1. **Feature branch** (`016-cms-puf-datasource-integration`): CronJob YAMLs are created and added to `k8s/base/kustomization.yaml`. `build-push.yaml` does NOT trigger on feature branches — no image build or deploy.
2. **Merge to `staging`**: CI workflow triggers → builds Docker image → pushes to GHCR with `staging-{shortSHA}` tag → auto-commits updated image tag to `k8s/overlays/staging/kustomization.yaml` → pushes manifest update.
3. **ArgoCD staging sync**: ArgoCD Application (`dk-data-staging`) watches `staging` branch at `k8s/overlays/staging`. Auto-sync with `prune: true` and `selfHeal: true` detects new CronJob resources and deploys them to `dk-data-staging` namespace.
4. **Promote to production**: After staging validation, `promote-to-prod.yaml` workflow tags the image for production. ArgoCD Application (`dk-data-prod`) watches `main` branch at `k8s/overlays/prod`, deploying to `dk-data-prod` namespace.

**DopplerSecret**: Project `dk-data-fe`, config `prd` (base), patched to `stg` for staging overlay. Syncs every 300s to `dk-data-secrets` Kubernetes secret. All secrets (DB credentials, API keys) are managed in Doppler — agent CronJobs that need `LITELLM_API_BASE` set it as a static `value:` (cluster-internal URL), not from DopplerSecret.

### Per-Source Implementation Details

Each source needs 7 artifacts: MCP adapter, fetcher, loader, raw table, bronze table, bronze transformer handler, tool registry entry.

**Common Socrata Fetcher Base Class** (`src/dk_data/ingestion/fetchers/cms_socrata_base.py`): Shared base for CMS data.cms.gov Socrata-style API + CSV sources. Used by sources #2-5, 9, 11-14, 19-20, 23, 27-30.

#### Phase 2: Provider & Claims (7 Sources)

| # | Source | MCP Adapter | CronJob Schedule | API Base URL | Key Params | Auth |
|---|--------|------------|-----------------|-------------|------------|------|
| 1 | NPPES | `adapters/nppes.py` | `0 3 1 * *` (monthly) | `https://npiregistry.cms.hhs.gov/api/` | npi, first_name, last_name, state | None |
| 2 | Part D Prescribers | `adapters/cms_partd_prescribers.py` | `0 4 * * 0` (weekly) | `https://data.cms.gov/data-api/v1/dataset/{id}/data` | Prscrbr_NPI, Gnrc_Name, year | None |
| 3 | Part D Summary | `adapters/cms_partd_prescribers_summary.py` | `30 4 * * 0` | Same Socrata pattern | Prscrbr_NPI, year | None |
| 4 | Physician PUF | `adapters/cms_physician_puf.py` | `0 5 * * 0` | Same Socrata pattern | Rndrng_NPI, HCPCS_Cd, year | None |
| 5 | Physician Summary | `adapters/cms_physician_puf_summary.py` | `30 5 * * 0` | Same Socrata pattern | Rndrng_NPI, year | None |
| 6 | Open Payments | `adapters/cms_open_payments.py` | `0 6 * * 0` | `https://openpaymentsdata.cms.gov/api/1/datastore/query/{id}` | Covered_Recipient_NPI, company | None |
| 7 | Care Compare | `adapters/cms_care_compare.py` | `0 3 * * 1` (bi-monthly) | `https://data.cms.gov/provider-data/api/1/datastore/query/{id}` | npi, provider_name | None |

#### Phase 3: Facility & Hospital (10 Sources)

| # | Source | MCP Adapter | CronJob | API/Data Pattern | Key Params |
|---|--------|------------|---------|-----------------|------------|
| 8 | Provider of Services | `adapters/cms_provider_of_services.py` | `0 3 1 */3 *` (quarterly) | Bulk CSV | PRVDR_NUM (CCN) |
| 9 | PECOS | `adapters/cms_pecos.py` | `0 4 1 * *` (monthly) | Socrata API | NPI, enrollment_id |
| 10 | CHOW | `adapters/cms_chow.py` | `0 5 1 */3 *` (quarterly) | Bulk CSV | old_ccn, new_ccn |
| 11 | Facility Affiliation | `adapters/cms_facility_affiliation.py` | `0 6 1 * *` (monthly) | Socrata API | facility_ccn, org_npi |
| 12 | Inpatient PUF Detail | `adapters/cms_inpatient_puf_detail.py` | `0 2 * * 0` | Socrata API | Rndrng_Prvdr_CCN, DRG_Cd |
| 13 | Outpatient PUF | `adapters/cms_outpatient_puf.py` | `30 2 * * 0` | Socrata API | Rndrng_Prvdr_CCN, APC_Cd |
| 14 | Hospital Quality | `adapters/cms_hospital_quality.py` | `0 7 * * 1` | Provider-data API | Facility_ID |
| 15 | DRG Weights | `adapters/cms_drg_weights.py` | `0 3 1 10 *` (annual Oct) | Direct CSV | MS_DRG |
| 16 | ANCC Magnet | `adapters/ancc_magnet.py` | `0 8 1 */3 *` (quarterly) | Web scrape | facility_name |
| 17 | HCPCS Level II | `adapters/cms_hcpcs.py` | `0 3 1 1 *` (annual Jan) | Direct CSV | HCPCS_Code |
| 37 | Inpatient Summary PUF | `adapters/cms_inpatient_puf_summary.py` | `0 3 * * 0` | Socrata API | Rndrng_Prvdr_CCN, year |

#### Phase 4: Drug & Market (9 Sources + 1)

| # | Source | MCP Adapter | CronJob | API Base URL | Key Params | Auth |
|---|--------|------------|---------|-------------|------------|------|
| 18 | FDA NDC | `adapters/fda_ndc.py` | `0 3 * * 3` | `https://api.fda.gov/drug/ndc.json` | generic_name, brand_name | OPENFDA_API_KEY (optional) |
| 19 | Part D Spending | `adapters/cms_partd_spending.py` | `0 4 * * 3` | Socrata API | Brnd_Name, Gnrc_Name | None |
| 20 | Part B Spending | `adapters/cms_partb_spending.py` | `30 4 * * 3` | Socrata API | Brnd_Name, HCPCS_Cd | None |
| 21 | Part D Formulary | `adapters/cms_partd_formulary.py` | `0 3 1 * *` | Bulk CSV | rxcui, plan_id | None |
| 22 | RBCS | `adapters/cms_rbcs.py` | `0 3 1 1 *` (annual) | CSV | HCPCS_CD | None |
| 23 | Price Lookup | `adapters/cms_price_lookup.py` | `0 4 1 1 *` (annual) | Socrata API | HCPCS_CD, MODIFIER | None |
| 24 | USP Drug Class | `adapters/usp_drug_class.py` | `0 5 1 1 *` (annual) | CMS crosswalk CSV | drug_name | None |
| 25 | NUCC Taxonomy | `adapters/cms_nucc_taxonomy.py` | `0 3 1 */6 *` (semi-annual) | nucc.org CSV | Code | None |
| 26 | WHO ATC | Extend existing `who_icd` | — | `https://rxnav.nlm.nih.gov/REST/` | rxcui, name | None |
| 38 | NLM RxNorm Bulk | `adapters/nlm_rxnorm.py` | `0 3 1 * *` (monthly) | Bulk files (UMLS account) | rxcui, name | UMLS account |

#### Phase 5: Population (4 Sources)

| # | Source | MCP Adapter | CronJob | Key Params |
|---|--------|------------|---------|------------|
| 27 | Geographic Variation | `adapters/cms_geographic_variation.py` | `0 3 1 1 *` (annual) | state, year |
| 28 | Chronic Conditions | `adapters/cms_chronic_conditions.py` | `0 4 1 1 *` (annual) | geo_level, condition |
| 29 | Post-Acute PUFs | `adapters/cms_post_acute.py` | `0 5 1 1 *` (annual) | Facility_ID, type |
| 30 | DMEPOS | `adapters/cms_dmepos.py` | `0 6 1 1 *` (annual) | Rfrg_NPI, HCPCS_Cd |

#### Phase 6: Clinical + News (5 Sources)

| # | Source | Approach | CronJob |
|---|--------|---------|---------|
| 31 | DDInter 2.0 | `adapters/ddinter.py` + `fetchers/ddinter.py` (cache full dataset) | `0 3 1 */3 *` (quarterly) |
| 32 | Stabilis 4.0 | `adapters/stabilis.py` + `fetchers/stabilis.py` (cache full dataset) | `0 4 1 */3 *` (quarterly) |
| 33 | Medicaid PDLs | `adapters/cms_medicaid_pdl.py` + `fetchers/cms_medicaid_pdl.py` | `0 5 1 * *` (monthly) |
| 34 | HCRIS Cost Reports | `fetchers/cms_cost_reports.py` + `sources/cms_cost_reports.py` (bulk CSV) | `0 3 1 1 *` (annual) |
| 35 | Becker's Hospital | Extend existing `journal_rss` fetcher — add feed URL | Existing CronJob |
| 36 | FierceHealthcare | Extend existing `medical_news` fetcher — add feed URL | Existing CronJob |
| 39 | Google News RSS | Extend existing `journal_rss` — healthcare topic filter | Existing CronJob |
| 40 | Modern Healthcare | Extend existing `medical_news` — add feed URL | Existing CronJob |

#### Phase 7: Advanced Clinical (6 Sources, Priority: P3)

| # | Source | Approach | CronJob | Notes |
|---|--------|---------|---------|-------|
| 41 | Drug-Allergy Cross-Ref | `fetchers/drug_allergy_crossref.py` (published tables) | `0 3 1 */6 *` (semi-annual) | UC Davis, VCH, UNMC tables + ATC hierarchy + ChEMBL |
| 42 | PSYHAMM/HeTOP Off-Label | `fetchers/psyhamm_offlabel.py` | `0 4 1 */6 *` (semi-annual) | 18K+ off-label drug-indication entries |
| 43 | ONCHigh + Phansalkar Alert Rules | `fetchers/alert_rules.py` (published lists) | `0 5 1 1 *` (annual) | 15 + 33 expert-curated DDI alert rules |
| 44 | PharmGKB | `fetchers/pharmgkb.py` | `0 3 1 */3 *` (quarterly) | Pharmacogenomics gene-drug interactions |
| 45 | DailyMed SPL XML Dose Ranges | Enable existing Tier 3 `dailymed` fetcher | Existing CronJob | Structured dosing sections for dose range extraction |
| 46 | CMS DE-SynPUF | `fetchers/cms_synpuf.py` (one-time load) | One-time | Synthetic claims for dev/test |

#### Phase 8: Contact Enrichment (4 Sources/Capabilities, Priority: P2)

| # | Source | Approach | CronJob | Notes |
|---|--------|---------|---------|-------|
| 47 | NPPES Address Geocoding | Enhancement to ContactVerification pipeline | Monthly (with NPPES) | Nominatim/Google Geocoding free tier |
| 48 | Insurer Provider Directories | `fetchers/insurer_directories.py` (Aetna/BCBS/UHC) | `0 3 1 * *` (monthly) | Phone/address triangulation source |
| 49 | PubMed Author Emails | Extend existing PubMed pipeline | Monthly (with PubMed) | Correspondence field extraction |
| 50 | ORCID Re-enablement | Re-enable existing dk-data-fe pipeline | Monthly | Academic researcher profiles |

#### Phase 9: Conference & Workforce Data (4 Sources, Priority: P3)

| # | Source | Approach | CronJob | Notes |
|---|--------|---------|---------|-------|
| 51 | Conference Abstracts | `fetchers/conference_abstracts.py` (ASCO/AHA/ESMO/ASH) | `0 3 1 1 *` (annual) | 10K+ abstracts/year, NPI linking via name matching |
| 52 | PBM Public Formularies | `fetchers/pbm_formulary.py` (CVS/Express/Optum) | `0 3 1 */3 *` (quarterly) | Commercial formulary coverage |
| 53 | State APCDs (pilot) | `fetchers/state_apcd.py` (framework + 2-3 states) | Per-state DUA schedule | All-payer patient-level claims |
| 54 | BLS OEWS | `fetchers/bls_oews.py` | `0 3 1 5 *` (annual May) | Occupational mix ratios for staffing agent |

### SQL Migrations

**Migration 083** (`083_cms_puf_foundation.sql`): Silver entity tables (9) + silver reference tables (3) + gold aggregate tables (5) + agent infrastructure (2) + RBAC grants.

Silver entity tables (9):
- `silver.providers` — PK: `npi` (VARCHAR(10))
- `silver.prescribing_profiles` — PK: `(npi, drug_name, year)`
- `silver.procedure_profiles` — PK: `(npi, hcpcs_code, year)`
- `silver.open_payments` — PK: `record_id`
- `silver.health_systems` — PK: `organization_npi`
- `silver.facility_service_lines` — PK: `(ccn, service_line, year)`
- `silver.drug_market` — PK: `(drug_name, year)`
- `silver.geographic_analytics` — PK: `(geo_level, geo_code, year)`
- `silver.healthcare_facilities` — PK: `ccn` (schema evolution from existing `(provider_id, source)` — see Integration Audit §E)

Silver reference tables (3 — see Integration Audit § Ontology Assessment):
- `silver.drg_service_line_mapping` — 772 DRGs → ~30 service lines
- `silver.hcpcs_equipment_mapping` — HCPCS codes → equipment categories
- `silver.nucc_taxonomy` — ~900 NUCC codes → specialty descriptions

Gold tables (5):
- `gold.provider_profile` — PK: `npi`, includes `entity_type TEXT` ('individual'/'organization')
- `gold.facility_profile` — PK: `ccn`
- `gold.drug_market_profile` — PK: `(drug_name, generic_name)`
- `gold.market_analytics` — PK: `(geo_level, geo_code, year)`
- `gold.provider_network` — PK: `(source_npi, dest_npi, relationship_type)`

All gold tables include: `_generation_source TEXT`, `_refreshed_at TIMESTAMPTZ`, `_source_freshness JSONB`.

Agent infrastructure:
- `meta.agent_execution_log` — Audit every agent invocation (agent name, timestamps, records processed/written/quarantined, model, tokens, cost, status)
- `meta.agent_quarantine` — Low-confidence agent outputs routed for human review (entity key, entity type, raw LLM output, confidence score, rejection reason, review status)

RBAC grants:
- `GRANT USAGE ON SCHEMA gold TO analyst;`
- `GRANT SELECT ON ALL TABLES IN SCHEMA gold TO analyst;`
- `web_anon`: NO access to gold (analyst JWT required)

**Migration 084** (`084_provider_raw_bronze_tables.sql`): Raw + bronze for Phase 2 (7 sources). Part D and Physician PUF use range partitioning by year (y2015-y2025). See Integration Audit § Range Partitioning for the new `PARTITION BY RANGE` pattern.

**Migration 085** (`085_facility_raw_bronze_tables.sql`): Raw + bronze for Phase 3 (10 facility sources).

**Migration 086** (`086_drug_market_raw_bronze_tables.sql`): Raw + bronze for Phase 4 (9 drug/market sources).

**Migration 087** (`087_population_clinical_raw_bronze_tables.sql`): Raw + bronze for Phase 5-6 (9 population + clinical sources).

**Migration 088** (`088_advanced_clinical_contact_raw_bronze_tables.sql`): Raw + bronze for Phase 7-9 (~14 additional sources). Includes `raw.drug_allergy_crossref`, `raw.psyhamm_offlabel`, `raw.pharmgkb`, `raw.cms_synpuf`, `raw.pbm_formulary`, `raw.insurer_directories`, `raw.conference_abstracts`, `raw.state_apcd`, `raw.nlm_rxnorm`, `raw.cms_inpatient_puf_summary`, `raw.bls_oews`. Silver tables: `silver.drug_allergy_crossref`, `silver.dose_ranges`, `silver.offlabel_indications`, `silver.pharmacogenomics`, `silver.alert_rules`, `silver.equipment_inventory`, `silver.conference_activity`.

### Transformation Pipeline

**Bronze SQLMesh Models (~25)** in `src/dk_data/sqlmesh/models/molecules/bronze/`: `INCREMENTAL_BY_TIME_RANGE` models extracting typed columns from raw JSONB. One model per source. Must follow pattern compliance rules from Integration Audit.

Bronze model pattern (reference: `bronze/pubmed.sql`):
```sql
MODEL (
    name bronze.cms_nppes,
    kind INCREMENTAL_BY_TIME_RANGE (time_column request_timestamp, batch_size 500),
    cron '@daily',
    audits (not_null(columns := (npi))),
    grain npi
);
SELECT
    gen_random_uuid() AS id,
    response_body->>'npi' AS npi,
    response_body->>'entity_type' AS entity_type,
    response_body AS raw_json,
    id AS raw_source_id,
    'cms_nppes' AS source,
    request_timestamp,
    FALSE AS processed_to_silver,
    NOW() AS created_at
FROM raw.cms_nppes
WHERE response_status = 200
  AND processed_to_bronze = FALSE
  AND request_timestamp BETWEEN @start_dt AND @end_dt;
```

**Bronze Transformer Handlers** (~35 handlers in `src/dk_data/services/mcp/bronze_transformer.py`): Each handler registered in `_HANDLERS` dict and `_RAW_SCHEMA_MAP`. Reuse existing `_parse_date()` and `_join_text()` helpers (see Integration Audit § Reuse Opportunities).

Handler pattern:
```python
async def _transform_cms_nppes(self, raw_id: str, response: dict) -> int:
    results = response.get("results", [response])
    rows = []
    for r in results:
        npi = r.get("number") or r.get("npi")
        if not npi: continue
        rows.append((str(uuid.uuid4()), raw_id, npi, r.get("enumeration_type"), ...))
    async with self.db_pool.acquire() as conn:
        await conn.executemany("""
            INSERT INTO bronze.cms_nppes (id, raw_id, npi, entity_type, ...)
            VALUES ($1, $2, $3, $4, ...) ON CONFLICT (npi) DO UPDATE SET ...
        """, rows)
    await self._mark_processed("cms_nppes", raw_id)
    return len(rows)

_HANDLERS["cms_nppes"] = _transform_cms_nppes
_RAW_SCHEMA_MAP["cms_nppes"] = "raw"
```

**Silver SQLMesh Models (16)** in `src/dk_data/sqlmesh/models/molecules/silver/`:
- `providers.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `npi`. Unions NPPES + Care Compare + Physician PUF Summary. NPPES authoritative (source_precedence = 1). `DISTINCT ON (npi) ORDER BY source_precedence ASC`. Columns: npi, entity_type, provider_name, credential, specialty, address, phone, mips_score, total_services, enumeration_date.
- `healthcare_facilities.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `ccn`. From bronze.cms_provider_of_services + bronze.cms_hospital_quality + bronze.ancc_magnet. POS authoritative (source_precedence = 1). Schema evolution from existing `(provider_id, source)` key (see Integration Audit §E).
- `prescribing_profiles.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `(npi, drug_name, year)`. From Part D Prescribers. Columns: npi, drug_name, generic_name, brand_name, total_claims, total_cost, beneficiary_count, total_30day_fills, year.
- `procedure_profiles.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `(npi, hcpcs_code, year)`. From Physician PUF.
- `open_payments.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `record_id`. From Open Payments.
- `health_systems.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `organization_npi`. From PECOS + CHOW + Facility Affiliation.
- `facility_service_lines.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `(ccn, service_line, year)`. From Inpatient PUF + POS.
- `drug_market.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `(drug_name, year)`. Unions Part D/B Spending + NDC + Formulary + USP + RBCS. Multi-source join on drug name (normalized lowercase).
- `geographic_analytics.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `(geo_level, geo_code, year)`. From Geographic Variation + Chronic Conditions.
- `drug_allergy_crossref.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `(drug_class, allergen_class)`. From published cross-reactivity tables + ATC hierarchy.
- `dose_ranges.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `(drug_name, indication)`. From DailyMed SPL XML + LLM extraction.
- `offlabel_indications.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `(drug_name, indication)`. From PSYHAMM/HeTOP + NCCN.
- `pharmacogenomics.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `(gene, drug)`. From PharmGKB.
- `alert_rules.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `(rule_id)`. From ONCHigh + Phansalkar.
- `equipment_inventory.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `(ccn, equipment_type)`. From POS capabilities + DRG inference.
- `conference_activity.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `(npi, abstract_id)`. From conference abstracts + NPPES name matching.

**Gold SQLMesh Models (5)** in `src/dk_data/sqlmesh/models/molecules/gold/` (template: `gold/molecule_profile.sql` — see Integration Audit § Reuse Opportunities):
- `provider_profile.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `npi`. CTEs joining silver.providers + prescribing (top 10 drugs via ROW_NUMBER) + procedures (top 10) + open_payments (aggregates) + care_compare. JSONB aggregates: `top_drugs JSONB`, `top_procedures JSONB`, `top_payers JSONB`. `entity_type TEXT` distinguishes 'individual' vs 'organization'.
- `facility_profile.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `ccn`. CTEs joining silver.healthcare_facilities + inpatient DRGs (top DRGs) + hospital quality (star ratings) + health_systems (parent org) + facility_service_lines (agent-produced) + ANCC magnet. Agent-enriched columns (service_lines, staffing) populated via UPDATE after agent runs.
- `drug_market_profile.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `(drug_name, generic_name)`. Multi-source join on drug name.
- `market_analytics.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `(geo_level, geo_code, year)`. Geographic aggregation.
- `provider_network.sql` — `INCREMENTAL_BY_UNIQUE_KEY` on `(source_npi, dest_npi, relationship_type)`. Entirely agent-produced (ReferralNetworkInferenceAgent). Filter: `WHERE confidence_score >= 0.50` in downstream queries.

### Agentic Processing Pipeline

**BaseAgent class** (`src/dk_data/claude_sdk/base_agent.py`): Extracts common patterns from existing `enrichment.py` and `scoring_agent.py`. Abstract methods: `_build_prompt()`, `_parse_response()`. Shared: `process_single()`, `process_batch()`, `_log_execution()` (writes to `meta.agent_execution_log`), `_check_quarantine()` (routes low-confidence to `meta.agent_quarantine`).

**AgentRegistry** (`src/dk_data/claude_sdk/agent_registry.py`): Mirrors `tool_registry.py` pattern with `AgentDefinition` dataclass.

**Runner CLI** (`src/dk_data/claude_sdk/runner.py`): Entry point for agent CronJobs: `python -m dk_data.claude_sdk.runner --agent service_line_inference --batch-size 100`. In K8s CronJob manifests, split as `command: ["python", "-m", "dk_data.claude_sdk.runner"]`, `args: ["--agent", "service_line_inference", "--batch-size", "100"]`.

**Six agents** in `src/dk_data/claude_sdk/agents/`:

| Agent | Input | Output | LLM Calls/Month | Cost/Month | Validation |
|-------|-------|--------|-----------------|------------|------------|
| ServiceLineInference | bronze.cms_inpatient_puf_detail + bronze.cms_provider_of_services | silver.facility_service_lines | ~30K (ambiguous DRGs only; 80% deterministic) | ~$39 | Volume sums must match DRG totals |
| IDNHierarchy | bronze.cms_pecos + bronze.cms_chow + bronze.cms_facility_affiliation + SEC EDGAR 10-K | silver.health_systems | ~150 (ambiguous systems only) | ~$0.36 | Top 50 US systems cross-referenced |
| ReferralNetwork | silver.providers + Post-Acute PUFs + DMEPOS + PECOS | gold.provider_network | ~50K-200K (after deterministic pre-filter) | ~$130-336 | confidence_score >= 0.50 for gold |
| ContactVerification | silver.providers + Google Places API + USPS API | UPDATE silver.providers | 0 LLM calls (API-only) | $0 (API costs) | Status: verified/unverified/mismatch |
| StaffingDecomposition | raw.cms_cost_reports (HCRIS S-3/A) + BLS OEWS occupational mix | silver facilities enrichment | ~3K | ~$3.36 | Decomposition sums to total_fte ± 2% |
| EquipmentInventoryInference | silver.healthcare_facilities + bronze.cms_hcpcs + bronze.cms_outpatient_puf | silver.equipment_inventory | ~6K | ~$6.72 | Equipment list validated against HCPCS procedure volumes |

**Total estimated cost: ~$175-385/month** (Haiku at $0.80/1M input, $4.00/1M output). See Integration Audit § Model Consistency Note for Haiku vs Sonnet rationale.

**Validation**: Three-tier — (1) Pydantic schema validation, (2) confidence thresholding (>=0.80 direct write, 0.50-0.79 write with `needs_review = true`, <0.50 route to `meta.agent_quarantine`), (3) post-agent SQL integrity checks (volume sums, FTE totals, hierarchy completeness).

**CronJob schedule** (staggered monthly, encoded dependencies via dates):
| Day | Agent | Resources | Deadline | Extra Env Vars |
|-----|-------|-----------|----------|----------------|
| 1 | ServiceLineInference | 512Mi/500m | 4h | `LITELLM_API_BASE` (static `value:`, not from DopplerSecret) |
| 2 | IDNHierarchy | 512Mi/500m | 4h | `LITELLM_API_BASE` (static `value:`) |
| 3 | StaffingDecomposition | 512Mi/500m | 4h | `LITELLM_API_BASE` (static `value:`) |
| 4 | EquipmentInventoryInference | 512Mi/500m | 4h | `LITELLM_API_BASE` (static `value:`) |
| 5 | ReferralNetwork | 1Gi/1000m | 8h | `LITELLM_API_BASE` (static `value:`) |
| 10 | ContactVerification | 256Mi/250m | 4h | `GOOGLE_PLACES_API_KEY`, `USPS_API_KEY` (from `dk-data-secrets` via `secretKeyRef`) |

All agent CronJobs also include the standard 5 DB `secretKeyRef` entries + OTEL static values (see § CronJob Manifest Template).

### Complete File Manifest

**New files (~220)**: 6 SQL migrations, ~40 MCP adapters, ~35 fetchers + `cms_socrata_base.py`, ~35 source loaders, ~35 bronze SQLMesh models, 16 silver models + 3 reference tables, 5 gold models, 9 Claude SDK files (base + registry + runner + 6 agents), ~47 CronJob YAMLs, ~14 test files, 1 shared config (`config/cms_datasets.py`).

**Modified files (18)**: `api/routes/mcp.py` (make drug_name Optional, add npi/ccn/params), `base_tool.py`, `adapters/base.py`, `tool_registry.py`, `bronze_transformer.py`, `silver_gold_refresher.py`, `silver/healthcare_facilities.sql` (schema evolution: provider_id→ccn), `main.py`, `fetchers/__init__.py`, `sources/__init__.py`, `metrics.py`, `rate_limits.yaml`, `seed_data_sources.sql`, `claude_sdk/__init__.py`, `postgrest/configmap.yaml`, `kustomization.yaml`, existing `journal_rss` fetcher config, existing `medical_news` fetcher config.

### Implementation Order

Phases aligned with tasks.md (organized by user story):

```
Phase 1:  Setup (verify prerequisites)
Phase 2:  Foundation (migration 083, base class mods, agent infra, PostgREST, metrics)
Phase 3:  US1+US2 Provider MVP (migration 084, 7 adapters, fetchers, bronze/silver/gold models)
Phase 4:  US3 Facility (migration 085, 10+1 facility sources incl. Inpatient Summary PUF, silver/gold facility models)
Phase 5:  US4 Drug Market (migration 086, 9+1 drug sources incl. RxNorm bulk, silver/gold drug models)
Phase 6:  US9 Pipeline (CronJob manifests for all sources, K8s validation)
Phase 7:  US5 Geographic (migration 087, 4 population sources, silver/gold market models)
Phase 8:  US6 Open Payments Detail (enhance existing adapter + refresher)
Phase 9:  US7 Health System (IDN hierarchy agent + SEC EDGAR reference, CHOW mid-year logic)
Phase 10: US8 Drug Interaction (DDInter, Stabilis, Medicaid PDL, RSS extensions incl. Google News + Modern Healthcare)
Phase 11: Agentic Processing (5 remaining agents: ServiceLine, Referral, Contact, Staffing, EquipmentInventory)
Phase 12: Contact Enrichment (geocoding, insurer directories, PubMed emails, ORCID re-enablement)
Phase 13: Advanced Clinical (migration 088, drug-allergy, dose ranges, off-label, pharmacogenomics, alert rules)
Phase 14: Conference & Workforce Data (conference abstracts, PBM formularies, State APCD framework, BLS OEWS, DE-SynPUF)
Phase 15: Polish (validation, backward compat, cleanup)
```

**Dependency graph**:
```
Phase 2 (Foundation) ← BLOCKS ALL
  ├── Phase 3 (US1+US2) ← MVP
  │   ├── Phase 8 (US6)
  │   ├── Phase 12 (Contact Enrichment) — needs silver.providers
  │   └── Phase 6 (US9, partial)
  ├── Phase 4 (US3)
  │   ├── Phase 9 (US7) — needs PECOS/CHOW + SEC EDGAR
  │   └── Phase 6 (US9, partial)
  ├── Phase 5 (US4)
  │   ├── Phase 6 (US9, partial)
  │   └── Phase 13 (Advanced Clinical) — needs drug pipeline
  ├── Phase 7 (US5)
  ├── Phase 10 (US8)
  ├── Phase 11 (Agentic) — needs Phases 3-7 complete
  │   └── Phase 14 (Workforce Data) — needs agent infrastructure
  └── Phase 15 (Polish) ← LAST
```

### Verification

```bash
# 1. Validate SQLMesh models compile
cd src && python -m sqlmesh plan --no-prompts

# 2. Run tests
pytest tests/test_cms_puf_*.py tests/test_agents/ -v

# 3. Validate k8s manifests
kubectl kustomize k8s/overlays/staging --enable-helm > /dev/null

# 4. Test MCP tool count (expected: ~68)
python -c "from dk_data.services.mcp.tool_registry import TOOL_REGISTRY; print(f'Tools: {len(TOOL_REGISTRY)}')"

# 5. Test NPI lookup via MCP
curl -X POST http://localhost:8000/api/v1/mcp/tools/nppes-search/invoke \
  -H "Content-Type: application/json" -H "Authorization: Bearer $JWT" \
  -d '{"npi": "1234567890"}'

# 6. Test PostgREST gold access
curl -H "Authorization: Bearer $JWT" \
  http://localhost:3000/gold/provider_profile?npi=eq.1234567890

# 7. Verify catalog entries
curl -H "Authorization: Bearer $JWT" \
  http://localhost:3000/api/catalog?source_name=like.*cms*

# 8. Check metrics
curl http://localhost:8000/api/v1/monitoring/metrics | grep dk_providers_total

# 9. Test agent runner
python -m dk_data.claude_sdk.runner --agent service_line_inference --dry-run

# 10. Verify agent registry (expected: 6)
python -c "from dk_data.claude_sdk.agent_registry import AGENT_REGISTRY; print(f'Agents: {len(AGENT_REGISTRY)}')"
```
