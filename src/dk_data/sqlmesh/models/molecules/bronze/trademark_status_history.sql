-- SQLMesh Model: Bronze Trademark Status History
-- Promotes raw.trademark_status_history (audit trail written by USPTO/EUIPO loaders)
-- to a typed bronze layer with molecule linkage hooks.
--
-- Source: raw.trademark_status_history
--   Written by: load_uspto_trademarks.py and load_euipo_trademarks.py
--   on every ingest when a trademark status change is detected.
-- Grain: (trademark_identifier, source, change_detected_at)
--
-- Ref: issue #171 M5

MODEL (
    name mol_bronze.trademark_status_history,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column change_detected_at,
        batch_size  1000
    ),
    cron '@daily',
    audits (
        not_null(columns := (trademark_identifier, source, new_status, change_detected_at)),
        unique_values(columns := (trademark_identifier, source, change_detected_at))
    ),
    grain (trademark_identifier, source, change_detected_at)
);

SELECT
    gen_random_uuid()           AS id,
    h.trademark_identifier,
    h.source,
    h.old_status,
    h.new_status,
    h.change_detected_at,
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
    h.change_detected_at        AS source_updated_at,
    NOW()                       AS created_at

FROM raw.trademark_status_history h
WHERE h.change_detected_at BETWEEN @start_dt AND @end_dt;
