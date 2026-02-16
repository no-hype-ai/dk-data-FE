-- SQLMesh Model: Silver Patents
-- Normalized patent data from DrugBank, USPTO Patents, USPTO CI, and EPO OPS
-- Part of: 014-uspto-euipo-model-datasource (extended from 012)

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

-- USPTO Patents (PatentsView direct)
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

-- USPTO CI (query-scoped)
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

-- EPO Patents (European)
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
