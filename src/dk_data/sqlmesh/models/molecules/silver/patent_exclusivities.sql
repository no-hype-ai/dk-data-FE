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

-- Entity linking: LEFT JOIN mol_silver.molecules on generic_name, trade_name as fallback.
-- FULL refresh ensures molecule_id is always current when new molecules are added.

MODEL (
    name mol_silver.patent_exclusivities,
    kind FULL,
    cron '@weekly',
    audits (
        not_null(columns := (application_number, source))
    )
);

-- Orange Book: explicit patents and exclusivities for NDA/ANDA small molecules
WITH orange_book_data AS (
    SELECT
        application_number,
        product_number,
        trade_name,
        ingredient AS generic_name,
        applicant,
        strength,
        df_route                    AS dosage_form,
        NULL::TEXT                  AS route,
        approval_date::TEXT AS approval_date,
        te_code,
        rld,
        patent_number,
        patent_expiration AS patent_expiry_date,
        drug_substance_patent,
        drug_product_patent,
        patent_use_code,
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
        -- Purple Book specific (NULL for Orange Book)
        NULL::TEXT AS license_type,
        NULL::TEXT AS presentation,
        NULL::TEXT AS status,
        NULL::TEXT AS center,
        NULL::DATE AS first_licensure_date,
        NULL::DATE AS exclusivity_expiry_date,
        NULL::DATE AS ref_product_exclusivity_end,
        NULL::DATE AS interchangeable_approval_date,
        NULL::BOOLEAN AS has_patent_list,
        -- Additional bronze domain columns
        rs,
        drug_type,
        ingested_at,
        NOW() AS source_updated_at
    FROM mol_bronze.orange_book
    WHERE application_number IS NOT NULL
    -- NOTE: FULL refresh — do NOT filter on processed_to_silver here.
    -- FULL models rebuild entirely each run; a processed_to_silver = FALSE filter
    -- would return empty results once all rows are marked as processed.
),

-- Purple Book: biologics with real exclusivity dates from FDA
purple_book_data AS (
    SELECT
        'BLA' || bla_number AS application_number,
        product_number,
        brand_name AS trade_name,
        generic_name,
        applicant,
        strength,
        dosage_form,
        route,
        approval_date::TEXT AS approval_date,
        NULL::TEXT AS te_code,
        NULL::BOOLEAN AS rld,
        NULL::TEXT AS patent_number,
        NULL::DATE AS patent_expiry_date,
        NULL::BOOLEAN AS drug_substance_patent,
        NULL::BOOLEAN AS drug_product_patent,
        NULL::TEXT AS patent_use_code,
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
        -- Purple Book specific columns
        license_type,
        presentation,
        status,
        center,
        CASE
            WHEN first_licensure_date IS NOT NULL
                AND first_licensure_date ~ '\w+ \d{2}, \d{4}'
            THEN TO_DATE(first_licensure_date, 'Month DD, YYYY')
            ELSE NULL
        END::DATE AS first_licensure_date,
        CASE
            WHEN exclusivity_expiry_date IS NOT NULL
                AND exclusivity_expiry_date ~ '\w+ \d{2}, \d{4}'
            THEN TO_DATE(exclusivity_expiry_date, 'Month DD, YYYY')
            ELSE NULL
        END::DATE AS exclusivity_expiry_date,
        CASE
            WHEN ref_product_exclusivity_end IS NOT NULL
                AND ref_product_exclusivity_end ~ '\w+ \d{2}, \d{4}'
            THEN TO_DATE(ref_product_exclusivity_end, 'Month DD, YYYY')
            ELSE NULL
        END::DATE AS ref_product_exclusivity_end,
        CASE
            WHEN interchangeable_approval_date IS NOT NULL
                AND interchangeable_approval_date ~ '\w+ \d{2}, \d{4}'
            THEN TO_DATE(interchangeable_approval_date, 'Month DD, YYYY')
            ELSE NULL
        END::DATE AS interchangeable_approval_date,
        has_patent_list,
        -- Additional bronze domain columns (Orange Book specific, NULL for Purple Book)
        NULL::BOOLEAN AS rs,
        NULL::TEXT AS drug_type,
        ingested_at,
        source_updated_at
    FROM mol_bronze.purple_book
    WHERE bla_number IS NOT NULL
    -- NOTE: FULL refresh — do NOT filter on processed_to_silver here.
      -- Deduplicate: take first product_number per BLA
      AND product_number = '001'
),

all_data AS (
    SELECT
        gen_random_uuid() AS id,
        application_number, product_number, trade_name, generic_name, applicant,
        strength, dosage_form, route, approval_date, te_code, rld, patent_number,
        patent_expiry_date, drug_substance_patent, drug_product_patent, patent_use_code,
        patent_type, exclusivity_code, exclusivity_date, source, source_book,
        is_biosimilar, is_interchangeable, reference_product_bla, reference_product_name,
        bpcia_data_exclusivity_end, bpcia_biosimilar_filing_date, orphan_exclusivity_end,
        interchangeable_exclusivity_end, license_type, presentation, status, center,
        first_licensure_date, exclusivity_expiry_date, ref_product_exclusivity_end,
        interchangeable_approval_date, has_patent_list, rs, drug_type, ingested_at,
        source_updated_at, NOW() AS created_at
    FROM orange_book_data

    UNION ALL

    SELECT
        gen_random_uuid() AS id,
        application_number, product_number, trade_name, generic_name, applicant,
        strength, dosage_form, route, approval_date, te_code, rld, patent_number,
        patent_expiry_date, drug_substance_patent, drug_product_patent, patent_use_code,
        patent_type, exclusivity_code, exclusivity_date, source, source_book,
        is_biosimilar, is_interchangeable, reference_product_bla, reference_product_name,
        bpcia_data_exclusivity_end, bpcia_biosimilar_filing_date, orphan_exclusivity_end,
        interchangeable_exclusivity_end, license_type, presentation, status, center,
        first_licensure_date, exclusivity_expiry_date, ref_product_exclusivity_end,
        interchangeable_approval_date, has_patent_list, rs, drug_type, ingested_at,
        source_updated_at, NOW() AS created_at
    FROM purple_book_data
)

SELECT
    d.id,
    COALESCE(m_gen.molecule_id, m_trade.molecule_id) AS molecule_id,
    d.application_number, d.product_number, d.trade_name, d.generic_name, d.applicant,
    d.strength, d.dosage_form, d.route, d.approval_date, d.te_code, d.rld,
    d.patent_number, d.patent_expiry_date, d.drug_substance_patent, d.drug_product_patent,
    d.patent_use_code, d.patent_type, d.exclusivity_code, d.exclusivity_date,
    d.source, d.source_book, d.is_biosimilar, d.is_interchangeable,
    d.reference_product_bla, d.reference_product_name, d.bpcia_data_exclusivity_end,
    d.bpcia_biosimilar_filing_date, d.orphan_exclusivity_end, d.interchangeable_exclusivity_end,
    d.license_type, d.presentation, d.status, d.center, d.first_licensure_date,
    d.exclusivity_expiry_date, d.ref_product_exclusivity_end, d.interchangeable_approval_date,
    d.has_patent_list, d.rs, d.drug_type, d.ingested_at, d.source_updated_at, d.created_at
FROM all_data d
LEFT JOIN mol_silver.molecules m_gen
       ON LOWER(m_gen.canonical_name) = LOWER(d.generic_name)
LEFT JOIN mol_silver.molecules m_trade
       ON m_gen.molecule_id IS NULL
      AND d.trade_name IS NOT NULL
      AND LOWER(m_trade.canonical_name) = LOWER(d.trade_name);
