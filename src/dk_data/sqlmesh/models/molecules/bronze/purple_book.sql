-- SQLMesh Model: Bronze Purple Book (Biologics)
-- Extracts BLA product data from FDA Purple Book API responses
-- Part of: 003-molecule-assessment-dashboard

MODEL (
    name mol_bronze.purple_book,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@monthly',
    audits (
        not_null(columns := (bla_number))
    ),
    grain (bla_number, product_number)
);

SELECT
    gen_random_uuid() AS id,

    -- BLA identifiers
    prod->>'bla_number' AS bla_number,
    prod->>'applicant' AS applicant,
    prod->>'brand_name' AS brand_name,
    prod->>'generic_name' AS generic_name,
    prod->>'license_type' AS license_type,
    prod->>'product_number' AS product_number,

    -- Product details
    prod->>'dosage_form' AS dosage_form,
    prod->>'strength' AS strength,
    prod->>'presentation' AS presentation,
    prod->>'route' AS route,
    prod->>'status' AS status,
    prod->>'center' AS center,

    -- Biosimilar/interchangeable status
    (prod->>'is_biosimilar')::BOOLEAN AS is_biosimilar,
    (prod->>'is_interchangeable')::BOOLEAN AS is_interchangeable,
    prod->>'reference_product_name' AS reference_product_name,
    prod->>'reference_product_brand' AS reference_product_brand,

    -- Dates (Purple Book provides formatted dates like "May 01, 2017")
    prod->>'approval_date' AS approval_date,
    prod->>'first_licensure_date' AS first_licensure_date,

    -- Exclusivity dates (key data for lifecycle/patent analysis)
    prod->>'orphan_exclusivity_end' AS orphan_exclusivity_end,
    prod->>'exclusivity_expiry_date' AS exclusivity_expiry_date,
    prod->>'interchangeable_exclusivity_end' AS interchangeable_exclusivity_end,
    prod->>'ref_product_exclusivity_end' AS ref_product_exclusivity_end,
    prod->>'interchangeable_approval_date' AS interchangeable_approval_date,

    -- Patent info
    (prod->>'has_patent_list')::BOOLEAN AS has_patent_list,

    -- Source tracking
    NULL::TEXT AS query_name,
    response_body AS raw_json,
    r.id AS raw_source_id,
    'purple_book' AS source,
    ingested_at,
    ingested_at AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.purple_book r,
     jsonb_array_elements(response_body->'_normalized_products') AS prod
WHERE
    response_body->'_normalized_products' IS NOT NULL
    AND jsonb_array_length(response_body->'_normalized_products') > 0
    AND ingested_at BETWEEN @start_dt AND @end_dt;
