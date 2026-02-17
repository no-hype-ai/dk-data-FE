# Contract: Silver SQLMesh Models

**Feature**: 014-uspto-euipo-model-datasource
**Date**: 2026-02-16

## silver.patents (MODIFY — extend to 4 sources)

**File**: `src/dk_data/sqlmesh/models/molecules/silver/patents.sql`
**Kind**: INCREMENTAL_BY_UNIQUE_KEY (unique_key: patent_number, when_matched_update_all: TRUE)
**Cron**: @monthly
**Grain**: patent_number
**Audits**: not_null(columns := (patent_number)), unique_values(columns := (patent_number))

### Change Required

**Structural refactor** (not just additive): The current model has 2 CTEs (`drugbank_patents` + `enriched`) reading only from `bronze.drugbank`. This must be replaced with a multi-source UNION ALL pattern: 4 source CTEs (`drugbank_patents`, `uspto_patents`, `uspto_ci`, `epo_patents`) + 1 `combined` CTE for the UNION ALL + `DISTINCT ON (patent_number)` deduplication with source priority. The existing `enriched` CTE is removed in favor of the unified output SELECT.

### Output Schema (extended)

```sql
WITH drugbank_patents AS (
    -- existing CTE (unchanged)
    SELECT
        drugbank_id, inchi_key, name AS drug_name,
        patent->>'number' AS patent_number,
        patent->>'country' AS country,
        (patent->>'approved')::DATE AS grant_date,
        (patent->>'expires')::DATE AS expiry_date,
        (patent->>'pediatric_extension')::BOOLEAN AS pediatric_extension,
        source, source_updated_at, created_at
    FROM bronze.drugbank,
         jsonb_array_elements(patents) AS patent
    WHERE processed_to_silver = FALSE
      AND patents IS NOT NULL
      AND jsonb_array_length(patents) > 0
      AND patent->>'number' IS NOT NULL
),

-- NEW: USPTO Patents
uspto_patents AS (
    SELECT
        patent_number,
        patent_title AS title,
        patent_abstract AS abstract,
        patent_date AS grant_date,
        NULL::DATE AS filing_date,
        assignee_organization AS assignee,
        inventors,
        cpc_codes,
        num_claims,
        'uspto_patents' AS source
    FROM bronze.uspto_patents
    WHERE processed_to_silver = FALSE
      AND patent_number IS NOT NULL
),

-- NEW: USPTO CI
uspto_ci AS (
    SELECT
        patent_number,
        patent_title AS title,
        patent_abstract AS abstract,
        patent_date AS grant_date,
        NULL::DATE AS filing_date,
        assignee_organization AS assignee,
        inventors,
        cpc_codes,
        num_claims,
        'uspto_ci' AS source
    FROM bronze.uspto_ci
    WHERE processed_to_silver = FALSE
      AND patent_number IS NOT NULL
),

-- NEW: EPO Patents
epo_patents AS (
    SELECT
        patent_number,
        patent_title AS title,
        patent_abstract AS abstract,
        patent_date AS grant_date,
        NULL::DATE AS filing_date,
        assignee_organization AS assignee,
        inventors,
        ipc_codes AS cpc_codes,
        num_claims,
        'epo_ops' AS source
    FROM bronze.epo_patents
    WHERE processed_to_silver = FALSE
      AND patent_number IS NOT NULL
),

-- Combine all sources
combined AS (
    -- DrugBank records (existing format)
    SELECT
        patent_number, NULL AS title, NULL AS abstract,
        NULL::DATE AS filing_date, grant_date, expiry_date,
        NULL AS assignee, NULL::JSONB AS inventors,
        NULL::JSONB AS cpc_codes, NULL::INTEGER AS num_claims,
        pediatric_extension, country,
        drug_name AS molecule_name,
        'drugbank' AS source,
        source_updated_at
    FROM drugbank_patents

    UNION ALL

    SELECT
        patent_number, title, abstract,
        filing_date, grant_date, NULL::DATE AS expiry_date,
        assignee, inventors,
        cpc_codes, num_claims,
        NULL::BOOLEAN AS pediatric_extension, 'US' AS country,
        NULL AS molecule_name,
        source,
        NOW() AS source_updated_at
    FROM uspto_patents

    UNION ALL

    SELECT
        patent_number, title, abstract,
        filing_date, grant_date, NULL::DATE AS expiry_date,
        assignee, inventors,
        cpc_codes, num_claims,
        NULL::BOOLEAN AS pediatric_extension, 'US' AS country,
        NULL AS molecule_name,
        source,
        NOW() AS source_updated_at
    FROM uspto_ci

    UNION ALL

    SELECT
        patent_number, title, abstract,
        filing_date, grant_date, NULL::DATE AS expiry_date,
        assignee, inventors,
        cpc_codes, num_claims,
        NULL::BOOLEAN AS pediatric_extension, 'EP' AS country,
        NULL AS molecule_name,
        source,
        NOW() AS source_updated_at
    FROM epo_patents
)

SELECT DISTINCT ON (patent_number)
    gen_random_uuid() AS id,
    patent_number,
    NULL::TEXT AS application_number,
    title,
    abstract,
    filing_date,
    grant_date,
    expiry_date,
    assignee,
    NULL::TEXT AS assignee_normalized,
    inventors,
    NULL::TEXT AS patent_type,
    country,
    cpc_codes,
    NULL::JSONB AS ipc_codes,
    CASE
        WHEN expiry_date < CURRENT_DATE THEN 'expired'
        WHEN grant_date IS NULL THEN 'pending'
        ELSE 'active'
    END AS status,
    pediatric_extension,
    CASE WHEN pediatric_extension = TRUE THEN 180 ELSE 0 END AS extension_days,
    NULL::JSONB AS related_patents,
    NULL::UUID AS molecule_id,
    source,
    source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM combined
ORDER BY patent_number,
    CASE source
        WHEN 'drugbank' THEN 1
        WHEN 'uspto_patents' THEN 2
        WHEN 'uspto_ci' THEN 3
        WHEN 'epo_ops' THEN 4
    END
```

### Source Priority Order

1. `drugbank` — highest priority (includes molecule linkage, expiry dates)
2. `uspto_patents` — credential-gated, more complete
3. `uspto_ci` — public, search-scoped
4. `epo_ops` — European patents

### Acceptance Criteria

- AC-1: `silver.patents` contains records from all 4 bronze sources.
- AC-2: Duplicate patent_numbers are resolved with source priority (drugbank wins).
- AC-3: Existing DrugBank-only behavior is preserved (no regression).
- AC-4: `source` column correctly identifies origin.

---

## silver.trademarks (NEW)

**File**: `src/dk_data/sqlmesh/models/molecules/silver/trademarks.sql`
**Kind**: INCREMENTAL_BY_UNIQUE_KEY (unique_key: (trademark_identifier, source), when_matched_update_all: TRUE)
**Cron**: @weekly
**Grain**: (trademark_identifier, source)
**Audits**: not_null(columns := (trademark_identifier)), not_null(columns := (source))

### Output Schema

```sql
WITH uspto AS (
    SELECT
        serial_number AS trademark_identifier,
        mark_element AS mark_name,
        mark_type,
        status,
        filing_date,
        registration_date,
        NULL::DATE AS expiry_date,
        owner_name,
        nice_classes,
        goods_and_services,
        is_pharma_related,
        'uspto_trademarks' AS source,
        ingested_at AS source_updated_at
    FROM bronze.uspto_trademarks
    WHERE processed_to_silver = FALSE
),

euipo AS (
    SELECT
        application_number AS trademark_identifier,
        mark_name,
        mark_kind AS mark_type,
        status,
        filing_date,
        registration_date,
        expiry_date,
        applicant_name AS owner_name,
        nice_classes,
        goods_and_services,
        is_pharma_related,
        'euipo_trademarks' AS source,
        ingested_at AS source_updated_at
    FROM bronze.euipo_trademarks
    WHERE processed_to_silver = FALSE
),

combined AS (
    SELECT * FROM uspto
    UNION ALL
    SELECT * FROM euipo
)

SELECT DISTINCT ON (trademark_identifier, source)
    gen_random_uuid() AS id,
    trademark_identifier,
    mark_name,
    mark_type,
    status,
    filing_date,
    registration_date,
    expiry_date,
    owner_name,
    nice_classes,
    goods_and_services,
    is_pharma_related,
    NULL::UUID AS molecule_id,  -- To be linked by entity resolution (future)
    source,
    source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM combined
ORDER BY trademark_identifier, source, source_updated_at DESC
```

### Deduplication Strategy

- Within-registry only: `DISTINCT ON (trademark_identifier, source)`
- No cross-registry dedup (same mark in USPTO + EUIPO = 2 rows)
- Latest ingestion wins within same registry

### Acceptance Criteria

- AC-1: `silver.trademarks` contains records from both USPTO and EUIPO.
- AC-2: `source` column distinguishes US from EU trademarks.
- AC-3: No cross-registry deduplication occurs (both entries preserved).
- AC-4: Grain is (trademark_identifier, source) composite key.
