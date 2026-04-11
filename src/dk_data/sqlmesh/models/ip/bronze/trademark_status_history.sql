-- SQLMesh Model: Bronze Trademark Status History
-- Promotes mol_raw.trademark_status_history (audit trail written by USPTO/EUIPO loaders)
-- to a typed bronze layer with molecule linkage hooks.
--
-- Source: mol_raw.trademark_status_history (canonical since migration 137)
--   Written by: load_uspto_trademarks.py and load_euipo_trademarks.py
--   on every ingest when a trademark status change is detected.
-- Grain: (trademark_identifier, source, changed_at)
--
-- Ref: issue #171 M5, #196 C3
-- Migrated from mol_bronze → ip_bronze by 001-silver-medallion-rebuild (FR-006d)

MODEL (
    name ip_bronze.trademark_status_history,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (trademark_identifier, source, changed_at)
    ),
    cron '@daily',
    audits (
        not_null(columns := (trademark_identifier, source, new_status, changed_at)),
        unique_values(columns := (trademark_identifier, source, changed_at))
    ),
    grain (trademark_identifier, source, changed_at)
);

SELECT
    gen_random_uuid()           AS id,
    h.trademark_identifier,
    h.source,
    h.old_status,
    h.new_status,
    h.changed_at,
    -- Classify transition type
    CASE
        WHEN h.old_status IS NULL                              THEN 'initial_registration'
        WHEN h.new_status ILIKE '%abandon%'
          OR h.new_status ILIKE '%cancel%'
          OR h.new_status ILIKE '%expire%'                    THEN 'lapsed'
        WHEN h.new_status ILIKE '%registr%'
          OR h.new_status ILIKE '%grant%'                     THEN 'granted'
        WHEN h.new_status ILIKE '%oppos%'
          OR h.new_status ILIKE '%appeal%'
          OR h.new_status ILIKE '%review%'                    THEN 'contested'
        ELSE 'status_update'
    END                         AS transition_type,
    h.changed_at                AS source_updated_at,
    NOW()                       AS created_at

FROM mol_raw.trademark_status_history h
WHERE h.changed_at BETWEEN @start_dt AND @end_dt;
