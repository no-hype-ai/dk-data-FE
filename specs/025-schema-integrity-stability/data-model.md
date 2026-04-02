# Data Model: Schema Integrity & Platform Stability

**Branch**: `025-schema-integrity-stability` | **Date**: 2026-04-01

## Changes to Existing Entities

### meta.refresh_log (Column Rename)

| Column | Current (dev-init.sql) | Target (all scripts) | Type |
|--------|----------------------|---------------------|------|
| started_at | `started_at` | `refresh_started_at` | TIMESTAMPTZ |
| completed_at | `completed_at` | `refresh_completed_at` | TIMESTAMPTZ |

All other columns unchanged: `log_id`, `source_id`, `source_name`, `status`, `records_fetched`, `records_inserted`, `records_updated`, `error_message`, `_logged_at`.

### mol_raw.pubchem (New UNIQUE Index)

```
UNIQUE INDEX uidx_mol_raw_pubchem_cid ON (response_body->>'cid')
```

Used by: `src/dk_data/ingestion/sources/pubchem.py` ON CONFLICT clause.

### mol_raw.chembl_molecules (New UNIQUE Index)

```
UNIQUE INDEX uidx_mol_raw_chembl_molecules_chembl_id ON (response_body->>'molecule_chembl_id')
```

Used by: `src/dk_data/ingestion/sources/chembl_molecules.py` ON CONFLICT clause.

### mol_raw.who_gho (New UNIQUE Index)

```
UNIQUE INDEX uidx_mol_raw_who_gho_indicator_code ON (response_body->>'IndicatorCode')
```

Used by: `src/dk_data/ingestion/sources/who_gho.py` ON CONFLICT clause.

### mol_raw.cdc_vaccines (Verify Existence)

Table defined in migration 121. If not present on cluster, migration 138 will create it with the standard envelope schema:
- `id` BIGSERIAL PRIMARY KEY
- `request_id` VARCHAR NOT NULL (UNIQUE)
- `request_timestamp` TIMESTAMPTZ
- `api_endpoint` VARCHAR
- `api_version` VARCHAR
- `request_params` JSONB
- `request_headers` JSONB
- `response_status` INTEGER
- `response_headers` JSONB
- `response_body` JSONB
- `response_body_hash` VARCHAR
- `response_size_bytes` INTEGER
- `response_time_ms` INTEGER
- `processed_to_bronze` BOOLEAN DEFAULT FALSE
- `processed_at` TIMESTAMPTZ
- `processing_error` TEXT
- `ingested_at` TIMESTAMPTZ DEFAULT NOW()
- `source_id` INTEGER

## No New Entities

All changes are modifications to existing tables/indexes. No new tables, schemas, or relationships introduced.
