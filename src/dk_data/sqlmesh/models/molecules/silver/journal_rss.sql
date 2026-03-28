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

SELECT
    gen_random_uuid()                                   AS id,
    -- Entity link: find molecule by name mention in article title.
    -- NULL for articles with no known molecule mention. Length guard prevents false positives.
    m.molecule_id,
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

FROM mol_bronze.journal_rss b
LEFT JOIN mol_silver.molecules m
       ON LOWER(b.title) LIKE '%' || LOWER(m.canonical_name) || '%'
      AND LENGTH(m.canonical_name) > 4
WHERE b.article_id IS NOT NULL
  AND b.title IS NOT NULL;
