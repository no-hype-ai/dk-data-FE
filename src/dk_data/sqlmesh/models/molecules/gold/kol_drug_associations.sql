-- SQLMesh Model: Gold KOL Drug Associations
-- Maps researchers to molecules via clinical trials, publications, and grants
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name hcp_gold.kol_drug_associations,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (researcher_id, molecule_id)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (researcher_id, molecule_id))
    ),
    grain (researcher_id, molecule_id)
);

-- Trial-based associations (researcher as investigator/sponsor)
WITH trial_associations AS (
    SELECT
        r.id AS researcher_id,
        ct.molecule_id,
        m.canonical_name AS drug_name,
        'trial_investigator' AS association_type,
        COUNT(DISTINCT ct.nct_id) AS evidence_count
    FROM hcp_silver.researchers r
    JOIN mol_silver.clinical_trials ct
        ON ct.lead_sponsor_name ILIKE '%' || r.family_name || '%'
    JOIN mol_silver.molecules m
        ON ct.molecule_id = m.molecule_id
    WHERE ct.molecule_id IS NOT NULL
    GROUP BY r.id, ct.molecule_id, m.canonical_name
),

-- Publication-based associations (researcher authored papers mentioning molecule)
publication_associations AS (
    SELECT
        r.id AS researcher_id,
        mp.molecule_id,
        m.canonical_name AS drug_name,
        'publication_author' AS association_type,
        COUNT(DISTINCT p.doi) AS evidence_count
    FROM hcp_silver.researchers r
    JOIN mol_silver.publications p
        ON p.first_author_name ILIKE '%' || r.family_name || '%'
    JOIN mol_silver.molecule_publications mp
        ON mp.publication_id = p.id
    JOIN mol_silver.molecules m
        ON mp.molecule_id = m.molecule_id
    WHERE mp.molecule_id IS NOT NULL
    GROUP BY r.id, mp.molecule_id, m.canonical_name
),

-- Combine all association types per researcher-molecule pair
combined AS (
    SELECT researcher_id, molecule_id, drug_name, association_type, evidence_count
    FROM trial_associations
    UNION ALL
    SELECT researcher_id, molecule_id, drug_name, association_type, evidence_count
    FROM publication_associations
),

aggregated AS (
    SELECT
        researcher_id,
        molecule_id,
        MAX(drug_name) AS drug_name,
        ARRAY_AGG(DISTINCT association_type) AS association_types,
        SUM(evidence_count) AS evidence_count
    FROM combined
    GROUP BY researcher_id, molecule_id
)

SELECT
    gen_random_uuid() AS id,
    researcher_id,
    molecule_id,
    drug_name,
    association_types,
    evidence_count,
    NOW() AS created_at,
    NOW() AS updated_at
FROM aggregated;
