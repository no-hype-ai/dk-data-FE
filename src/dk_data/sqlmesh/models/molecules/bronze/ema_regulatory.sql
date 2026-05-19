-- SQLMesh Model: Bronze EMA Regulatory Documents
-- Transforms flat mol_raw.ema_regulatory typed table to Bronze typed columns.
-- mol_raw.ema_regulatory is a flat table populated by EMAFetcher
-- (src/dk_data/ingestion/sources/ema_regulatory.py), NOT the JSONB envelope
-- mol_raw.ema which is handled by bronze/ema.sql.
--
-- Columns in mol_raw.ema_regulatory:
--   document_id VARCHAR(100) NOT NULL UNIQUE
--   document_type VARCHAR(50)
--   product_name VARCHAR(500)
--   active_substance VARCHAR(500)
--   therapeutic_area VARCHAR(500)
--   decision_date DATE
--   decision_type VARCHAR(100)
--   document_url TEXT
--   summary TEXT
--   _loaded_at TIMESTAMPTZ NOT NULL
--   _source_file VARCHAR(500)
--   _source_hash VARCHAR(64)
--
-- Part of: 019-cms-puf-platform-reconciliation (bronze coverage gap fix)

MODEL (
    name mol_bronze.ema_regulatory,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key document_id
    ),
    cron '@weekly',
    audits (
        not_null(columns := (document_id)),
        unique_values(columns := (document_id))
    ),
    grain document_id
);

SELECT
    gen_random_uuid()                       AS id,

    -- Document identification (all raw column names preserved)
    document_id::TEXT                       AS document_id,
    document_type::TEXT                     AS document_type,

    -- Product details
    product_name::TEXT                      AS product_name,
    active_substance::TEXT                  AS active_substance,
    therapeutic_area::TEXT                  AS therapeutic_area,

    -- Regulatory decision
    decision_date::DATE                     AS decision_date,
    decision_type::TEXT                     AS decision_type,

    -- Document reference
    document_url::TEXT                      AS document_url,
    summary::TEXT                           AS summary,

    -- Source metadata
    _source_file::TEXT                      AS _source_file,
    _source_hash::TEXT                      AS _source_hash,

    -- Processing metadata
    'ema_regulatory'::TEXT                  AS source,
    _loaded_at::TIMESTAMPTZ                 AS source_updated_at,
    _loaded_at::TIMESTAMPTZ                 AS _loaded_at,
    FALSE                                   AS processed_to_silver,
    NOW()                                   AS _bronze_loaded_at

FROM mol_raw.ema_regulatory
WHERE
    document_id IS NOT NULL
    AND _loaded_at BETWEEN @start_dt AND @end_dt;
