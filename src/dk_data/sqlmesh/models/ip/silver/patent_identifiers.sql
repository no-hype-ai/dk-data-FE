-- T040: ip_silver.patent_identifiers — patent identifier crosswalk
-- Covers: patent_number (by jurisdiction), application_number, publication_number, pct_number.

MODEL (
    name ip_silver.patent_identifiers,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (source, identifier)
    ),
    grain (source, identifier),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

WITH uspto_ids AS (
    SELECT
        'us_patent'                                                              AS source,
        patent_number                                                            AS identifier,
        ('x' || substr(md5('US:' || COALESCE(patent_number, application_number, publication_number)), 1, 16))::bit(64)::bigint AS patent_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM ip_bronze.uspto_patents
    WHERE patent_number IS NOT NULL

    UNION ALL

    SELECT
        'us_application'                                                         AS source,
        application_number                                                       AS identifier,
        ('x' || substr(md5('US:' || COALESCE(patent_number, application_number, publication_number)), 1, 16))::bit(64)::bigint AS patent_id,
        FALSE                                                                    AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM ip_bronze.uspto_patents
    WHERE application_number IS NOT NULL
),

epo_ids AS (
    SELECT
        'ep_patent'                                                              AS source,
        patent_number                                                            AS identifier,
        ('x' || substr(md5('EP:' || COALESCE(patent_number, application_number, publication_number)), 1, 16))::bit(64)::bigint AS patent_id,
        TRUE                                                                     AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM ip_bronze.epo_patents
    WHERE patent_number IS NOT NULL

    UNION ALL

    SELECT
        'ep_application'                                                         AS source,
        application_number                                                       AS identifier,
        ('x' || substr(md5('EP:' || COALESCE(patent_number, application_number, publication_number)), 1, 16))::bit(64)::bigint AS patent_id,
        FALSE                                                                    AS is_primary,
        ingested_at                                                              AS first_seen_at
    FROM ip_bronze.epo_patents
    WHERE application_number IS NOT NULL
),

all_ids AS (
    SELECT * FROM uspto_ids
    UNION ALL
    SELECT * FROM epo_ids
)

SELECT DISTINCT ON (source, identifier)
    source,
    identifier,
    patent_id,
    is_primary,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM all_ids
WHERE patent_id IS NOT NULL
ORDER BY source, identifier, first_seen_at ASC;

-- CREATE UNIQUE INDEX IF NOT EXISTS ip_silver_pat_ident_src_id_idx ON ip_silver.patent_identifiers (source, identifier);
-- CREATE INDEX IF NOT EXISTS ip_silver_pat_ident_pat_idx ON ip_silver.patent_identifiers (patent_id);
