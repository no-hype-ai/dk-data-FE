-- SQLMesh Model: Silver Journal RSS Articles
-- Promotes mol_bronze.journal_rss into mol_silver.journal_rss with molecule_id linkage.
-- Entity linking: canonical_name substring match in article title.
-- Complements mol_silver.publications (OpenAlex/EuropePMC) with journal RSS feeds.

MODEL (
    name mol_silver.journal_rss,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key entry_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (entry_id))
    ),
    grain entry_id
);

SELECT
    gen_random_uuid()                                   AS id,
    -- Entity link: find molecule by name mention in article title.
    -- NULL for articles with no known molecule mention. Length guard prevents false positives.
    m.molecule_id,
    b.entry_id,
    b.title,
    b.link                                              AS url,
    b.doi,
    b.journal_name,
    b.summary                                           AS abstract,
    b.authors,
    -- Normalise pub_date (RSS feeds use RFC 822 or ISO 8601)
    CASE
        WHEN b.pub_date ~ '^\d{4}-\d{2}-\d{2}'
        THEN TO_DATE(LEFT(b.pub_date, 10), 'YYYY-MM-DD')
        WHEN b.pub_date ~ '^\d{4}'
        THEN TO_DATE(LEFT(b.pub_date, 4), 'YYYY')
        ELSE NULL
    END                                                 AS publication_date,
    'journal_rss'                                       AS source,
    b.source_updated_at,
    NOW()                                               AS created_at

FROM mol_bronze.journal_rss b
LEFT JOIN mol_silver.molecules m
       ON LOWER(b.title) LIKE '%' || LOWER(m.canonical_name) || '%'
      AND LENGTH(m.canonical_name) > 4
WHERE b.entry_id IS NOT NULL
  AND b.title IS NOT NULL;
