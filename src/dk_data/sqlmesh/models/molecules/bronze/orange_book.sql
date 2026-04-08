-- SQLMesh Model: Bronze Orange Book
-- Transforms raw FDA Orange Book JSONB API responses into typed bronze layer
-- Part of DK Molecule Data Platform (012-dk-data-platform)
--
-- Source table: mol_raw.orange_book (JSONB response_body, see migration 062_mol_source_raw_tables.sql)
--
-- FDA Orange Book API field names (products section):
--   appl_no          -> application_number
--   product_no       -> product_number
--   ingredient       -> ingredient  (active_ingredient / INN)
--   trade_name       -> trade_name
--   applicant        -> applicant   (short applicant code)
--   applicant_full_name -> applicant_full_name
--   strength         -> strength
--   df_route         -> df_route    (dosage form + route combined, e.g. "TABLET;ORAL")
--   approval_date    -> approval_date (DATE, format "Jan 1, 1984" or YYYY-MM-DD)
--   te_code          -> te_code     (therapeutic equivalence code)
--   rld              -> rld         (reference listed drug flag: "Yes"/"No")
--   rs               -> rs          (reference standard: "Yes"/"No")
--   type             -> type        (RX / OTC / DISCN)
--
-- Patents section fields:
--   appl_no              -> application_number (join key)
--   product_no           -> product_number     (join key)
--   patent_no            -> patent_number
--   patent_expire_date_text -> patent_expiration (text date, cast where ISO)
--   drug_substance_flag  -> drug_substance_patent (Y/N -> BOOLEAN)
--   drug_product_flag    -> drug_product_patent   (Y/N -> BOOLEAN)
--   patent_use_code      -> patent_use_code
--
-- Exclusivity section fields:
--   exclusivity_code -> exclusivity_code
--   exclusivity_date -> exclusivity_date (DATE)

MODEL (
    name mol_bronze.orange_book,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (application_number, product_number, patent_number)
    ),
    cron '@weekly',
    grain (application_number, product_number, patent_number),
    audits (
        not_null(columns := (application_number))
    )
);

SELECT
    uuid_generate_v4() AS id,
    r.id AS raw_id,

    -- Drug identification (FDA Orange Book uses appl_no / Appl_No)
    COALESCE(
        r.response_body->>'appl_no',
        r.response_body->>'Appl_No',
        r.response_body->>'application_number'
    )::TEXT AS application_number,
    COALESCE(
        r.response_body->>'product_no',
        r.response_body->>'Product_No',
        r.response_body->>'product_number',
        '001'
    )::TEXT AS product_number,
    -- ingredient = active ingredient / INN
    COALESCE(
        r.response_body->>'ingredient',
        r.response_body->>'Ingredient',
        r.response_body->>'active_ingredient'
    )::TEXT AS ingredient,
    COALESCE(
        r.response_body->>'trade_name',
        r.response_body->>'Trade_Name'
    )::TEXT AS trade_name,
    -- applicant: prefer full name, fall back to short code
    COALESCE(
        r.response_body->>'applicant_full_name',
        r.response_body->>'Applicant_Full_Name',
        r.response_body->>'applicant',
        r.response_body->>'Applicant'
    )::TEXT AS applicant,

    -- Drug details
    COALESCE(
        r.response_body->>'strength',
        r.response_body->>'Strength'
    )::TEXT AS strength,
    -- df_route is the combined dosage form + route field in the FDA API
    COALESCE(
        r.response_body->>'df_route',
        r.response_body->>'DF_Route',
        r.response_body->>'dosage_form'
    )::TEXT AS df_route,
    -- drug type: RX, OTC, DISCN
    COALESCE(
        r.response_body->>'type',
        r.response_body->>'Type'
    )::TEXT AS drug_type,

    -- Approval info
    CASE
        WHEN r.response_body->>'approval_date' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'approval_date')::DATE
        WHEN r.response_body->>'Approval_Date' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'Approval_Date')::DATE
        ELSE NULL
    END AS approval_date,
    COALESCE(
        r.response_body->>'te_code',
        r.response_body->>'TE_Code'
    )::TEXT AS te_code,
    -- rld: "Yes"/"No" flag
    CASE
        WHEN UPPER(COALESCE(r.response_body->>'rld', r.response_body->>'RLD')) IN ('YES', 'Y') THEN TRUE
        WHEN UPPER(COALESCE(r.response_body->>'rld', r.response_body->>'RLD')) IN ('NO', 'N')  THEN FALSE
        ELSE NULL
    END AS rld,
    -- rs: reference standard flag
    CASE
        WHEN UPPER(COALESCE(r.response_body->>'rs', r.response_body->>'RS')) IN ('YES', 'Y') THEN TRUE
        WHEN UPPER(COALESCE(r.response_body->>'rs', r.response_body->>'RS')) IN ('NO', 'N')  THEN FALSE
        ELSE NULL
    END AS rs,

    -- Patent info (patent_no / Patent_No)
    COALESCE(
        r.response_body->>'patent_no',
        r.response_body->>'Patent_No',
        r.response_body->>'patent_number'
    )::TEXT AS patent_number,
    CASE
        WHEN r.response_body->>'patent_expire_date_text' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'patent_expire_date_text')::DATE
        WHEN r.response_body->>'Patent_Expire_Date_Text' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'Patent_Expire_Date_Text')::DATE
        ELSE NULL
    END AS patent_expiration,
    CASE
        WHEN COALESCE(r.response_body->>'drug_substance_flag', r.response_body->>'Drug_Substance_Flag') = 'Y' THEN TRUE
        WHEN COALESCE(r.response_body->>'drug_substance_flag', r.response_body->>'Drug_Substance_Flag') = 'N' THEN FALSE
        ELSE NULL
    END AS drug_substance_patent,
    CASE
        WHEN COALESCE(r.response_body->>'drug_product_flag', r.response_body->>'Drug_Product_Flag') = 'Y' THEN TRUE
        WHEN COALESCE(r.response_body->>'drug_product_flag', r.response_body->>'Drug_Product_Flag') = 'N' THEN FALSE
        ELSE NULL
    END AS drug_product_patent,
    COALESCE(
        r.response_body->>'patent_use_code',
        r.response_body->>'Patent_Use_Code'
    )::TEXT AS patent_use_code,

    -- Exclusivity info
    COALESCE(
        r.response_body->>'exclusivity_code',
        r.response_body->>'Exclusivity_Code'
    )::TEXT AS exclusivity_code,
    CASE
        WHEN r.response_body->>'exclusivity_date' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'exclusivity_date')::DATE
        WHEN r.response_body->>'Exclusivity_Date' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'Exclusivity_Date')::DATE
        ELSE NULL
    END AS exclusivity_date,

    -- Source tracking
    'orange_book'               AS source,
    r.ingested_at               AS source_updated_at,

    -- Processing metadata
    FALSE                       AS processed_to_silver,
    r.ingested_at               AS ingested_at

FROM mol_raw.orange_book r
WHERE r.response_status = 200
  AND r.processed_to_bronze = FALSE
  AND r.response_body IS NOT NULL
  AND COALESCE(
      r.response_body->>'appl_no',
      r.response_body->>'Appl_No',
      r.response_body->>'application_number'
  ) IS NOT NULL
  AND r.ingested_at BETWEEN @start_dt AND @end_dt
