-- T040: ip_silver.patents — patent hub (NEW)
-- Hub architecture: one row per unique patent, keyed by (jurisdiction, patent_number).
-- Sources: USPTO patents, EPO patents from bronze.

MODEL (
    name ip_silver.patents,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key patent_id
    ),
    grain patent_id
);

WITH uspto_patents AS (
    SELECT
        ('x' || substr(md5('US:' || COALESCE(patent_number, application_number, publication_number)), 1, 16))::bit(64)::bigint AS patent_id,
        'US'                                                                     AS jurisdiction,
        NULLIF(patent_number, '')                                                AS patent_number,
        NULLIF(application_number, '')                                           AS application_number,
        NULLIF(publication_number, '')                                           AS publication_number,
        NULL::text                                                               AS pct_application_number,
        NULLIF(title, '')                                                        AS title,
        NULLIF(abstract, '')                                                     AS abstract,
        filing_date::date                                                        AS filing_date,
        grant_date::date                                                         AS grant_date,
        expiry_date::date                                                        AS expiry_date,
        cpc_codes,
        ipc_codes,
        NULLIF(kind_code, '')                                                    AS kind_code,
        NULLIF(status, '')                                                       AS status,
        1                                                                        AS src_priority,
        ingested_at                                                              AS first_seen_at
    FROM ip_bronze.uspto_patents
    WHERE COALESCE(patent_number, application_number, publication_number) IS NOT NULL
),

epo_patents AS (
    SELECT
        ('x' || substr(md5('EP:' || COALESCE(patent_number, application_number, publication_number)), 1, 16))::bit(64)::bigint AS patent_id,
        'EP'                                                                     AS jurisdiction,
        NULLIF(patent_number, '')                                                AS patent_number,
        NULLIF(application_number, '')                                           AS application_number,
        NULLIF(publication_number, '')                                           AS publication_number,
        NULLIF(pct_application_number, '')                                       AS pct_application_number,
        NULLIF(title, '')                                                        AS title,
        NULLIF(abstract, '')                                                     AS abstract,
        filing_date::date                                                        AS filing_date,
        grant_date::date                                                         AS grant_date,
        expiry_date::date                                                        AS expiry_date,
        cpc_codes,
        ipc_codes,
        NULLIF(kind_code, '')                                                    AS kind_code,
        NULLIF(status, '')                                                       AS status,
        2                                                                        AS src_priority,
        ingested_at                                                              AS first_seen_at
    FROM ip_bronze.epo_patents
    WHERE COALESCE(patent_number, application_number, publication_number) IS NOT NULL
),

all_patents AS (
    SELECT * FROM uspto_patents
    UNION ALL
    SELECT * FROM epo_patents
),

deduped AS (
    SELECT DISTINCT ON (patent_id)
        patent_id,
        jurisdiction,
        patent_number,
        application_number,
        publication_number,
        pct_application_number,
        title,
        abstract,
        filing_date,
        grant_date,
        expiry_date,
        cpc_codes,
        ipc_codes,
        kind_code,
        status,
        first_seen_at
    FROM all_patents
    ORDER BY patent_id, src_priority ASC
)

SELECT
    patent_id,
    jurisdiction,
    patent_number,
    application_number,
    publication_number,
    pct_application_number,
    title,
    abstract,
    filing_date,
    grant_date,
    expiry_date,
    cpc_codes,
    ipc_codes,
    kind_code,
    status,
    COALESCE(first_seen_at, NOW()) AS first_seen_at,
    NOW()                          AS last_updated_at
FROM deduped;

-- CREATE INDEX IF NOT EXISTS ip_silver_pat_filing_idx ON ip_silver.patents (filing_date);
-- CREATE INDEX IF NOT EXISTS ip_silver_pat_cpc_gin_idx ON ip_silver.patents USING GIN (cpc_codes);
-- CREATE INDEX IF NOT EXISTS ip_silver_pat_title_gin_idx ON ip_silver.patents USING GIN (LOWER(title) gin_trgm_ops);
