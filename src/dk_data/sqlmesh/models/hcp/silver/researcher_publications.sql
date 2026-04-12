-- T039a: hcp_silver.researcher_publications — researcher to publication bridge
-- One row per (researcher_id, pmid/doi/pmcid). Populated from PubMed / EuropePMC.
-- Compound PK: (researcher_id, COALESCE(pmid, doi, pmcid)).

MODEL (
    name hcp_silver.researcher_publications,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (researcher_id, pub_key)
    ),
    grain (researcher_id, pub_key)
    ,
    -- T4: large input — raise work_mem to keep sorts in memory (per-session 256MB ceiling per FR-021b)
);

WITH europepmc_pubs AS (
    SELECT
        ('x' || substr(md5(COALESCE(e.orcid, 'pubmed_sig:' || LOWER(e.last_name || '_' || LEFT(e.first_name, 1)))), 1, 16))::bit(64)::bigint AS researcher_id,
        COALESCE(e.pmid, e.doi, e.pmcid)                                        AS pub_key,
        NULLIF(e.pmid, '')                                                       AS pmid,
        NULLIF(e.doi, '')                                                        AS doi,
        NULLIF(e.pmcid, '')                                                      AS pmcid,
        e.publication_year,
        NULLIF(e.author_position, '')                                            AS author_position,
        NULLIF(e.journal_name, '')                                               AS journal_name,
        e.ingested_at                                                            AS first_seen_at
    FROM mol_bronze.europepmc e
    WHERE COALESCE(e.orcid, e.last_name) IS NOT NULL
      AND COALESCE(e.pmid, e.doi, e.pmcid) IS NOT NULL
)

SELECT DISTINCT ON (researcher_id, pub_key)
    researcher_id,
    pub_key,
    pmid,
    doi,
    pmcid,
    publication_year,
    author_position,
    journal_name,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM europepmc_pubs
WHERE researcher_id IS NOT NULL
  AND pub_key IS NOT NULL
ORDER BY researcher_id, pub_key, first_seen_at ASC;

-- CREATE INDEX IF NOT EXISTS hcp_silver_res_pub_pmid_idx ON hcp_silver.researcher_publications (pmid) WHERE pmid IS NOT NULL;
-- CREATE INDEX IF NOT EXISTS hcp_silver_res_pub_doi_idx ON hcp_silver.researcher_publications (doi) WHERE doi IS NOT NULL;
-- CREATE INDEX IF NOT EXISTS hcp_silver_res_pub_year_idx ON hcp_silver.researcher_publications (publication_year DESC);
