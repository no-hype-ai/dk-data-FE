-- T039a: hcp_silver.researcher_affiliations — researcher institution affiliations
-- Compound PK: (researcher_id, institution_name, COALESCE(first_year, 0)).
-- When affiliation_type='industry', company_id FK resolves to mol_silver.companies.

MODEL (
    name hcp_silver.researcher_affiliations,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (researcher_id, institution_name, affiliation_year_key)
    ),
    grain (researcher_id, institution_name, affiliation_year_key),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

WITH orcid_affiliations AS (
    SELECT
        ('x' || substr(md5(COALESCE(o.orcid_id, 'scopus:' || o.scopus_author_id, 'pubmed:' || o.pubmed_author_signature, LOWER(o.full_name || '|' || COALESCE(o.institution, '')))), 1, 16))::bit(64)::bigint AS researcher_id,
        COALESCE(NULLIF(o.institution, ''), NULLIF(o.affiliation, ''))          AS institution_name,
        COALESCE(o.affiliation_country, o.country)                              AS institution_country,
        CASE
            WHEN o.affiliation_type IN ('industry', 'pharma', 'biotech') THEN 'industry'
            WHEN o.affiliation_type IN ('academic', 'university') THEN 'academic'
            WHEN o.affiliation_type IN ('hospital', 'medical_center') THEN 'hospital'
            WHEN o.affiliation_type IN ('government', 'nih', 'nih_funded') THEN 'government'
            ELSE 'unknown'
        END                                                                      AS affiliation_type,
        NULL::bigint                                                             AS company_id,
        o.affiliation_start_year                                                 AS first_year,
        o.affiliation_end_year                                                   AS last_year,
        (o.affiliation_end_year IS NULL OR o.affiliation_end_year >= EXTRACT(YEAR FROM NOW())::int) AS is_current,
        COALESCE(o.affiliation_start_year, 0)                                   AS affiliation_year_key,
        o.ingested_at                                                            AS first_seen_at
    FROM mol_bronze.orcid o
    WHERE COALESCE(o.institution, o.affiliation) IS NOT NULL
)

SELECT DISTINCT ON (researcher_id, institution_name, affiliation_year_key)
    researcher_id,
    institution_name,
    institution_country,
    affiliation_type,
    company_id,
    first_year,
    last_year,
    COALESCE(is_current, FALSE)    AS is_current,
    affiliation_year_key,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM orcid_affiliations
WHERE researcher_id IS NOT NULL
  AND institution_name IS NOT NULL
ORDER BY researcher_id, institution_name, affiliation_year_key, first_seen_at ASC;

-- CREATE INDEX IF NOT EXISTS hcp_silver_res_aff_inst_idx ON hcp_silver.researcher_affiliations (institution_name);
-- CREATE INDEX IF NOT EXISTS hcp_silver_res_aff_co_idx ON hcp_silver.researcher_affiliations (company_id) WHERE company_id IS NOT NULL;
