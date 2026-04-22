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

Every data source flows through four layers. Schema prefix is determined by domain (per CLAUDE.md domain-prefix rule):

| Domain | Prefix | Existing layers | Typical sources |
|--------|--------|-----------------|-----------------|
| Molecule / drug / compound | `mol_` | `mol_raw`, `mol_bronze`, `mol_silver`, `mol_gold`, `mol_api` | ChEMBL, DrugBank, PubChem, FDA, OpenFDA drug, ClinicalTrials.gov, EuropePMC, PubMed, DailyMed |
| Healthcare system / CMS | `hcs_` | `hcs_raw`, `hcs_bronze`, `hcs_silver`, `hcs_gold` | All CMS PUFs, NPPES, HRSA, Open Payments, hospital quality |
| Indication / disease | `ind_` | `ind_raw`, `ind_bronze`, `ind_silver`, `ind_gold` | WHO ICD, MeSH, SNOMED; Orphanet + OMIM pending |
| Healthcare professional | `hcp_` | `hcp_raw` (ROR only so far), `hcp_silver`, `hcp_gold` (empty) | ORCID, NIH Reporter, ROR, Scopus |
| Intellectual property | `ip_` | `ip_raw`, `ip_bronze`, `ip_silver`, `ip_gold` (empty), `ip_api` | USPTO, EPO, EUIPO patents / trademarks / designs |
| Medical devices | `dev_` | `dev_raw`, `dev_bronze`, `dev_silver`, `dev_gold` | OpenFDA 510(k), PMA, classification; UDI / MAUDE / enforcement pending |

**`hcp_bronze` does not exist yet.** Researcher bronze data is currently parasitic in `mol_bronze.orcid` / `mol_bronze.nih_reporter` — per CLAUDE.md this is a known domain-prefix violation. Ingest new researcher sources into `hcp_raw`; create `hcp_bronze` if it doesn't yet exist rather than propagating the violation.

**`hcp_gold`, `ip_gold` exist as schemas but have no models yet.** Adding the first gold model requires creating the SQLMesh models directory.

**Schemas vs tables**: one schema per layer per domain. Each data source gets its own table within the schema.

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

**Always extend an existing silver hub before creating a new silver entity.** Determine which existing hub the source feeds.

### The 12 canonical hubs

Every hub has: a primary entity table (deterministic `bigint` PK), an `_identifiers` table (one row per external identifier), and a `_names` table (canonical + aliases with `normalized_name` for fuzzy resolve). Bootstrap migrations: `189_bootstrap_*.sql` through `200_bootstrap_*.sql` + `250_bootstrap_devices.sql`. Resolve functions: `178_resolve_*.sql` through `188_resolve_*.sql` + `249_resolve_device.sql`.

| Hub | Primary table | Identifiers | Names | When to link a new source |
|-----|---------------|-------------|-------|---------------------------|
| Molecule | `mol_silver.molecules` | `mol_silver.molecule_identifiers` | `mol_silver.molecule_names` | Source has drug/molecule data: ChEMBL, DrugBank, PubChem, OpenFDA |
| Drug Product | `mol_silver.drug_products` | `mol_silver.drug_product_identifiers` | `mol_silver.drug_product_names` | Branded/generic products, NDC-level data, Purple Book BLAs |
| Company | `mol_silver.companies` | `mol_silver.company_identifiers` | `mol_silver.company_names` | Sponsor / manufacturer / MAH data |
| Target | `mol_silver.targets` | `mol_silver.target_identifiers` | `mol_silver.target_names` | Protein targets, UniProt-linked |
| Provider | `hcs_silver.providers` | `hcs_silver.provider_identifiers` | `hcs_silver.provider_names` | NPI-keyed sources: NPPES, physician PUFs |
| Facility | `hcs_silver.facilities` | `hcs_silver.facility_identifiers` | `hcs_silver.facility_names` | CCN-keyed sources: hospital PUFs, cost reports |
| Condition | `ind_silver.conditions` | `ind_silver.condition_identifiers` | `ind_silver.condition_names` | ICD-10, ICD-11, MeSH, SNOMED, Orphanet |
| Researcher | `hcp_silver.researchers` | `hcp_silver.researcher_identifiers` | `hcp_silver.researcher_names` | ORCID, NIH Reporter, Scopus |
| Patent | `ip_silver.patents` | `ip_silver.patent_identifiers` | `ip_silver.patent_names` | USPTO, EPO, WIPO |
| Trademark | `ip_silver.trademarks` | `ip_silver.trademark_identifiers` | `ip_silver.trademark_names` | USPTO, EUIPO |
| Design | `ip_silver.designs` | `ip_silver.design_identifiers` | `ip_silver.design_names` | EUIPO designs, USPTO designs |
| **Device** | `dev_silver.devices` | `dev_silver.device_identifiers` | `dev_silver.device_names` | OpenFDA /device/510k, /pma, /classification; UDI / MAUDE pending |

**Deprecated — do not use in new models:**
- `mol_silver.molecule_aliases` → use `mol_silver.molecule_names`
- `mol_silver.identifier_mappings` → use `mol_silver.molecule_identifiers`
- `mol_silver.researchers` (denormalized copy) → use canonical `hcp_silver.researchers`

### Tables that look like hubs but are NOT — treat with care

These silver entities are currently denormalized fact tables with string PKs. Do not call them hubs; do not `resolve_*()` them; do not assume future sources can deduplicate against them cleanly.

| Table | PK (string) | What it actually is |
|-------|-------------|---------------------|
| `mol_silver.clinical_trials` | `nct_id` | CT.gov fact table; `molecule_id` FK is nullable; `conditions` is JSONB. Belongs in a future `clin_*` domain per entity-linkage audit. |
| `mol_silver.publications` | `doi` | Publications fact; many rows have no DOI; no deterministic `publication_id`. |
| `mol_silver.adverse_events` | aggregated | Pre-aggregated FAERS signals, not case-level. Case-level lives in `mol_bronze.openfda_faers`. |
| `mol_silver.drug_labels` | `set_id` | DailyMed/OpenFDA labels; `indications_and_usage` is free text — not resolved to `condition_id`. |

If your source feeds one of these, keep using it for now, but add a task to promote it to a proper hub before linking new domains through it.

### HCS non-hub silver models (keep extending these)

| Silver model | Entity key | When to extend |
|--------------|------------|----------------|
| `hcs_silver.geographic_health` | `geo_code` + `geo_level` | Geographic aggregates: geographic_variation, chronic_conditions, enrollment_puf, opioid_puf, dual_eligible, medicare_advantage, claim_type_puf, utilization_puf |
| `hcs_silver.drug_utilization` | `drug_or_hcpcs_code` + `code_type` | Drug spending: part_d_spending, part_b_spending, medicaid_drug_spending, dme_puf, lab_services, imaging_puf |
| `hcs_silver.part_d_prescribing` | `prscrbr_npi` + `gnrc_name` | Part D prescriber-level: part_d_prescriber |
| `hcs_silver.open_payments_drug_linkage` | `record_id` + `drug_slot` | Open Payments drug strings → `molecule_id` |
| `hcs_silver.cms_drug_market` | `drug_or_hcpcs_code` + `year` | Market-level drug spending aggregates |

### Entity Linking — resolve functions (exact signatures)

**Every resolve function takes multiple positional parameters with a priority-tiered lookup and returns `bigint`.** Calling them with a single positional arg will silently miss because the first param is usually a structural identifier the source doesn't have.

Always call with named-parameter syntax (`=>`) so the compiler catches wrong-parameter-name errors at validation time.

| Function | Signature | Priority tiers |
|----------|-----------|----------------|
| `mol_silver.resolve_molecule` | `(p_inchi_key, p_chembl_id, p_drugbank_id, p_pubchem_cid, p_unii, p_cas_number, p_rxcui, p_ndc, p_inn, p_name) → bigint` | InChIKey → ChEMBL → DrugBank → PubChem → UNII → CAS → RxCUI(IN/PIN) → NDC → INN → name fuzzy ≥0.85 |
| `mol_silver.resolve_drug_product` | `(p_bla_number, p_nda_number, p_rxcui_scdf, p_ndc, p_brand_name) → bigint` | BLA → NDA → RxCUI(SCDF/SBDF) → NDC → brand name fuzzy ≥0.85 |
| `mol_silver.resolve_company` | `(p_duns, p_cik, p_ror, p_chembl_src_id, p_fda_registration, p_name) → bigint` | DUNS → CIK → ROR → ChEMBL src → FDA reg → name fuzzy ≥0.85 |
| `mol_silver.resolve_target` | `(p_uniprot_accession, p_gene_symbol, p_chembl_target_id, p_sequence_hash, p_name) → bigint` | UniProt → gene symbol → ChEMBL target ID → sequence hash → name fuzzy |
| `hcs_silver.resolve_provider` | `(p_npi, p_state_license, p_dea, p_last_name, p_first_name) → bigint` | NPI → state license → DEA → name fuzzy |
| `hcs_silver.resolve_facility` | `(p_ccn, p_cms_id, p_npi, p_state_license, p_name) → bigint` | CCN → CMS ID → NPI → state license → name fuzzy |
| `ind_silver.resolve_condition` | `(p_icd10, p_icd11, p_mesh_id, p_snomed_id, p_orphanet_id, p_name) → bigint` | ICD-10 → ICD-11 → MeSH → SNOMED → Orphanet → name fuzzy |
| `hcp_silver.resolve_researcher` | `(p_orcid, p_scopus_id, p_pubmed_signature, p_last_name, p_first_name) → bigint` | ORCID → Scopus → PubMed signature → name fuzzy |
| `ip_silver.resolve_patent` | `(p_uspto_number, p_epo_number, p_wipo_number, p_title) → bigint` | USPTO → EPO → WIPO → title fuzzy |
| `ip_silver.resolve_trademark` | `(p_uspto_serial, p_euipo_number, p_mark_text) → bigint` | USPTO serial → EUIPO number → mark text fuzzy |
| `ip_silver.resolve_design` | `(p_uspto_number, p_euipo_number, p_title) → bigint` | USPTO → EUIPO → title fuzzy |
| `dev_silver.resolve_device` | `(p_udi_di, p_k_number, p_pma_number, p_fei_number, p_name) → bigint` | UDI-DI → K-number → PMA number → FEI number → name fuzzy |

**All STABLE PARALLEL SAFE; SC-004 target p99 ≤10ms.** Relies on trigram GIN indexes on `*_names.normalized_name` — registering a new `_names` table requires adding the index to `src/dk_data/sql/post_sqlmesh/000_hub_indexes.sql` (see "Post-SQLMesh Index Registration" below).

**Correct call pattern — use named parameters:**

```sql
SELECT
    mol_silver.resolve_molecule(p_chembl_id => b.chembl_id, p_name => b.drug_name)  AS molecule_id,
    mol_silver.resolve_drug_product(p_bla_number => b.bla, p_brand_name => b.brand) AS product_id,
    mol_silver.resolve_company(p_name => b.sponsor_name)                            AS company_id,
    hcs_silver.resolve_provider(p_npi => b.npi)                                     AS provider_id,
    hcs_silver.resolve_facility(p_ccn => b.ccn)                                     AS facility_id,
    ind_silver.resolve_condition(p_icd10 => b.icd10, p_name => b.condition_name)    AS condition_id,
    b.*
FROM mol_bronze.new_source b;
```

**`molecule_id`, `product_id`, `company_id`, etc. are `bigint` — declare them `bigint` in the model output, not `UUID`.**

### `mol_silver.resolve_company()` is currently orphaned — wire it

Per 2026-04-20 audit: `resolve_company()` has **zero callsites** across all SQLMesh silver models. FDA sponsor strings, EMA MAH strings, CT.gov `lead_sponsor_name`, Purple Book `applicant` — all are kept as strings and never resolved. **If your new source has a company-string column, it is your responsibility to call `resolve_company()` and emit a `company_id bigint` column.** Reviewers will reject any new mol-silver model that keeps a company string without the resolved ID.

### Cross-hub bridges — extend these when your source spans two entities

When a source carries information about a relationship between two entities (molecule ↔ target, drug_product ↔ molecule, etc.), add rows to the bridge table, not to either hub.

**Existing bridges (FR-014 compliant):**

| Bridge | Schema | Link |
|--------|--------|------|
| `molecule_targets` | `mol_silver` | molecule_id ↔ target_id (ChEMBL bioactivity, DrugBank targets) |
| `molecule_publications` | `mol_silver` | molecule_id ↔ publication (still string-keyed pending publications hub) |
| `drug_product_ingredients` | `mol_silver` | product_id ↔ molecule_id (RxNorm SCD/SBD path — name-join bug for biologics, see Hub ID section) |
| `researcher_publications` | `hcp_silver` | researcher_id ↔ publication |
| `researcher_provider_crosswalk` | `hcp_silver` | researcher_id ↔ provider_id (NPI+ORCID match) |
| `ndc_molecule_bridge` | `mol_silver` | NDC ↔ molecule_id |
| `hcpcs_molecule_bridge` | `mol_silver` | HCPCS ↔ molecule_id |

**Bridges that do not yet exist but are commonly needed — create as `mol_silver.{left}_{right}` per left-side-owns convention:**

- `molecule_companies` (molecule_id ↔ company_id + `role` enum)
- `drug_product_companies` (product_id ↔ company_id + `role`)
- `drug_product_indications` (product_id ↔ condition_id + `approval_status`)
- `drug_product_facilities` (product_id ↔ facility_id + `role`)
- `molecule_patents` (molecule_id ↔ patent_id + `link_basis`)
- `ip_silver.patent_inventors` (patent_id ↔ researcher_id)

If your source supplies data for one of these, create the bridge — do not invent a new silver fact table that carries both string-keys and expect downstream consumers to reconcile.

### Banned silver antipatterns (CI-enforced where possible)

Never write these patterns in a silver model — they will be rejected in review. Per 2026-04-20 audit, live S1/S5 violations exist in `mol_gold/kol_drug_associations.sql:27,44` (0.3 similarity threshold) and `mol_silver/drug_product_ingredients.sql:32` (string-equi-join bypassing resolve) — do not add more.

| Code | Pattern | Why banned | Fix |
|------|---------|-----------|-----|
| S1 | `WHERE hub_id = A OR hub_id = B` | OR-join causes seq scan | `= ANY(ARRAY[A, B])` or two separate joins |
| S2 | `WHERE name LIKE '%query%'` (leading wildcard) | Cannot use index | `similarity(LOWER(name), LOWER(query)) >= 0.85` with trigram GIN index |
| S3 | Correlated scalar subquery per-row | N+1 in SELECT | Lateral join or CTE (see `competitive_landscape.sql` header for the fix pattern) |
| S4 | `DISTINCT ON ... UNION ALL` over hub tables | Disguises fan-out | Single hub join with explicit dedup key |
| S5 | `similarity(name, q) > 0.8 OR name = q` | Mixed fuzzy+exact in OR | Two passes (exact first, fuzzy fallback) or call the resolve function |

**Additional rule — any fuzzy similarity threshold below 0.85 needs explicit justification** (the hub-resolve tier 10 fallback uses ≥0.85; lower thresholds at silver/gold create false joins).

Cross-domain links to always include when present:
- Drug names/NDCs → `mol_silver.molecule_names` (not `molecule_aliases`)
- Identifier cross-refs → `mol_silver.molecule_identifiers` (not `identifier_mappings`)
- NPI → `hcs_silver.providers` via `resolve_provider(p_npi => ...)`
- CCN → `hcs_silver.facilities` via `resolve_facility(p_ccn => ...)`
- Sponsor/applicant strings → `mol_silver.companies` via `resolve_company(p_name => ...)` — the orphan wiring above

### Hub ID construction & canonicalization

**Hub IDs are deterministic `bigint` hashes of a canonical identifier.** Two rules that silver models adding to hubs must honor:

**Rule H1 — Immutability.** Once a hub row has an ID, never rehash it. Identifier evolution happens in `{entity}_identifiers`, never by recomputing the hub PK. If your source introduces a new identifier type for an existing entity, UPSERT into `_identifiers`, don't change the hub row.

**Rule H2 — Canonical-identifier priority.** Hub ID is `md5(lower(canonical_identifier))` where `canonical_identifier` is the first non-null value from the hub's documented priority list. The priority list per hub matches the resolve function's tiers (molecule: inchi_key > unii > cas > chembl > drugbank > ...; drug_product: bla > nda > rxcui_scdf > ndc > brand_name; etc.).

**Biologic / fusion-protein gotcha (active bug per entity-linkage audit §5.4).** The current `mol_silver.molecules` builds biologic hub IDs as `md5('bio:' || LOWER(COALESCE(pref_name, chembl_id)))` — no TRIM, no punctuation strip, no NFC. This means:
- `'Rilonacept'` vs `'rilonacept '` vs `'Rilonacept (recombinant)'` → three molecule rows
- ChEMBL NULL `pref_name` → hashes on `chembl_id`; DrugBank → hashes on `name`; split-brain for the same drug

**When ingesting a biologic source**, either:
(a) canonicalize aggressively before inserting — `md5('bio:' || regexp_replace(lower(trim(name)), '\s+', ' ', 'g'))` — and add a test confirming known biologics (rilonacept, adalimumab) land on one row, OR
(b) load the row and map via `mol_silver.molecule_dedup_map` sidecar (if present) rather than through the hash PK.

**`product_id` hash scheme (active bug per audit §5.6)**: `drug_product_ingredients.product_id = md5(rxcui_product)` does not match `purple_book.product_id = md5('bla:' + bla_number + ':' + product_number)` for the same ARCALYST BLA. When you write a new model that emits `product_id`, use `resolve_drug_product()` with the priority list — never compute `md5()` locally. Silver models that compute `product_id` inline will be rejected.

**Research-code / pipeline-asset handling.** `resolve_molecule()` has no `research_code` parameter today. Sources ingesting pre-regulatory assets (KPL-387, KPL-1161) must:
1. Write the research code to `mol_silver.molecule_names` with `source = 'research_code'`
2. Rely on the name-fuzzy tier (similarity ≥ 0.85) for later sources to match

Do not create a separate pipeline-assets table — extend the molecule hub.

### Post-SQLMesh index registration

Adding a new silver `_names` table, a new bronze partition, or a new gold view requires registering indexes/grants in the post-SQLMesh scripts (run after SQLMesh materializes tables). See cluster-access runbook §7.

**When you add a new silver hub `_names` table**, append to `src/dk_data/sql/post_sqlmesh/000_hub_indexes.sql`:

```sql
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS {domain}_silver_{entity}_names_trgm_idx ON {domain}_silver.{entity}_names USING GIN (LOWER(normalized_name) gin_trgm_ops)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS {domain}_silver_{entity}_names_norm_idx ON {domain}_silver.{entity}_names (normalized_name)');
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS {domain}_silver_{entity}_names_pk_idx ON {domain}_silver.{entity}_names ({entity}_id)');
```

Without the trigram GIN index, the resolve function's fuzzy-name tier degrades from p99 ≤10ms to seq-scan territory.

**When you add a new bronze table with a time column**, append a BRIN index to `src/dk_data/sql/post_sqlmesh/035_brin_indexes.sql`:

```sql
SELECT _try_create_index('CREATE INDEX IF NOT EXISTS {domain}_bronze_{table}_ingested_at_brin ON {domain}_bronze.{table} USING BRIN (ingested_at) WITH (pages_per_range = 32)');
```

**When you add a new silver/gold view to expose via PostgREST**, append grants to `src/dk_data/sql/post_sqlmesh/055_postgrest_hub_grants.sql`:

```sql
GRANT SELECT ON {domain}_silver.{new_table} TO web_anon, analyst, api_user;
```

**When you add a high-write table**, tune autovacuum in `src/dk_data/sql/post_sqlmesh/036a_autovacuum_tuning.sql` to avoid bloat.

Verify post-SQLMesh scripts apply cleanly:

```bash
export KUBECONFIG=/tmp/k3s-fresh.yaml
JOB_POD=$(kubectl get pods -n dk-data-prod | grep job-trigger | grep Running | awk '{print $1}' | head -1)
kubectl exec -n dk-data-prod $JOB_POD -- python3 -c "
import psycopg2, os
conn = psycopg2.connect(host=os.environ['POSTGRES_HOST'], port=os.environ['POSTGRES_PORT'],
    dbname=os.environ['POSTGRES_DB'], user=os.environ['POSTGRES_USER'], password=os.environ['POSTGRES_PASSWORD'])
conn.autocommit = True
sql = open('/usr/local/lib/python3.11/site-packages/dk_data/sql/post_sqlmesh/000_hub_indexes.sql').read()
conn.cursor().execute(sql)
print('hub indexes OK')
"
```

### Resolve-function performance fixtures

`tests/perf/test_resolve_latency.py` enforces the SC-004 ≤10ms p99 target. **Test is currently `@pytest.mark.perf` gated — it does not run in default CI**, so regressions can land silently.

When your new source introduces a new identifier type, synonym pattern, or biologic/fusion-protein class, add fixtures:

```python
# tests/perf/test_resolve_latency.py RESOLVE_FUNCTIONS entry
(
    "mol_silver.resolve_molecule",
    [
        # Add your new source's representative calls:
        ("YOUR_INCHI_KEY", None, None, None, None, None, None, None, None, None),
        (None, None, None, None, None, None, None, None, None, "rilonacept"),  # biologic name fallback
        (None, None, None, None, None, None, None, None, None, "KPL-387"),     # research code
    ],
),
```

Run manually against production-like data:

```bash
pytest tests/perf/test_resolve_latency.py -m perf -v
```

### Gold Models

Gold models aggregate from ≥2 silver sources, add computed metrics (rankings, ratios, indices), and use `kind FULL, cron '@daily'`. Update existing gold models when extending existing silver entities. Create new gold models only for genuinely new entity types.

`hcp_gold` and `ip_gold` have no models yet — adding one requires creating the SQLMesh directory (`src/dk_data/sqlmesh/models/hcp/gold/` or `src/dk_data/sqlmesh/models/ip/gold/`) and registering the layer in `transform_molecules.py` LAYER_MODELS.

---

## Implementation Order

### Phase 1: API Discovery

1. Analyze user input — fetch URL/spec if provided, research via web search if description only.
2. Determine: base URL, auth method, data format, pagination strategy, rate limits, natural key, domain (`mol_`/`hcs_`/`ind_`/`hcp_`/`ip_`), pattern (file-based vs API-based).
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

**i.2. Register in `meta.backfill_state`** (append to `src/dk_data/sql/seed_backfill_state.sql` or equivalent seed):

The platform has two ingestion paths: **per-source CronJobs** (primary; fires on its own schedule) and the **`backfill-orchestrator`** CronJob (priority-queued, picks one source per 10-min tick from `meta.backfill_state WHERE status='active'`). Both must be registered:

```sql
INSERT INTO meta.backfill_state (source_name, status, priority, fetcher_args)
VALUES ('example_source', 'active', 40, '{"max_records": 50000}'::jsonb)
ON CONFLICT (source_name) DO UPDATE
SET status = EXCLUDED.status, priority = EXCLUDED.priority, fetcher_args = EXCLUDED.fetcher_args;
```

Priority tiers in current use: `10` (critical IP/literature), `20` (secondary IP/research), `30` (high-volume molecular), `40` (CMS PUF bulk), `50` (reference/regulatory), `60` (news/feeds).

**As of 2026-04-21 the orchestrator is inoperative** — WAL-dir circuit-breaker misreads actual WAL usage and skips every tick. Your per-source CronJob (step `l` below) is what actually runs. The orchestrator registration is still required so that when the breaker bug is fixed the source auto-enrolls.

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
# 1. Syntax check — imports resolve
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

# 3. Unit tests
pytest tests/test_{source_name}*.py -v

# 4. Resolve-function calls use named params (not positional)
grep -n 'resolve_molecule\|resolve_company\|resolve_condition\|resolve_drug_product' \
  src/dk_data/sqlmesh/models/**/silver/{source_name}.sql && echo '⚠️ verify each call uses p_* named params'

# 5. Post-SQLMesh index registration present for any new _names table
grep -n '{source_name}\|{new_entity}_names' src/dk_data/sql/post_sqlmesh/000_hub_indexes.sql

# 6. Resolve-latency perf test passes (p99 ≤10ms) — run manually, not in default CI
pytest tests/perf/test_resolve_latency.py -m perf -v

# 7. SQLMesh plan dry run
cd src && python -m dk_data.ingestion.transform_molecules --plan

# 8. Kustomize validation
kubectl kustomize k8s/overlays/staging > /dev/null && echo OK
```

---

## Deployment Checklist

1. **Doppler secret** (if API key needed): `doppler secrets set {SOURCE_NAME_UPPER}_API_KEY --project dk-data-fe --config prd`
2. **Migration**: `doppler run -- python -m dk_data.scripts.run_migrations src/dk_data/sql/migrations/NNN_{source_name}.sql`
3. **Seed sources**: `doppler run -- psql $DATABASE_URL -f src/dk_data/sql/seed_data_sources.sql`
4. **Register in `meta.backfill_state`** (for orchestrator path): run the seed INSERT from step i.2
5. **Test fetch** (1000 records): `doppler run -- python -m dk_data.ingestion.main {source_name} --max-records 1000`
6. **Verify raw**: `SELECT COUNT(*) FROM {prefix}_raw.{source_name};`
7. **SQLMesh plan + apply**: `doppler run -- python -m dk_data.ingestion.transform_molecules --layer {layer}`
8. **Verify bronze**: `SELECT COUNT(*) FROM {prefix}_bronze.{source_name};`
9. **Apply post-SQLMesh scripts** (trigram/BRIN indexes + grants for any new silver hub tables):
   ```bash
   export KUBECONFIG=/tmp/k3s-fresh.yaml
   JOB_POD=$(kubectl get pods -n dk-data-prod | grep job-trigger | grep Running | awk '{print $1}' | head -1)
   kubectl exec -n dk-data-prod $JOB_POD -- python3 -c "
   import psycopg2, os
   conn = psycopg2.connect(host=os.environ['POSTGRES_HOST'], port=os.environ['POSTGRES_PORT'],
       dbname=os.environ['POSTGRES_DB'], user=os.environ['POSTGRES_USER'], password=os.environ['POSTGRES_PASSWORD'])
   conn.autocommit = True
   for f in ('000_hub_indexes.sql', '000a_gold_indexes.sql', '055_postgrest_hub_grants.sql', '035_brin_indexes.sql'):
       sql = open(f'/usr/local/lib/python3.11/site-packages/dk_data/sql/post_sqlmesh/{f}').read()
       conn.cursor().execute(sql)
       print(f, 'OK')
   "
   ```
10. **Verify silver entity linking** — NULL rates should be low for the resolved FKs:
    ```sql
    SELECT
      COUNT(*) AS total,
      COUNT(*) FILTER (WHERE molecule_id IS NULL) AS null_mol,
      COUNT(*) FILTER (WHERE company_id IS NULL) AS null_co,
      COUNT(*) FILTER (WHERE condition_id IS NULL) AS null_cond
    FROM {prefix}_silver.{source_name};
    ```
    If `null_mol` or `null_co` ratio > 20%, investigate — likely a missing identifier tier or unnormalized name.
11. **Verify gold**: `SELECT COUNT(*) FROM {prefix}_gold.{mart_name};`
12. **Deploy CronJob**: `kubectl apply -f k8s/apps/cronjobs/base/cronjob-fetch-{source-name}.yaml -n dk-data-prod`
13. **Verify orchestrator registration** (even while orchestrator bug blocks actual picks):
    ```sql
    SELECT source_name, status, priority, total_rows_loaded, last_success_at
    FROM meta.backfill_state WHERE source_name = '{source_name}';
    ```

---

## Key Rules

### Naming & registration
- **SOURCE_NAME in fetcher must exactly match the key in SOURCES dict** — mismatches break `_meta_name()` tracking
- **Schema prefix per CLAUDE.md**: `mol_` (drugs), `hcs_` (CMS), `ind_` (disease), `hcp_` (researcher), `ip_` (patents/trademarks/designs). `api` schema is deprecated — new views go in `{domain}_api` or `{domain}_gold`.
- **Source name**: always `snake_case` (e.g., `cms_physician_puf`, `nice_hta`)
- **CronJob name**: always `kebab-case` with `fetch-` prefix (e.g., `fetch-cms-physician-puf`)
- **Register in both paths**: `SOURCES` dict (per-source CronJob) AND `meta.backfill_state` (orchestrator queue)

### Table shape
- **HCS raw**: preserve API field names; flat columns; `_source_year`+`_source_hash` required
- **Mol/IP/Ind/HCP raw**: standardized JSONB — `response_body JSONB` + `request_id` unique index + natural-key expression index + `processed_to_bronze` partial index + `ingested_at` index
- **HCS bronze**: `INCREMENTAL_BY_UNIQUE_KEY`; cast every column; never drop/rename columns
- **Mol/IP/Ind bronze**: `INCREMENTAL_BY_TIME_RANGE` on `ingested_at`; JSONB extraction via `->>`; include `processed_to_silver`, `raw_json`, `source`, `created_at`

### Loaders
- **HCS loaders**: `apply_column_mapping(df, COLUMN_MAPPING)` — never `df.rename()` (case-sensitive bug)
- **Mol/IP/Ind/HCP loaders**: `json.dumps(record)` JSONB insert with expression-index `ON CONFLICT`; skip records missing natural key

### Silver entity linking
- **Resolve functions return `bigint`, not UUID** — declare hub FK columns `bigint`
- **Call with named params** (`p_chembl_id => ..., p_name => ...`) — positional calls silently miss because first param is usually a structural identifier
- **`resolve_company()` has zero callsites today** — any new mol source with a sponsor/applicant string must wire it and emit `company_id bigint`
- **Never compute hub hashes locally** (`md5(...)` in a silver model) — always use `resolve_*()`; `product_id` hash scheme is scheme-inconsistent across existing models and a PR adding another local hash will be rejected
- **Biologic names must be aggressively canonicalized** before feeding the molecule hub: `regexp_replace(lower(trim(name)), '\s+', ' ', 'g')` at minimum, or use the dedup sidecar
- **NULL resolved-FK is acceptable only when the source genuinely lacks the identifier** — >20% NULL rate on `molecule_id` / `company_id` / `condition_id` indicates a missing tier or normalization bug
- **Hub IDs are immutable** — never rehash a hub row; evolve identifiers via `*_identifiers` table

### Silver antipatterns (rejected in review)
- S1 OR-join hub IDs · S2 leading-wildcard LIKE · S3 correlated scalar subquery · S4 DISTINCT ON over UNION ALL · S5 similarity + = in OR
- Any `similarity(...)` threshold below `0.85` without written justification
- Bypassing `resolve_*()` with a string equi-join on a name column (active bug in `drug_product_ingredients.sql:32` — do not add more)

### Gold models
- Aggregate from ≥2 silver sources; add computed metrics; `kind FULL, cron '@daily'`

### Performance
- **Every new `_names` table** requires a trigram GIN index in `post_sqlmesh/000_hub_indexes.sql` — without it, fuzzy-name resolve degrades to seq-scan
- **Every new bronze partition** gets a BRIN index in `post_sqlmesh/035_brin_indexes.sql`
- **Resolve-latency test** (`tests/perf/test_resolve_latency.py`) is not CI-gated — add fixtures for your source's representative calls and run manually

### Secrets & infra
- **API keys**: from Doppler `dk-data-fe` / `dk-data-secrets` — never hardcoded
- **DB host**: `postgres-cluster-rw.infra.svc.cluster.local:5432` (production); DO NOT use `postgres.postgres.svc.cluster.local` (the Doppler-managed `DATABASE_URL` points there but the host doesn't exist — override with individual `POSTGRES_*` env vars)
- **Pipeline jobs bypass PgBouncer** — they connect directly to PostgreSQL (PgBouncer's transaction-mode breaks `SET LOCAL`, advisory locks, `LISTEN/NOTIFY`)

### PostgREST
- **Grants**: `GRANT SELECT ON {view} TO web_anon, analyst, api_user;` in migration. For `mol_api` views also `GRANT USAGE ON SCHEMA mol_api TO web_anon, analyst, api_user;`
- **Exposed schemas**: `api` (deprecated) and `mol_api` per `postgrest.conf` `db-schemas`. New mol domain views → `mol_api`; platform/ops views → `api` only if they span multiple domains, else a domain-specific `*_api` schema
- **103 sources registered** in `meta.backfill_state` (55 active, 48 complete as of 2026-04-21) — check `main.py` SOURCES dict and `meta.backfill_state` before naming to avoid collisions

## Current Sources Reference (103 total)

Pulled live from `meta.backfill_state` 2026-04-21 — re-verify before merging a new source:

```
acc_tvc, bindingdb, cdc_vaccines, chembl_activities, chembl_molecules,
clinicaltrials, cms_care_compare, cms_chow, cms_chronic_conditions,
cms_claim_type_puf, cms_cost_reports, cms_cost_reports_puf, cms_coverage,
cms_ddinter, cms_dme_puf, cms_dmepos, cms_dual_eligible,
cms_enrollment_puf, cms_formulary, cms_geographic_variation, cms_hcris,
cms_home_health, cms_hospice_puf, cms_hospital_affiliation,
cms_hospital_general_info, cms_hospital_info, cms_hospital_quality,
cms_imaging_puf, cms_inpatient, cms_inpatient_puf, cms_lab_services,
cms_magnet, cms_medicaid_drug_spending, cms_medicare,
cms_medicare_advantage, cms_mental_health_puf, cms_ndc, cms_nppes,
cms_nucc, cms_open_payments, cms_opioid_puf, cms_ordering_providers,
cms_outpatient_puf, cms_part_b_spending, cms_part_d_prescriber,
cms_part_d_spending, cms_pecos, cms_physician_puf,
cms_physician_puf_services, cms_pos, cms_post_acute, cms_puf, cms_rbcs,
cms_referring_providers, cms_snf_puf, cms_stabilis, cms_telehealth_puf,
cms_usp, cms_utilization_puf, cochrane_reviews, dailymed, drugbank, ema,
ema_regulatory, epo_patents, euipo_designs, euipo_trademarks, europepmc,
fda_drugs, fda_ndc, fda_rems, hrsa_shortage_areas, hta_decisions, imgt,
journal_rss, kegg_drug, medical_news, nice_hta, nih_reporter,
npi_registry, openalex_ci, openfda_faers, openfda_labels, orange_book,
orcid, pdb, pharmgkb, pubchem, pubmed, purple_book, reactome, rxnorm,
sec_edgar, sider, tdc_admet, ttd, uniprot, uspto_ci, uspto_patents,
uspto_trademarks, who_gho, who_icd, who_inn
```

Re-pull the current list any time before naming:

```bash
export KUBECONFIG=/tmp/k3s-fresh.yaml
JOB_POD=$(kubectl get pods -n dk-data-prod | grep job-trigger | grep Running | awk '{print $1}' | head -1)
kubectl exec -n dk-data-prod $JOB_POD -- python3 -c "
import psycopg2, os
conn = psycopg2.connect(host=os.environ['POSTGRES_HOST'], port=os.environ['POSTGRES_PORT'],
    dbname=os.environ['POSTGRES_DB'], user=os.environ['POSTGRES_USER'], password=os.environ['POSTGRES_PASSWORD'])
cur = conn.cursor()
cur.execute('SELECT source_name FROM meta.backfill_state ORDER BY source_name')
print(', '.join(r[0] for r in cur.fetchall()))
"
```
