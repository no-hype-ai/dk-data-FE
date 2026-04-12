-- WAL status snapshot table
-- Feature: 001-silver-medallion-rebuild / T223
-- Periodic snapshots of pg_stat_replication and pg_current_wal_lsn()
-- for WAL lag monitoring and replication health.

CREATE TABLE IF NOT EXISTS meta.wal_status (
    id              bigserial PRIMARY KEY,
    snapshotted_at  timestamptz NOT NULL DEFAULT now(),
    -- Primary WAL position
    current_lsn     pg_lsn,
    wal_insert_lsn  pg_lsn,
    -- Replication slots (one row per snapshot, aggregated)
    slot_count      int,
    slot_names      text[],
    -- Oldest replication slot lag (bytes behind primary)
    max_slot_lag_bytes bigint,
    -- pg_stat_replication aggregate
    replica_count   int,
    max_replica_lag_bytes bigint,
    -- WAL directory size
    wal_dir_bytes   bigint
);

CREATE INDEX IF NOT EXISTS wal_status_snapshotted_at_brin
    ON meta.wal_status USING BRIN (snapshotted_at);

COMMENT ON TABLE meta.wal_status IS
    'Periodic WAL position and replication lag snapshots. Captured by cronjob-wal-status-snapshot (T229).';

-- Snapshot function — called by the CronJob
CREATE OR REPLACE FUNCTION meta.snapshot_wal_status()
RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    v_current_lsn       pg_lsn;
    v_insert_lsn        pg_lsn;
    v_slot_count        int;
    v_slot_names        text[];
    v_max_slot_lag      bigint;
    v_replica_count     int;
    v_max_replica_lag   bigint;
    v_wal_bytes         bigint;
BEGIN
    v_current_lsn := pg_current_wal_lsn();
    v_insert_lsn  := pg_current_wal_insert_lsn();

    SELECT
        count(*),
        array_agg(slot_name),
        max(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn))
    INTO v_slot_count, v_slot_names, v_max_slot_lag
    FROM pg_replication_slots;

    SELECT
        count(*),
        max(pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn))
    INTO v_replica_count, v_max_replica_lag
    FROM pg_stat_replication;

    -- WAL directory size (requires pg_ls_waldir privilege)
    BEGIN
        SELECT sum(size) INTO v_wal_bytes FROM pg_ls_waldir();
    EXCEPTION WHEN insufficient_privilege THEN
        v_wal_bytes := NULL;
    END;

    INSERT INTO meta.wal_status (
        snapshotted_at,
        current_lsn, wal_insert_lsn,
        slot_count, slot_names, max_slot_lag_bytes,
        replica_count, max_replica_lag_bytes,
        wal_dir_bytes
    ) VALUES (
        now(),
        v_current_lsn, v_insert_lsn,
        v_slot_count, v_slot_names, v_max_slot_lag,
        v_replica_count, v_max_replica_lag,
        v_wal_bytes
    );
END;
$$;

-- Retention: purge snapshots older than 30 days
CREATE OR REPLACE FUNCTION meta.purge_wal_status(p_days int DEFAULT 30)
RETURNS int
LANGUAGE plpgsql AS $$
DECLARE
    deleted int;
BEGIN
    DELETE FROM meta.wal_status
    WHERE snapshotted_at < now() - (p_days || ' days')::interval;
    GET DIAGNOSTICS deleted = ROW_COUNT;
    RETURN deleted;
END;
$$;
