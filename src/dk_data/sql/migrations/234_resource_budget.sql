-- Feature: Horizon 3 / plan §D.3 — admission control by budget
--
-- Creates meta.resource_budget: a small KV-shaped table of named capacity
-- budgets (wal_headroom, db_connections, concurrent_restores, seaweedfs_iops)
-- plus a live `reserved` counter per budget. The admission module in
-- src/dk_data/ingestion/resource_budget.py reads these rows inside a single
-- transaction with SELECT ... FOR UPDATE so concurrent dispatcher workers
-- cannot double-book the same slot.
--
-- Each descriptor (plan §D.2) declares a `consumes:` dict naming how much
-- of each budget one of its steps needs. The dispatcher (plan §D.1) calls
-- `ResourceBudget.try_reserve(descriptor.consumes)` before enqueueing a
-- source step; if the atomic reservation fails for any key, the dispatcher
-- defers and retries later.
--
-- Schema notes:
--   - `budget_key` is the natural primary key. We keep it as TEXT rather
--     than a PG enum so operators can add new budget classes without a
--     migration (platform-api will eventually surface create/update via
--     dk CLI). The initial seed covers the four budgets from plan §D.3.
--   - `total_capacity` and `reserved` are both NUMERIC so budgets can
--     express percentages (wal_headroom = 100 pct, reservation values
--     like 5.0 = "5 pct of headroom") alongside integer slot counts
--     (db_connections = 20, reservation = 2). A single NUMERIC type keeps
--     the Python-side math uniform across keys.
--   - `reserved` is the LIVE counter modified by try_reserve / release.
--     Budgets are reservations, NOT monotonic counters (see plan §D.3
--     hard constraint) — they rise when a step begins and fall when it
--     completes / fails / times out. The writer side takes row-level
--     locks via SELECT ... FOR UPDATE to serialize concurrent updates.
--   - `updated_at` is touched on every update so the dashboard can
--     surface staleness ("budget hasn't moved in 1h → scheduler stuck?").
--
-- Idempotency:
--   Every statement is IF NOT EXISTS / ON CONFLICT DO NOTHING. Re-running
--   this migration against a live table is a no-op; existing rows keep
--   their current total_capacity (operators can tune via platform-api
--   without this migration rewriting their values on redeploy).
--
-- Migration number rationale:
--   230 = hydration_dashboard_view.sql
--   231 = wal_pressure_view.sql
--   232 = hydration_backlog.sql
--   233 is reserved for plan §D.2 (source_registry / source descriptors)
--        — that PR is in-flight. We take 234 to avoid a filename collision.

BEGIN;

SET LOCAL statement_timeout = '120s';
SET LOCAL lock_timeout = '10s';

CREATE TABLE IF NOT EXISTS meta.resource_budget (
  budget_key       TEXT        PRIMARY KEY,
  -- Total capacity expressed in whatever unit is natural for the key.
  -- wal_headroom: percent-of-headroom (0..100). Reservations subtract
  --   "pct consumed" and the remaining value tracks free headroom.
  -- db_connections: integer slots from the dedicated dk_data_hydration
  --   PgBouncer pool (plan §C.5).
  -- concurrent_restores: integer slots matching the dispatcher's
  --   --max-parallel default (plan §D.1).
  -- seaweedfs_iops: rough IOPS headroom; tune as we measure.
  total_capacity   NUMERIC     NOT NULL CHECK (total_capacity >= 0),
  -- Live reserved counter. Never exceeds total_capacity when admission
  -- control is working — the module's try_reserve() returns False once
  -- remaining < requested. We don't add a DB-level CHECK (reserved <=
  -- total_capacity) on purpose: an operator bumping down total_capacity
  -- below the current reserved must not make the DB error-out on a
  -- stale update; Python-side clamping is the safer place.
  reserved         NUMERIC     NOT NULL DEFAULT 0 CHECK (reserved >= 0),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed initial budgets. ON CONFLICT DO NOTHING preserves any operator-
-- tuned total_capacity on re-run — this migration must never overwrite
-- a tuned value.
INSERT INTO meta.resource_budget (budget_key, total_capacity) VALUES
  ('wal_headroom', 100),        -- pct-used headroom; reservation = pct consumed
  ('db_connections', 20),       -- dedicated dk_data_hydration pool from plan §C.5
  ('concurrent_restores', 4),   -- matches default dispatcher --max-parallel (§D.1)
  ('seaweedfs_iops', 1000)      -- rough IOPS headroom; tune later
ON CONFLICT (budget_key) DO NOTHING;

COMMIT;
