-- SQLMesh Model: Silver Journal RSS Articles
-- Promotes mol_bronze.journal_rss into mol_silver.journal_rss with molecule_id linkage.
-- Entity linking: WHO INN name match in article title + abstract (FR-035, T135).
-- Complements mol_silver.publications (OpenAlex/EuropePMC) with journal RSS feeds.
--
-- FR-035 implementation:
--   inn_set CTE: compile normalized INN names at query-time from mol_bronze.who_inn.
--   molecule_id: equi-join article title/abstract tokens (word-split >= 5 chars) against
--   mol_silver.molecule_names where normalized_name is in inn_set.
--   This ensures only WHO-registered INN names are matched (not arbitrary trade names).
--   No LLM calls; all linkage is structural/terminological.
--
-- T135: Replaced S3 correlated scalar subquery with LEFT JOIN LATERAL + token equi-join.
--       Token split uses ANY(ARRAY(...)) — equi-join, no leading-wildcard LIKE (no S2).
-- T118 verified: rewrite uses hub equi-join, zero S1-S5 antipatterns per test_silver_antipatterns.py

MODEL (
    name mol_silver.journal_rss,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key article_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (article_id))
    ),
    grain article_id
);

-- Deduplicate by article_id before MERGE.
-- Bronze may contain multiple rows for the same article (re-ingested from overlapping feed windows).
-- DISTINCT ON (article_id) keeps the most recently updated record per unique article.
WITH deduped_bronze AS (
    SELECT DISTINCT ON (article_id)
        article_id, title, link, doi, feed_source, abstract, authors, pub_date, categories, source_updated_at
    FROM mol_bronze.journal_rss
    WHERE article_id IS NOT NULL AND title IS NOT NULL
    ORDER BY article_id, source_updated_at DESC NULLS LAST
),

-- FR-035: compile WHO INN name set at query-time from mol_bronze.who_inn.
-- Normalized form strips non-alnum characters and lowercases — same normalization as
-- mol_silver.molecule_names.normalized_name, enabling equi-join matching.
inn_set AS (
    SELECT LOWER(REGEXP_REPLACE(TRIM(inn_name), '[^a-zA-Z0-9]', '', 'g')) AS normalized_inn
    FROM mol_bronze.who_inn
    WHERE inn_name IS NOT NULL
      AND LENGTH(TRIM(inn_name)) >= 5
)

SELECT
    gen_random_uuid()                                   AS id,
    -- Entity link: match article title+abstract words against WHO INN names via molecule_names hub.
    -- Strategy: split title||abstract on word boundaries, normalize each token, equi-join to
    -- mol_silver.molecule_names where normalized_name is a registered WHO INN (in inn_set).
    -- Tokens < 5 chars excluded to prevent false positives on short names.
    -- No leading-wildcard LIKE (no S2); no correlated scalar subquery (no S3).
    inn_link.molecule_id                                AS molecule_id,
    b.article_id,
    b.title,
    b.link                                              AS url,
    b.doi,
    b.feed_source                                       AS journal_name,
    b.abstract,
    b.authors,
    b.pub_date                                          AS publication_date,
    b.categories,
    'journal_rss'                                       AS source,
    b.source_updated_at,
    NOW()                                               AS created_at

FROM deduped_bronze b

-- FR-035: WHO INN molecule linkage via token equi-join (no LIKE wildcards)
LEFT JOIN LATERAL (
    SELECT mn.molecule_id
    FROM regexp_split_to_table(
        LOWER(b.title || ' ' || COALESCE(b.abstract, '')),
        '[^a-zA-Z0-9]+'
    ) AS tok(word)
    JOIN inn_set ON inn_set.normalized_inn = tok.word
    JOIN mol_silver.molecule_names mn ON mn.normalized_name = tok.word
    WHERE LENGTH(tok.word) >= 5
    ORDER BY LENGTH(tok.word) DESC
    LIMIT 1
) inn_link ON TRUE;
