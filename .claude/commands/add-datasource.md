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

**There are two distinct implementation patterns** based on how the source delivers data:

| Pattern | Used for | Raw table shape |
|---------|----------|----------------|
| **HCS / file-based** | CMS CSV downloads, flat structured files | Flat columns per API field, `_source_year`, `_source_hash` audit cols |
| **Mol / API-based** | REST/JSON APIs returning records | Standardized JSONB schema (`response_body JSONB`, `ingested_at TIMESTAMPTZ`) |

Determine which pattern applies before designing the schema.

---

## Pattern A: HCS / File-Based Sources

Used for CMS CSV downloads and any source whose data arrives as structured flat files per year.

### Raw Table DDL (`hcs_raw.{source_name}`)

One column per API/CSV field, named exactly as delivered (snake_case). All columns use the most permissive type. Required audit columns appended at the end:

```sql
CREATE TABLE IF NOT EXISTS hcs_raw.cms_example (
    id              BIGSERIAL PRIMARY KEY,
    npi             TEXT,
    provider_name   TEXT,
    total_claims    INTEGER,
    -- ... all source fields ...
    _source_year    INTEGER NOT NULL,
    _source_hash    TEXT NOT NULL,
    _source_file    TEXT,
    _loaded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (_source_hash, npi, _source_year)
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_example_year ON hcs_raw.cms_example(_source_year);
```

### Bronze SQLMesh Model (`hcs_bronze.{source_name}`)

`INCREMENTAL_BY_UNIQUE_KEY` on the natural key + `_source_year`. Cast every column explicitly — no `SELECT *`. Add `processed_to_silver` and `_bronze_loaded_at`.

```sql
MODEL (
    name hcs_bronze.cms_example,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (npi, _source_year)
    ),
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

### Fetcher (`src/dk_data/ingestion/fetchers/{source_name}.py`)

Inherit from `BaseFetcher`. For file-based CMS sources that download via `_fetch_cms_api()`:

```python
class CMSExampleFetcher(BaseFetcher):
    SOURCE_NAME = "cms_example"
    BASE_URL = "https://data.cms.gov/api/1/datastore/query/{UUID}/0"

    def get_latest_url(self) -> str:
        return self.BASE_URL

    def fetch(self, **kwargs):
        return self._fetch_cms_api(self.BASE_URL, **kwargs)
```

### Source Loader (`src/dk_data/ingestion/sources/{source_name}.py`)

Use `apply_column_mapping(df, COLUMN_MAPPING)` — **never** `df.rename(columns=COLUMN_MAPPING)` (case-sensitive bug). Validate with Pydantic model from `validators.py`. Use `upsert_records()` for batch INSERT.

```python
from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSExampleRecord

COLUMN_MAPPING = {
    'NPI': 'npi',
    'Provider_Name': 'provider_name',
    'Total_Claims': 'total_claims',
}

def load_cms_example_data(records, source_year, source_hash=None):
    df = pd.DataFrame(records)
    df = apply_column_mapping(df, COLUMN_MAPPING)
    # validate with Pydantic, then upsert
    ...
```

Add a Pydantic validator class to `src/dk_data/ingestion/utils/validators.py` extending `CMSPUFBaseRecord` (handles NaN → None and CMS suppression codes automatically).

---

## Pattern B: Mol / API-Based Sources

Used for REST JSON APIs (ChEMBL, EuropePMC, OpenFDA, NIH Reporter, etc.) where records are fetched as JSON objects.

### Raw Table DDL (`mol_raw.{source_name}`)

**Standardized JSONB schema** — identical structure for every mol_raw table. Only `source_id` default differs:

```sql
CREATE TABLE IF NOT EXISTS mol_raw.example_source (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'example_source',
    api_version         VARCHAR(20),
    request_params      JSONB,
    request_headers     JSONB,
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_headers    JSONB,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  VARCHAR(64),
    response_size_bytes INTEGER,
    response_time_ms    INTEGER,
    processed_to_bronze BOOLEAN DEFAULT false,
    processed_at        TIMESTAMPTZ,
    processing_error    TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           VARCHAR(50) NOT NULL DEFAULT 'example_source'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_example_source_request_id
    ON mol_raw.example_source(request_id);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_example_source_natural_key
    ON mol_raw.example_source ((response_body->>'natural_key_field'))
    WHERE response_body->>'natural_key_field' IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_mol_raw_example_source_ts
    ON mol_raw.example_source(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_example_source_bronze
    ON mol_raw.example_source(processed_to_bronze) WHERE NOT processed_to_bronze;
```

### Bronze SQLMesh Model (`mol_bronze.{source_name}`)

`INCREMENTAL_BY_TIME_RANGE` on `ingested_at`. Extract typed fields from `response_body` using JSON path operators (`->>`). Always include `processed_to_silver`, `created_at`, `raw_json`.

```sql
MODEL (
    name mol_bronze.example_source,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        lookback 7
    ),
    cron '@daily',
    audits (
        not_null(columns := (natural_key)),
        unique_values(columns := (natural_key))
    ),
    grain natural_key
);

SELECT
    gen_random_uuid()                            AS id,
    r.response_body->>'natural_key'              AS natural_key,
    r.response_body->>'name'                     AS name,
    (r.response_body->>'count')::INTEGER         AS count,
    CASE
        WHEN r.response_body->>'date' ~ '^\d{4}-\d{2}-\d{2}$'
        THEN (r.response_body->>'date')::DATE
        ELSE NULL
    END                                          AS some_date,
    r.response_body                              AS raw_json,
    r.id::TEXT                                   AS raw_source_id,
    'example_source'                             AS source,
    r.ingested_at                                AS source_updated_at,
    FALSE                                        AS processed_to_silver,
    NOW()                                        AS created_at,
    r.ingested_at
FROM mol_raw.example_source r
WHERE r.response_status = 200
  AND r.processed_to_bronze = FALSE
  AND r.response_body->>'natural_key' IS NOT NULL
  AND r.ingested_at BETWEEN @start_dt AND @end_dt;
```

### Fetcher (`src/dk_data/ingestion/fetchers/{source_name}.py`)

Inherit from `BaseFetcher`. Implement `SOURCE_NAME`, `BASE_URL`, `get_latest_url()`, `fetch(**kwargs)`. Use `self.fetch_json()` for HTTP requests (session has retry logic built in). Use `self._fetch_cms_api()` for CMS data.gov sources.

```python
class ExampleSourceFetcher(BaseFetcher):
    SOURCE_NAME = "example_source"
    BASE_URL = "https://api.example.com/v1"

    def get_latest_url(self) -> str:
        return f"{self.BASE_URL}/records"

    def fetch(self, **kwargs):
        max_records = int(kwargs.get("max_records", 10_000))
        records = []
        offset = 0
        while len(records) < max_records:
            data = self.fetch_json(self.get_latest_url(), params={"limit": 100, "offset": offset})
            page = data.get("results", [])
            if not page:
                break
            records.extend(page)
            offset += len(page)
            if len(page) < 100:
                break
        return {"status": "success", "records": records, "record_count": len(records), "hash": None}
```

**OpenFDA sources** (25k skip limit): use year-partitioned `receivedate` or `effective_time` filtering. See `openfda_faers.py` and `openfda_labels.py` for the pattern.

### Source Loader (`src/dk_data/ingestion/sources/{source_name}.py`)

Direct JSONB insert with expression-index `ON CONFLICT`. No Pydantic, no pandas. Skip records missing the natural key.

```python
from ..utils.database import get_cursor

def load_example_source_data(records, source_hash=None):
    sql = """
        INSERT INTO mol_raw.example_source (response_body, response_status)
        VALUES (%s::JSONB, 200)
        ON CONFLICT ((response_body->>'natural_key'))
        WHERE (response_body->>'natural_key') IS NOT NULL
        DO UPDATE SET
            response_body = EXCLUDED.response_body,
            ingested_at   = NOW()
        WHERE mol_raw.example_source.response_body IS DISTINCT FROM EXCLUDED.response_body
    """
    inserted = 0
    errors = []
    with get_cursor() as cur:
        for record in records:
            if not record.get("natural_key"):
                continue
            try:
                cur.execute(sql, (json.dumps(record),))
                inserted += 1
            except Exception as exc:
                errors.append(str(exc))
    return {"status": "success" if not errors else "partial",
            "records_fetched": len(records), "records_inserted": inserted,
            "records_updated": 0, "errors": errors[:10]}
```

---

## Silver Models

### Strategy

**Always extend an existing silver model before creating a new one.** Determine which existing silver entity the source feeds:

| Silver Model | Entity Key | When to extend |
|-------------|------------|----------------|
| `hcs_silver.provider_profile` | `npi` | Source has NPI: NPPES, physician_puf, referring/ordering providers, mental_health, telehealth, dme_puf |
| `hcs_silver.facility_profile` | `provider_id` (CCN) | Source has CCN/provider_id: hospital_general_info, cost_reports_puf, inpatient/outpatient/snf/hospice/home_health |
| `hcs_silver.geographic_health` | `geo_code` + `geo_level` | Geographic/population aggregates: geographic_variation, chronic_conditions, enrollment_puf, opioid_puf, dual_eligible, medicare_advantage, claim_type_puf, utilization_puf |
| `hcs_silver.drug_utilization` | `drug_or_hcpcs_code` + `code_type` | Drug utilization/spending: part_d_spending, part_b_spending, medicaid_drug_spending, dme_puf, lab_services, imaging_puf |
| `hcs_silver.part_d_prescribing` | `prscrbr_npi` + `gnrc_name` | Part D prescribing: part_d_prescriber |
| `hcs_silver.open_payments_drug_linkage` | `record_id` + `drug_slot` | Open payments: open_payments |
| `hcs_silver.cms_drug_market` | `drug_or_hcpcs_code` + `year` | Market-level drug spending aggregates |
| `mol_silver.molecules` | `molecule_id` | Drug/molecule sources: drugbank, chembl, pubchem, openfda |
| `mol_silver.molecule_aliases` | `alias_name_normalized` | Any drug name source |
| `mol_silver.publications` | `pmid` / `source_id` | Literature: europepmc, nih_reporter, pubmed |
| `mol_silver.drug_labels` | `set_id` | Drug labeling: openfda_labels, dailymed |
| `mol_silver.adverse_events` | `report_id` | Safety signals: openfda_faers |

Cross-domain links to always include when present:
- Drug names/NDCs → `mol_silver.molecule_aliases.alias_name_normalized`
- NDC codes → `mol_silver.ndc_molecule_bridge`
- NPI → `hcs_silver.provider_profile`
- CCN/provider_id → `hcs_silver.facility_profile`

### Gold Models

Gold models aggregate from ≥2 silver sources, add computed metrics (rankings, ratios, indices), and use `kind FULL, cron '@daily'`. Update existing gold models when extending existing silver entities. Create new gold models only for genuinely new entity types.

---

## Implementation Order

### Phase 1: API Discovery

1. Analyze user input — fetch URL/spec if provided, research via web search if description only.
2. Determine: base URL, auth method, data format, pagination strategy, rate limits, natural key, domain (`hcs_`/`mol_`/`ind_`/`hcp_`), pattern (file-based vs API-based).
3. Present a summary for user confirmation before writing any code.

### Phase 2: Implementation Files

Create in this order:

**a. SQL Migration** (`src/dk_data/sql/migrations/NNN_{source_name}.sql`):
- Check last migration number: `ls src/dk_data/sql/migrations/ | sort | tail -5`
- `BEGIN;` … `COMMIT;`
- Raw table DDL using the correct pattern (A or B above)
- For mol_raw: all indexes (request_id unique, natural key expression index, ingested_at, processed_to_bronze)
- For hcs_raw: flat columns, `UNIQUE` constraint, year index
- `GRANT SELECT ON` raw/bronze/silver/gold tables `TO web_anon, analyst;`

**b. Pydantic Validator** (HCS pattern only — `src/dk_data/ingestion/utils/validators.py`):
- Extend `CMSPUFBaseRecord` for CMS sources (inherits NaN→None and suppression code handling)
- Field validators for date parsing, numeric coercion, string normalization

**c. Fetcher** (`src/dk_data/ingestion/fetchers/{source_name}.py`):
- Set `SOURCE_NAME = "source_name"` matching the SOURCES registry key exactly
- Implement pagination strategy appropriate to the API
- Return `{"status": "success"/"failed", "records": [...], "record_count": N, "hash": hash_or_None}`

**d. Source Loader** (`src/dk_data/ingestion/sources/{source_name}.py`):
- HCS: `load_{source_name}_data(records, source_year, source_hash=None)` — pandas + Pydantic + `upsert_records()`
- Mol: `load_{source_name}_data(records, source_hash=None)` — direct JSONB insert with `ON CONFLICT` expression index

**e. Register in `src/dk_data/ingestion/main.py`**:

```python
# Add import near other source imports:
from .sources.example_source import load_example_source_data

# Add fetcher to the from .fetchers import (...) block:
ExampleSourceFetcher,

# Add to SOURCES dict:
'example_source': {
    'name': 'Example Source Display Name',
    'description': 'One-line description',
    'fetcher': ExampleSourceFetcher,
    'loader': load_example_source_data,
    'requires_file': False,
    'default_days_back': None,  # None = full dataset; int = incremental days window
},
```

**f. Register in `src/dk_data/ingestion/fetchers/__init__.py`**:
- Add `from .example_source import ExampleSourceFetcher`
- Add `'ExampleSourceFetcher'` to `__all__`

**g. Bronze SQLMesh model** (`src/dk_data/sqlmesh/models/{domain}/bronze/{source_name}.sql`):
- Pattern A (HCS): `INCREMENTAL_BY_UNIQUE_KEY`, explicit cast of every column, no `SELECT *`
- Pattern B (Mol): `INCREMENTAL_BY_TIME_RANGE` on `ingested_at`, JSONB extraction via `->>`

**h. Register in `src/dk_data/ingestion/transform_molecules.py` LAYER_MODELS**:

Layer assignment:
- `bronze` — core mol_bronze models (chembl_molecules, pubchem, openfda_faers, openfda_labels, clinicaltrials)
- `ip_bronze` — IP/patent/trademark + EUIPO: uspto_*, epo_*, euipo_*, plus legacy hcs_bronze for acc_tvc/hrsa/cms_hospital_info/cms_inpatient/cms_cost_reports
- `mol_bronze_ext` — all other mol_bronze models (vocabulary, FDA, literature, CMS cross-domain)
- `hcs_bronze` — all hcs_bronze.* CMS PUF models (53 models)
- `ind_bronze` / `ind_silver` — indication/ICD models

**i. Update backfill kwargs** (`src/dk_data/ingestion/initial_backfill.py` `BACKFILL_SOURCE_KWARGS`):
- Add entry only if source needs raised caps for the one-time historical fetch
- For OpenFDA sources: `{'full_backfill': True}` (year-partitioned)
- For high-volume API sources: `{'max_records': N}` raising above the conservative default
- For CMS PUF multi-year sources: `{'years': [2021, 2022, 2023]}`

**j. Silver SQLMesh model** — extend existing or create new (see Strategy above):
- File: `src/dk_data/sqlmesh/models/{domain}/silver/{model_name}.sql`
- Register in appropriate LAYER_MODELS layer (`silver`, `hcs_silver`, `mol_silver_ext`, etc.)

**k. Gold SQLMesh model** — update existing SELECT or create new mart:
- File: `src/dk_data/sqlmesh/models/{domain}/gold/{mart_name}.sql`
- Register in appropriate LAYER_MODELS layer (`gold`, `ip_gold`, `mol_gold_ext`, `mart`)

**l. CronJob manifest** (`k8s/apps/cronjobs/base/cronjob-fetch-{source-name}.yaml`):

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: fetch-{source-name}
  labels:
    app: fetch-{source-name}
    app.kubernetes.io/name: fetch-{source-name}
    app.kubernetes.io/component: ingestion
    app.kubernetes.io/part-of: dk-data
spec:
  schedule: "0 N * * *"   # pick slot avoiding conflicts (see schedule table below)
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 3600
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 2
      ttlSecondsAfterFinished: 86400
      activeDeadlineSeconds: N  # seconds matching expected runtime
      template:
        metadata:
          labels:
            app: fetch-{source-name}
            app.kubernetes.io/component: batch-job
            app.kubernetes.io/part-of: dk-data
            team: data-platform
            service: dk-data
            product: dk-data
        spec:
          restartPolicy: Never
          securityContext:
            runAsNonRoot: true
            runAsUser: 1000
            fsGroup: 1000
            seccompProfile:
              type: RuntimeDefault
          imagePullSecrets:
            - name: ghcr-credentials
          containers:
            - name: fetch-{source-name}
              image: ghcr.io/data-kinetic/dk-data-fe/job-trigger:main
              command: ["python", "-m", "dk_data.ingestion.main"]
              args: ["{source_name}"]
              env:
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
                - name: OTEL_EXPORTER_OTLP_ENDPOINT
                  value: "http://alloy.infra.svc.cluster.local:4317"
                - name: OTEL_ENABLED
                  value: "true"
              resources:
                requests:
                  memory: "256Mi"
                  cpu: "100m"
                limits:
                  memory: "1Gi"   # scale up for large sources
                  cpu: "500m"
              securityContext:
                allowPrivilegeEscalation: false
                readOnlyRootFilesystem: true
                capabilities:
                  drop: ["ALL"]
              volumeMounts:
                - name: tmp
                  mountPath: /tmp
          volumes:
            - name: tmp
              emptyDir: {}
```

- Add to `k8s/apps/cronjobs/base/kustomization.yaml` resources list in the appropriate section
- For sources needing API keys: add `envFrom: - secretRef: name: dk-data-secrets` instead of individual env vars, or add the specific key under `env:`

**m. Catalog metadata** (`src/dk_data/scripts/catalog_refresh.py` `SOURCE_METADATA` dict):

```python
"source_name": {
    "topic_tags": ["tag1", "tag2"],
    "ai_description": "One paragraph plain-English description for LLM context.",
    "column_descriptions": {
        "column_name": {"description": "...", "type": "string|integer|decimal|date"},
    },
    "staleness_threshold_hours": 720,  # 30 days monthly; 168 = weekly; 24 = daily
    "target_tables": ["schema.table"],
},
```

**n. Seed SQL** (`src/dk_data/sql/seed_data_sources.sql`):
- Append to the `INSERT INTO meta.data_sources ... ON CONFLICT (source_name) DO UPDATE` block

**o. Tests** (`tests/test_{source_name}_loader.py`):
- Loader with mock DB cursor (using `unittest.mock.patch`)
- Happy path: valid records insert correctly
- Skip path: records missing natural key are skipped
- Error path: DB error is caught and reported in errors list

---

## Secrets & Schedule

**API keys** — never hardcode. Environment variable naming: `{SOURCE_NAME_UPPER}_API_KEY`. Add to Doppler project `dk-data-fe`, configs `prd` and `stg`. Reference in CronJob via `secretKeyRef: name: dk-data-secrets`.

**CronJob schedule** — pick a slot avoiding conflicts. Check current schedules:
```bash
grep "schedule:" k8s/apps/cronjobs/base/cronjob-*.yaml | sed 's/.*schedule: //' | sort -u
```

Common cadences:
- Hourly reference data: `"0 * * * *"`
- Daily: `"0 N * * *"` — stagger by hour
- Weekly: `"0 N * * 0"` (Sunday)
- Monthly: `"0 N 1 * *"`
- Annual: `"0 N 1 1 *"`

---

## Validation

```bash
# 1. Syntax check
python3 -c "
from dk_data.ingestion.sources.{source_name} import load_{source_name}_data
from dk_data.ingestion.fetchers.{source_name} import {SourceName}Fetcher
print('OK')
"

# 2. SOURCE_NAME matches SOURCES registry key
python3 -c "
from dk_data.ingestion.fetchers.{source_name} import {SourceName}Fetcher
from dk_data.ingestion.main import SOURCES
assert '{source_name}' in SOURCES, 'source missing from SOURCES dict'
assert SOURCES['{source_name}']['fetcher'] == {SourceName}Fetcher
print('OK')
"

# 3. Run tests
pytest tests/test_{source_name}*.py -v

# 4. SQLMesh dry run
cd src && python -m dk_data.ingestion.transform_molecules --plan

# 5. Kustomize validation
kubectl kustomize k8s/overlays/staging > /dev/null && echo OK
```

---

## Deployment Checklist

1. **Doppler secret** (if API key needed): `doppler secrets set {SOURCE_NAME_UPPER}_API_KEY --project dk-data-fe --config prd`
2. **Migration**: `doppler run -- python -m dk_data.scripts.run_migrations src/dk_data/sql/migrations/NNN_{source_name}.sql`
3. **Seed sources**: `doppler run -- psql $DATABASE_URL -f src/dk_data/sql/seed_data_sources.sql`
4. **Test fetch** (1000 records): `doppler run -- python -m dk_data.ingestion.main {source_name} --max-records 1000`
5. **Verify raw**: `SELECT COUNT(*) FROM {prefix}_raw.{source_name};`
6. **SQLMesh plan + apply**: `doppler run -- python -m dk_data.ingestion.transform_molecules --layer {layer}`
7. **Verify bronze**: `SELECT COUNT(*) FROM {prefix}_bronze.{source_name};`
8. **Verify silver entity linking**: check NULL rates for `molecule_id` / `npi` / `provider_id`
9. **Verify gold**: `SELECT COUNT(*) FROM {prefix}_gold.{mart_name};`
10. **Deploy CronJob**: `kubectl apply -f k8s/apps/cronjobs/base/cronjob-fetch-{source-name}.yaml -n dk-data-prod`

---

## Key Rules

- **SOURCE_NAME in fetcher must exactly match the key in SOURCES dict** — mismatches break `_meta_name()` tracking
- **Schema prefix**: `hcs_` for CMS/healthcare system, `mol_` for drugs/molecules, `ind_` for indications, `hcp_` for healthcare professionals
- **Source name**: always `snake_case` (e.g., `cms_physician_puf`, `nice_hta`)
- **CronJob name**: always `kebab-case` with `fetch-` prefix (e.g., `fetch-cms-physician-puf`)
- **HCS raw tables**: preserve API field names exactly; flat columns; `_source_year`+`_source_hash` required
- **Mol raw tables**: standardized JSONB schema — never flat columns; `response_body JSONB` + expression indexes
- **HCS bronze models**: `INCREMENTAL_BY_UNIQUE_KEY`; cast every column explicitly; never drop or rename columns
- **Mol bronze models**: `INCREMENTAL_BY_TIME_RANGE` on `ingested_at`; JSONB extraction via `->>`; include `processed_to_silver`, `raw_json`, `source`, `created_at`
- **HCS loaders**: always use `apply_column_mapping(df, COLUMN_MAPPING)` — never `df.rename()` (case-sensitive bug)
- **Mol loaders**: direct `json.dumps(record)` JSONB insert with expression-index `ON CONFLICT`; skip records missing natural key
- **Silver models**: include entity linking to mol/hcs/hcp/ind when identifiers are present; NULL molecule_id is acceptable when no drug data exists
- **Gold models**: aggregate from ≥2 silver sources; add computed metrics; `kind FULL`
- **API keys**: never hardcoded — always from environment via Doppler → `dk-data-fe` / `dk-data-secrets`
- **DB host**: `postgres-cluster-rw.infra.svc.cluster.local:5432` (production)
- **PostgREST grants**: `GRANT SELECT ON {view} TO web_anon, analyst;` in migration
- **102 sources** currently registered — check `main.py` SOURCES dict before naming to avoid collisions

## Current Sources Reference (102 total)

```
acc_tvc, bindingdb, cdc_vaccines, chembl_activities, chembl_molecules,
clinicaltrials, cms_care_compare, cms_chow, cms_chronic_conditions,
cms_claim_type_puf, cms_cost_reports, cms_cost_reports_puf,
cms_cost_reports_puf_lines, cms_ddinter, cms_dme_puf, cms_dmepos,
cms_dual_eligible, cms_enrollment_puf, cms_formulary,
cms_geographic_variation, cms_hcris, cms_home_health, cms_hospice_puf,
cms_hospital_affiliation, cms_hospital_general_info, cms_hospital_info,
cms_hospital_quality, cms_imaging_puf, cms_inpatient, cms_inpatient_puf,
cms_lab_services, cms_magnet, cms_medicaid_drug_spending, cms_medicare,
cms_medicare_advantage, cms_mental_health_puf, cms_ndc, cms_nppes,
cms_nucc, cms_open_payments, cms_opioid_puf, cms_ordering_providers,
cms_outpatient_puf, cms_part_b_spending, cms_part_d_prescriber,
cms_part_d_spending, cms_pecos, cms_physician_puf,
cms_physician_puf_services, cms_pos, cms_post_acute, cms_rbcs,
cms_referring_providers, cms_snf_puf, cms_stabilis, cms_telehealth_puf,
cms_usp, cms_utilization_puf, cochrane, dailymed, drugbank, ema,
ema_regulatory, epo_ops, euipo_designs, euipo_trademarks, europepmc,
fda_drugs, fda_ndc, fda_rems, hrsa, hta_bodies, imgt, journal_rss,
kegg_drug, medical_news, nice_hta, nih_reporter, npi_registry,
openalex_ci, openfda_faers, openfda_labels, orange_book, orcid, pdb,
pharmgkb, pubchem, pubmed, purple_book, reactome, rxnorm, sec_edgar,
sider, tdc_admet, ttd, uniprot, uspto_ci, uspto_patents,
uspto_trademarks, who_gho, who_icd, who_inn
```
