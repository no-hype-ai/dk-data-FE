-- T037: mol_silver.companies — pharmaceutical / biotech company hub
-- Canonical name is normalized (lowercase, stripped of Inc./Corp./Ltd./AG/SA).
-- CIK is the SEC Central Index Key (unique per public company).

MODEL (
    name mol_silver.companies,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key company_id
    ),
    grain company_id
);

-- Hash determinism (FR-014): both source CTEs MUST hash on the same canonical key.
-- CIK is stored in mol_silver.company_identifiers as an alternate id; it is NOT part
-- of the hub product_id derivation, otherwise FDA-with-CIK and DrugBank-without-CIK
-- rows for the same company would land in two distinct hub rows.
WITH fda_companies AS (
    SELECT
        ('x' || substr(md5(LOWER(REGEXP_REPLACE(company_name, '\s*(Inc\.|Corp\.|Ltd\.|AG|SA|LLC|GmbH|PLC|SE|NV|BV)\s*$', '', 'gi'))), 1, 16))::bit(64)::bigint AS company_id,
        cik,
        ticker,
        LOWER(REGEXP_REPLACE(company_name, '\s*(Inc\.|Corp\.|Ltd\.|AG|SA|LLC|GmbH|PLC|SE|NV|BV)\s*$', '', 'gi')) AS canonical_name,
        country,
        1                                                                        AS src_priority,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.company_financials
    WHERE company_name IS NOT NULL
),

drugbank_companies AS (
    SELECT
        ('x' || substr(md5(LOWER(REGEXP_REPLACE(company_name, '\s*(Inc\.|Corp\.|Ltd\.|AG|SA|LLC|GmbH|PLC|SE|NV|BV)\s*$', '', 'gi'))), 1, 16))::bit(64)::bigint AS company_id,
        NULL::text                                                               AS cik,
        NULL::text                                                               AS ticker,
        LOWER(REGEXP_REPLACE(company_name, '\s*(Inc\.|Corp\.|Ltd\.|AG|SA|LLC|GmbH|PLC|SE|NV|BV)\s*$', '', 'gi')) AS canonical_name,
        country,
        2                                                                        AS src_priority,
        ingested_at                                                              AS first_seen_at
    FROM (
        SELECT DISTINCT manufacturer_name AS company_name, manufacturer_country AS country, ingested_at
        FROM mol_bronze.drugbank
        WHERE manufacturer_name IS NOT NULL
    ) db_companies
),

all_companies AS (
    SELECT * FROM fda_companies
    UNION ALL
    SELECT * FROM drugbank_companies
),

deduped AS (
    SELECT DISTINCT ON (company_id)
        company_id,
        cik,
        ticker,
        canonical_name,
        country,
        first_seen_at
    FROM all_companies
    WHERE canonical_name IS NOT NULL
    ORDER BY company_id, src_priority ASC
)

SELECT
    company_id,
    cik,
    ticker,
    canonical_name,
    country,
    COALESCE(first_seen_at, NOW()) AS first_seen_at,
    NOW()                          AS last_updated_at
FROM deduped;

-- CREATE INDEX IF NOT EXISTS mol_silver_co_canonical_idx ON mol_silver.companies (canonical_name);
-- CREATE INDEX IF NOT EXISTS mol_silver_co_gin_idx ON mol_silver.companies USING GIN (LOWER(canonical_name) gin_trgm_ops);
