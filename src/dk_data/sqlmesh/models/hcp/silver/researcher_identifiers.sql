-- T039a: hcp_silver.researcher_identifiers — researcher identifier crosswalk
-- Covers: orcid, scopus_author_id, pubmed_signature, researchgate_id, google_scholar_id.

MODEL (
    name hcp_silver.researcher_identifiers,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (source, identifier)
    ),
    grain (source, identifier)
    ,
    -- T4: large input — raise work_mem to keep sorts in memory (per-session 256MB ceiling per FR-021b)
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

WITH orcid_ids AS (
    SELECT
        'orcid'                                                                  AS source,
        orcid_id                                                                 AS identifier,
        ('x' || substr(md5(COALESCE(orcid_id, 'scopus:' || scopus_author_id, 'pubmed:' || pubmed_author_signature, LOWER(full_name || '|' || COALESCE(institution, '')))), 1, 16))::bit(64)::bigint AS researcher_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.orcid
    WHERE orcid_id IS NOT NULL

    UNION ALL

    SELECT
        'scopus_author_id'                                                       AS source,
        scopus_author_id                                                         AS identifier,
        ('x' || substr(md5(COALESCE(orcid_id, 'scopus:' || scopus_author_id, 'pubmed:' || pubmed_author_signature, LOWER(full_name || '|' || COALESCE(institution, '')))), 1, 16))::bit(64)::bigint AS researcher_id,
        FALSE                                                                    AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.orcid
    WHERE scopus_author_id IS NOT NULL
),

pubmed_sigs AS (
    SELECT
        'pubmed_signature'                                                       AS source,
        LOWER(last_name) || '_' || LOWER(LEFT(first_name, 1))                   AS identifier,
        ('x' || substr(md5(COALESCE(orcid, 'pubmed_sig:' || LOWER(last_name || '_' || LEFT(first_name, 1)))), 1, 16))::bit(64)::bigint AS researcher_id,
        FALSE                                                                    AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.europepmc
    WHERE last_name IS NOT NULL AND first_name IS NOT NULL
),

all_ids AS (
    SELECT * FROM orcid_ids
    UNION ALL
    SELECT * FROM pubmed_sigs
)

SELECT DISTINCT ON (source, identifier)
    source,
    identifier,
    researcher_id,
    is_primary,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM all_ids
WHERE researcher_id IS NOT NULL
  AND identifier IS NOT NULL
ORDER BY source, identifier, first_seen_at ASC;

-- CREATE UNIQUE INDEX IF NOT EXISTS hcp_silver_res_ident_src_id_idx ON hcp_silver.researcher_identifiers (source, identifier);
-- CREATE INDEX IF NOT EXISTS hcp_silver_res_ident_res_idx ON hcp_silver.researcher_identifiers (researcher_id);
