-- Feature: Horizon 2 / plan §C.3 — hydration dead-letter queue / source quarantine
--
-- This migration creates `meta.hydration_backlog`, a per-(source_id, schema,
-- table) row tracking consecutive failures across hydration runs so a
-- repeatedly-failing source can be auto-quarantined (skipped on subsequent
-- dispatch) after N consecutive same-signature failures. The quarantine
-- state is cleared only by explicit operator action via
-- `dk_data.ingestion.hydration_backlog.unquarantine(...)`, which also
-- writes an audit row to meta.transform_runs.
--
-- Why this exists (plan §C.3):
--   Today a transient or persistent source failure (bad dump, credential
--   drift, upstream outage, schema mismatch) is retried on every hydration
--   run with no budget / cooldown. That burns cluster resources and can
--   block hub-dependent sources (see propagate_blocked in load_order.py).
--   The backlog table gives us:
--     1. Exponential backoff (`next_retry_at`) so a failing source isn't
--        hammered every run.
--     2. Auto-quarantine on sustained same-signature failure, taking the
--        source out of rotation until a human looks at it.
--     3. Visibility — `--list-backlog` CLI + dashboards can surface
--        quarantined sources and recent error signatures.
--
-- Schema notes:
--   - (source_id, schema_name, table_name) is the natural key — one row
--     per (source, destination-table). `source_id` is the canonical
--     "{schema}.{table}" id from load_order.py; we keep schema_name +
--     table_name as explicit columns for cheap filtering / joins.
--   - `consecutive_same_error_count` is the counter that drives the
--     auto-quarantine decision. It increments when a new failure shares
--     the same `last_error_code` as the prior row, and resets to 1 when
--     the error signature changes. A simpler "count >= N" rule on
--     `failure_count` would quarantine sources whose errors bounce
--     around — that's often a symptom of upstream flapping, not a
--     persistent bug, so we only quarantine on truly repeatable failures.
--   - `next_retry_at` is set via exponential backoff capped at 24h:
--     `NOW() + least(pow(2, least(failure_count, 10)) * 60, 86400) seconds`.
--     Dispatcher consults this when picking the next run's source set.
--   - `quarantined_by` / `quarantined_at` are NULL until auto-quarantine
--     (value 'auto') or manual quarantine (value: operator name) fires.
--     When non-NULL, the dispatcher SKIPs the source with outcome
--     status='quarantined' and returns early.
--   - The `hydration_backlog_quarantined_idx` partial index keeps the
--     "which sources are quarantined right now?" query O(k) where k is
--     the typically-small quarantined set, not O(n) over all backlog rows.
--
-- Idempotency:
--   Every statement is IF NOT EXISTS. Re-running this migration is a no-op.
--
-- Migration number rationale:
--   230 is taken by 230_hydration_dashboard_view.sql (already on main).
--   A parallel C.2 worker is landing a wal_pressure view migration also
--   in the 230-range — we take 231 to avoid a filename collision.

BEGIN;

SET LOCAL statement_timeout = '120s';
SET LOCAL lock_timeout = '10s';

CREATE TABLE IF NOT EXISTS meta.hydration_backlog (
  backlog_id                    BIGSERIAL PRIMARY KEY,
  source_id                     TEXT NOT NULL,
  schema_name                   TEXT NOT NULL,
  table_name                    TEXT NOT NULL,
  last_failure_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  failure_count                 INT  NOT NULL DEFAULT 1,
  last_error_code               TEXT,
  last_error_detail             TEXT,
  first_failure_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  next_retry_at                 TIMESTAMPTZ,
  quarantined_by                TEXT,
  quarantined_at                TIMESTAMPTZ,
  -- Counter that drives auto-quarantine. Increments on a failure whose
  -- last_error_code matches the row's prior last_error_code; resets to 1
  -- when the error signature changes. See plan §C.3 — "same signature"
  -- check. Kept on the row (rather than derived from a view) so the upsert
  -- in record_failure() is a single statement with no race window.
  consecutive_same_error_count  INT  NOT NULL DEFAULT 1,
  UNIQUE (source_id, schema_name, table_name)
);

-- Partial index: only quarantined rows matter for the "what's currently
-- blocked?" query. Index size stays tiny; seq-scan is still OK against the
-- full table for uncommon analytical queries.
CREATE INDEX IF NOT EXISTS hydration_backlog_quarantined_idx
  ON meta.hydration_backlog (quarantined_at)
  WHERE quarantined_by IS NOT NULL;

COMMIT;
