-- SQLMesh Model: Gold Prescriber Payments (Open Payments / Sunshine Act)
-- Drug-level industry payment analytics derived from hcs_silver.open_payments_drug_linkage.
-- Answers: "Total industry payments for drug X by manufacturer", "Which physicians received
-- payments for drug X?", "Which drugs have the highest payment volumes?"
--
-- Key design decisions:
-- 1. Grain is (molecule_id, manufacturer, _source_year) — one row per drug-manufacturer-year
-- 2. Rows with molecule_id IS NULL (unresolved drugs) are included — queryable by drug_name_normalized
-- 3. molecule_resolved_pct gives a data quality signal per drug-manufacturer pair
-- Part of: issue #172 H5

MODEL (
    name hcs_gold.prescriber_payments,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (applicable_manufacturer_or_gpo_name, _source_year))
    ),
    grain (molecule_id, applicable_manufacturer_or_gpo_name, _source_year)
);

WITH payment_agg AS (
    SELECT
        molecule_id,
        drug_name,
        drug_name_normalized,
        applicable_manufacturer_or_gpo_name,
        _source_year,

        -- Payment volume
        COUNT(DISTINCT record_id)                                       AS payment_count,
        SUM(total_amount_of_payment_usdollars)                          AS total_payment_usd,
        AVG(total_amount_of_payment_usdollars)                          AS avg_payment_usd,
        MAX(total_amount_of_payment_usdollars)                          AS max_payment_usd,

        -- Recipient reach
        COUNT(DISTINCT physician_profile_id)
            FILTER (WHERE physician_profile_id IS NOT NULL)             AS unique_physicians,
        COUNT(DISTINCT recipient_state)                                 AS states_covered,

        -- Payment type breakdown
        COUNT(*) FILTER (WHERE nature_of_payment_or_transfer_of_value = 'Food and Beverage')        AS payments_food_beverage,
        COUNT(*) FILTER (WHERE nature_of_payment_or_transfer_of_value = 'Speaker Programs/Training') AS payments_speaker,
        COUNT(*) FILTER (WHERE nature_of_payment_or_transfer_of_value = 'Consulting Fee')           AS payments_consulting,
        COUNT(*) FILTER (WHERE nature_of_payment_or_transfer_of_value = 'Research')                 AS payments_research,

        -- Resolution quality
        ROUND(
            100.0 * COUNT(*) FILTER (WHERE molecule_resolved = TRUE) / NULLIF(COUNT(*), 0),
            1
        )                                                               AS molecule_resolved_pct,
        MIN(link_confidence)                                            AS min_link_confidence,
        MAX(link_confidence)                                            AS max_link_confidence
    FROM hcs_silver.open_payments_drug_linkage
    GROUP BY
        molecule_id,
        drug_name,
        drug_name_normalized,
        applicable_manufacturer_or_gpo_name,
        _source_year
)

SELECT
    gen_random_uuid()                                   AS id,
    pa.molecule_id,
    pa.drug_name,
    pa.drug_name_normalized,
    pa.applicable_manufacturer_or_gpo_name,
    pa._source_year,
    pa.payment_count,
    pa.total_payment_usd,
    pa.avg_payment_usd,
    pa.max_payment_usd,
    pa.unique_physicians,
    pa.states_covered,
    pa.payments_food_beverage,
    pa.payments_speaker,
    pa.payments_consulting,
    pa.payments_research,
    pa.molecule_resolved_pct,
    pa.min_link_confidence,
    pa.max_link_confidence,
    NOW()                                               AS gold_built_at

FROM payment_agg pa;
