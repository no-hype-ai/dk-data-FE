-- SQLMesh Model: Silver CMS Provider Profile
-- Joins bronze NPPES, Part D Prescriber, Physician PUF, Open Payments, and NUCC
-- into a unified provider profile with aggregated metrics
-- Part of: 016-cms-puf-datasource-integration
--
-- Key design decisions:
-- 1. Spending/claims filtered to latest year only (avoids multi-year collapse)
-- 2. Beneficiary counts use MAX across drugs — this is a lower-bound estimate
--    since unique beneficiary IDs are not available for deduplication
-- 3. NUCC taxonomy joined for human-readable specialty names

MODEL (
    name silver.cms_provider_profile,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (npi)),
        unique_values(columns := (npi))
    ),
    grain (npi)
);

WITH prescriber_agg AS (
    SELECT
        npi,
        SUM(total_claims)                       AS total_prescriptions,
        SUM(total_drug_cost)                    AS total_drug_cost,
        -- MAX is a lower-bound estimate; we lack distinct beneficiary IDs
        MAX(total_beneficiaries)                AS max_beneficiaries_rx,
        COUNT(DISTINCT drug_name)               AS distinct_drugs_prescribed
    FROM bronze.cms_part_d_prescriber
    WHERE year = (SELECT MAX(year) FROM bronze.cms_part_d_prescriber)
    GROUP BY npi
),

procedure_agg AS (
    SELECT
        npi,
        SUM(line_srvc_cnt)                      AS total_procedures,
        MAX(bene_unique_cnt)                    AS max_beneficiaries_proc
    FROM bronze.cms_physician_puf
    WHERE year = (SELECT MAX(year) FROM bronze.cms_physician_puf)
    GROUP BY npi
),

payment_agg AS (
    SELECT
        physician_npi AS npi,
        SUM(total_amount_usd)                   AS total_payment_received,
        COUNT(DISTINCT payer_name)              AS distinct_payers,
        COUNT(*)                                AS total_payment_records
    FROM bronze.cms_open_payments
    WHERE physician_npi IS NOT NULL
    GROUP BY physician_npi
)

SELECT
    n.npi,
    n.entity_type,
    n.name_first,
    n.name_last,
    n.name_org,
    n.credential,
    n.taxonomy_code                                                     AS primary_specialty,
    -- Human-readable specialty from NUCC taxonomy
    nucc.classification                                                 AS specialty_classification,
    nucc.specialization                                                 AS specialty_detail,
    n.practice_state,
    n.practice_city,
    n.practice_zip,
    n.gender,
    n.enumeration_date,
    n.last_updated,

    -- Prescribing metrics
    COALESCE(rx.total_prescriptions, 0)                                 AS total_prescriptions,
    COALESCE(rx.total_drug_cost, 0)                                     AS total_drug_cost,
    COALESCE(rx.distinct_drugs_prescribed, 0)                           AS distinct_drugs_prescribed,

    -- Procedure metrics
    COALESCE(proc.total_procedures, 0)                                  AS total_procedures,

    -- Beneficiary estimate (lower bound: max single-source beneficiary count)
    GREATEST(
        COALESCE(rx.max_beneficiaries_rx, 0),
        COALESCE(proc.max_beneficiaries_proc, 0)
    )                                                                   AS total_beneficiaries,

    -- Payment metrics
    COALESCE(pay.total_payment_received, 0)                             AS total_payment_received,
    COALESCE(pay.distinct_payers, 0)                                    AS distinct_payers,
    COALESCE(pay.total_payment_records, 0)                              AS total_payment_records,

    NOW()                                                               AS profile_built_at

FROM bronze.cms_nppes n
LEFT JOIN prescriber_agg rx ON n.npi = rx.npi
LEFT JOIN procedure_agg proc ON n.npi = proc.npi
LEFT JOIN payment_agg pay ON n.npi = pay.npi
LEFT JOIN bronze.cms_nucc nucc ON n.taxonomy_code = nucc.taxonomy_code
WHERE n.deactivation_date IS NULL;
