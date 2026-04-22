-- SQLMesh Model: Silver FDA PMA (Premarket Approvals)
-- Entity-resolved PMA fact table with device_id + company_id FKs.
-- PMA records include supplements (labeling changes, manufacturing changes, PAS
-- studies). Each supplement gets its own row, but all reference the same
-- device_id (the base PMA's hash).
--
-- Grain: (pma_number, supplement_number)

MODEL (
    name dev_silver.fda_pma,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (pma_number, supplement_number)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (pma_number, device_id))
    ),
    grain (pma_number, supplement_number)
);

SELECT
    -- Entity-resolved FKs
    dev_silver.resolve_device(
        p_pma_number => b.pma_number,
        p_name       => COALESCE(b.trade_name, b.device_name, b.generic_name)
    )                                                                    AS device_id,

    mol_silver.resolve_company(
        p_name => b.applicant
    )                                                                    AS company_id,

    -- Natural keys
    b.pma_number,
    b.supplement_number,

    -- Applicant
    b.applicant                                                          AS applicant_name,

    -- Dates
    b.date_received,
    b.decision_date,

    -- Decision
    b.decision_code,
    b.ao_statement,
    (b.expedited_review_flag = 'Y')                                      AS is_expedited,

    -- Supplement details
    b.supplement_type,
    b.supplement_reason,
    (COALESCE(b.supplement_number, '0') = '0')                           AS is_base_pma,

    -- Device metadata
    b.device_name,
    b.generic_name,
    b.trade_name,
    b.product_code,
    b.openfda_device_name,
    b.openfda_device_class,
    b.openfda_regulation_number,
    b.openfda_medical_specialty_description                              AS medical_specialty,

    -- Geography
    b.city,
    b.state,

    -- Advisory committee
    b.advisory_committee,

    -- Raw tracking
    b.raw_source_id,
    b.source                                                             AS source_id,
    b.source_updated_at,
    NOW()                                                                AS silver_loaded_at

FROM dev_bronze.openfda_device_pma AS b
WHERE b.processed_to_silver = FALSE
  AND b.pma_number IS NOT NULL;
