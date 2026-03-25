# Contract: Bronze SQLMesh Models

**Feature**: 014-uspto-euipo-model-datasource
**Date**: 2026-02-16

> **Incremental processing**: All bronze models below use `r._loaded_at AS ingested_at` and `@incremental_time_filter(_loaded_at)`, matching the efficient pattern from `bronze.drugbank`. This ensures only new/updated rows are processed each run instead of full table scans.

## bronze.uspto_patents (MODIFY — fix JSONB to flat column)

**File**: `src/dk_data/sqlmesh/models/molecules/bronze/uspto_patents.sql`
**Kind**: INCREMENTAL_BY_TIME_RANGE (time_column: ingested_at, lookback: 7)
**Cron**: @weekly
**Grain**: patent_number
**Audits**: not_null(columns := (patent_number)), unique_values(columns := (patent_number))

### Change Required

The current model reads `r.response_body->'patents'` via `jsonb_array_elements()`, but `raw.uspto_patents` has flat columns (patent_number, title, abstract, etc.). Refactor to read flat columns directly.

### Output Schema

```sql
SELECT
    gen_random_uuid() AS id,
    r.patent_number,
    r.title AS patent_title,
    r.abstract AS patent_abstract,
    r.grant_date AS patent_date,
    NULL::TEXT AS patent_type,
    NULL::TEXT AS patent_kind,
    CASE
        WHEN r.cpc_codes IS NOT NULL
        THEN to_jsonb(r.cpc_codes)
        ELSE NULL
    END AS cpc_codes,
    r.assignees->0->>'assignee_organization' AS assignee_organization,  -- PatentsView API field name
    r.assignees->0->>'assignee_type' AS assignee_type,
    r.inventors,
    r.claims_count AS num_claims,
    EXISTS (
        SELECT 1 FROM unnest(COALESCE(r.cpc_codes, '{}')) AS code
        WHERE code LIKE 'A61K%' OR code LIKE 'A61P%'
           OR code LIKE 'C07D%' OR code LIKE 'C07K%'
    ) AS is_pharma_related,
    FALSE AS processed_to_silver,
    r._loaded_at AS ingested_at
FROM raw.uspto_patents r
WHERE r.patent_number IS NOT NULL
  AND @incremental_time_filter(_loaded_at)
```

### Acceptance Criteria

- AC-1: Model compiles with `sqlmesh plan` without errors.
- AC-2: All existing records in `raw.uspto_patents` appear in `bronze.uspto_patents` after `sqlmesh apply`.
- AC-3: No JSONB parsing errors (the core bug fix).
- AC-4: `is_pharma_related` correctly flags CPC codes A61K, A61P, C07D, C07K.

---

## bronze.uspto_ci (NEW)

**File**: `src/dk_data/sqlmesh/models/molecules/bronze/uspto_ci.sql`
**Kind**: INCREMENTAL_BY_TIME_RANGE (time_column: ingested_at, lookback: 7)
**Cron**: @weekly
**Grain**: patent_number
**Audits**: not_null(columns := (patent_number)), unique_values(columns := (patent_number))

### Output Schema

```sql
SELECT
    gen_random_uuid() AS id,
    r.patent_id AS patent_number,
    r.title AS patent_title,
    r.abstract AS patent_abstract,
    r.grant_date AS patent_date,
    CASE
        WHEN r.cpc_codes IS NOT NULL
        THEN to_jsonb(r.cpc_codes)
        ELSE NULL
    END AS cpc_codes,
    r.assignees->0->>'assignee_organization' AS assignee_organization,  -- PatentsView API field name
    r.inventors,
    r.claims_count AS num_claims,
    EXISTS (
        SELECT 1 FROM unnest(COALESCE(r.cpc_codes, '{}')) AS code
        WHERE code LIKE 'A61K%' OR code LIKE 'A61P%'
           OR code LIKE 'C07D%' OR code LIKE 'C07K%'
    ) AS is_pharma_related,
    FALSE AS processed_to_silver,
    r._loaded_at AS ingested_at
FROM raw.uspto_ci r
WHERE r.patent_id IS NOT NULL
  AND @incremental_time_filter(_loaded_at)
```

### Acceptance Criteria

- AC-1: Model compiles and all `raw.uspto_ci` records appear in bronze.
- AC-2: `patent_id` is renamed to `patent_number` for schema consistency with `bronze.uspto_patents`.

---

## bronze.epo_patents (NEW)

**File**: `src/dk_data/sqlmesh/models/molecules/bronze/epo_patents.sql`
**Kind**: INCREMENTAL_BY_TIME_RANGE (time_column: ingested_at, lookback: 7)
**Cron**: @weekly
**Grain**: patent_number
**Audits**: not_null(columns := (patent_number)), unique_values(columns := (patent_number))

### Output Schema

```sql
SELECT
    gen_random_uuid() AS id,
    r.publication_id AS patent_number,
    r.title AS patent_title,
    r.abstract AS patent_abstract,
    r.publication_date AS patent_date,
    CASE
        WHEN r.ipc_codes IS NOT NULL
        THEN to_jsonb(r.ipc_codes)
        ELSE NULL
    END AS ipc_codes,
    NULL::JSONB AS cpc_codes,
    r.applicants->>0 AS assignee_organization,  -- ->> extracts text (not ->)
    r.inventors,
    NULL::INTEGER AS num_claims,
    r.family_id,
    EXISTS (
        SELECT 1 FROM unnest(COALESCE(r.ipc_codes, '{}')) AS code
        WHERE code LIKE 'A61K%' OR code LIKE 'A61P%'
           OR code LIKE 'C07D%' OR code LIKE 'C07K%'
    ) AS is_pharma_related,
    FALSE AS processed_to_silver,
    r._loaded_at AS ingested_at
FROM raw.epo_patents r
WHERE r.publication_id IS NOT NULL
  AND @incremental_time_filter(_loaded_at)
```

### Acceptance Criteria

- AC-1: Model compiles and EPO records flow to bronze.
- AC-2: `publication_id` is mapped to `patent_number` for silver compatibility.
- AC-3: IPC codes preserved in `ipc_codes` column (not mapped to cpc_codes).

---

## bronze.uspto_trademarks (NEW)

**File**: `src/dk_data/sqlmesh/models/molecules/bronze/uspto_trademarks.sql`
**Kind**: INCREMENTAL_BY_TIME_RANGE (time_column: ingested_at, lookback: 7)
**Cron**: @weekly
**Grain**: serial_number
**Audits**: not_null(columns := (serial_number)), unique_values(columns := (serial_number))

### Output Schema

```sql
SELECT
    gen_random_uuid() AS id,
    r.serial_number,
    r.mark_element,
    r.mark_type,
    r.status,
    r.status_date,
    r.filing_date,
    r.registration_number,
    r.registration_date,
    CASE
        WHEN r.nice_classes IS NOT NULL
        THEN to_jsonb(r.nice_classes)
        ELSE NULL
    END AS nice_classes,
    r.owner_name,
    r.owner_entity_type,
    r.goods_and_services,
    5 = ANY(COALESCE(r.nice_classes, '{}')) AS is_pharma_related,
    FALSE AS processed_to_silver,
    r._loaded_at AS ingested_at
FROM raw.uspto_trademarks r
WHERE r.serial_number IS NOT NULL
  AND @incremental_time_filter(_loaded_at)
```

### Acceptance Criteria

- AC-1: Model compiles and raw USPTO trademark records flow to bronze.
- AC-2: `is_pharma_related` is TRUE when Nice class 5 is present.

---

## bronze.euipo_trademarks (NEW)

**File**: `src/dk_data/sqlmesh/models/molecules/bronze/euipo_trademarks.sql`
**Kind**: INCREMENTAL_BY_TIME_RANGE (time_column: ingested_at, lookback: 7)
**Cron**: @weekly
**Grain**: application_number
**Audits**: not_null(columns := (application_number)), unique_values(columns := (application_number))

### Output Schema

```sql
SELECT
    gen_random_uuid() AS id,
    r.application_number,
    r.mark_name,
    r.mark_kind,
    r.mark_feature,
    r.applicant_name,
    r.applicant_country,
    r.representative_name,
    r.status,
    r.filing_date,
    r.registration_date,
    r.expiry_date,
    CASE
        WHEN r.nice_classes IS NOT NULL
        THEN to_jsonb(r.nice_classes)
        ELSE NULL
    END AS nice_classes,
    r.goods_and_services,
    5 = ANY(COALESCE(r.nice_classes, '{}')) AS is_pharma_related,
    FALSE AS processed_to_silver,
    r._loaded_at AS ingested_at
FROM raw.euipo_trademarks r
WHERE r.application_number IS NOT NULL
  AND @incremental_time_filter(_loaded_at)
```

### Acceptance Criteria

- AC-1: Model compiles and raw EUIPO trademark records flow to bronze.
- AC-2: EUIPO-specific fields (mark_kind, mark_feature, expiry_date) are preserved.
