-- SQLMesh Model: Gold NPI Prescribing Profile
-- Molecule-level Part D prescribing analytics derived from hcs_silver.part_d_prescribing.
-- Provides two views: (1) drug-centric — how many prescribers write drug X across years,
-- (2) prescriber-centric — top drugs per NPI with year-over-year trend.
--
-- Key design decisions:
-- 1. Grain is (molecule_id, _source_year) for drug-level analytics
-- 2. Includes unresolved drugs (molecule_id IS NULL) via gnrc_name grouping fallback
-- 3. 65+ suppressed rows (ge65_sprsn_flag = 'Y') are excluded from 65+ aggregates
--    per CMS methodology (suppressed values are NULL, not zero, in silver)
-- Part of: issue #172 H5

MODEL (
    name hcs_gold.npi_prescribing,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (gnrc_name, _source_year))
    ),
    grain (molecule_id, gnrc_name, _source_year)
);

WITH drug_year_agg AS (
    SELECT
        molecule_id,
        gnrc_name,
        brnd_name,
        _source_year,

        -- Prescriber volume
        COUNT(DISTINCT prscrbr_npi)                                     AS prescriber_count,
        COUNT(DISTINCT prscrbr_state_abrvtn)                            AS states_covered,

        -- Utilization totals
        SUM(tot_clms)                                                   AS total_claims,
        SUM(tot_30day_fills)                                            AS total_30day_fills,
        SUM(tot_day_suply)                                              AS total_days_supply,
        SUM(tot_drug_cst)                                               AS total_drug_cost_usd,
        SUM(tot_benes)                                                  AS total_beneficiaries,

        -- 65+ cohort (suppressed rows excluded)
        SUM(ge65_tot_clms)
            FILTER (WHERE ge65_sprsn_flag IS DISTINCT FROM 'Y')        AS ge65_total_claims,
        SUM(ge65_tot_drug_cst)
            FILTER (WHERE ge65_sprsn_flag IS DISTINCT FROM 'Y')        AS ge65_total_drug_cost_usd,
        SUM(ge65_tot_benes)
            FILTER (WHERE ge65_bene_sprsn_flag IS DISTINCT FROM 'Y')   AS ge65_total_beneficiaries,

        -- Derived metrics
        ROUND(
            SUM(tot_drug_cst) / NULLIF(SUM(tot_clms), 0),
            2
        )                                                               AS avg_cost_per_claim_usd,

        ROUND(
            SUM(tot_day_suply)::NUMERIC / NULLIF(SUM(tot_clms), 0),
            1
        )                                                               AS avg_days_per_claim,

        -- Entity linking quality
        ROUND(
            100.0 * COUNT(*) FILTER (WHERE molecule_resolved = TRUE) / NULLIF(COUNT(*), 0),
            1
        )                                                               AS molecule_resolved_pct,
        MAX(link_confidence)                                            AS max_link_confidence
    FROM hcs_silver.part_d_prescribing
    GROUP BY
        molecule_id,
        gnrc_name,
        brnd_name,
        _source_year
)

SELECT
    gen_random_uuid()                                   AS id,
    da.molecule_id,
    da.gnrc_name,
    da.brnd_name,
    da._source_year,
    da.prescriber_count,
    da.states_covered,
    da.total_claims,
    da.total_30day_fills,
    da.total_days_supply,
    da.total_drug_cost_usd,
    da.total_beneficiaries,
    da.ge65_total_claims,
    da.ge65_total_drug_cost_usd,
    da.ge65_total_beneficiaries,
    da.avg_cost_per_claim_usd,
    da.avg_days_per_claim,
    da.molecule_resolved_pct,
    da.max_link_confidence,
    NOW()                                               AS gold_built_at

FROM drug_year_agg da;
