-- SQLMesh Model: Silver FDA Device Classification
-- Reference table: FDA product code → device class, medical specialty, regulation.
-- Joined at query time by dev_silver.fda_510k and dev_silver.fda_pma on product_code.
-- No entity resolution (product_code is a taxonomy key, not a device).
-- Grain: product_code

MODEL (
    name dev_silver.fda_classification,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key product_code
    ),
    cron '@weekly',
    audits (
        not_null(columns := (product_code, device_class))
    ),
    grain product_code
);

SELECT
    b.product_code,

    -- Device identity
    b.device_name,
    b.device_class,                     -- '1', '2', '3', 'U', 'N', 'HDE'
    b.definition,
    b.regulation_number,

    -- Medical specialty
    b.medical_specialty_code,
    b.medical_specialty_description,
    b.review_panel,

    -- Regulatory flags (normalized to booleans)
    b.submission_type_id,
    (b.gmp_exempt_flag = 'Y')                                            AS is_gmp_exempt,
    (b.implant_flag = 'Y')                                               AS is_implant,
    (b.life_sustain_support_flag = 'Y')                                  AS is_life_sustaining,
    (b.third_party_flag = 'Y')                                           AS is_third_party_eligible,
    b.summary_malfunction_reporting,

    -- Derived numeric class for sorting
    CASE
        WHEN b.device_class IN ('1', '2', '3') THEN (b.device_class)::INTEGER
        ELSE NULL
    END                                                                  AS device_class_numeric,

    -- Raw tracking
    b.raw_source_id,
    b.source                                                             AS source_id,
    b.source_updated_at,
    NOW()                                                                AS silver_loaded_at

FROM dev_bronze.openfda_device_classification AS b
WHERE b.processed_to_silver = FALSE
  AND b.product_code IS NOT NULL;
