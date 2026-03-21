-- SQLMesh Model: Silver Patent Exclusivities
-- Unified patent + exclusivity data from Orange Book (NDA) and Purple Book (BLA)
-- Part of: 003-molecule-assessment-dashboard
--
-- Orange Book: NDA/ANDA products with explicit patent numbers and expiry dates
-- Purple Book: BLA products with real exclusivity dates from FDA Purple Book API
--   - Orphan exclusivity (7 years)
--   - BPCIA 12-year data exclusivity (derived from approval date)
--   - BPCIA 4-year biosimilar filing block (derived from approval date)
--   - First interchangeable exclusivity
--   - Reference product exclusivity

MODEL (
    name mol_silver.patent_exclusivities,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (application_number, patent_number, exclusivity_code)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (application_number, source))
    ),
    grain (application_number, patent_number, exclusivity_code)
);

-- Orange Book: explicit patents and exclusivities for NDA/ANDA small molecules
WITH orange_book_data AS (
    SELECT
        application_number,
        trade_name,
        ingredient AS generic_name,
        patent_number,
        patent_expiration AS patent_expiry_date,
        CASE
            WHEN drug_substance_patent THEN 'substance'
            WHEN drug_product_patent THEN 'product'
            ELSE patent_use_code
        END AS patent_type,
        exclusivity_code,
        exclusivity_date,
        'orange_book' AS source,
        'orange_book' AS source_book,
        FALSE AS is_biosimilar,
        NULL::BOOLEAN AS is_interchangeable,
        NULL::TEXT AS reference_product_bla,
        NULL::TEXT AS reference_product_name,
        NULL::DATE AS bpcia_data_exclusivity_end,
        NULL::DATE AS bpcia_biosimilar_filing_date,
        NULL::DATE AS orphan_exclusivity_end,
        NULL::DATE AS interchangeable_exclusivity_end,
        NOW() AS source_updated_at
    FROM mol_bronze.orange_book
    WHERE processed_to_silver = FALSE
      AND application_number IS NOT NULL
),

-- Purple Book: biologics with real exclusivity dates from FDA
purple_book_data AS (
    SELECT
        'BLA' || bla_number AS application_number,
        brand_name AS trade_name,
        generic_name,
        NULL::TEXT AS patent_number,
        NULL::DATE AS patent_expiry_date,
        'biologic' AS patent_type,
        CASE
            WHEN is_biosimilar AND is_interchangeable THEN 'BIO-IC'
            WHEN is_biosimilar THEN 'BIO-BS'
            ELSE 'BIO-REF'
        END AS exclusivity_code,
        -- Use orphan exclusivity if available, otherwise derive BPCIA 12-year
        CASE
            WHEN orphan_exclusivity_end IS NOT NULL
                AND orphan_exclusivity_end ~ '\w+ \d{2}, \d{4}'
            THEN TO_DATE(orphan_exclusivity_end, 'Month DD, YYYY')
            WHEN approval_date IS NOT NULL
                AND approval_date ~ '\w+ \d{2}, \d{4}'
            THEN TO_DATE(approval_date, 'Month DD, YYYY') + INTERVAL '12 years'
            ELSE NULL
        END::DATE AS exclusivity_date,
        'purple_book' AS source,
        'purple_book' AS source_book,
        is_biosimilar,
        is_interchangeable,
        reference_product_name AS reference_product_bla,
        reference_product_brand AS reference_product_name,
        -- BPCIA 12-year data exclusivity
        CASE
            WHEN approval_date IS NOT NULL
                AND approval_date ~ '\w+ \d{2}, \d{4}'
            THEN (TO_DATE(approval_date, 'Month DD, YYYY') + INTERVAL '12 years')::DATE
            ELSE NULL
        END AS bpcia_data_exclusivity_end,
        -- BPCIA 4-year biosimilar filing block
        CASE
            WHEN approval_date IS NOT NULL
                AND approval_date ~ '\w+ \d{2}, \d{4}'
            THEN (TO_DATE(approval_date, 'Month DD, YYYY') + INTERVAL '4 years')::DATE
            ELSE NULL
        END AS bpcia_biosimilar_filing_date,
        -- Orphan exclusivity (real date from Purple Book)
        CASE
            WHEN orphan_exclusivity_end IS NOT NULL
                AND orphan_exclusivity_end ~ '\w+ \d{2}, \d{4}'
            THEN TO_DATE(orphan_exclusivity_end, 'Month DD, YYYY')
            ELSE NULL
        END::DATE AS orphan_exclusivity_end,
        -- Interchangeable exclusivity
        CASE
            WHEN interchangeable_exclusivity_end IS NOT NULL
                AND interchangeable_exclusivity_end ~ '\w+ \d{2}, \d{4}'
            THEN TO_DATE(interchangeable_exclusivity_end, 'Month DD, YYYY')
            ELSE NULL
        END::DATE AS interchangeable_exclusivity_end,
        source_updated_at
    FROM mol_bronze.purple_book
    WHERE processed_to_silver = FALSE
      AND bla_number IS NOT NULL
      -- Deduplicate: take first product_number per BLA
      AND product_number = '001'
)

SELECT
    gen_random_uuid() AS id,
    NULL::UUID AS molecule_id,  -- entity linking fills this
    application_number,
    trade_name,
    patent_number,
    patent_expiry_date,
    patent_type,
    exclusivity_code,
    exclusivity_date,
    source,
    source_book,
    is_biosimilar,
    is_interchangeable,
    reference_product_bla,
    reference_product_name,
    bpcia_data_exclusivity_end,
    bpcia_biosimilar_filing_date,
    orphan_exclusivity_end,
    interchangeable_exclusivity_end,
    source_updated_at,
    NOW() AS created_at
FROM orange_book_data

UNION ALL

SELECT
    gen_random_uuid() AS id,
    NULL::UUID AS molecule_id,
    application_number,
    trade_name,
    patent_number,
    patent_expiry_date,
    patent_type,
    exclusivity_code,
    exclusivity_date,
    source,
    source_book,
    is_biosimilar,
    is_interchangeable,
    reference_product_bla,
    reference_product_name,
    bpcia_data_exclusivity_end,
    bpcia_biosimilar_filing_date,
    orphan_exclusivity_end,
    interchangeable_exclusivity_end,
    source_updated_at
FROM purple_book_data;
