-- T039a: hcp_silver.researchers — healthcare researcher / KOL hub (FR-011b)
-- Hub architecture: one row per unique researcher, keyed by ORCID iD (primary).
-- Identity: ORCID → Scopus Author ID → PubMed author signature → name + institution.

MODEL (
    name hcp_silver.researchers,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key researcher_id
    ),
    audits (
        -- Entity-resolution key integrity (FR-011b / FR-014 Silver Hub Architecture).
        -- canonical_full_name is WHERE-clause-enforced in the final SELECT.
        not_null(columns := (researcher_id, canonical_full_name)),
        unique_values(columns := (researcher_id))
    ),
    grain researcher_id

);

-- Hash determinism (FR-014): both branches must derive researcher_id from the same
-- canonical key expression. The pubmed signature is normalized identically here and
-- in europepmc_researchers; the prefix label MUST also match.
WITH orcid_researchers AS (
    SELECT
        ('x' || substr(md5(COALESCE(orcid_id, 'scopus:' || scopus_author_id, 'pubmed_sig:' || LOWER(pubmed_author_signature), LOWER(full_name || '|' || COALESCE(institution, '')))), 1, 16))::bit(64)::bigint AS researcher_id,
        NULLIF(orcid_id, '')                                                     AS orcid_id,
        NULLIF(scopus_author_id, '')                                             AS scopus_author_id,
        NULLIF(pubmed_author_signature, '')                                      AS pubmed_author_signature,
        NULL::text                                                               AS researchgate_id,
        NULL::text                                                               AS google_scholar_id,
        COALESCE(full_name, display_name, orcid_id)                             AS canonical_full_name,
        NULLIF(affiliation, '')                                                  AS primary_affiliation_institution,
        NULLIF(country, '')                                                      AS primary_affiliation_country,
        NULL::int                                                                AS h_index,
        NULLIF(first_publication_year, 0)                                        AS first_publication_year,
        NULLIF(last_publication_year, 0)                                         AS last_publication_year,
        TRUE                                                                     AS is_active,
        1                                                                        AS src_priority,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.orcid
    WHERE COALESCE(orcid_id, full_name) IS NOT NULL
),

europepmc_researchers AS (
    SELECT
        ('x' || substr(md5(COALESCE(orcid, 'pubmed_sig:' || LOWER(last_name || '_' || LEFT(first_name, 1)))), 1, 16))::bit(64)::bigint AS researcher_id,
        NULLIF(orcid, '')                                                        AS orcid_id,
        NULL::text                                                               AS scopus_author_id,
        CASE WHEN last_name IS NOT NULL AND first_name IS NOT NULL
             THEN LOWER(last_name) || '_' || LOWER(LEFT(first_name, 1))
             ELSE NULL END                                                       AS pubmed_author_signature,
        NULL::text                                                               AS researchgate_id,
        NULL::text                                                               AS google_scholar_id,
        CASE WHEN last_name IS NOT NULL THEN last_name || ', ' || first_name
             ELSE full_name END                                                  AS canonical_full_name,
        NULLIF(affiliation, '')                                                  AS primary_affiliation_institution,
        NULLIF(country, '')                                                      AS primary_affiliation_country,
        NULL::int                                                                AS h_index,
        NULL::int                                                                AS first_publication_year,
        NULL::int                                                                AS last_publication_year,
        TRUE                                                                     AS is_active,
        2                                                                        AS src_priority,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.europepmc
    WHERE COALESCE(orcid, last_name, full_name) IS NOT NULL
),

all_researchers AS (
    SELECT * FROM orcid_researchers
    UNION ALL
    SELECT * FROM europepmc_researchers
),

deduped AS (
    SELECT DISTINCT ON (researcher_id)
        researcher_id,
        orcid_id,
        scopus_author_id,
        pubmed_author_signature,
        researchgate_id,
        google_scholar_id,
        canonical_full_name,
        primary_affiliation_institution,
        primary_affiliation_country,
        h_index,
        first_publication_year,
        last_publication_year,
        is_active,
        first_seen_at
    FROM all_researchers
    ORDER BY researcher_id, src_priority ASC
)

SELECT
    researcher_id,
    orcid_id,
    scopus_author_id,
    pubmed_author_signature,
    researchgate_id,
    google_scholar_id,
    canonical_full_name,
    primary_affiliation_institution,
    primary_affiliation_country,
    h_index,
    first_publication_year,
    last_publication_year,
    COALESCE(is_active, TRUE)      AS is_active,
    COALESCE(first_seen_at, NOW()) AS first_seen_at,
    NOW()                          AS last_updated_at
FROM deduped
WHERE canonical_full_name IS NOT NULL;

-- CREATE INDEX IF NOT EXISTS hcp_silver_res_canonical_idx ON hcp_silver.researchers (canonical_full_name);
-- CREATE INDEX IF NOT EXISTS hcp_silver_res_gin_idx ON hcp_silver.researchers USING GIN (LOWER(canonical_full_name) gin_trgm_ops);
-- CREATE INDEX IF NOT EXISTS hcp_silver_res_institution_idx ON hcp_silver.researchers (primary_affiliation_institution);
-- CREATE INDEX IF NOT EXISTS hcp_silver_res_pub_year_idx ON hcp_silver.researchers (last_publication_year DESC);
