-- Feature: Horizon 2 / plan §C.2 — real WAL backpressure (un-stub FR-007)
--
-- Creates `meta.wal_pressure`: a LIVE view of WAL pressure that returns a
-- single row with the current percentage of `max_wal_size` consumed since
-- the last checkpoint, plus replica lag if observable.
--
-- Why: `src/dk_data/ingestion/wal_throttle.py:wal_pressure()` previously
-- returned a hard-coded `0.0` because the older `meta.wal_usage` table is
-- a per-chunk write log, not a live pressure signal. Without a real
-- pressure signal, FR-007 (pause pg_restore when pct_used > 70, resume
-- below 40) is a no-op and prod WAL can fill unbounded during multi-GB
-- restores of the 5 WAL-mode tables (load_order.WAL_MODE_TABLES).
--
-- What this view reports (single row):
--   observed_at               — now() at query time
--   pct_used                  — 100 * bytes_since_last_checkpoint / max_wal_bytes
--   current_lsn               — pg_current_wal_lsn() as text (for debug)
--   max_wal_bytes             — max_wal_size GUC in bytes
--   headroom_bytes            — max_wal_bytes - bytes_since_last_checkpoint
--   oldest_replica_lag_bytes  — max lag (bytes) across pg_stat_replication,
--                               NULL when the calling role can't read it
--                               (non-replication users see an empty set —
--                               documented PostgreSQL behaviour).
--
-- Pressure math:
--   * We cannot cheaply observe "bytes written since last checkpoint" per
--     the PG catalogs, but the WAL LSN distance between the most recent
--     checkpoint REDO pointer (pg_control_checkpoint().redo_lsn) and the
--     current WAL LSN (pg_current_wal_lsn()) is exactly that number of
--     bytes. Subtracting LSNs yields bytes directly (pg_wal_lsn_diff).
--   * max_wal_size is a GUC expressed like '1GB'; pg_size_bytes() converts.
--   * If pg_size_bytes returns 0 (empty/unparseable), we clamp pct_used to
--     0.0 so the view never divides by zero.
--
-- Replica lag:
--   * pg_stat_replication is a per-role view — only superusers, replication
--     users, or members of pg_monitor / pg_read_all_stats see rows. The
--     hydration role has neither. To keep this view creatable under any
--     role (idempotent migration constraint), we wrap the aggregate in a
--     LEFT JOIN LATERAL that silently returns NULL when the hydration role
--     sees zero rows. This is graceful degradation: the throttle pauses on
--     primary-side pressure anyway; replica lag is an extra signal.
--
-- Idempotent: CREATE OR REPLACE VIEW — safe to rerun against an already
-- initialised database. Grants are re-applied each time.

BEGIN;

CREATE OR REPLACE VIEW meta.wal_pressure AS
WITH
  -- Parse max_wal_size GUC to bytes. `current_setting` returns something
  -- like '1GB'; pg_size_bytes handles the human unit. Clamp to 1 to avoid
  -- division by zero if the GUC was ever blanked.
  max_wal AS (
    SELECT GREATEST(pg_size_bytes(current_setting('max_wal_size')), 1) AS bytes
  ),
  -- Distance from the last checkpoint REDO pointer to the current write
  -- position = bytes of WAL accumulated since the last checkpoint. This
  -- is exactly the quantity max_wal_size bounds.
  since_checkpoint AS (
    SELECT
      pg_current_wal_lsn() AS cur_lsn,
      pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        (pg_control_checkpoint()).redo_lsn
      ) AS bytes
  ),
  -- Replica lag: max bytes across all active standbys. Returns NULL if
  -- the role can't read pg_stat_replication (non-privileged roles see an
  -- empty set, not an error — COUNT(*) = 0 → MAX(...) = NULL).
  replica_lag AS (
    SELECT MAX(
      pg_wal_lsn_diff(sent_lsn, replay_lsn)
    ) AS max_lag_bytes
    FROM pg_stat_replication
  )
SELECT
  now()                                                      AS observed_at,
  CASE
    WHEN max_wal.bytes = 0 THEN 0.0::numeric
    ELSE ROUND(
      100.0 * since_checkpoint.bytes::numeric / max_wal.bytes::numeric,
      2
    )
  END                                                        AS pct_used,
  since_checkpoint.cur_lsn::text                             AS current_lsn,
  max_wal.bytes                                              AS max_wal_bytes,
  GREATEST(max_wal.bytes - since_checkpoint.bytes, 0)::bigint AS headroom_bytes,
  replica_lag.max_lag_bytes::bigint                          AS oldest_replica_lag_bytes
FROM max_wal, since_checkpoint, replica_lag;

COMMENT ON VIEW meta.wal_pressure IS
  'Live WAL pressure: pct of max_wal_size consumed since last checkpoint, '
  'plus replica lag if visible to the calling role. Plan §C.2 / FR-007 — '
  'consumed by src/dk_data/ingestion/wal_throttle.py:wal_pressure().';

-- Grants: any role that runs the hydration (and anyone reading the
-- observability dashboards) must be able to SELECT. The underlying
-- pg_current_wal_lsn / pg_control_checkpoint functions are SECURITY
-- INVOKER, so access still depends on role privileges, but the view
-- itself is readable by all.
GRANT SELECT ON meta.wal_pressure TO PUBLIC;

COMMIT;
