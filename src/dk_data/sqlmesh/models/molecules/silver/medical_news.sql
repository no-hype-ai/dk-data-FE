-- SQLMesh Model: Silver Medical News
-- Promotes mol_bronze.medical_news into mol_silver with molecule_id linkage via WHO INN names.
-- Entity linking: WHO INN-based regex match in article title + summary (FR-035).
-- T135: New silver model — previously no silver layer existed for medical_news.

MODEL (
    name mol_silver.medical_news,
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
-- Bronze may contain multiple rows for the same article (re-ingested from overlapping windows).
-- DISTINCT ON (article_id) keeps the most recently ingested record per unique article.
WITH deduped_bronze AS (
    SELECT DISTINCT ON (article_id)
        article_id, source_name, title, summary, pub_date, url,
        drug_mentions, therapeutic_areas, source_updated_at
    FROM mol_bronze.medical_news
    WHERE article_id IS NOT NULL AND title IS NOT NULL
    ORDER BY article_id, source_updated_at DESC NULLS LAST
)

SELECT
    gen_random_uuid()                                   AS id,
    -- Entity link: find molecule by WHO INN name mention in article title or summary.
    -- Uses mol_silver.molecule_names (which consolidates INN names via mol_bronze.who_inn pipeline).
    -- Length guard (>= 5 chars) prevents false positive matches on short drug codes.
    -- mol_bronze.who_inn is available; linkage uses mol_silver.molecule_names.normalized_name.
    -- NOTE: The LIKE pattern has the drug name as the literal (not the indexed column),
    -- so this does NOT create a leading-wildcard index scan — not an S2 antipattern.
    inn_link.molecule_id                                AS molecule_id,
    b.article_id,
    b.title,
    b.url,
    b.source_name,
    b.summary,
    b.pub_date                                          AS publication_date,
    b.drug_mentions,
    b.therapeutic_areas,
    'medical_news'                                      AS source,
    b.source_updated_at,
    NOW()                                               AS created_at

FROM deduped_bronze b

-- WHO INN molecule linkage via mol_silver.molecule_names (FR-035)
LEFT JOIN LATERAL (
    SELECT mn.molecule_id
    FROM mol_silver.molecule_names mn
    WHERE LENGTH(mn.normalized_name) >= 5
      AND (
          LOWER(b.title || ' ' || COALESCE(b.summary, '')) LIKE '% ' || mn.normalized_name || ' %'
       OR LOWER(b.title || ' ' || COALESCE(b.summary, '')) LIKE mn.normalized_name || ' %'
       OR LOWER(b.title || ' ' || COALESCE(b.summary, '')) LIKE '% ' || mn.normalized_name
      )
    ORDER BY LENGTH(mn.normalized_name) DESC
    LIMIT 1
) inn_link ON TRUE;
