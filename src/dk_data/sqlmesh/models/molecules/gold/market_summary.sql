-- SQLMesh Model: Gold Market Summary
-- 10-way LEFT JOIN from mol_silver.molecules to all evidence sources.
-- Feature: 019-cms-puf-platform-reconciliation (T026)
--
-- Grain: molecule_id
-- Sources: mol_silver.molecules, mol_silver.drug_spending, mol_silver.ema_regulatory,
--          mol_bronze.cochrane_reviews, mol_bronze.europepmc, mol_bronze.nih_reporter,
--          mol_gold.trial_outcomes, mol_silver.publication_evidence
--
-- NOTE: All joins are LEFT — model degrades gracefully when any source is absent.

MODEL (
    name mol_gold.market_summary,
    kind FULL,
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
        authorisation_status,
        authorisation_date,
        active_substance
    FROM mol_silver.ema_regulatory
    WHERE molecule_id IS NOT NULL
    ORDER BY molecule_id, authorisation_date DESC NULLS LAST
),

-- Cochrane: count of systematic reviews
cochrane AS (
    SELECT
        -- Join via mol_silver.molecules canonical name match in bronze
        m.molecule_id,
        COUNT(cr.id)                        AS cochrane_review_count
    FROM mol_silver.molecules m
    JOIN mol_bronze.cochrane_reviews cr
        ON LOWER(cr.title) LIKE '%' || LOWER(m.canonical_name) || '%'
    GROUP BY m.molecule_id
),

-- EuropePMC: publication count
europepmc AS (
    SELECT
        m.molecule_id,
        COUNT(ep.id)                        AS europepmc_pub_count
    FROM mol_silver.molecules m
    JOIN mol_bronze.europepmc ep
        ON LOWER(ep.title) LIKE '%' || LOWER(m.canonical_name) || '%'
        OR LOWER(ep.abstract_text) LIKE '%' || LOWER(m.canonical_name) || '%'
    GROUP BY m.molecule_id
),

-- NIH Reporter: grant count and total funding
nih AS (
    SELECT
        m.molecule_id,
        COUNT(nr.id)                        AS nih_grant_count,
        SUM(nr.award_amount)                AS nih_total_funding
    FROM mol_silver.molecules m
    JOIN mol_bronze.nih_reporter nr
        ON LOWER(nr.abstract_text) LIKE '%' || LOWER(m.canonical_name) || '%'
        OR LOWER(nr.terms) LIKE '%' || LOWER(m.canonical_name) || '%'
    GROUP BY m.molecule_id
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
    m.development_status,
    m.therapeutic_areas,

    -- Drug spending
    ds.part_d_total_spending,
    ds.part_b_total_spending,
    ds.total_medicare_spending,
    ds.total_medicare_beneficiaries,
    ds.latest_spending_year,

    -- EMA regulatory
    e.authorisation_status                  AS ema_authorisation_status,
    e.authorisation_date                    AS ema_authorisation_date,

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
