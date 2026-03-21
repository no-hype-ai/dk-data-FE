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
        'drugbank' AS source,
        ingested_at AS source_updated_at
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
        NULL::JSONB AS ipc_codes,
        num_claims,
        is_pharma_related,
        NULL::TEXT AS family_id,
        'uspto_patents' AS source
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
        NULL::TEXT AS assignee_type,
        inventors,
        cpc_codes,
        NULL::JSONB AS ipc_codes,
        num_claims,
        is_pharma_related,
        NULL::TEXT AS family_id,
        'uspto_ci' AS source
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
        NULL::TEXT AS assignee_type,
        inventors,
        cpc_codes,
        ipc_codes,
        num_claims,
        is_pharma_related,
        family_id,
        'epo_ops' AS source
    FROM mol_bronze.epo_patents
    WHERE processed_to_silver = FALSE
      AND patent_number IS NOT NULL
),

-- Feature 015: Orange Book patents
orange_book_patents AS (
    SELECT
        patent_number,
        patent_title AS title,
        NULL::TEXT AS abstract,
        NULL::DATE AS grant_date,
        filing_date,
        assignee_organization AS assignee,
        NULL::TEXT AS assignee_type,
        NULL::JSONB AS inventors,
        NULL::JSONB AS cpc_codes,
        NULL::JSONB AS ipc_codes,
        NULL::INTEGER AS num_claims,
        is_pharma_related,
        NULL::TEXT AS family_id,
        'orange_book' AS source
    FROM mol_bronze.orange_book
    WHERE processed_to_silver = FALSE
      AND patent_number IS NOT NULL
),

-- Combine all sources
-- inchi_key is propagated from DrugBank (the only source with structure data)
-- to enable molecule_id resolution via mol_silver.molecules.
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
        NULL::TEXT AS inchi_key,
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
        NULL::TEXT AS inchi_key,
        source,
        NOW() AS source_updated_at
    FROM orange_book_patents
),

-- Deduplicate: one row per patent_number, prefer DrugBank then USPTO
deduped AS (
    SELECT DISTINCT ON (patent_number) *
    FROM combined
    ORDER BY patent_number,
        CASE source
            WHEN 'drugbank' THEN 1
            WHEN 'uspto_patents' THEN 2
            WHEN 'uspto_ci' THEN 3
            WHEN 'epo_ops' THEN 4
            WHEN 'orange_book' THEN 5
        END
)

SELECT
    gen_random_uuid() AS id,
    d.patent_number,
    NULL::TEXT AS application_number,
    d.title,
    d.abstract,
    d.filing_date,
    d.grant_date,
    d.expiry_date,
    d.assignee,
    d.assignee_type,
    NULL::TEXT AS assignee_normalized,
    d.inventors,
    NULL::TEXT AS patent_type,
    d.country,
    d.cpc_codes,
    d.ipc_codes,
    d.num_claims,
    d.family_id,
    CASE
        WHEN d.expiry_date < CURRENT_DATE THEN 'expired'
        WHEN d.grant_date IS NULL THEN 'pending'
        ELSE 'active'
    END AS status,
    d.is_pharma_related,
    d.pediatric_extension,
    CASE WHEN d.pediatric_extension = TRUE THEN 180 ELSE 0 END AS extension_days,
    NULL::JSONB AS related_patents,
    -- Resolve molecule_id: DrugBank records have inchi_key for exact match;
    -- other sources fall back to name matching via molecule_aliases.
    COALESCE(
        m_ik.molecule_id,
        m_alias.molecule_id
    ) AS molecule_id,
    d.source,
    d.source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM deduped d
LEFT JOIN mol_silver.molecules m_ik
    ON d.inchi_key IS NOT NULL AND d.inchi_key = m_ik.inchi_key
LEFT JOIN mol_silver.molecule_aliases ma
    ON d.inchi_key IS NULL
    AND d.molecule_name IS NOT NULL
    AND LOWER(REGEXP_REPLACE(d.molecule_name, '[^a-zA-Z0-9]', '', 'g')) = ma.alias_name_normalized
LEFT JOIN mol_silver.molecules m_alias
    ON m_alias.molecule_id = ma.molecule_id
