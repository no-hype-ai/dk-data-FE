-- SQLMesh Model: Bronze EUIPO Registered Community Designs
-- Transforms raw EUIPO design search flat columns into typed bronze layer.
-- Source table: mol_raw.euipo_designs (flat typed columns, not JSONB envelope)
-- Part of: 014-uspto-euipo-model-datasource

MODEL (
    name mol_bronze.euipo_designs,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key application_number
    ),
    cron '@weekly',
    grain (application_number),
    audits (
        not_null(columns := (application_number)),
        unique_values(columns := (application_number))
    )
);

SELECT
    gen_random_uuid() AS id,

    -- Design identification (flat columns — no JSON extraction needed)
    r.application_number,
    r.design_title,

    -- Applicant info
    r.applicant_name,
    r.applicant_country,
    r.representative_name,
    r.designer_name,

    -- Status
    r.status,

    -- Dates (already typed as DATE in the raw table)
    r.filing_date,
    r.registration_date,
    r.expiry_date,
    r.publication_date,

    -- Classification (Locarno classes JSONB)
    r.locarno_classes,

    -- Product description
    r.product_indication,

    -- Medical/pharma relevance: Locarno class 24 = medical equipment, 09 = packaging
    (
        COALESCE(r.locarno_classes, '[]'::jsonb) @> '"24"'::jsonb
        OR COALESCE(r.locarno_classes, '[]'::jsonb) @> '"09"'::jsonb
    )                                        AS is_healthcare_related,

    -- Design image
    r.image_url,

    -- Number of individual designs in the application
    r.number_of_designs,

    -- Processing metadata
    FALSE                                    AS processed_to_silver,
    r._loaded_at

FROM mol_raw.euipo_designs r
WHERE r.application_number IS NOT NULL
  AND r._loaded_at BETWEEN @start_dt AND @end_dt
