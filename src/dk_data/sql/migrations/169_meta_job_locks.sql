-- Migration: 001_meta_job_locks.sql
-- Feature: 001-silver-medallion-rebuild
-- FR-025: meta.job_locks — application-level advisory locks for CronJob concurrency control.
--
-- WHY: pg_try_advisory_lock() is broken under PgBouncer transaction mode (a new
-- transaction gets a new connection, so the lock appears unset on the second call).
-- These table-level locks survive across transactions and are visible to all pods.
--
-- USAGE: INSERT to acquire; DELETE to release; rows with expires_at < NOW() are
-- treated as stale and may be skipped (the bootstrap procedures do this check).
-- The CronJob concurrency cap (FR-021e) is enforced at the Kubernetes level via
-- concurrencyPolicy: Forbid, but job_locks adds a second layer so long-lived pods
-- don't collide if the k8s concurrencyPolicy check races.

BEGIN;

CREATE TABLE IF NOT EXISTS meta.job_locks (
    name       text        PRIMARY KEY,
    locked_by  text        NOT NULL,
    locked_at  timestamptz DEFAULT NOW(),
    expires_at timestamptz NOT NULL
);

COMMENT ON TABLE meta.job_locks IS
    'FR-025: application-level concurrency locks. INSERT to acquire, DELETE to release. '
    'Rows with expires_at < NOW() are stale — callers must clean them up before re-acquiring.';

COMMENT ON COLUMN meta.job_locks.name IS
    'Lock key — use the CronJob or procedure name, e.g. ''bootstrap_providers''.';
COMMENT ON COLUMN meta.job_locks.locked_by IS
    'Identifier of the holder — pod name + pid, e.g. ''fetcher-pod-abc123/42''.';
COMMENT ON COLUMN meta.job_locks.expires_at IS
    'Hard deadline. Set to NOW() + expected_max_runtime + buffer. '
    'A new caller may skip/overwrite a row whose expires_at is in the past.';

COMMIT;
