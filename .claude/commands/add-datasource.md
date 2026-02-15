---
description: Add a new external data source with fetcher, loader, database tables, CronJob, Doppler secrets, and catalog integration.
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

This skill guides the complete integration of a new external data source into the dk-data-fe platform. It covers API discovery, secrets, database schema, fetcher/loader code, CronJob scheduling, and catalog registration.

The user input should describe the data source to add. It can be:
- A URL to an API or documentation page
- A name and description of the data source
- A path to an OpenAPI spec file
- A brief description of what data to fetch

If the input is empty, ask the user what data source they want to add.

### Phase 1: API Discovery & Documentation

1. **Analyze the user input** to understand the data source:
   - If a URL is provided, fetch it and extract API information (endpoints, auth, data format)
   - If an OpenAPI spec URL is provided (e.g., `openapi.json`, `swagger.json`), fetch and parse it
   - If a description is provided, research the API using web search

2. **Gather API details** — for each, determine or ask:
   - Base URL and available endpoints
   - Authentication method (`none`, `api_key`, `oauth2`, `bearer`)
   - Data format (`json`, `csv`, `xml`)
   - Pagination strategy (`offset`, `cursor`, `page`, `none`)
   - Rate limits
   - Refresh frequency (how often the upstream data changes)
   - Estimated record count per fetch

3. **Load the datasource template**:
   - Read `.specify/templates/datasource-template.md`
   - Fill in Section 1 (Source Discovery) with gathered API details

4. **Present the filled discovery section** to the user for confirmation before proceeding.

### Phase 2: Schema Design

5. **Map API response fields to database columns**:
   - Identify the natural/primary key for deduplication
   - Map response fields → raw table columns (preserve original field names)
   - Design staging table with cleaned/normalized column names
   - Determine if a mart table or existing mart join is needed
   - Design the API view for PostgREST exposure

6. **Fill template Section 3** (Database Schema) with:
   - `raw.[source_name]` table DDL
   - `staging.[table_name]` table DDL (if applicable)
   - `api.[view_name]` view DDL with grants
   - Proper audit columns (`_loaded_at`, `_source_file`, `_source_hash`)
   - `UNIQUE` constraint for upsert deduplication

### Phase 3: Secrets & Configuration

7. **Identify required secrets** and fill template Section 2:
   - API keys, tokens, or credentials needed
   - Environment variable names (convention: `[SOURCE_NAME_UPPER]_API_KEY`)
   - Doppler project: `dk-data-fe`, configs: `prd` and `stg`

8. **Determine CronJob schedule** and fill template Section 6:
   - Match schedule to upstream data refresh frequency
   - Use existing schedule patterns:
     - Daily: `"0 N * * *"` (pick hour N to avoid conflicts with existing jobs)
     - Weekly: `"0 N * * 0"` (Sunday at hour N)
     - Monthly: `"0 N D * *"` (Day D at hour N)
     - Quarterly: `"0 N 1 */3 *"` (1st of quarter months at hour N)
   - Existing schedules to avoid conflicts:
     - `0 2 * * 0` — fetch-cms-all
     - `0 3 1 * *` — fetch-cms-hospitals
     - `0 3 1 */3 *` — fetch-cms-inpatient
     - `0 4 1 */3 *` — fetch-acc-tvc
     - `0 5 15 * *` — fetch-hrsa
     - `0 6 * * *` — catalog-refresh
     - `0 7 * * *` — sqlmesh-run
   - Set appropriate `activeDeadlineSeconds` (default 600s for small sources, 3600s for large)
   - Set resource requests/limits based on expected data volume

### Phase 4: Implementation

9. **Write the datasource integration document**:
   - Fill all remaining template sections
   - Save to `specs/[feature-name]/datasource-[source_name].md` if a feature branch is active
   - Otherwise save to `docs/datasources/[source_name].md`

10. **Create the implementation files** in order:

    **a. SQL Migration** (`src/dk_data/sql/migrations/NNN_[source_name]_tables.sql`):
    - Determine next migration number by checking existing files in `src/dk_data/sql/migrations/`
    - Create raw table, staging table, indexes, and API view
    - Include `ON CONFLICT` support in the schema design

    **b. Pydantic Validator** — add to `src/dk_data/ingestion/utils/validators.py`:
    - Create a validation model class: `[SourceName]Record(BaseModel)`
    - Add field validators for data normalization
    - Follow existing patterns (see `CMSMedicareInpatientRecord` etc.)

    **c. Fetcher** (`src/dk_data/ingestion/fetchers/[source_name].py`):
    - Inherit from `BaseFetcher`
    - Set `SOURCE_NAME` and `BASE_URL` class attributes
    - Implement `fetch(**kwargs)` → returns `{status, filepath/records, error, hash}`
    - Implement `get_latest_url()` → returns URL string
    - Handle pagination if needed
    - Use `self.session` for HTTP requests (has retry logic built in)
    - Read API key from environment: `os.getenv('[SOURCE_NAME_UPPER]_API_KEY')`

    **d. Source Loader** (`src/dk_data/ingestion/sources/[source_name].py`):
    - Implement `load_[source_name]_file(filepath, **kwargs)` or `load_[source_name]_data(records, **kwargs)`
    - Parse CSV/JSON, validate with Pydantic model
    - Batch INSERT with `ON CONFLICT` for upserts
    - Return `{status, records_inserted, records_failed, errors, source_hash}`
    - Use `from ingestion.utils.database import get_connection, get_cursor`

    **e. Register the source**:
    - Add import + export to `src/dk_data/ingestion/fetchers/__init__.py`
    - Add entry to `FETCHERS` dict in `src/dk_data/ingestion/fetch_data.py`
    - Add entry to `SOURCES` dict in `src/dk_data/ingestion/main.py` (if loader created)

    **f. Catalog metadata** — add to `SOURCE_METADATA` in `src/dk_data/scripts/catalog_refresh.py`:
    - `topic_tags`, `ai_description`, `column_descriptions`
    - `staleness_threshold_hours`, `target_tables`

    **g. Seed SQL updates**:
    - Append to `src/dk_data/sql/seed_data_sources.sql`
    - Append to `src/dk_data/sql/seed_batch_jobs.sql`

    **h. CronJob manifest** (`k8s/base/ingestion/cronjob-[source_name].yaml`):
    - Follow the template from Section 6
    - Use `dk_data.ingestion.fetch_data --source [source_name]` as the command
    - Include source-specific env vars for API keys if needed
    - Add to `k8s/base/kustomization.yaml` resources list

    **i. Tests** (`tests/test_[source_name]_fetcher.py`):
    - Test fetcher initialization
    - Test `get_latest_url()` returns valid URL
    - Mock HTTP responses for `fetch()` tests
    - Test Pydantic validator with valid and invalid data
    - Test loader with mock database connection

11. **Validate the implementation**:
    - Run `pytest tests/test_[source_name]*.py -v`
    - Verify kustomize overlays still build: `kubectl kustomize k8s/overlays/prod --enable-helm > /dev/null`
    - Run import checks: `python -c "from dk_data.ingestion.fetchers import [ClassName]"`

### Phase 5: Deployment Guidance

12. **Output a deployment checklist** with actionable commands:
    - Doppler secret setup commands
    - Database migration commands (kubectl exec into postgres)
    - ArgoCD sync commands
    - Manual job trigger for verification
    - Log inspection commands
    - API endpoint verification

## Key Rules

- **Source name convention**: Always `snake_case` (e.g., `cms_inpatient`, `hrsa_shortage_areas`)
- **CronJob name convention**: Always `kebab-case` with `fetch-` prefix (e.g., `fetch-cms-all`, `fetch-hrsa`)
- **All raw tables MUST have**: `_loaded_at`, `_source_file`, `_source_hash` audit columns
- **All raw tables MUST have**: A `UNIQUE` constraint for idempotent upserts
- **Fetchers MUST extend**: `BaseFetcher` from `src/dk_data/ingestion/fetchers/base.py`
- **API keys MUST come from**: Environment variables (never hardcoded), sourced via Doppler → `dk-data-secrets`
- **Python module paths**: Use `dk_data.ingestion.fetch_data` pattern (matches Dockerfile PYTHONPATH=/app)
- **Image tag**: Use `latest` in base manifests; overlay kustomizations handle per-environment tags
- **Secrets project**: Doppler project `dk-data-fe`, configs `prd` (production) and `stg` (staging)
- **Database host**: Production uses `postgres-cluster-rw.infra.svc.cluster.local:5432`
- **PostgREST grants**: Always grant `SELECT` on API views to both `web_anon` and `analyst` roles

## Existing Sources Reference

Current registered data sources (avoid duplicate source_names):

| Source Name | Type | Frequency | Fetcher Class |
|------------|------|-----------|---------------|
| `cms_medicare_inpatient` | csv/api | quarterly | `CMSInpatientFetcher` |
| `cms_hospital_info` | csv | monthly | `CMSHospitalInfoFetcher` |
| `cms_cost_reports` | csv | annual | `CMSCostReportsFetcher` |
| `acc_tvc` | scrape | quarterly | `ACCTVCFetcher` |
| `hrsa_shortage_areas` | api | monthly | `HRSAFetcher` |
