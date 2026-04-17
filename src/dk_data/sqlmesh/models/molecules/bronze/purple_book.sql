-- SQLMesh Model: Bronze Purple Book (Biologics)
-- Extracts BLA product data from FDA Purple Book API responses
-- Part of: 003-molecule-assessment-dashboard

MODEL (
    name mol_bronze.purple_book,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (bla_number, product_number)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (bla_number))
    ),
    grain (bla_number, product_number)
);

-- Handle two raw data formats:
--   Format A (legacy): response_body = {results: [{application_number, products, submissions, ...}]}
--   Format B (current): response_body = {application_number, products, submissions, sponsor_name}
--                       (individual application record, stored one-per-row by the loader)

WITH raw_records AS (
    -- Format B: individual records (current loader format)
    SELECT
        r.id AS raw_source_id,
        r.ingested_at,
        r.response_body AS app,
        prod
    FROM mol_raw.purple_book r,
         LATERAL jsonb_array_elements(r.response_body->'products') AS prod
    WHERE r.response_status = 200
      AND r.response_body->>'application_number' IS NOT NULL
      AND r.response_body->>'application_number' LIKE 'BLA%'
      AND r.response_body->'results' IS NULL
      AND r.ingested_at BETWEEN @start_dt AND @end_dt

    UNION ALL

    -- Format A: full-page response with results array (legacy loader format)
    SELECT
        r.id AS raw_source_id,
        r.ingested_at,
        app,
        prod
    FROM mol_raw.purple_book r,
         jsonb_array_elements(r.response_body->'results') AS app,
         LATERAL jsonb_array_elements(app->'products') AS prod
    WHERE r.response_status = 200
      AND r.response_body->'results' IS NOT NULL
      AND jsonb_array_length(r.response_body->'results') > 0
      AND app->>'application_number' LIKE 'BLA%'
      AND r.ingested_at BETWEEN @start_dt AND @end_dt
),

first_orig_approval AS (
    -- Get earliest ORIG-AP submission date per BLA from Format B records
    SELECT DISTINCT ON (r.response_body->>'application_number')
        r.response_body->>'application_number' AS bla_number,
        sub->>'submission_status_date' AS approval_date_raw
    FROM mol_raw.purple_book r,
         LATERAL jsonb_array_elements(COALESCE(r.response_body->'submissions', '[]'::jsonb)) AS sub
    WHERE r.response_status = 200
      AND r.response_body->>'application_number' IS NOT NULL
      AND r.response_body->'results' IS NULL
      AND sub->>'submission_status' = 'AP'
      AND sub->>'submission_type' = 'ORIG'
    ORDER BY r.response_body->>'application_number', sub->>'submission_status_date' ASC NULLS LAST
)

SELECT
    gen_random_uuid() AS id,
    app->>'application_number' AS bla_number,
    COALESCE(app->>'sponsor_name', app->>'applicant_full_name') AS applicant,
    prod->>'brand_name' AS brand_name,
    COALESCE(
        app->'openfda'->'generic_name'->>0,
        prod->'active_ingredients'->0->>'name',
        prod->>'generic_name'
    ) AS generic_name,
    prod->>'license_type' AS license_type,
    prod->>'product_number' AS product_number,
    prod->>'dosage_form' AS dosage_form,
    COALESCE(
        prod->'active_ingredients'->0->>'strength',
        prod->>'strength'
    ) AS strength,
    prod->>'presentation' AS presentation,
    prod->>'route' AS route,
    COALESCE(prod->>'marketing_status', prod->>'status') AS status,
    prod->>'center' AS center,

    -- Biosimilar flags (present in FDA Purple Book but not in openFDA Drugs@FDA API)
    (prod->>'is_biosimilar')::BOOLEAN AS is_biosimilar,
    (prod->>'is_interchangeable')::BOOLEAN AS is_interchangeable,
    prod->>'reference_product_name' AS reference_product_name,
    prod->>'reference_product_brand' AS reference_product_brand,

    -- Approval date: prefer product field, fall back to first ORIG-AP submission
    COALESCE(
        prod->>'approval_date',
        CASE
            WHEN foa.approval_date_raw ~ '^\d{8}$'
            THEN TO_CHAR(TO_DATE(foa.approval_date_raw, 'YYYYMMDD'), 'Mon DD, YYYY')
            ELSE foa.approval_date_raw
        END
    ) AS approval_date,
    prod->>'first_licensure_date' AS first_licensure_date,
    prod->>'orphan_exclusivity_end' AS orphan_exclusivity_end,
    prod->>'exclusivity_expiry_date' AS exclusivity_expiry_date,
    prod->>'interchangeable_exclusivity_end' AS interchangeable_exclusivity_end,
    prod->>'ref_product_exclusivity_end' AS ref_product_exclusivity_end,
    prod->>'interchangeable_approval_date' AS interchangeable_approval_date,
    (prod->>'has_patent_list')::BOOLEAN AS has_patent_list,

    NULL::TEXT AS query_name,
    prod AS raw_json,
    rr.raw_source_id,
    'purple_book' AS source,
    rr.ingested_at,
    rr.ingested_at AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM raw_records rr
LEFT JOIN first_orig_approval foa
       ON foa.bla_number = rr.app->>'application_number';
