# Medallion Architecture

Last Updated: 2026-03-28

## Overview

The platform implements a **four-layer medallion architecture** with domain-prefixed schemas. All schema names carry a domain prefix — there are no bare `raw`, `bronze`, `silver`, or `gold` schemas in production.

```
External APIs / Files
        │
        ▼
┌───────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  *_raw        │────▶│  *_bronze    │────▶│  *_silver    │────▶│  *_gold      │
│               │     │              │     │              │     │              │
│ Unmodified    │     │ Source-native│     │ Entity-      │     │ Analytics-   │
│ JSONB envelope│     │ typed cols   │     │ resolved,    │     │ ready views  │
│ (audit trail) │     │ deduplicated │     │ normalized   │     │ & aggregates │
└───────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

## Domain Prefixes

| Prefix | Domain | Physical schemas |
|--------|--------|-----------------|
| `mol_` | Drug / molecule / compound data | `mol_raw`, `mol_bronze`, `mol_silver`, `mol_gold` |
| `hcs_` | Healthcare system / CMS / provider data | `hcs_raw`, `hcs_bronze`, `hcs_silver`, `hcs_gold` |
| `ind_` | Indication / disease / epidemiology | `ind_silver`, `ind_gold` |
| `hcp_` | Healthcare professional / KOL / researcher | `hcp_silver`, `hcp_gold` |

Infrastructure schemas (no prefix): `meta`, `staging`, `mart`, `scoring`, `xenon`.

## Schema Redirect (SQLMesh config.yaml)

SQLMesh model files use bare logical names (`silver.molecules`, `bronze.chembl_molecules`). The `config.yaml` `physical_schema_mapping` redirects them to domain-prefixed physical schemas at deploy time. **Model files do not need renaming.**

| Model declares | Lands in (physical) |
|---------------|---------------------|
| `raw.*` | `mol_raw.*` |
| `bronze.*` | `mol_bronze.*` |
| `silver.*` | `mol_silver.*` |
| `gold.*` | `mol_gold.*` |
| `hcs_raw.*` | `hcs_raw.*` |
| `hcs_bronze.*` | `hcs_bronze.*` |
| `hcs_silver.*` | `hcs_silver.*` |
| `hcs_gold.*` | `hcs_gold.*` |

## Raw Layer

**Purpose**: Immutable audit trail. Every API response or file row is stored verbatim as JSONB.

**Schema pattern** (all raw tables share this envelope):

```sql
CREATE TABLE mol_raw.<source> (
    request_id          VARCHAR(512) PRIMARY KEY,  -- stable, deterministic per record
    request_timestamp   TIMESTAMPTZ NOT NULL,
    api_endpoint        TEXT NOT NULL,
    api_version         VARCHAR(50),
    request_params      JSONB,
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,            -- full API response verbatim
    response_body_hash  VARCHAR(64),               -- SHA-256 for change detection
    response_size_bytes INTEGER,
    processed_to_bronze BOOLEAN NOT NULL DEFAULT FALSE,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id           VARCHAR(100) NOT NULL
);
```

**Upsert strategy**: `ON CONFLICT (request_id) DO UPDATE ... WHERE response_body_hash IS DISTINCT FROM EXCLUDED.response_body_hash` — only overwrites when content changes, preserving the original record otherwise.

**Mol raw tables** (26): `bindingdb`, `chembl`, `clinicaltrials`, `cochrane_reviews`, `drugbank`, `ema`, `epo_patents`, `euipo_trademarks`, `hta_decisions`, `journal_rss`, `medical_news`, `openalex_ci`, `openfda_faers`, `openfda_labels`, `orange_book`, `orcid`, `pdb`, `pubchem`, `pubmed`, `sec_edgar`, `sider`, `uniprot`, `uspto_ci`, `uspto_patents`, `uspto_trademarks`, `who_icd`

**HCS raw tables** (48+): One raw table per CMS bronze source. Legacy file-based tables: `acc_tvc_certification`, `cms_cost_reports`, `cms_hospital_info`, `cms_medicare_inpatient`, `cms_geographic_variation`, `hrsa_shortage_areas`. API/PUF tables include: `cms_open_payments`, `cms_nppes`, `cms_part_d_prescriber`, `cms_physician_puf`, `cms_inpatient_puf`, `cms_part_d_spending`, `cms_part_b_spending`, and 40+ others. See DATA_LOADERS.md for the full inventory.

## Bronze Layer

**Purpose**: Source-native typed columns parsed from raw JSONB. One table per data source.

**Key characteristics**:
- Typed columns matching the source's schema
- Preserves original field names
- `processed_to_silver` flag for pipeline tracking
- `raw_json` fallback column for full source access
- Managed by SQLMesh (`mol_bronze.*`, `hcs_bronze.*`)

**Example tables**: `mol_bronze.chembl_molecules`, `mol_bronze.clinicaltrials`, `mol_bronze.bindingdb`, `mol_bronze.sider`, `hcs_bronze.cms_inpatient_puf`, `hcs_bronze.cms_open_payments`, `hcs_bronze.cms_part_d_prescriber`

## Silver Layer

**Purpose**: Entity-resolved, normalized, deduplicated data. Cross-source identifiers linked.

**Key characteristics**:
- Entity-centric (molecules, trials, providers, publications)
- molecule_id is the master FK across all mol_silver tables
- npi is the master FK across hcs_silver tables
- SQLMesh models define all transformations declaratively

**Mol silver tables** (key ones): `molecules`, `molecule_aliases`, `identifier_mappings`, `clinical_trials`, `adverse_events`, `publications`, `patents`, `trademarks`, `drug_labels`, `bioactivity`, `binding_affinities`, `side_effects`, `regulatory_decisions`, `hcpcs_molecule_bridge`, `ndc_molecule_bridge`, `drug_pharmacology`, `proteins`, `research_grants`, `protein_structures`, `company_financials`

**HCS silver tables**: `provider_profile`, `drug_utilization`, `cms_drug_market`, `part_d_prescribing`, `open_payments_drug_linkage`, `facility_profile`, `cms_facility_profile`, `geographic_health`, `ref_nucc_taxonomy`

## Gold Layer

**Purpose**: Pre-aggregated analytics-ready models. Denormalized for dashboard consumption.

**Mol gold tables**: `molecule_profile`, `competitive_landscape`, `company_pipeline`, `kol_profiles`, `kol_drug_associations`, `lifecycle_evidence`, `trial_outcomes`

**HCS gold tables**: `cms_provider_360`, `cms_facility_360`, `cms_drug_market_profile`, `cms_market_analytics`

## Data Flow

```
Fetcher (Python)
    │  HTTP/file download → normalize → list[dict]
    ▼
Loader (Python)
    │  INSERT INTO mol_raw.<source> ... ON CONFLICT DO UPDATE WHERE hash changed
    ▼
mol_raw.<source>                (JSONB envelope — immutable)
    │  SQLMesh INCREMENTAL_BY_TIME_RANGE or INCREMENTAL_BY_UNIQUE_KEY
    ▼
mol_bronze.<source>             (typed columns, source-native schema)
    │  SQLMesh FULL or INCREMENTAL_BY_UNIQUE_KEY
    ▼
mol_silver.<entity>             (entity-resolved, molecule_id FK)
    │  SQLMesh FULL (monthly) or INCREMENTAL (daily)
    ▼
mol_gold.<view>                 (aggregated, analytics-ready)
```

## Transformations (SQLMesh)

All Bronze → Silver → Gold transformations are declared as SQLMesh models under `src/dk_data/sqlmesh/models/`.

```
src/dk_data/sqlmesh/models/
├── molecules/
│   ├── bronze/    # mol_bronze.* models
│   ├── silver/    # mol_silver.* models
│   └── gold/      # mol_gold.* models
└── hcs/
    ├── bronze/    # hcs_bronze.* models
    └── silver/    # hcs_silver.* models
```

**Running transformations:**

```bash
# Plan and apply all pending transforms
uv run sqlmesh -p src/dk_data/sqlmesh plan --auto-apply

# Dry run (no apply)
uv run sqlmesh -p src/dk_data/sqlmesh plan
```

Transformations are also run automatically by the `cronjob-mol-transform` CronJob (daily 6 AM UTC).

## Data Quality (SQLMesh Audits)

Every silver model declares audits inline:

```sql
MODEL (
    name mol_silver.binding_affinities,
    kind INCREMENTAL_BY_UNIQUE_KEY (unique_key bindingdb_id),
    audits (
        not_null(columns := (bindingdb_id, activity_value_nm))
    )
);
```

Standard audits used: `not_null`, `unique`, `accepted_values`.

## Pipeline Scheduling

| CronJob | Schedule | Scope |
|---------|----------|-------|
| `cronjob-mol-fetch-daily` | 2 AM UTC daily | PubMed, EuropePMC, OpenAlex, Journal RSS, Medical News, SEC EDGAR, NIH Reporter |
| `cronjob-mol-fetch-weekly` | 3 AM UTC Sunday | EMA, USPTO Patents/CI/Trademarks, EPO, EUIPO, UniProt, PDB, ORCID, EUIPO Designs, HTA Bodies |
| `cronjob-mol-fetch-monthly` | 2–11 AM UTC 1st | BindingDB, SIDER, WHO ICD, RxNorm, WHO INN, PharmGKB, KEGG Drug, TDC ADMET, DrugBank, Cochrane |
| `cronjob-mol-transform` | 6 AM UTC daily | SQLMesh bronze → silver → gold |
| `cronjob-cms-all` | Weekly | All CMS file-based PUF sources |

## Key Invariants

1. **Raw is immutable** — never modify raw rows; only upsert when content hash changes
2. **Stable request_id** — format `{source}_{natural_key}` so ON CONFLICT correctly deduplicates across re-runs
3. **molecule_id is deterministic** — `md5(chembl_id::text)::uuid` — stable across full rebuilds, no FK cascade failures
4. **Schema redirect, not rename** — model files declare `silver.molecules`; config.yaml maps that to `mol_silver`
5. **Column zero-loss policy** — all bronze columns must reach silver or be documented as dropped (see COLUMN_LINEAGE.md)
