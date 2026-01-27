-- SQLMesh Model: Silver Patents
-- Normalized patent data from DrugBank and Orange Book
-- Part of: 012-dk-data-platform

MODEL (
    name silver.patents,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key patent_number,
        when_matched_update_all TRUE
    ),
    cron '@monthly',
    audits (
        not_null(columns := (patent_number)),
        unique_values(columns := (patent_number))
    ),
    grain patent_number
);

-- Extract patent information from DrugBank drug records
WITH drugbank_patents AS (
    SELECT
        drugbank_id,
        inchi_key,
        name AS drug_name,
        patent->>'number' AS patent_number,
        patent->>'country' AS country,
        (patent->>'approved')::DATE AS grant_date,
        (patent->>'expires')::DATE AS expiry_date,
        (patent->>'pediatric_extension')::BOOLEAN AS pediatric_extension,
        source,
        source_updated_at,
        created_at
    FROM bronze.drugbank,
         jsonb_array_elements(patents) AS patent
    WHERE
        processed_to_silver = FALSE
        AND patents IS NOT NULL
        AND jsonb_array_length(patents) > 0
        AND patent->>'number' IS NOT NULL
),

-- Deduplicate and enrich
enriched AS (
    SELECT DISTINCT ON (patent_number)
        patent_number,
        country,
        grant_date,
        expiry_date,
        -- Determine status
        CASE
            WHEN expiry_date < CURRENT_DATE THEN 'expired'
            WHEN grant_date IS NULL THEN 'pending'
            ELSE 'active'
        END AS status,
        pediatric_extension,
        -- Calculate extension days
        CASE
            WHEN pediatric_extension = TRUE THEN 180
            ELSE 0
        END AS extension_days,
        drugbank_id,
        drug_name AS molecule_name,
        source,
        source_updated_at,
        created_at
    FROM drugbank_patents
    ORDER BY patent_number, source_updated_at DESC
)

SELECT
    gen_random_uuid() AS id,
    patent_number,
    NULL::TEXT AS application_number,
    NULL::TEXT AS title,
    NULL::TEXT AS abstract,
    NULL::DATE AS filing_date,
    grant_date,
    expiry_date,
    NULL::TEXT AS assignee,
    NULL::TEXT AS assignee_normalized,
    NULL::JSONB AS inventors,
    NULL::TEXT AS patent_type,
    country,
    NULL::JSONB AS cpc_codes,
    NULL::JSONB AS ipc_codes,
    status,
    pediatric_extension,
    extension_days,
    NULL::JSONB AS related_patents,
    NULL::UUID AS molecule_id,  -- To be linked by entity resolution
    'drugbank' AS source,
    source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM enriched;


-- Post-insert would mark Bronze records as processed
-- But since we extract from patents array, we track differently
