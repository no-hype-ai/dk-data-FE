-- SQLMesh Model: Gold Lifecycle Evidence
-- Consolidated evidence for lifecycle stage validation
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name gold.lifecycle_evidence,
    kind FULL,
    cron '@daily',
    grain (molecule_id, evidence_type, evidence_id)
);

-- Clinical trial evidence
SELECT
    m.id AS molecule_id,
    m.inchi_key,
    m.canonical_name,
    'clinical_trial' AS evidence_type,
    ct.nct_id AS evidence_id,
    ct.title AS evidence_title,
    ct.phase AS evidence_detail,
    ct.status AS evidence_status,
    'ClinicalTrials.gov' AS evidence_source,
    ct.start_date AS evidence_date,
    'https://clinicaltrials.gov/study/' || ct.nct_id AS evidence_url,
    NOW() AS computed_at

FROM silver.molecules m
JOIN silver.clinical_trials ct ON m.id = ct.molecule_id
WHERE m.needs_review = FALSE

UNION ALL

-- Drug label evidence
SELECT
    m.id AS molecule_id,
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

FROM silver.molecules m
JOIN silver.drug_labels dl ON m.id = dl.molecule_id
WHERE m.needs_review = FALSE

UNION ALL

-- Adverse event evidence (aggregated as single evidence type per molecule)
SELECT DISTINCT ON (m.id)
    m.id AS molecule_id,
    m.inchi_key,
    m.canonical_name,
    'adverse_events' AS evidence_type,
    'FAERS_' || m.id::text AS evidence_id,
    'FDA Adverse Event Reports' AS evidence_title,
    (
        SELECT COALESCE(SUM(report_count), 0)::text || ' total reports'
        FROM silver.adverse_events ae
        WHERE ae.molecule_id = m.id
    ) AS evidence_detail,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM silver.adverse_events ae
            WHERE ae.molecule_id = m.id AND ae.death_count > 0
        ) THEN 'Has Death Reports'
        WHEN EXISTS (
            SELECT 1 FROM silver.adverse_events ae
            WHERE ae.molecule_id = m.id AND ae.serious_count > 0
        ) THEN 'Has Serious Reports'
        ELSE 'Active'
    END AS evidence_status,
    'OpenFDA FAERS' AS evidence_source,
    (
        SELECT MAX(last_report_date)
        FROM silver.adverse_events ae
        WHERE ae.molecule_id = m.id
    ) AS evidence_date,
    'https://open.fda.gov/apis/drug/event/' AS evidence_url,
    NOW() AS computed_at

FROM silver.molecules m
WHERE m.needs_review = FALSE
  AND EXISTS (
      SELECT 1 FROM silver.adverse_events ae WHERE ae.molecule_id = m.id
  )

UNION ALL

-- Patent evidence from Orange Book
SELECT
    m.id AS molecule_id,
    m.inchi_key,
    m.canonical_name,
    'patent' AS evidence_type,
    ob.patent_number AS evidence_id,
    ob.trade_name || ' Patent' AS evidence_title,
    'Expires: ' || COALESCE(ob.patent_expiration::text, 'Unknown') AS evidence_detail,
    CASE
        WHEN ob.patent_expiration < CURRENT_DATE THEN 'Expired'
        WHEN ob.patent_expiration < CURRENT_DATE + INTERVAL '1 year' THEN 'Expiring Soon'
        ELSE 'Active'
    END AS evidence_status,
    'FDA Orange Book' AS evidence_source,
    ob.approval_date AS evidence_date,
    'https://www.accessdata.fda.gov/scripts/cder/ob/' AS evidence_url,
    NOW() AS computed_at

FROM silver.molecules m
JOIN silver.molecule_aliases ma ON m.id = ma.molecule_id
JOIN bronze.orange_book ob ON LOWER(ma.alias_name) = LOWER(ob.ingredient)
WHERE m.needs_review = FALSE
  AND ob.patent_number IS NOT NULL

ORDER BY molecule_id, evidence_date DESC NULLS LAST
