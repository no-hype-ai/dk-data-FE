-- T040: ip_silver.patents — patent hub (NEW)
-- Hub architecture: one row per unique patent, keyed by (jurisdiction, patent_number).
-- Sources: USPTO patents, EPO patents from bronze.
-- T117+T134: Added molecule_id via Orange Book LEFT JOIN LATERAL (FR-034).

MODEL (
    name ip_silver.patents,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key patent_id
    ),
    grain patent_id,
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
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
    d.patent_id,
    d.jurisdiction,
    d.patent_number,
    d.application_number,
    d.publication_number,
    d.pct_application_number,
    d.title,
    d.abstract,
    d.filing_date,
    d.grant_date,
    d.expiry_date,
    d.cpc_codes,
    d.ipc_codes,
    d.kind_code,
    d.status,
    COALESCE(d.first_seen_at, NOW()) AS first_seen_at,
    NOW()                             AS last_updated_at,
    -- molecule_id via Orange Book join (FR-034): match patent_number against ob.patent_no,
    -- then resolve to molecule via NDA application number in mol_silver.molecule_identifiers.
    -- LEFT JOIN LATERAL ensures LIMIT 1 prevents fan-out.
    ob_link.molecule_id               AS molecule_id
FROM deduped d

LEFT JOIN LATERAL (
    SELECT mi.molecule_id
    FROM mol_bronze.orange_book ob
    JOIN mol_silver.molecule_identifiers mi ON mi.source = 'nda' AND mi.identifier = ob.appl_no
    WHERE ob.patent_no = d.patent_number
       OR ob.patent_no = REGEXP_REPLACE(d.patent_number, '^US0*', '')
    ORDER BY mi.molecule_id
    LIMIT 1
) ob_link ON TRUE;

-- CREATE INDEX IF NOT EXISTS ip_silver_pat_filing_idx ON ip_silver.patents (filing_date);
-- CREATE INDEX IF NOT EXISTS ip_silver_pat_cpc_gin_idx ON ip_silver.patents USING GIN (cpc_codes);
-- CREATE INDEX IF NOT EXISTS ip_silver_pat_title_gin_idx ON ip_silver.patents USING GIN (LOWER(title) gin_trgm_ops);
