-- SQLMesh Model: Gold Lifecycle Evidence
-- Consolidated evidence for lifecycle stage validation
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_gold.lifecycle_evidence,
    kind FULL,
    cron '@daily',
    grain (molecule_id, evidence_type, evidence_id)
);

-- Clinical trial evidence
SELECT
    m.molecule_id,
    m.inchi_key,
    m.canonical_name,
    'clinical_trial' AS evidence_type,
    ct.nct_id AS evidence_id,
    ct.brief_title AS evidence_title,
    ct.phases::TEXT AS evidence_detail,
    ct.overall_status AS evidence_status,
    'ClinicalTrials.gov' AS evidence_source,
    ct.start_date::TEXT AS evidence_date,
    'https://clinicaltrials.gov/study/' || ct.nct_id AS evidence_url,
    NOW() AS computed_at

FROM mol_silver.molecules m
JOIN mol_silver.clinical_trials ct ON m.molecule_id = ct.molecule_id
WHERE m.needs_review = FALSE

UNION ALL

-- Drug label evidence
SELECT
    m.molecule_id,
    m.inchi_key,
    m.canonical_name,
    'drug_label' AS evidence_type,
    dl.set_id AS evidence_id,
    COALESCE(dl.brand_name, dl.generic_name) AS evidence_title,
    dl.product_type AS evidence_detail,
    CASE
        WHEN dl.boxed_warning IS NOT NULL THEN 'Has Boxed Warning'
        ELSE 'Active'
    END AS evidence_status,
    'DailyMed' AS evidence_source,
    dl.effective_date::TEXT AS evidence_date,
    'https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=' || dl.set_id AS evidence_url,
    NOW() AS computed_at

FROM mol_silver.molecules m
JOIN mol_silver.drug_labels dl ON m.molecule_id = dl.molecule_id
WHERE m.needs_review = FALSE

UNION ALL

-- Adverse event evidence (aggregated as single evidence type per molecule)
-- adverse_events has individual report rows with boolean seriousness flags
SELECT DISTINCT ON (m.molecule_id)
    m.molecule_id,
    m.inchi_key,
    m.canonical_name,
    'adverse_events' AS evidence_type,
    'FAERS_' || m.molecule_id::text AS evidence_id,
    'FDA Adverse Event Reports' AS evidence_title,
    (
        SELECT COUNT(*)::text || ' total reports'
        FROM mol_silver.adverse_events ae
        WHERE ae.molecule_id = m.molecule_id
    ) AS evidence_detail,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM mol_silver.adverse_events ae
            WHERE ae.molecule_id = m.molecule_id AND ae.serious_death = TRUE
        ) THEN 'Has Death Reports'
        WHEN EXISTS (
            SELECT 1 FROM mol_silver.adverse_events ae
            WHERE ae.molecule_id = m.molecule_id AND ae.serious = TRUE
        ) THEN 'Has Serious Reports'
        ELSE 'Active'
    END AS evidence_status,
    'OpenFDA FAERS' AS evidence_source,
    (
        SELECT MAX(receipt_date)::TEXT
        FROM mol_silver.adverse_events ae
        WHERE ae.molecule_id = m.molecule_id
    ) AS evidence_date,
    'https://open.fda.gov/apis/drug/event/' AS evidence_url,
    NOW() AS computed_at

FROM mol_silver.molecules m
WHERE m.needs_review = FALSE
  AND EXISTS (
      SELECT 1 FROM mol_silver.adverse_events ae WHERE ae.molecule_id = m.molecule_id
  )

ORDER BY molecule_id, evidence_date DESC NULLS LAST
