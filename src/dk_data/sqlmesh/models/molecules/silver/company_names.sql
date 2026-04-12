-- T037: mol_silver.company_names — company name index
-- Canonical + alternative names, trade names, former names.

MODEL (
    name mol_silver.company_names,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (normalized_name, company_id, source)
    ),
    grain (normalized_name, company_id, source),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

WITH fin_names AS (
    SELECT
        LOWER(TRIM(REGEXP_REPLACE(company_name, '\s*(Inc\.|Corp\.|Ltd\.|AG|SA|LLC|GmbH|PLC|SE|NV|BV)\s*$', '', 'gi'))) AS normalized_name,
        ('x' || substr(md5(COALESCE(cik, LOWER(REGEXP_REPLACE(company_name, '\s*(Inc\.|Corp\.|Ltd\.|AG|SA|LLC|GmbH|PLC|SE|NV|BV)\s*$', '', 'gi')))), 1, 16))::bit(64)::bigint AS company_id,
        'canonical'                                                              AS name_kind,
        'sec'                                                                    AS source,
        1.0                                                                      AS confidence,
        company_name                                                             AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.company_financials
    WHERE company_name IS NOT NULL
),

db_names AS (
    SELECT
        LOWER(TRIM(REGEXP_REPLACE(company_name, '\s*(Inc\.|Corp\.|Ltd\.|AG|SA|LLC|GmbH|PLC|SE|NV|BV)\s*$', '', 'gi'))) AS normalized_name,
        ('x' || substr(md5(LOWER(REGEXP_REPLACE(company_name, '\s*(Inc\.|Corp\.|Ltd\.|AG|SA|LLC|GmbH|PLC|SE|NV|BV)\s*$', '', 'gi'))), 1, 16))::bit(64)::bigint AS company_id,
        'canonical'                                                              AS name_kind,
        'drugbank'                                                               AS source,
        0.8                                                                      AS confidence,
        company_name                                                             AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM (
        SELECT DISTINCT manufacturer_name AS company_name, ingested_at
        FROM mol_bronze.drugbank
        WHERE manufacturer_name IS NOT NULL
    ) db_co
),

all_names AS (
    SELECT * FROM fin_names
    UNION ALL
    SELECT * FROM db_names
)

SELECT DISTINCT ON (normalized_name, company_id, source)
    normalized_name,
    company_id,
    name_kind,
    source,
    confidence,
    display_name,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM all_names
WHERE normalized_name IS NOT NULL
  AND company_id IS NOT NULL
ORDER BY normalized_name, company_id, source, first_seen_at ASC;

-- CREATE INDEX IF NOT EXISTS mol_silver_co_names_co_idx ON mol_silver.company_names (company_id);
-- CREATE INDEX IF NOT EXISTS mol_silver_co_names_gin_idx ON mol_silver.company_names USING GIN (normalized_name gin_trgm_ops);
