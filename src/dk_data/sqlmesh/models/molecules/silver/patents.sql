-- SQLMesh Model: Silver Patents
-- Normalized patent data from DrugBank, USPTO Patents, USPTO CI, and EPO OPS
-- Part of: 014-uspto-euipo-model-datasource (extended from 012)

MODEL (
    name mol_silver.patents,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key patent_number
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
    FROM mol_bronze.drugbank,
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
        filing_date,
        assignee_organization AS assignee,
        assignee_type,
        inventors,
        cpc_codes,
        NULL::JSONB AS ipc_codes,        -- USPTO does not expose IPC codes in PatentsView
        num_claims,
        is_pharma_related,
        NULL::TEXT AS family_id,         -- family_id not tracked in PatentsView schema
        patent_type,
        NULL::TEXT AS application_number, -- not exposed in PatentsView bulk data
        'uspto'::TEXT AS source
    FROM mol_bronze.uspto_patents
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
        filing_date,
        assignee_organization AS assignee,
        NULL::TEXT AS assignee_type,     -- not in USPTO CI query schema
        inventors,
        cpc_codes,
        NULL::JSONB AS ipc_codes,        -- not in USPTO CI schema
        num_claims,
        is_pharma_related,
        NULL::TEXT AS family_id,         -- not tracked in USPTO CI
        NULL::TEXT AS patent_type,       -- not in USPTO CI schema
        NULL::TEXT AS application_number, -- not in USPTO CI schema
        'uspto_ci'::TEXT AS source
    FROM mol_bronze.uspto_ci
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
        filing_date,
        assignee_organization AS assignee,
        NULL::TEXT AS assignee_type,     -- EPO uses different assignee classification
        inventors,
        cpc_codes,
        ipc_codes,
        num_claims,
        is_pharma_related,
        family_id,
        NULL::TEXT AS patent_type,       -- EPO uses different type taxonomy
        NULL::TEXT AS application_number, -- not exposed in EPO OPS schema
        'epo'::TEXT AS source
    FROM mol_bronze.epo_patents
    WHERE processed_to_silver = FALSE
      AND patent_number IS NOT NULL
),

-- Feature 015: Orange Book patents
orange_book_patents AS (
    SELECT
        patent_number,
        trade_name AS title,
        NULL::TEXT AS abstract,          -- not in Orange Book
        NULL::DATE AS grant_date,        -- not in Orange Book (only expiry date)
        NULL::DATE AS filing_date,       -- not in Orange Book
        applicant AS assignee,
        NULL::TEXT AS assignee_type,     -- not in Orange Book
        NULL::JSONB AS inventors,        -- not in Orange Book
        NULL::JSONB AS cpc_codes,        -- not in Orange Book
        NULL::JSONB AS ipc_codes,        -- not in Orange Book
        NULL::INTEGER AS num_claims,     -- not in Orange Book
        TRUE AS is_pharma_related,
        NULL::TEXT AS family_id,         -- not in Orange Book
        NULL::TEXT AS patent_type,       -- not in Orange Book
        application_number,              -- from Orange Book appl_no column
        'orange_book'::TEXT AS source
    FROM mol_bronze.orange_book
    WHERE processed_to_silver = FALSE
      AND patent_number IS NOT NULL
),

-- Combine all sources
combined AS (
    -- DrugBank records (existing format)
    SELECT
        patent_number, NULL AS title, NULL AS abstract,
        NULL::DATE AS filing_date, grant_date, expiry_date,
        NULL AS assignee, NULL::TEXT AS assignee_type,
        NULL::JSONB AS inventors,
        NULL::JSONB AS cpc_codes, NULL::JSONB AS ipc_codes,
        NULL::INTEGER AS num_claims,
        NULL::BOOLEAN AS is_pharma_related,
        NULL::TEXT AS family_id,
        pediatric_extension, country,
        drug_name AS molecule_name,
        NULL::TEXT AS patent_type,       -- not tracked in DrugBank patent records
        NULL::TEXT AS application_number, -- not tracked in DrugBank patent records
        inchi_key,
        'drugbank' AS source,
        source_updated_at
    FROM drugbank_patents

    UNION ALL

    SELECT
        patent_number, title, abstract,
        filing_date, grant_date, NULL::DATE AS expiry_date,
        assignee, assignee_type, inventors,
        cpc_codes, ipc_codes, num_claims,
        is_pharma_related, family_id,
        NULL::BOOLEAN AS pediatric_extension, 'US' AS country,
        NULL AS molecule_name,
        patent_type,
        application_number,
        NULL::TEXT AS inchi_key,         -- not linked at patent level in PatentsView
        source,
        NOW() AS source_updated_at
    FROM uspto_patents

    UNION ALL

    SELECT
        patent_number, title, abstract,
        filing_date, grant_date, NULL::DATE AS expiry_date,
        assignee, assignee_type, inventors,
        cpc_codes, ipc_codes, num_claims,
        is_pharma_related, family_id,
        NULL::BOOLEAN AS pediatric_extension, 'US' AS country,
        NULL AS molecule_name,
        patent_type,
        application_number,
        NULL::TEXT AS inchi_key,
        source,
        NOW() AS source_updated_at
    FROM uspto_ci

    UNION ALL

    SELECT
        patent_number, title, abstract,
        filing_date, grant_date, NULL::DATE AS expiry_date,
        assignee, assignee_type, inventors,
        cpc_codes, ipc_codes, num_claims,
        is_pharma_related, family_id,
        NULL::BOOLEAN AS pediatric_extension, 'EP' AS country,
        NULL AS molecule_name,
        patent_type,
        application_number,
        NULL::TEXT AS inchi_key,
        source,
        NOW() AS source_updated_at
    FROM epo_patents

    UNION ALL

    -- Feature 015: Orange Book
    SELECT
        patent_number, title, abstract,
        filing_date, grant_date, NULL::DATE AS expiry_date,
        assignee, assignee_type, inventors,
        cpc_codes, ipc_codes, num_claims,
        is_pharma_related, family_id,
        NULL::BOOLEAN AS pediatric_extension, 'US' AS country,
        NULL AS molecule_name,
        patent_type,
        application_number,
        NULL::TEXT AS inchi_key,
        source,
        NOW() AS source_updated_at
    FROM orange_book_patents
)

SELECT DISTINCT ON (patent_number)
    gen_random_uuid() AS id,
    patent_number,
    application_number,
    title,
    abstract,
    filing_date,
    grant_date,
    expiry_date,
    assignee,
    assignee_type,
    NULL::TEXT AS assignee_normalized,   -- requires entity resolution, deferred
    inventors,
    patent_type,
    country,
    cpc_codes,
    ipc_codes,
    num_claims,
    family_id,
    CASE
        WHEN expiry_date < CURRENT_DATE THEN 'expired'
        WHEN grant_date IS NULL THEN 'pending'
        ELSE 'active'
    END AS status,
    is_pharma_related,
    pediatric_extension,
    CASE WHEN pediatric_extension = TRUE THEN 180 ELSE 0 END AS extension_days,
    NULL::JSONB AS related_patents,      -- requires patent citation network data (not ingested)
    m.molecule_id,
    combined.source,
    combined.source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM combined
LEFT JOIN mol_silver.molecules m ON combined.inchi_key IS NOT NULL
    AND combined.inchi_key = m.inchi_key
ORDER BY patent_number,
    CASE combined.source
        WHEN 'drugbank' THEN 1
        WHEN 'uspto_patents' THEN 2
        WHEN 'uspto_ci' THEN 3
        WHEN 'epo_ops' THEN 4
        WHEN 'orange_book' THEN 5
    END
