-- SQLMesh Model: Silver Journal RSS Articles
-- Promotes mol_bronze.journal_rss into mol_silver.journal_rss with molecule_id linkage.
-- Entity linking: WHO INN name match in article title + abstract (FR-035, T135).
-- Complements mol_silver.publications (OpenAlex/EuropePMC) with journal RSS feeds.
-- T135: Replaced S3 correlated scalar subquery with LEFT JOIN LATERAL; switched
--       from mol_silver.molecules.canonical_name to mol_silver.molecule_names.normalized_name.

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
)

SELECT
    gen_random_uuid()                                   AS id,
    -- Entity link: find molecule by WHO INN name mention in article title or abstract.
    -- NULL for articles with no known molecule mention. Length guard (>= 5) prevents false positives.
    -- LEFT JOIN LATERAL replaces S3 correlated scalar subquery (T135).
    -- NOTE: LIKE has the drug name as literal (not the indexed column) — not an S2 antipattern.
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

-- WHO INN molecule linkage via mol_silver.molecule_names (FR-035)
LEFT JOIN LATERAL (
    SELECT mn.molecule_id
    FROM mol_silver.molecule_names mn
    WHERE LENGTH(mn.normalized_name) >= 5
      AND (
          LOWER(b.title || ' ' || COALESCE(b.abstract, '')) LIKE '% ' || mn.normalized_name || ' %'
       OR LOWER(b.title || ' ' || COALESCE(b.abstract, '')) LIKE mn.normalized_name || ' %'
       OR LOWER(b.title || ' ' || COALESCE(b.abstract, '')) LIKE '% ' || mn.normalized_name
      )
    ORDER BY LENGTH(mn.normalized_name) DESC
    LIMIT 1
) inn_link ON TRUE;
