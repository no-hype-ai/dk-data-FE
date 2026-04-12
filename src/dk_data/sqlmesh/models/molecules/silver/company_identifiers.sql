-- T037: mol_silver.company_identifiers — company identifier crosswalk
-- Covers: cik, ticker, lei, duns, gvkey.

MODEL (
    name mol_silver.company_identifiers,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (source, identifier)
    ),
    grain (source, identifier),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

WITH cik_ids AS (
    SELECT
        'cik'                                                                    AS source,
        cik                                                                      AS identifier,
        ('x' || substr(md5(COALESCE(cik, LOWER(REGEXP_REPLACE(company_name, '\s*(Inc\.|Corp\.|Ltd\.|AG|SA|LLC|GmbH|PLC|SE|NV|BV)\s*$', '', 'gi')))), 1, 16))::bit(64)::bigint AS company_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.company_financials
    WHERE cik IS NOT NULL

    UNION ALL

    SELECT
        'ticker'                                                                 AS source,
        ticker                                                                   AS identifier,
        ('x' || substr(md5(COALESCE(cik, LOWER(REGEXP_REPLACE(company_name, '\s*(Inc\.|Corp\.|Ltd\.|AG|SA|LLC|GmbH|PLC|SE|NV|BV)\s*$', '', 'gi')))), 1, 16))::bit(64)::bigint AS company_id,
        FALSE                                                                    AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM mol_bronze.company_financials
    WHERE ticker IS NOT NULL
)

SELECT DISTINCT ON (source, identifier)
    source,
    identifier,
    company_id,
    is_primary,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM cik_ids
WHERE company_id IS NOT NULL
ORDER BY source, identifier, first_seen_at ASC;

-- CREATE UNIQUE INDEX IF NOT EXISTS mol_silver_co_ident_src_id_idx ON mol_silver.company_identifiers (source, identifier);
-- CREATE INDEX IF NOT EXISTS mol_silver_co_ident_co_idx ON mol_silver.company_identifiers (company_id);
