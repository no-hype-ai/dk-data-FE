-- SQLMesh Model: Gold Market Summary
-- 10-way LEFT JOIN from mol_silver.molecules to all evidence sources.
-- Feature: 019-cms-puf-platform-reconciliation (T026)
--
-- Grain: molecule_id
-- Sources: mol_silver.molecules, mol_silver.drug_spending, mol_silver.ema_regulatory,
--          mol_silver.cochrane_reviews, mol_silver.molecule_publications (europepmc),
--          mol_silver.research_grants, mol_gold.trial_outcomes, mol_silver.publication_evidence
--
-- All evidence sources are read from SILVER only — no direct bronze reads.
-- Entity linking is done at the silver layer; gold aggregates counts only.
--
-- NOTE: All joins are LEFT — model degrades gracefully when any source is absent.

-- T173: Converted FULL → INCREMENTAL_BY_UNIQUE_KEY on molecule_id.
-- Rationale: 10-way LEFT JOIN aggregation keyed on molecule_id. Incremental avoids
-- recomputing unchanged molecules every week. No cross-row dependencies.
MODEL (
    name mol_gold.market_summary,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key molecule_id
    ),
    cron '@weekly',
    audits (
        not_null(columns := (molecule_id))
    ),
    grain molecule_id
);

WITH molecules AS (
    SELECT
        molecule_id,
        canonical_name,
        molecule_type,
        development_status,
        therapeutic_areas
    FROM mol_silver.molecules
),

-- Drug spending aggregated across Part D + Part B, most recent year
drug_spending AS (
    SELECT
        molecule_id,
        SUM(CASE WHEN program = 'part_d' THEN total_spending ELSE 0 END) AS part_d_total_spending,
        SUM(CASE WHEN program = 'part_b' THEN total_spending ELSE 0 END) AS part_b_total_spending,
        SUM(total_spending)                                               AS total_medicare_spending,
        SUM(total_beneficiaries)                                          AS total_medicare_beneficiaries,
        MAX(_source_year)                                                 AS latest_spending_year
    FROM mol_silver.drug_spending
    WHERE molecule_id IS NOT NULL
    GROUP BY molecule_id
),

-- EMA: latest authorisation status and date
ema AS (
    SELECT DISTINCT ON (molecule_id)
        molecule_id,
        authorization_status,
        authorization_date,
        active_substance
    FROM mol_silver.ema_regulatory
    WHERE molecule_id IS NOT NULL
    ORDER BY molecule_id, authorization_date DESC NULLS LAST
),

-- Cochrane: count of systematic reviews
-- mol_silver.cochrane_reviews already has molecule_id via entity linking in silver layer
cochrane AS (
    SELECT
        molecule_id,
        COUNT(*)                            AS cochrane_review_count
    FROM mol_silver.cochrane_reviews
    WHERE molecule_id IS NOT NULL
    GROUP BY molecule_id
),

-- EuropePMC: publication count via mol_silver.molecule_publications junction table
-- Entity linking (name matching) is done in silver; gold reads the pre-linked result
europepmc AS (
    SELECT
        molecule_id,
        COUNT(DISTINCT publication_id)      AS europepmc_pub_count
    FROM mol_silver.molecule_publications
    WHERE source = 'europepmc'
    GROUP BY molecule_id
),

-- NIH Reporter: grant count and total funding
-- mol_silver.research_grants already has molecule_id via entity linking in silver layer
nih AS (
    SELECT
        molecule_id,
        COUNT(*)                            AS nih_grant_count,
        SUM(award_amount)                   AS nih_total_funding
    FROM mol_silver.research_grants
    WHERE molecule_id IS NOT NULL
    GROUP BY molecule_id
),

-- Trial outcomes: count of endpoint extractions
trial_outcomes AS (
    SELECT
        molecule_id,
        COUNT(*)                            AS trial_outcome_count,
        COUNT(DISTINCT trial_nct_id)        AS trial_count
    FROM mol_gold.trial_outcomes
    WHERE molecule_id IS NOT NULL
    GROUP BY molecule_id
),

-- Publication evidence: count of extracted endpoints
pub_evidence AS (
    SELECT
        molecule_id,
        COUNT(*)                            AS pub_evidence_count,
        AVG(confidence_score)               AS avg_evidence_confidence
    FROM mol_silver.publication_evidence
    WHERE molecule_id IS NOT NULL
    GROUP BY molecule_id
)

SELECT
    m.molecule_id,
    m.canonical_name,
    m.molecule_type,
    CASE
        WHEN m.max_phase >= 4 THEN 'approved'
        WHEN m.max_phase = 3  THEN 'phase_3'
        WHEN m.max_phase = 2  THEN 'phase_2'
        WHEN m.max_phase = 1  THEN 'phase_1'
        WHEN m.max_phase = 0  THEN 'preclinical'
        ELSE 'unknown'
    END                                     AS development_status,
    m.therapeutic_areas,

    -- Drug spending
    ds.part_d_total_spending,
    ds.part_b_total_spending,
    ds.total_medicare_spending,
    ds.total_medicare_beneficiaries,
    ds.latest_spending_year,

    -- EMA regulatory
    e.authorization_status                  AS ema_authorisation_status,
    e.authorization_date                    AS ema_authorisation_date,

    -- Evidence counts
    COALESCE(co.cochrane_review_count, 0)   AS cochrane_review_count,
    COALESCE(ep.europepmc_pub_count, 0)     AS europepmc_pub_count,
    COALESCE(n.nih_grant_count, 0)          AS nih_grant_count,
    n.nih_total_funding,
    COALESCE(to_.trial_count, 0)            AS trial_count,
    COALESCE(to_.trial_outcome_count, 0)    AS trial_outcome_count,
    COALESCE(pe.pub_evidence_count, 0)      AS pub_evidence_count,
    pe.avg_evidence_confidence,

    NOW()                                   AS created_at,
    NOW()                                   AS updated_at

FROM molecules m
LEFT JOIN drug_spending ds  ON m.molecule_id = ds.molecule_id
LEFT JOIN ema e             ON m.molecule_id = e.molecule_id
LEFT JOIN cochrane co       ON m.molecule_id = co.molecule_id
LEFT JOIN europepmc ep      ON m.molecule_id = ep.molecule_id
LEFT JOIN nih n             ON m.molecule_id = n.molecule_id
LEFT JOIN trial_outcomes to_ ON m.molecule_id = to_.molecule_id
LEFT JOIN pub_evidence pe   ON m.molecule_id = pe.molecule_id;
