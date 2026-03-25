# Feature Specification: Assessment Dashboard Integration

**Feature Branch**: `015-assessment-dashboard-integration`
**Created**: 2026-02-25
**Status**: Draft
**Input**: GitHub Issue #120 — Assessment Dashboard Integration: PostgREST schema expansion, cache tables, KOL/advocacy views, trial outcomes, financial data, MCP data retrieval, and connectivity verification
**Tracking Issue**: data-kinetic-projects/xenon#2
**Xenon Spec Branch**: `003-molecule-assessment-dashboard`

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Xenon Dashboard Reads Molecule Data (Priority: P1)

The xenon assessment dashboard needs to query molecule profile data, clinical trial data, safety signals, and metadata from the data platform. Currently, only two data schemas are accessible to external consumers. The dashboard requires read access to four additional schemas containing gold-layer molecule profiles, silver-layer detailed records, application-specific data, and platform metadata.

**Why this priority**: This is the foundational capability — every data section in the assessment dashboard depends on being able to read molecule data from the data platform. Without this, nothing else works.

**Independent Test**: Can be fully tested by issuing authenticated read requests against molecule profiles and clinical trial tables and confirming data is returned. Delivers the core data access needed for all dashboard sections.

**Acceptance Scenarios**:

1. **Given** an authenticated user with analyst-level permissions, **When** they request molecule profile data, **Then** the system returns molecule records with all profile fields.
2. **Given** an authenticated user with analyst-level permissions, **When** they request clinical trial data for a specific molecule, **Then** the system returns all trials linked to that molecule.
3. **Given** an unauthenticated request, **When** it queries publicly exposed health/catalog endpoints, **Then** the system returns data without requiring credentials.
4. **Given** an unauthenticated request, **When** it queries molecule-specific data, **Then** the system returns an authorization error (401/403).
5. **Given** the expanded schema access, **When** any existing endpoint is queried, **Then** it continues to return the same data as before (no regression).

---

### User Story 2 - Xenon Stores AI-Generated Assessment Content (Priority: P1)

The assessment dashboard's AI agents generate structured content for sections such as executive summary, key metrics, financial analysis, HCP segmentation, patient journey, market opportunity, dosing/administration, risk assessment, strategic recommendations, and investment thesis. This generated content needs persistent storage so it can be cached, versioned, and retrieved without re-generation.

**Why this priority**: Without persistent storage for generated content, every page load would require expensive AI re-generation, making the dashboard unusable in practice.

**Independent Test**: Can be tested by writing a generated assessment record and then reading it back, verifying content integrity and version tracking. Delivers the caching foundation for AI content.

**Acceptance Scenarios**:

1. **Given** an assessment agent has generated content for a molecule's executive summary, **When** it writes the content to the platform, **Then** the content is stored with molecule ID, section type, version, and generation metadata.
2. **Given** stored assessment content exists for a molecule, **When** a dashboard user loads that molecule's page, **Then** the cached content is returned instantly without re-generation.
3. **Given** a newer version of content is generated, **When** it is written, **Then** it is stored as a new version while the previous version remains accessible.
4. **Given** content for the same molecule and section already exists at the same version, **When** a duplicate write is attempted, **Then** it is handled via deduplication (upsert) without creating duplicates.

---

### User Story 3 - Dashboard Displays KOL and Advocacy Data (Priority: P2)

The assessment dashboard includes Key Opinion Leader (KOL) and patient advocacy sections. KOL data includes researcher profiles with influence metrics (h-index, publications, citations, clinical trial involvement, grants), co-authorship networks, and drug associations. Advocacy data includes patient advocacy organizations by disease focus and sentiment signals from news and media sources.

**Why this priority**: KOL and advocacy sections are core Tier 1 data sections in the dashboard. They require dedicated data views that aggregate and expose data from multiple underlying source tables.

**Independent Test**: Can be tested by querying KOL profile data and verifying researcher records with influence metrics are returned. Delivers the KOL and advocacy data sections independently.

**Acceptance Scenarios**:

1. **Given** a request for KOL profiles, **When** filtered by therapeutic area, **Then** the system returns researchers with h-index, publication count, citation count, trial count, grant count, affiliations, and expertise areas.
2. **Given** a request for a KOL's network, **When** queried by researcher ID, **Then** the system returns co-authorship relationships with shared publication counts.
3. **Given** a request for KOL-drug associations, **When** queried by drug name or molecule ID, **Then** the system returns associated KOLs with association types.
4. **Given** a request for advocacy groups, **When** filtered by indication, **Then** the system returns organizations with disease focus, size estimates, and activities.
5. **Given** a request for advocacy sentiment, **When** filtered by molecule ID, **Then** the system returns sentiment signals by source with signal counts and recent signals.

---

### User Story 4 - On-Demand Drug-Specific Data Retrieval (Priority: P2)

When the assessment dashboard needs data for a specific drug/molecule that is not yet in the data platform (tables are empty or incomplete), an automated data retrieval system should fetch drug-specific data from 28 external sources on demand. These tools span clinical/regulatory data, molecule/target data, publications/IP, financial/competitive intelligence, literature feeds, trademarks, and healthcare infrastructure context. After fetching, the data should be persisted through the standard data pipeline so it is available for future queries.

**Why this priority**: Without on-demand retrieval, the dashboard shows empty sections for any molecule that hasn't been batch-ingested. This is the fallback mechanism that makes the dashboard useful for any molecule, not just pre-loaded ones.

**Independent Test**: Can be tested by requesting data for a specific drug name (e.g., "durvalumab") via the retrieval tools and verifying that external API results are returned and subsequently available in the platform's data tables.

**Acceptance Scenarios**:

1. **Given** a drug name, **When** a clinical trials retrieval tool is invoked, **Then** the system queries the external trials API and returns drug-specific trial data with NCT IDs, phases, enrollment, and dates.
2. **Given** a drug name, **When** a safety/adverse events retrieval tool is invoked, **Then** the system returns adverse event reports and signal counts from the regulatory database.
3. **Given** a drug name, **When** a publications retrieval tool is invoked, **Then** the system returns relevant publications with PMIDs, abstracts, and citation data.
4. **Given** any retrieval tool is invoked successfully, **When** results are returned, **Then** the fetched data is also persisted to the platform's data pipeline for future queries.
5. **Given** a retrieval tool is invoked with an unknown drug, **When** no results are found, **Then** the system returns a structured empty response (not an error).
6. **Given** a retrieval tool is invoked without valid analyst-level authentication, **When** the request is processed, **Then** the system returns an authorization error.

---

### User Story 5 - Combined Trial Outcomes from Multiple Evidence Sources (Priority: P2)

Clinical trial outcome data comes from two sources: structured results posted to government trial registries (~30% of completed trials report this) and evidence extracted by AI from publication abstracts (~70% coverage gap). The dashboard needs a unified view that combines both sources, with each row indicating its evidence source and a confidence score.

**Why this priority**: Trial outcomes are a critical assessment section. Relying solely on structured registry data would leave 70% of trials without outcome data.

**Independent Test**: Can be tested by querying trial outcomes for a molecule and verifying that results include rows from both evidence sources with appropriate confidence scores. Delivers the complete trial outcomes section.

**Acceptance Scenarios**:

1. **Given** a molecule with structured trial results in the registry, **When** trial outcomes are queried, **Then** results include rows with evidence_source "clinicaltrials_gov" and confidence_score 1.0.
2. **Given** a molecule with AI-extracted publication evidence, **When** trial outcomes are queried, **Then** results include rows with evidence_source "publication" and confidence_score between 0.40 and 1.0.
3. **Given** a molecule with both sources of evidence, **When** trial outcomes are queried, **Then** both sources appear in the unified results with their respective confidence scores.
4. **Given** extracted publication evidence with confidence below 0.40, **When** trial outcomes are queried, **Then** the low-confidence evidence is excluded from results.

---

### User Story 6 - On-Demand Data Pipeline Propagation (Priority: P3)

When on-demand retrieval tools (Story 4) fetch data from external APIs, the raw data needs to be transformed through the platform's standard data pipeline (raw layer to intermediate layer to refined layer) before it can appear in the views and tables the dashboard queries. Currently, this transformation only runs as a daily batch job. An on-demand trigger is needed so retrieved data is available within minutes, not hours.

**Why this priority**: Without on-demand transformation, data fetched by retrieval tools would sit in the raw layer until the next daily batch run — making on-demand retrieval pointless for real-time dashboard use.

**Independent Test**: Can be tested by inserting a raw data record and triggering the on-demand transformation, then verifying the record appears in the refined data tables within minutes.

**Acceptance Scenarios**:

1. **Given** raw data has been inserted for a specific source, **When** the on-demand transformation is triggered for that source, **Then** the system processes the raw data through all transformation layers.
2. **Given** an on-demand transform request, **When** the transformation completes, **Then** only unprocessed rows are transformed (not the entire dataset).
3. **Given** a transform request for a specific molecule, **When** processed, **Then** only rows for that molecule are transformed.
4. **Given** the daily batch transformation is running, **When** an on-demand transform is requested, **Then** the on-demand request is queued rather than conflicting with the batch job.
5. **Given** more than 10 transform requests per minute for the same source, **When** additional requests arrive, **Then** they are rate-limited to prevent system overload.

---

### User Story 7 - LLM-Extracted Publication Evidence Storage (Priority: P3)

The xenon assessment system uses AI to extract structured clinical endpoint data (hazard ratios, p-values, response rates, survival metrics) from publication abstracts. This extracted evidence needs persistent storage with deduplication, confidence scoring, and source provenance tracking, so it can feed into the unified trial outcomes view (Story 5).

**Why this priority**: This is the data foundation for the publication-derived half of the trial outcomes view, covering the ~70% of trials that lack structured registry results.

**Independent Test**: Can be tested by writing extracted evidence records and reading them back, verifying deduplication and confidence score filtering. Delivers the publication evidence storage independently.

**Acceptance Scenarios**:

1. **Given** an AI extraction pipeline produces structured endpoint data from a publication, **When** it writes the evidence to the platform, **Then** the record includes molecule ID, endpoint details, confidence score, and source provenance (DOI/PMID).
2. **Given** evidence for the same molecule/endpoint/trial already exists, **When** a duplicate is written, **Then** the system deduplicates using a content hash without creating duplicate records.
3. **Given** stored publication evidence, **When** queried by molecule ID, **Then** all evidence records are returned with confidence scores and source references.

---

### User Story 8 - Cross-Service Authentication and Connectivity (Priority: P3)

The xenon assessment dashboard and its backend services need to authenticate to the data platform using shared credentials. The authentication mechanism must work across different deployment environments (local development, staging cluster, production) and support both read-only access for public data and authenticated read/write access for analyst-level operations.

**Why this priority**: Authentication and connectivity are prerequisites for all cross-service data access. If the dashboard cannot authenticate, none of the data stories work.

**Independent Test**: Can be tested by generating analyst-level credentials and making authenticated requests from the consumer application's container environment, verifying data is returned.

**Acceptance Scenarios**:

1. **Given** valid analyst-level credentials, **When** a request is made from the consumer application's container, **Then** the data platform returns the requested data.
2. **Given** expired credentials, **When** a request is made, **Then** the data platform returns an authentication error.
3. **Given** credentials with insufficient permissions, **When** a write operation is attempted, **Then** the data platform returns an authorization error.
4. **Given** each deployment environment (local, staging, production), **When** the base URL for that environment is used, **Then** the data platform is reachable and responds correctly.

---

### User Story 9 - Financial Data for Assessment Analysis (Priority: P4)

The assessment dashboard includes a Financial Analysis section covering revenue projections, drug pricing, and health economic valuations. A data ingestion pipeline is needed to bring financial data (regulatory filings, health technology assessments, pricing data) into the platform so the Financial Analysis section can be backed by real data rather than solely AI-generated content.

**Why this priority**: Financial data is important for a complete assessment but is not a launch blocker. The AI generation system can produce reasonable financial analysis content without a dedicated data pipeline at MVP.

**Independent Test**: Can be tested by verifying that financial data records are ingested and queryable via the data platform. Delivers the financial data section with real data backing.

**Acceptance Scenarios**:

1. **Given** financial data has been ingested for a company, **When** the financial summary is queried, **Then** the system returns structured financial metrics (revenue, pricing, economic valuations).
2. **Given** no financial data exists for a company, **When** the financial summary is queried, **Then** the system returns an empty result set (allowing the dashboard to fall back to AI generation).

---

### User Story 10 - Data Field Verification for Dashboard Requirements (Priority: P4)

Several dashboard sections depend on specific data fields existing in existing tables: trial end dates for waterfall timeline visualization, and company pipeline detail fields (indication, mechanism of action, enrollment, expected completion) for pipeline section rendering. These fields need to be verified and, if missing, added.

**Why this priority**: These are data completeness checks that enhance existing sections. The dashboard can render partial data if fields are missing, but complete data improves the user experience.

**Independent Test**: Can be tested by querying the relevant tables and verifying the expected fields exist with non-null values.

**Acceptance Scenarios**:

1. **Given** a clinical trial record, **When** trial data is queried, **Then** an end/completion date field is present and populated.
2. **Given** a company pipeline record, **When** pipeline data is queried, **Then** indication, mechanism of action, enrollment, and expected completion fields are present.

---

### User Story 11 - Developer Tooling for Extending Data Retrieval (Priority: P4)

As new external data sources are added to the platform, developers need a streamlined way to create corresponding on-demand retrieval tool wrappers, register them in the tool registry, and generate input/output schemas. An automated skill/template should reduce boilerplate and ensure consistency.

**Why this priority**: Developer experience enhancement. Not needed for initial launch but reduces friction for ongoing development.

**Independent Test**: Can be tested by using the skill to generate a new tool wrapper and verifying all necessary files are created with correct structure.

**Acceptance Scenarios**:

1. **Given** a developer describes a new data source, **When** they invoke the tooling skill, **Then** it generates a tool wrapper, registers it, and creates input/output schemas.
2. **Given** the generated tool follows platform patterns, **When** reviewed, **Then** it is consistent with existing tool implementations.

---

### Edge Cases

- What happens when an external API is unreachable or times out during on-demand retrieval? The tool should return a structured error response indicating the source is unavailable or timed out, not a raw exception. The raw table should NOT receive a partial/empty record. Each source has a configurable timeout (default 30s) in the rate limit registry.
- What happens when the daily batch transform and an on-demand transform target the same source simultaneously? The on-demand request should be queued or serialized to prevent data corruption. SQLMesh's incremental processing and the `processed_to_bronze`/`processed_to_silver` flags must prevent double-processing of rows.
- What happens when a molecule has no data in any table? The dashboard should gracefully show empty states rather than errors.
- What happens when a JWT token is malformed (not just expired)? The system should return a clear authentication error.
- What happens when on-demand retrieval fetches data that conflicts with existing batch-ingested data? The raw table stores both records (each with its own `request_id`). Bronze deduplication (by source-specific unique keys like `nct_id`, `chembl_id`) ensures only one record propagates to silver.
- What happens when publication evidence extraction produces a confidence score exactly at the 0.40 threshold? The evidence should be included (greater-than-or-equal semantics).
- What happens when an MCP tool's per-source adapter produces a `response_body` structure that doesn't match the batch fetcher's format? The bronze SQLMesh model will fail to parse the record. Each adapter MUST be validated against its bronze model via integration tests before deployment. If the adapter produces a field the model doesn't expect, the extra field is silently ignored by the model. If the adapter is missing a field the model requires, the model will produce NULLs or fail — this MUST be caught by adapter tests.
- What happens when an MCP tool calls a different API endpoint than the batch fetcher and the response schema has different nesting? The per-source adapter must flatten/restructure the response to match the canonical format. For high-divergence sources (e.g., DrugBank REST API vs XML dump), the adapter is substantial and requires dedicated testing.
- What happens when `PGRST_DB_SCHEMAS` is expanded but a table in the newly exposed schema has columns that should not be publicly visible? PostgREST exposes ALL tables in listed schemas by default. Role-level GRANT/REVOKE must be the access control mechanism — only tables with explicit SELECT grants for the requesting role will return data.

## Medallion Architecture Constraints *(mandatory)*

This section defines hard constraints to prevent architectural drift. All changes in this feature MUST preserve the existing medallion pipeline: raw → bronze → silver → gold.

### Constraint 1: MCP Tools Write to Existing Raw Tables — With Adapter Pattern

Each MCP tool persists fetched data into the **same raw table** that the corresponding batch fetcher writes to. MCP tools MAY call different external API endpoints than the batch fetchers (e.g., search APIs vs bulk download endpoints) to optimize for single-drug queries. However, each tool MUST include a **per-source adapter** that normalizes the API response into the canonical `response_body` JSONB structure that the bronze SQLMesh model expects.

The adapter contract per source:
1. The tool calls the best-fit external API endpoint for single-drug lookup
2. The adapter transforms the response into the same JSONB structure the batch fetcher produces
3. The normalized response is inserted as `response_body` with `processed_to_bronze = FALSE` plus standard request metadata (`request_id`, `request_timestamp`, `api_endpoint`, `request_params`, `response_status`, `ingested_at`)
4. Each adapter MUST be tested against its corresponding bronze SQLMesh model to verify the model can parse the adapted `response_body` without errors

**Canonical tool-to-raw-table mapping** (verified against codebase):

| MCP Tool | Raw Table | Schema | Adapter Needed |
| -------- | --------- | ------ | -------------- |
| clinicaltrials-search | clinicaltrials | mol_raw | Yes — search v2 API vs bulk v2 API |
| fda-faers-query | openfda_faers | mol_raw | Yes — drug-specific query vs bulk download |
| fda-drug-labels | openfda_labels | mol_raw | Yes — drug-specific query vs bulk download |
| fda-orange-book | orange_book | raw | Yes — drug-specific query vs bulk download |
| openfda-approvals | openfda_labels | mol_raw | Shares table with fda-drug-labels; adapter normalizes approval-specific fields |
| ema-regulatory | ema | raw | Yes — product search vs bulk regulatory data |
| hta-decisions | hta_decisions | raw | Minimal — existing fetcher already supports drug-name query |
| cochrane-reviews | cochrane_reviews | raw | Minimal — existing fetcher already supports drug-name search |
| chembl-molecule-lookup | chembl | mol_raw | Yes — REST search vs bulk API |
| drugbank-lookup | drugbank | mol_raw | Yes — REST API vs XML bulk download (fundamentally different format) |
| uniprot-proteins | uniprot | mol_raw | Minimal — existing fetcher uses same REST query |
| pdb-structures | pdb_structures | raw | **NEW TABLE** — create `raw.pdb_structures` with standard schema |
| pubmed-search | pubmed | raw | Minimal — existing fetcher uses same eutils query |
| openalex-publications | openalex | mol_raw | Minimal — existing fetcher supports text search |
| uspto-patents | uspto_patents | raw | Minimal — existing fetcher supports text search |
| epo-patents | epo_patents | raw | Minimal — existing fetcher uses same CQL search |
| sec-edgar-financials | sec_edgar | raw | Yes — full-text search vs SIC-code bulk fetch |
| who-icd-lookup | who_icd | raw | **NEW TABLE** — create `raw.who_icd` with standard schema |
| orcid-researchers | orcid | raw | Minimal — existing fetcher uses same search API |
| journal-articles | journal_rss | raw | Minimal — existing fetcher uses same RSS feeds |
| medical-news | medical_news | raw | Minimal — existing fetcher uses same RSS feeds |
| uspto-trademarks | uspto_trademarks | raw | Minimal — existing fetcher uses TSDR lookup |
| euipo-trademarks | euipo_trademarks | raw | Minimal — existing fetcher uses TMview search |
| cms-inpatient | cms_medicare_inpatient | raw | Minimal — existing fetcher uses DRG filter |
| cms-hospital-info | cms_hospital_info | raw | Minimal — existing fetcher uses state/type filter |
| cms-cost-reports | cms_cost_reports | raw | Minimal — existing fetcher uses provider ID |
| acc-tvc | acc_tvc_certification | raw | Minimal — existing fetcher uses geo filter |
| hrsa-hpsa | hrsa_shortage_areas | raw | Minimal — existing fetcher uses geo filter |

**New raw tables required** (2):
- `raw.pdb_structures` — PDB protein structure co-crystal data. Standard raw schema. New bronze model required.
- `raw.who_icd` — WHO ICD-10 code mappings. Standard raw schema. New bronze model required.

### Constraint 2: Dual Schema Awareness

The platform uses TWO raw schemas, not one:
- **`mol_raw.*`** — molecule-specific API responses (ChEMBL, PubChem, ClinicalTrials, OpenFDA, DrugBank, UniProt, SIDER, OpenAlex)
- **`raw.*`** — IP, regulatory, financial, CMS, and general data sources (USPTO, EPO, EUIPO, EMA, HTA, Cochrane, PubMed, SEC, ORCID, journal RSS, medical news, CMS, ACC, HRSA)

MCP tools MUST write to the correct schema for their source. The on-demand transform endpoint MUST accept both schemas and route accordingly.

### Constraint 3: Full Pipeline Coverage for All 28 MCP Sources

New gold-layer **views** (KOL profiles, advocacy, trial outcomes) are read-only aggregations of existing silver data — this is permitted and does not introduce pipeline drift.

Every MCP tool source MUST have a complete medallion pipeline (raw table → bronze SQLMesh model → silver SQLMesh model) so that on-demand retrieval always triggers full transformation. For sources that currently lack bronze/silver models, new models MUST be created as part of this feature. No MCP tool operates in return-only mode.

**Sources requiring new bronze+silver SQLMesh models** (15 sources):

| Source | New Raw Table? | New Bronze Model | New Silver Model | Notes |
| ------ | -------------- | ---------------- | ---------------- | ----- |
| pubmed | No (raw.pubmed exists) | bronze.pubmed | silver.publications (extend) | Feeds into existing publications silver table |
| ema | No (raw.ema exists) | bronze.ema (exists) | silver.regulatory_decisions (new) | EMA regulatory decisions |
| hta_decisions | No (raw.hta_decisions exists) | bronze.hta_decisions | silver.regulatory_decisions (extend) | HTA body decisions |
| cochrane_reviews | No (raw.cochrane_reviews exists) | bronze.cochrane_reviews | silver.publications (extend) | Systematic reviews |
| orange_book | No (raw.orange_book exists) | bronze.orange_book (exists) | silver.patents (extend) | FDA patent/exclusivity |
| sec_edgar | No (raw.sec_edgar exists) | bronze.sec_edgar | silver.financial_data (new) | SEC financial filings |
| orcid | No (raw.orcid exists) | bronze.orcid | silver.researchers (new) | Researcher profiles for KOL |
| journal_rss | No (raw.journal_rss exists) | bronze.journal_rss | silver.publications (extend) | Journal article feeds |
| medical_news | No (raw.medical_news exists) | bronze.medical_news | silver.news_signals (new) | Medical/pharma news |
| cms_medicare_inpatient | No (raw.cms_medicare_inpatient exists) | bronze.cms_inpatient | silver.healthcare_facilities (new) | CMS procedure data |
| cms_hospital_info | No (raw.cms_hospital_info exists) | bronze.cms_hospital_info | silver.healthcare_facilities (extend) | Hospital demographics |
| cms_cost_reports | No (raw.cms_cost_reports exists) | bronze.cms_cost_reports | silver.healthcare_facilities (extend) | Hospital financials |
| acc_tvc | No (raw.acc_tvc_certification exists) | bronze.acc_tvc | silver.healthcare_facilities (extend) | Site certifications |
| hrsa | No (raw.hrsa_shortage_areas exists) | bronze.hrsa | silver.healthcare_facilities (extend) | Shortage area data |
| pdb_structures | **Yes** (raw.pdb_structures) | bronze.pdb_structures | silver.targets (extend) | Protein co-crystal structures |
| who_icd | **Yes** (raw.who_icd) | bronze.who_icd | silver.icd_codes (new) | ICD-10 reference codes |

**New silver tables introduced**: `silver.regulatory_decisions`, `silver.financial_data`, `silver.researchers`, `silver.news_signals`, `silver.healthcare_facilities`, `silver.icd_codes`. These extend the silver layer without modifying existing silver tables.

**Existing silver tables extended**: `silver.publications` (add PubMed/Cochrane/journal sources), `silver.patents` (add Orange Book source), `silver.targets` (add PDB structural data).

All new models MUST follow existing SQLMesh conventions: incremental processing, `processed_to_bronze`/`processed_to_silver` flags, unique key deduplication, and `LAYER_MODELS` registry inclusion.

### Constraint 4: On-Demand Transform Uses Same SQLMesh Models as Batch

The on-demand transform endpoint MUST invoke the same SQLMesh models as the daily batch job. It uses `sqlmesh run --select-model {model_name}` to target specific models. After this feature, ALL 28 sources have complete pipelines and the on-demand transform works for every source.

**Existing molecule pipeline sources → models** (already in `LAYER_MODELS`):

| Source | Bronze Model | Silver Model(s) | Gold Model(s) |
| ------ | ------------ | ---------------- | -------------- |
| clinicaltrials | mol_bronze.clinical_trials | mol_silver.clinical_trials | mol_gold.molecule_profiles_agg, mol_gold.trial_analytics_agg |
| chembl | mol_bronze.chembl_molecules | mol_silver.molecules_from_bronze | mol_gold.molecule_profiles_agg |
| openfda_labels | mol_bronze.openfda_labels | mol_silver.drug_labels | mol_gold.molecule_profiles_agg |
| openfda_faers | mol_bronze.openfda_faers | mol_silver.adverse_events | mol_gold.safety_signals_agg |
| pubchem | mol_bronze.pubchem_compounds | mol_silver.molecules_from_bronze | mol_gold.molecule_profiles_agg |
| drugbank | *(dynamic silver transform)* | mol_silver.molecules_from_bronze | mol_gold.molecule_profiles_agg |
| openalex | *(bronze model exists)* | mol_silver.publications, mol_silver.molecule_publications | mol_gold.molecule_profiles_agg |
| uniprot | *(bronze model exists)* | mol_silver.targets, mol_silver.molecule_targets | mol_gold.molecule_profiles_agg |

**Existing IP pipeline sources → models** (already in `LAYER_MODELS`):

| Source | Bronze Model | Silver Model | Gold Model |
| ------ | ------------ | ------------ | ---------- |
| uspto_patents | bronze.uspto_patents | silver.patents | gold.molecule_profile |
| epo_patents | bronze.epo_patents | silver.patents | gold.molecule_profile |
| uspto_trademarks | bronze.uspto_trademarks | silver.trademarks | gold.molecule_profile |
| euipo_trademarks | bronze.euipo_trademarks | silver.trademarks | gold.molecule_profile |
| orange_book | bronze.orange_book | silver.patents | gold.molecule_profile |

**NEW pipeline models to create** (must be added to `LAYER_MODELS` after creation):

| Source | Bronze Model (new) | Silver Model (new/extend) | Gold Model |
| ------ | ------------------ | ------------------------- | ---------- |
| pubmed | bronze.pubmed | silver.publications (extend) | gold.molecule_profile |
| ema | bronze.ema *(may exist)* | silver.regulatory_decisions (new) | mol_gold.regulatory_timeline (new — cross-joins molecules) |
| hta_decisions | bronze.hta_decisions | silver.regulatory_decisions (extend) | mol_gold.regulatory_timeline (shared) |
| cochrane_reviews | bronze.cochrane_reviews | silver.publications (extend) | gold.molecule_profile |
| sec_edgar | bronze.sec_edgar | silver.financial_data (new) | mol_gold.financial_summary (new — cross-joins molecules/companies) |
| orcid | bronze.orcid | silver.researchers (new) | mol_gold.kol_profiles (feeds existing planned view) |
| journal_rss | bronze.journal_rss | silver.publications (extend) | gold.molecule_profile |
| medical_news | bronze.medical_news | silver.news_signals (new) | mol_gold.advocacy_sentiment (feeds existing planned view) |
| cms_medicare_inpatient | bronze.cms_inpatient | silver.healthcare_facilities (new) | *(silver-only — no molecule cross-join)* |
| cms_hospital_info | bronze.cms_hospital_info | silver.healthcare_facilities (extend) | *(silver-only)* |
| cms_cost_reports | bronze.cms_cost_reports | silver.healthcare_facilities (extend) | *(silver-only)* |
| acc_tvc | bronze.acc_tvc | silver.healthcare_facilities (extend) | *(silver-only)* |
| hrsa | bronze.hrsa | silver.healthcare_facilities (extend) | *(silver-only)* |
| pdb_structures | bronze.pdb_structures | silver.targets (extend) | gold.molecule_profile |
| who_icd | bronze.who_icd | silver.icd_codes (new) | *(silver-only — reference lookup)* |

All new models MUST be registered in `LAYER_MODELS` in `transform_molecules.py` and follow existing SQLMesh conventions (incremental, processing flags, unique key dedup).

### Constraint 5: Application Data Lives Outside the Medallion Pipeline

The `xenon` schema stores **application output** data written by external consumers. It is explicitly NOT part of the raw → bronze → silver → gold medallion pipeline:
- `xenon.assessment_generated` — AI-generated content (written by xenon, read by xenon)
- `xenon.publication_evidence` — LLM-extracted clinical evidence (written by xenon, consumed by `mol_gold.trial_outcomes` view as a UNION source)

These tables are accessed via PostgREST directly. They do NOT flow through bronze/silver transformation. This is intentional: application-generated data is not raw API data and should not enter the medallion pipeline.

The `xenon` schema is distinct from the existing `mol_app` schema, which serves dk-data-FE internal features (user tracking, annotations, alerts with row-level security). The `xenon` schema serves the xenon application specifically.

### Constraint 6: Gold Views Are Read-Only Aggregations

New `mol_gold.*` views (kol_profiles, kol_network, kol_drug_associations, advocacy_groups, advocacy_sentiment, trial_outcomes) MUST be defined as SQL views (or materialized views) that SELECT from existing silver tables. They MUST NOT:
- Accept direct writes
- Contain data that bypasses the medallion pipeline
- Create circular dependencies with application tables (exception: `mol_gold.trial_outcomes` legitimately UNIONs from `xenon.publication_evidence` — this is documented and intentional)

### Constraint 7: Role Alignment — Use Existing `analyst` Role

**Decision**: Xenon uses the existing `analyst` database role (already granted to `authenticator` in db-init-job.yaml). This avoids creating new roles or patching the `authenticator` → `mol_analyst` grant chain.

The implementation MUST:
1. Add `GRANT USAGE ON SCHEMA mol_gold TO analyst` and `GRANT SELECT ON ALL TABLES IN SCHEMA mol_gold TO analyst` (and similarly for `mol_silver`, `xenon`, `meta`) to db-init-job.yaml
2. Add `GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA xenon TO analyst` for write access to xenon application data
3. Ensure JWT tokens issued for xenon carry `"role": "analyst"` (matching the existing JWT service ANALYST tier)
4. Verify PostgREST can switch to the `analyst` role when processing JWT-authenticated requests against the newly exposed schemas
5. Update issue #120's references from `mol_analyst` to `analyst` in implementation

**Note**: The `mol_analyst` role from migration 020 is NOT used for this feature. If future features need finer-grained molecule-specific permissions, `mol_analyst` can be introduced then with proper `authenticator` grant chain. For now, `analyst` provides the correct permission scope.

---

## Requirements *(mandatory)*

### Functional Requirements

**Schema & Access**

- **FR-001**: System MUST expose molecule gold-layer data, silver-layer data, application data, and metadata schemas for authenticated read access via PostgREST.
- **FR-002**: System MUST create a dedicated `xenon` application schema for consumer-written data (assessment content, publication evidence), separate from both the medallion pipeline schemas (`mol_raw`/`mol_bronze`/`mol_silver`/`mol_gold`) and the existing internal app schema (`mol_app`).
- **FR-003**: System MUST support role-based access: read-only for `web_anon` on public endpoints only, read access for `analyst` on gold/silver/meta, and read+write for `analyst` on the `xenon` schema. The existing `analyst` database role (already granted to `authenticator`) is used — no new roles created.
- **FR-017**: System MUST maintain backward compatibility — existing `api.*` and `mol_api.*` endpoints must continue functioning identically. Expanding `PGRST_DB_SCHEMAS` MUST NOT change behavior for existing queries.

**Assessment & Evidence Storage**

- **FR-004**: System MUST persist AI-generated assessment content in the `xenon` schema with molecule ID, section type, JSONB content, version tracking, and generation metadata.
- **FR-005**: System MUST deduplicate assessment content writes using a unique constraint on molecule ID, section type, and version.
- **FR-009**: System MUST persist LLM-extracted publication evidence in the `xenon` schema with endpoint details, confidence scores, source provenance (DOI/PMID), and content-hash-based deduplication.

**Gold-Layer Views**

- **FR-006**: System MUST provide aggregated KOL profile views in `mol_gold` with influence metrics (h-index, publications, citations, trials, grants), network relationships, and drug associations — sourced exclusively from existing silver tables.
- **FR-007**: System MUST provide aggregated advocacy views in `mol_gold` with organization profiles by disease focus and sentiment signal tracking — sourced exclusively from existing silver tables.
- **FR-008**: System MUST provide a unified trial outcomes view in `mol_gold` combining structured registry results (confidence 1.0) from silver clinical trials data and AI-extracted publication evidence (confidence 0.40-1.0) from the `xenon` schema, with source attribution on each row.
- **FR-018**: System MUST ensure KOL influence scoring uses documented formula: h_index * 0.3 + publications * 0.2 + citations * 0.25 + trials * 0.15 + grants * 0.1, with tier thresholds at 95th (Global), 80th (National), 50th (Regional), and below 50th (Rising).
- **FR-027**: System MUST provide a `mol_gold.regulatory_timeline` view that cross-joins `silver.regulatory_decisions` with `silver.molecules` to present per-molecule regulatory decision history across EMA and HTA agencies.
- **FR-028**: System MUST provide a `mol_gold.financial_summary` view that cross-joins `silver.financial_data` with `silver.molecules` (via company/sponsor linkage) to present per-molecule financial metrics from SEC filings.

**On-Demand Data Retrieval (MCP)**

- **FR-010**: System MUST provide 28 on-demand data retrieval tools organized in three tiers: 19 direct drug-name query tools, 4 fetch-and-filter tools, and 5 supplementary context tools.
- **FR-011**: System MUST authenticate on-demand retrieval tool access using the same JWT credential mechanism as PostgREST (analyst-level role, same secret).
- **FR-012**: Each on-demand retrieval tool MUST persist fetched data to the **same raw table** used by the corresponding batch fetcher (see Constraint 1 mapping). MCP tools MAY call different external API endpoints than batch fetchers, but each MUST include a **per-source adapter** that normalizes the response into the canonical `response_body` JSONB structure the bronze model expects. Records include `processed_to_bronze = FALSE` plus standard request metadata columns. Two new raw tables (`raw.pdb_structures`, `raw.who_icd`) are created for sources that currently lack them.
- **FR-020**: System MUST return structured error responses (not raw exceptions) from all on-demand retrieval tools.
- **FR-021**: On-demand retrieval tools MUST NOT write directly to bronze/silver/gold tables. The only write target is the source's raw table. Two new raw tables are created as part of this feature (`raw.pdb_structures`, `raw.who_icd`) — no other new tables are created at runtime.
- **FR-022**: Every retrieval tool MUST trigger the on-demand transform (FR-013) after raw insert, since all 28 sources will have complete bronze+silver pipelines after this feature is implemented (see Constraint 3).
- **FR-025**: Each per-source adapter MUST be tested against its corresponding bronze SQLMesh model to verify the adapted `response_body` can be parsed without errors. Adapter tests are mandatory before a tool is considered complete.
- **FR-026**: Each MCP tool MUST enforce per-source rate limits matching the upstream external API's published limits (e.g., NCBI 3 req/sec, OpenFDA 240 req/min, EPO OPS 10 req/sec). Requests exceeding the limit MUST be queued with exponential backoff (defaults: base_delay=1s, max_delay=30s, max_retries=3, jitter=true; configurable per source in the rate limit registry). A rate limit registry MUST define the limit per source, and the registry MUST be updateable without code changes.
- **FR-029**: Each MCP tool MUST enforce a per-source request timeout (default 30 seconds, configurable per source in the rate limit registry). When a timeout occurs, the tool MUST return a structured error response indicating timeout and the source name. The raw table MUST NOT be written to on timeout — only successful, complete API responses are persisted. The timeout value is stored alongside rate limits in the same per-source registry.

**On-Demand Transform**

- **FR-013**: System MUST provide an on-demand transformation trigger scoped to a specific data source and optionally a specific molecule. The trigger MUST invoke the same SQLMesh models used by the daily batch pipeline (see Constraint 4 mapping).
- **FR-014**: System MUST rate-limit on-demand transformations to a maximum of 10 per minute per source.
- **FR-015**: System MUST prevent concurrent on-demand transforms from conflicting with daily batch transforms.
- **FR-023**: The on-demand transform MUST respect existing incremental processing flags (`processed_to_bronze`, `processed_to_silver`) — it processes only rows with `FALSE` flags, same as the batch job.
- **FR-024**: The on-demand transform MUST support both `mol_raw.*` → `mol_bronze.*` → `mol_silver.*` and `raw.*` → `bronze.*` → `silver.*` pipeline paths, routing based on which schema the source table belongs to.

**Verification & Compatibility**

- **FR-016**: System MUST verify or add trial end dates and company pipeline detail fields (indication, mechanism of action, enrollment, expected completion).
- **FR-019**: System MUST provide environment-specific base URLs for all services (local development, staging, production) documented in a central reference.

### Key Entities

- **Assessment Content**: AI-generated assessment section content tied to a molecule. Stored in `xenon` schema (outside medallion pipeline). Key attributes: molecule reference, section type (10 types: executive summary, key metrics, financial analysis, HCP segmentation, patient journey, market opportunity, dosing/administration, risk assessment, strategic recommendations, investment thesis), content body, version, generation source, timestamp.
- **Publication Evidence**: Structured clinical endpoint data extracted from publication abstracts. Stored in `xenon` schema (outside medallion pipeline). Key attributes: molecule reference, trial linkage (optional), endpoint name and type, statistical measures (hazard ratio, p-value, response rates, survival metrics), confidence score, source provenance (DOI/PMID), extraction metadata, content hash for deduplication. Consumed by the `mol_gold.trial_outcomes` UNION view.
- **KOL Profile**: Read-only gold view aggregating researcher data from existing silver tables. Key attributes: identity, h-index, publication/citation/trial/grant counts, affiliations, expertise areas, therapeutic areas, influence tier.
- **KOL Network**: Read-only gold view of co-authorship relationships from existing silver tables. Key attributes: source/target researchers, connection type, shared publication count.
- **Advocacy Group**: Read-only gold view of patient advocacy organizations from existing silver tables. Key attributes: identity, disease focus, size estimate, activities, website, indication.
- **Advocacy Sentiment**: Read-only gold view of media/news sentiment signals from existing silver tables. Key attributes: molecule reference, source, sentiment polarity, signal count, recent signals.
- **Trial Outcome**: Read-only gold UNION view combining structured registry results from silver clinical_trials and LLM-extracted evidence from `xenon.publication_evidence`. Key attributes: molecule reference, trial ID, evidence source, statistical measures, confidence score, sample size, evidence date.
- **Financial Summary**: Aggregated financial data for company/drug analysis. Key attributes: revenue data, pricing information, health economic valuations.

## Clarifications

### Session 2026-02-25

- Q: Should MCP tools enforce per-source rate limits matching upstream API published limits, or react to 429s only? → A: Each MCP tool MUST enforce per-source rate limits matching the upstream API's published limits. Exceeded requests are queued with exponential backoff. A rate limit registry defines limits per source.
- Q: Should gold views be created for new silver tables (regulatory_decisions, financial_data, news_signals, healthcare_facilities, icd_codes)? → A: Gold views for tables that require cross-table aggregation with molecule data (regulatory_decisions → mol_gold.regulatory_timeline, financial_data → mol_gold.financial_summary). Silver tables that already feed planned gold views (researchers → kol_profiles, news_signals → advocacy_sentiment) are covered. Healthcare_facilities and icd_codes stay silver-only (no molecule cross-join needed).
- Q: How should MCP tools handle external API timeouts? → A: Per-source configurable timeout (default 30s) stored in the rate limit registry. Timeout returns structured error response; raw table is NOT written to on timeout.

## Assumptions

- The xenon assessment dashboard is the primary initial consumer, but all capabilities are built as general-purpose data platform features usable by any authenticated application.
- The existing JWT role hierarchy (VIEWER, ANALYST, DATA_OPS, ADMIN) is already implemented and functional. The xenon application uses ANALYST-tier credentials. The JWT `role` claim maps to the existing `analyst` database role (already granted to `authenticator` in db-init).
- The 28 on-demand retrieval tools each correspond to an external API that is publicly accessible (possibly with API keys managed as platform secrets). No new paid API subscriptions are required beyond existing ones.
- The daily batch transformation job runs at 6 AM UTC (daily mol-transform CronJob) and the on-demand transform must avoid conflicts with it.
- Financial data ingestion (Story 9) is acceptable as a documented future work item if no suitable free/existing data source can be identified for MVP.
- The KOL influence formula and tier thresholds are stable and agreed upon by stakeholders.
- Publication evidence confidence threshold of 0.40 is the agreed minimum for inclusion in the unified trial outcomes view.
- All existing raw tables use the standard schema: `id`, `request_id`, `request_timestamp`, `api_endpoint`, `request_params`, `response_status`, `response_body` (JSONB), `processed_to_bronze` (BOOLEAN DEFAULT FALSE), `ingested_at`. MCP tool adapters must produce records conforming to this schema. Two new raw tables (`raw.pdb_structures`, `raw.who_icd`) are created following the same standard schema.
- The `LAYER_MODELS` dictionary in `transform_molecules.py` is the authoritative registry. After this feature, it will be expanded to include all 28 sources (15 new bronze+silver models added).
- The `xenon` schema is a new schema (not yet created). The existing `mol_app` schema serves dk-data-FE internal app features (user tracking, annotations, alerts with row-level security) and is NOT used for xenon application data.
- PostgREST `PGRST_DB_SCHEMAS` will be expanded to directly expose `mol_gold`, `mol_silver`, `xenon`, and `meta` schemas. Access control is enforced via per-role GRANT/REVOKE on individual tables — PostgREST does not expose tables the requesting role lacks SELECT permission on.
- MCP tools may call different external API endpoints than batch fetchers (e.g., search APIs vs bulk APIs). Each tool includes a per-source adapter that normalizes the response into the canonical `response_body` format the corresponding bronze model expects. Adapters are tested against bronze models.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All molecule gold-layer, silver-layer, application, and metadata tables are queryable by authenticated users, with responses returned in under 2 seconds for standard queries.
- **SC-002**: Assessment content read/write round-trip completes successfully — write a generated section, read it back, verify content integrity — for all 10 section types.
- **SC-003**: KOL and advocacy views return data for at least one therapeutic area with all required fields populated.
- **SC-004**: On-demand retrieval tools return drug-specific results for at least 3 different drug names, with results persisted to the correct raw table and available in refined data tables within 5 minutes after on-demand transform completes.
- **SC-005**: Unified trial outcomes view returns rows from both evidence sources (structured registry and publication-extracted) for molecules that have both.
- **SC-006**: On-demand transform processes newly inserted raw rows and makes them available in refined tables within 3 minutes of trigger, using the same SQLMesh models as the daily batch job.
- **SC-007**: Cross-service authentication works from the consumer application's containers across all deployment environments (local, staging, production).
- **SC-008**: No regression in existing data API endpoints — all previously functional queries continue to return identical results. `api.*` and `mol_api.*` schemas unaffected.
- **SC-009**: 100% of on-demand retrieval tools return structured responses (data or error), with zero raw exceptions reaching the caller.
- **SC-010**: Rate limiting prevents more than 10 on-demand transforms per minute per source without dropping requests (excess requests are queued or rejected with clear feedback).
- **SC-011**: Zero new database tables created by MCP tools at runtime. All raw inserts go to tables that exist before deployment (including the 2 new tables created during setup: `raw.pdb_structures`, `raw.who_icd`).
- **SC-012**: All 28 per-source adapters pass integration tests against their corresponding bronze SQLMesh models — adapted `response_body` records are successfully parsed and transformed to bronze layer.
- **SC-013**: All 15 new bronze+silver SQLMesh models are registered in `LAYER_MODELS` and successfully process records via `sqlmesh run --select-model` (same mechanism as daily batch).
