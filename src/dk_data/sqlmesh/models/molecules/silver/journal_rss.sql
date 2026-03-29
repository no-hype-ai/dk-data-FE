-- SQLMesh Model: Silver Journal RSS Articles
-- Promotes mol_bronze.journal_rss into mol_silver.journal_rss with molecule_id linkage.
-- Entity linking: canonical_name substring match in article title.
-- Complements mol_silver.publications (OpenAlex/EuropePMC) with journal RSS feeds.

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
        article_id, title, link, doi, feed_source, abstract, authors, pub_date, source_updated_at
    FROM mol_bronze.journal_rss
    WHERE article_id IS NOT NULL AND title IS NOT NULL
    ORDER BY article_id, source_updated_at DESC NULLS LAST
)

SELECT
    gen_random_uuid()                                   AS id,
    -- Entity link: find molecule by name mention in article title.
    -- NULL for articles with no known molecule mention. Length guard prevents false positives.
    -- Use DISTINCT ON here too to handle one article matching multiple molecules —
    -- we only store the best (longest canonical_name) match to preserve unique key.
    (
        SELECT m2.molecule_id
        FROM mol_silver.molecules m2
        WHERE LOWER(b.title) LIKE '%' || LOWER(m2.canonical_name) || '%'
          AND LENGTH(m2.canonical_name) > 4
        ORDER BY LENGTH(m2.canonical_name) DESC
        LIMIT 1
    )                                                   AS molecule_id,
    b.article_id,
    b.title,
    b.link                                              AS url,
    b.doi,
    b.feed_source                                       AS journal_name,
    b.abstract,
    b.authors,
    b.pub_date                                          AS publication_date,
    'journal_rss'                                       AS source,
    b.source_updated_at,
    NOW()                                               AS created_at

FROM deduped_bronze b;
