-- SQLMesh Model: Silver EUIPO Design Registrations
-- Typed pass-through of EUIPO design registrations from mol_bronze.euipo_designs.
-- Filtered to healthcare-related registrations (is_healthcare_related = TRUE).
-- No direct drug identifier — molecule linkage not attempted at this layer.
-- Consumers: IP landscape analysis, competitive intelligence dashboards.
-- Part of: issue #172 H2

MODEL (
    name mol_silver.euipo_designs,
    kind FULL,
    cron '@weekly',
    audits (
        not_null(columns := (application_number, source))
    ),
    grain application_number
);

SELECT
    gen_random_uuid()               AS id,
    b.application_number,
    b.design_title,
    b.applicant_name,
    b.applicant_country,
    b.representative_name,
    b.designer_name,
    b.status,
    b.filing_date,
    b.registration_date,
    b.expiry_date,
    b.publication_date,
    b.locarno_classes,
    b.product_indication,
    b.is_healthcare_related,
    b.image_url,
    b.number_of_designs,
    'euipo'                         AS source,
    b._loaded_at                    AS source_updated_at,
    NOW()                           AS created_at

FROM mol_bronze.euipo_designs b
WHERE b.application_number IS NOT NULL
  AND b.is_healthcare_related = TRUE
