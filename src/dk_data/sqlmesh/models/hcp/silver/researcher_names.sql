-- T039a: hcp_silver.researcher_names — researcher name index
-- Full name variants for fuzzy resolution; includes name_kind = 'canonical' / 'display'.

MODEL (
    name hcp_silver.researcher_names,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (normalized_name, researcher_id, source)
    ),
    grain (normalized_name, researcher_id, source)
    ,
    -- T4: large input — raise work_mem to keep sorts in memory (per-session 256MB ceiling per FR-021b)
);

WITH orcid_names AS (
    SELECT
        LOWER(TRIM(COALESCE(full_name, display_name, orcid_id)))                AS normalized_name,
        ('x' || substr(md5(COALESCE(orcid_id, 'scopus:' || scopus_author_id, 'pubmed:' || pubmed_author_signature, LOWER(full_name || '|' || COALESCE(institution, '')))), 1, 16))::bit(64)::bigint AS researcher_id,
        'canonical'                                                              AS name_kind,
        'orcid'                                                                  AS source,
        1.0                                                                      AS confidence,
        COALESCE(full_name, display_name, orcid_id)                             AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.orcid
    WHERE COALESCE(full_name, display_name) IS NOT NULL
),

europepmc_names AS (
    SELECT
        LOWER(TRIM(CASE WHEN last_name IS NOT NULL THEN last_name || ', ' || first_name ELSE full_name END)) AS normalized_name,
        ('x' || substr(md5(COALESCE(orcid, 'pubmed_sig:' || LOWER(last_name || '_' || LEFT(first_name, 1)))), 1, 16))::bit(64)::bigint AS researcher_id,
        'canonical'                                                              AS name_kind,
        'europepmc'                                                              AS source,
        0.9                                                                      AS confidence,
        CASE WHEN last_name IS NOT NULL THEN last_name || ', ' || first_name ELSE full_name END AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.europepmc
    WHERE COALESCE(last_name, full_name) IS NOT NULL
),

all_names AS (
    SELECT * FROM orcid_names
    UNION ALL
    SELECT * FROM europepmc_names
)

SELECT DISTINCT ON (normalized_name, researcher_id, source)
    normalized_name,
    researcher_id,
    name_kind,
    source,
    confidence,
    display_name,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM all_names
WHERE normalized_name IS NOT NULL
  AND researcher_id IS NOT NULL
ORDER BY normalized_name, researcher_id, source, first_seen_at ASC;
