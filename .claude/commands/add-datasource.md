---
description: Add a new external data source with full medallion architecture — raw ingestion, bronze typing, silver entity linking, and gold aggregation.
handoffs:
  - label: Create Feature Spec
    agent: speckit.specify
    prompt: Create a feature spec for adding the new data source
  - label: Generate Tasks
    agent: speckit.tasks
    prompt: Generate implementation tasks for the data source integration
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Outline

This skill guides the complete integration of a new external data source into the dk-data-fe platform following the **medallion architecture**. It covers API discovery, secrets, database schema across all four layers, fetcher/loader code, SQLMesh models, CronJob scheduling, and catalog registration.

The user input should describe the data source to add. It can be:
- A URL to an API or documentation page
- A name and description of the data source
- A path to an OpenAPI spec file
- A brief description of what data to fetch

If the input is empty, ask the user what data source they want to add.

---

## Medallion Architecture Overview

Every data source flows through four layers. Schema prefix is determined by domain:

| Domain | Prefix | Examples |
|--------|--------|---------|
| Healthcare system / CMS | `hcs_` | `hcs_raw`, `hcs_bronze`, `hcs_silver`, `hcs_gold` |
| Molecules / drugs | `mol_` | `mol_raw`, `mol_bronze`, `mol_silver`, `mol_gold` |
| Indications / disease | `ind_` | `ind_raw`, `ind_bronze`, `ind_silver`, `ind_gold` |
| Healthcare professionals | `hcp_` | `hcp_raw`, `hcp_bronze`, `hcp_silver`, `hcp_gold` |

**Schemas vs tables**: Use schemas as prefixes (not table prefixes). One schema per layer per domain. Each data source gets its own table within the schema.

### Layer Rules

**Raw** (`{prefix}_raw.{source_name}`)
- Stores the raw API response exactly as received — no renaming, no transforming
- Every column from the API response must be present
- Required metadata columns: `_source_year`, `_source_hash`, `_source_file`, `_loaded_at`
- Has a `UNIQUE` constraint for idempotent upserts
- Managed by the ingestion layer (Python loader)

**Bronze** (`{prefix}_bronze.{source_name}` — SQLMesh model)
- Typed pass-through from raw: every raw column cast to the correct PostgreSQL type
- Column names must match raw **exactly** — no renaming, no dropping
- `INCREMENTAL_BY_UNIQUE_KEY` on the natural key
- Adds two columns: `processed_to_silver BOOLEAN DEFAULT FALSE`, `_bronze_loaded_at TIMESTAMPTZ`
- **Zero column loss** from raw → bronze is mandatory
- File: `src/dk_data/sqlmesh/models/{domain}/bronze/{source_name}.sql`

**Silver** (`{prefix}_silver.{model_name}` — SQLMesh model)
- Entity-linking layer: joins multiple bronze sources into a unified entity view
- No column or data loss from bronze sources that feed this model
- **Must link across all relevant domains**: mol ↔ cms ↔ hcp ↔ ind
  - Link to `mol_silver.molecules` via drug name → `mol_silver.molecule_aliases.alias_name_normalized`
  - Link to `mol_silver.ndc_molecule_bridge` via NDC code
  - Link to `hcs_silver.provider_profile` via NPI
  - Link to `hcs_silver.facility_profile` via CCN/provider_id
- Entity linking strategy by source type:
  - **NPI-bearing sources** → extend or join `hcs_silver.provider_profile`
  - **CCN/facility sources** → extend or join `hcs_silver.facility_profile`
  - **Geographic/population sources** → extend or join `hcs_silver.geographic_health`
  - **Drug/molecule sources** → extend or join `hcs_silver.drug_utilization` or `hcs_silver.cms_drug_market`
  - **New entity type** → create a new silver model named after the entity
- File: `src/dk_data/sqlmesh/models/{domain}/silver/{model_name}.sql`

**Gold** (`{prefix}_gold.{mart_name}` — SQLMesh model)
- Decision-ready aggregation: joins columns from **multiple silver tables** into one view
- `kind FULL`, `cron '@daily'`
- Adds computed metrics, rankings, indices (never raw fields only)
- Each gold model must pull from ≥2 silver sources
- File: `src/dk_data/sqlmesh/models/{domain}/gold/{mart_name}.sql`

---

### Phase 1: API Discovery & Documentation

1. **Analyze the user input** to understand the data source:
   - If a URL is provided, fetch it and extract API information
   - If an OpenAPI spec URL is provided, fetch and parse it
   - If a description is provided, research using web search

2. **Gather API details**:
   - Base URL and available endpoints
   - Authentication method (`none`, `api_key`, `oauth2`, `bearer`)
   - Data format (`json`, `csv`, `xml`)
   - Pagination strategy (`offset`, `cursor`, `page`, `none`)
   - Rate limits and refresh frequency
   - **Exact column names** from the API response (critical for raw layer)
   - Natural/primary key for deduplication
   - **Domain**: which prefix family does this belong to? (`hcs_`, `mol_`, `ind_`, `hcp_`)
   - **Silver destination**: which existing silver model should this feed, or does a new one need to be created?

3. **Present a summary** to the user for confirmation before proceeding.

---

### Phase 2: Schema Design (All Four Layers)

4. **Raw table DDL** (`{prefix}_raw.{source_name}`):
   - One column per API response field, named exactly as the API returns it (snake_case)
   - All columns `TEXT` or most permissive type — raw is not the place for strict typing
   - Required audit columns: `id BIGSERIAL PRIMARY KEY`, `_source_year INTEGER`, `_source_hash TEXT`, `_source_file TEXT`, `_loaded_at TIMESTAMPTZ DEFAULT NOW()`
   - `UNIQUE` constraint on the natural key + `_source_year`
   - Example:
     ```sql
     CREATE TABLE IF NOT EXISTS hcs_raw.cms_example (
         id BIGSERIAL PRIMARY KEY,
         npi TEXT,
         provider_name TEXT,
         total_claims INTEGER,
         _source_year INTEGER,
         _source_hash TEXT,
         _source_file TEXT,
         _loaded_at TIMESTAMPTZ DEFAULT NOW(),
         UNIQUE (npi, _source_year)
     );
     ```

5. **Bronze SQLMesh model** (`{prefix}_bronze.{source_name}`):
   - `SELECT` every column from raw with explicit type casts
   - Must cast every column — no `SELECT *`
   - Unique key = natural key + `_source_year`
   - Example:
     ```sql
     MODEL (
         name hcs_bronze.cms_example,
         kind INCREMENTAL_BY_UNIQUE_KEY (unique_key (npi, _source_year)),
         cron '@monthly',
         audits (not_null(columns := (_source_year))),
         grain (npi, _source_year)
     );
     SELECT
         id::BIGINT,
         npi::TEXT,
         provider_name::TEXT,
         total_claims::INTEGER,
         _source_year::INTEGER,
         _source_hash::TEXT,
         _source_file::TEXT,
         _loaded_at::TIMESTAMPTZ,
         FALSE AS processed_to_silver,
         NOW() AS _bronze_loaded_at
     FROM hcs_raw.cms_example;
     ```

6. **Silver SQLMesh model** — determine the correct approach:

   **Case A — extend an existing silver model** (most common):
   Add a new CTE to the existing silver model that sources from the new bronze table, then LEFT JOIN it into the final SELECT. Example for a NPI-bearing source added to `hcs_silver.provider_profile`:
   ```sql
   -- Add this CTE to provider_profile.sql
   new_source AS (
       SELECT npi, _source_year, col1, col2, SUM(col3) AS total_col3
       FROM hcs_bronze.cms_example
       WHERE npi IS NOT NULL
       GROUP BY npi, _source_year
   ),
   ```
   Then extend `all_npis`, the SELECT, and the LEFT JOIN.

   **Case B — new entity type** (less common):
   Create `src/dk_data/sqlmesh/models/{domain}/silver/{entity_name}.sql` as a new `INCREMENTAL_BY_UNIQUE_KEY` model joining the new bronze source with existing silver tables.
   - Must include molecule linkage if drug names/NDCs are present
   - Must include NPI/CCN linkage if provider identifiers are present
   - Must include cross-domain links (e.g., mol_silver ↔ hcs_silver)

7. **Gold SQLMesh model** — determine if a new gold model is needed or if existing ones should be updated:
   - If the silver model extends an existing silver entity, the existing gold model that reads from it will automatically include the new columns — just add them explicitly to the gold SELECT
   - If a new silver entity was created, consider whether it warrants a new gold mart or should join into an existing one

---

### Phase 3: Secrets & Configuration

8. **Identify required secrets**:
   - Environment variable names: `{SOURCE_NAME_UPPER}_API_KEY`
   - Doppler project: `dk-data-fe`, configs: `prd` and `stg`

9. **Determine CronJob schedule**:
   - Daily: `"0 N * * *"` — avoid conflicts with existing jobs
   - Weekly: `"0 N * * 0"`
   - Monthly: `"0 N D * *"`
   - Quarterly: `"0 N 1 */3 *"`
   - Existing schedules:
     - `0 2 * * 0` — fetch-cms-all
     - `0 3 1 * *` — fetch-cms-hospitals
     - `0 3 1 */3 *` — fetch-cms-inpatient
     - `0 4 1 */3 *` — fetch-acc-tvc
     - `0 5 15 * *` — fetch-hrsa
     - `0 6 * * *` — catalog-refresh
     - `0 7 * * *` — sqlmesh-run

---

### Phase 4: Implementation

10. **Create implementation files in this order**:

    **a. SQL Migration** (`src/dk_data/sql/migrations/NNN_{source_name}_tables.sql`):
    - Check existing files to determine next migration number
    - Create raw table with all columns, indexes, and UNIQUE constraint
    - Grant SELECT to `web_anon` and `analyst` roles

    **b. Pydantic Validator** — add to `src/dk_data/ingestion/utils/validators.py`:
    - Class name: `{SourceName}Record(BaseModel)`
    - Field validators for data normalization (dates, nulls, numeric coercion)
    - Use `apply_column_mapping(df, COLUMN_MAPPING)` in the loader for case-insensitive column matching

    **c. Fetcher** (`src/dk_data/ingestion/fetchers/{source_name}.py`):
    - Inherit from `BaseFetcher`
    - Set `SOURCE_NAME` and `BASE_URL`
    - For file-based CMS sources: return `{"status": "success", "records": [], "hash": None}` stub — download is handled by CronJob
    - For API sources: implement full pagination

    **d. Source Loader** (`src/dk_data/ingestion/sources/{source_name}.py`):
    - `load_{source_name}_file(filepath, source_year, conn=None, max_records=0)` for file-based
    - `load_{source_name}_data(records, source_year, conn=None)` for API-based
    - Use `apply_column_mapping(df, COLUMN_MAPPING)` — **never** `df.rename(columns=COLUMN_MAPPING)` (case-sensitive bug)
    - Validate with Pydantic model, batch INSERT with `ON CONFLICT DO UPDATE`
    - Return `{status, records_inserted, records_failed, errors, source_hash}`

    **e. Register the source** in `src/dk_data/ingestion/main.py`:
    ```python
    "{source_name}": {
        "fetcher": {SourceName}Fetcher,
        "loader": load_{source_name}_file,
        "requires_file": True,   # for file-based sources
        "accepts_batch_size": False,
    },
    ```

    **f. Bronze SQLMesh model** (`src/dk_data/sqlmesh/models/{domain}/bronze/{source_name}.sql`):
    - Every raw column with explicit type cast
    - No columns dropped or renamed
    - `FALSE AS processed_to_silver`, `NOW() AS _bronze_loaded_at`

    **g. Silver SQLMesh model** — either extend existing or create new (see Phase 2 step 6)

    **h. Gold SQLMesh model** — update existing SELECT or create new mart (see Phase 2 step 7)

    **i. Catalog metadata** in `src/dk_data/scripts/catalog_refresh.py`:
    - `topic_tags`, `ai_description`, `column_descriptions`
    - `staleness_threshold_hours`, `target_tables` (include all four layer tables)

    **j. Seed SQL updates**:
    - Append to `src/dk_data/sql/seed_data_sources.sql`
    - Append to `src/dk_data/sql/seed_batch_jobs.sql`

    **k. CronJob manifest** (`k8s/apps/cronjobs/base/cronjob-{source-name}.yaml`):
    - Follow existing CronJob YAML pattern
    - Add to `k8s/apps/cronjobs/base/kustomization.yaml`

    **l. Tests** (`tests/test_{source_name}_fetcher.py`, `tests/test_{source_name}_loader.py`):
    - Fetcher init and URL tests
    - Loader with mock DB connection
    - Pydantic validator with valid/invalid data
    - Column mapping round-trip test

11. **Validate**:
    ```bash
    # Syntax check
    python -c "from dk_data.ingestion.sources.{source_name} import load_{source_name}_file"
    # Run tests
    pytest tests/test_{source_name}*.py -v
    # SQLMesh dry run
    cd src/dk_data && sqlmesh plan --no-auto-apply
    # Kustomize check
    kubectl kustomize k8s/overlays/staging --enable-helm > /dev/null
    ```

---

### Phase 5: Deployment Guidance

12. **Output a deployment checklist**:
    - Doppler secret setup commands
    - Migration: `docker exec -it dk-data-fe-postgres psql -U dk_data -d dk_data -f /path/to/NNN_migration.sql`
    - SQLMesh apply: `cd src/dk_data && sqlmesh plan --auto-apply`
    - Seed 1000 rows for Nick: `python3 -m dk_data.ingestion.main --source {source_name} --max-records 1000`
    - Verify raw count: `SELECT COUNT(*) FROM {prefix}_raw.{source_name};`
    - Verify bronze count: `SELECT COUNT(*) FROM {prefix}_bronze.{source_name};`
    - Verify silver entity linking: check for NULL molecule_id / npi / provider_id rates
    - Verify gold: `SELECT COUNT(*) FROM {prefix}_gold.{mart_name};`

---

## Key Rules

- **Schema prefix**: `hcs_` for CMS/healthcare system, `mol_` for drugs/molecules, `ind_` for indications, `hcp_` for healthcare professionals
- **Source name**: always `snake_case` (e.g., `cms_physician_puf`, `drugbank_compounds`)
- **CronJob name**: always `kebab-case` with `fetch-` prefix (e.g., `fetch-cms-physician-puf`)
- **Raw tables**: preserve API field names exactly; use `TEXT` for uncertain types
- **Bronze models**: cast every column explicitly; never drop columns; never rename columns
- **Column mapping**: always use `apply_column_mapping(df, COLUMN_MAPPING)` — never `df.rename()` (case-sensitive bug)
- **Silver models**: include entity linking to mol/hcs/hcp/ind; NULL molecule_id is acceptable when no drug data present
- **Gold models**: always aggregate from ≥2 silver sources; add computed metrics (rankings, ratios, indices)
- **API keys**: never hardcoded — always from environment via Doppler → `dk-data-fe` / `dk-data-secrets`
- **DB host**: `postgres-cluster-rw.infra.svc.cluster.local:5432` (production)
- **PostgREST grants**: `GRANT SELECT ON {view} TO web_anon, analyst;`
- **SQLMesh**: bronze = `INCREMENTAL_BY_UNIQUE_KEY`; silver = `INCREMENTAL_BY_UNIQUE_KEY`; gold = `FULL`

## Existing Silver Models Reference

Extend these before creating new ones:

| Silver Model | Entity Key | Sources It Already Joins |
|-------------|------------|--------------------------|
| `hcs_silver.provider_profile` | `npi` | NPPES, physician_puf, dme_puf, mental_health_puf, telehealth_puf, referring_providers, ordering_providers |
| `hcs_silver.facility_profile` | `provider_id` (CCN) | hospital_general_info, cost_reports_puf, inpatient_puf, outpatient_puf, snf_puf, home_health, hospice_puf |
| `hcs_silver.geographic_health` | `geo_code` + `geo_level` | geographic_variation, chronic_conditions, opioid_puf, enrollment_puf, dual_eligible, medicare_advantage, claim_type_puf, utilization_puf |
| `hcs_silver.drug_utilization` | `drug_or_hcpcs_code` + `code_type` | part_d_spending, part_b_spending, medicaid_drug_spending, dme_puf, lab_services, imaging_puf (→ mol_silver) |
| `hcs_silver.part_d_prescribing` | `prscrbr_npi` + `gnrc_name` | part_d_prescriber (→ mol_silver via alias) |
| `hcs_silver.open_payments_drug_linkage` | `record_id` + `drug_slot` | open_payments (→ mol_silver via NDC + alias) |
| `mol_silver.molecules` | `molecule_id` | drugbank, chembl, pubchem, openfda |
| `mol_silver.molecule_aliases` | `alias_name_normalized` | all drug name sources |

## Existing Sources Reference

Current registered data sources (avoid duplicate source_names):

| Source Name | Domain | Frequency | Silver Destination |
|------------|--------|-----------|-------------------|
| `cms_physician_puf` | hcs | annual | provider_profile |
| `cms_nppes` | hcs | monthly | provider_profile |
| `cms_inpatient_puf` | hcs | annual | facility_profile |
| `cms_outpatient_puf` | hcs | annual | facility_profile |
| `cms_hospital_general_info` | hcs | monthly | facility_profile |
| `cms_cost_reports_puf` | hcs | annual | facility_profile |
| `cms_snf_puf` | hcs | annual | facility_profile |
| `cms_hospice_puf` | hcs | annual | facility_profile |
| `cms_home_health` | hcs | monthly | facility_profile |
| `cms_dme_puf` | hcs | annual | provider_profile + drug_utilization |
| `cms_part_d_spending` | hcs | annual | drug_utilization + cms_drug_market |
| `cms_part_b_spending` | hcs | annual | drug_utilization + cms_drug_market |
| `cms_medicaid_drug_spending` | hcs | annual | drug_utilization |
| `cms_open_payments` | hcs | annual | open_payments_drug_linkage |
| `cms_geographic_variation` | hcs | annual | geographic_health |
| `cms_enrollment_puf` | hcs | monthly | geographic_health |
| `cms_chronic_conditions` | hcs | annual | geographic_health |
| `cms_opioid_puf` | hcs | annual | geographic_health + part_d_prescribing |
| `cms_dual_eligible` | hcs | annual | geographic_health |
| `cms_medicare_advantage` | hcs | annual | geographic_health |
| `cms_referring_providers` | hcs | annual | provider_profile |
| `cms_ordering_providers` | hcs | annual | provider_profile |
| `hrsa_shortage_areas` | hcs | monthly | geographic_health |
| `drugbank` | mol | annual | molecules |
| `cochrane` | mol | monthly | clinical_trials |
| `ema_regulatory` | mol | monthly | drug_approvals |
| `europepmc` | mol | weekly | publications |
| `nih_reporter` | mol | monthly | publications |
