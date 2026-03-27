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
    m.molecule_id AS molecule_id,
    m.inchi_key,
    m.canonical_name,
    'clinical_trial' AS evidence_type,
    ct.nct_id AS evidence_id,
    ct.brief_title AS evidence_title,
    ct.phase AS evidence_detail,
    ct.overall_status AS evidence_status,
    'ClinicalTrials.gov' AS evidence_source,
    ct.start_date AS evidence_date,
    'https://clinicaltrials.gov/study/' || ct.nct_id AS evidence_url,
    NOW() AS computed_at

FROM mol_silver.molecules m
JOIN mol_silver.clinical_trials ct ON m.molecule_id = ct.molecule_id
WHERE m.needs_review = FALSE

UNION ALL

-- Drug label evidence
SELECT
    m.molecule_id AS molecule_id,
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
    dl.effective_date AS evidence_date,
    'https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=' || dl.set_id AS evidence_url,
    NOW() AS computed_at

FROM mol_silver.molecules m
JOIN mol_silver.drug_labels dl ON m.molecule_id = dl.molecule_id
WHERE m.needs_review = FALSE

UNION ALL

-- Adverse event evidence (aggregated as single evidence type per molecule)
SELECT DISTINCT ON (m.molecule_id)
    m.molecule_id AS molecule_id,
    m.inchi_key,
    m.canonical_name,
    'adverse_events' AS evidence_type,
    'FAERS_' || m.molecule_id::text AS evidence_id,
    'FDA Adverse Event Reports' AS evidence_title,
    (
        SELECT COALESCE(SUM(report_count), 0)::text || ' total reports'
        FROM mol_silver.adverse_events ae
        WHERE ae.molecule_id = m.molecule_id
    ) AS evidence_detail,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM mol_silver.adverse_events ae
            WHERE ae.molecule_id = m.molecule_id AND ae.death_count > 0
        ) THEN 'Has Death Reports'
        WHEN EXISTS (
            SELECT 1 FROM mol_silver.adverse_events ae
            WHERE ae.molecule_id = m.molecule_id AND ae.serious_count > 0
        ) THEN 'Has Serious Reports'
        ELSE 'Active'
    END AS evidence_status,
    'OpenFDA FAERS' AS evidence_source,
    (
        SELECT MAX(last_report_date)
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

UNION ALL

-- Patent evidence from patent_exclusivities (Orange Book + Purple Book silver)
SELECT
    m.molecule_id AS molecule_id,
    m.inchi_key,
    m.canonical_name,
    'patent' AS evidence_type,
    pe.patent_number AS evidence_id,
    COALESCE(pe.trade_name, pe.generic_name) || ' Patent' AS evidence_title,
    'Expires: ' || COALESCE(pe.patent_expiry_date::text, 'Unknown') AS evidence_detail,
    CASE
        WHEN pe.patent_expiry_date < CURRENT_DATE THEN 'Expired'
        WHEN pe.patent_expiry_date < CURRENT_DATE + INTERVAL '1 year' THEN 'Expiring Soon'
        ELSE 'Active'
    END AS evidence_status,
    'FDA Orange Book' AS evidence_source,
    pe.approval_date::DATE AS evidence_date,
    'https://www.accessdata.fda.gov/scripts/cder/ob/' AS evidence_url,
    NOW() AS computed_at

FROM mol_silver.molecules m
JOIN mol_silver.patent_exclusivities pe ON pe.molecule_id = m.molecule_id
WHERE m.needs_review = FALSE
  AND pe.patent_number IS NOT NULL

ORDER BY molecule_id, evidence_date DESC NULLS LAST
