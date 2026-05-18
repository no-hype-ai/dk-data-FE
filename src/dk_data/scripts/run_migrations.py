#!/usr/bin/env python3
"""
Database Migration Runner
Feature: 013-observability-governance (US4)

Lightweight CLI tool that discovers, checksums, and applies SQL migrations
from src/dk_data/sql/migrations/ in numeric-prefix order.

Usage:
    python -m dk_data.scripts.run_migrations
    python -m dk_data.scripts.run_migrations --dry-run
    python -m dk_data.scripts.run_migrations --baseline
    python -m dk_data.scripts.run_migrations --migrations-dir /path/to/migrations
"""

import argparse
import hashlib
import os
import re
import sys
import time
from pathlib import Path

import psycopg2

# Default migrations directory (relative to repo root)
DEFAULT_MIGRATIONS_DIR = str(
    Path(__file__).resolve().parent.parent / "sql" / "migrations"
)

# Database connection from environment
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Fallback to individual env vars (matches catalog_refresh.py pattern)
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5433")),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
    "database": os.getenv("POSTGRES_DB", "dk_data"),
}

# Regex to extract numeric prefix from migration filename
PREFIX_RE = re.compile(r"^(\d+)")


def get_connection():
    """Get a database connection from DATABASE_URL or individual env vars."""
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(**DB_CONFIG)


def discover_migrations(migrations_dir: str) -> list[tuple[str, str, str]]:
    """Scan migrations directory for *.sql files, sorted by numeric prefix.

    Returns:
        List of (version, filename, filepath) tuples sorted by version.
    """
    migrations = []
    migrations_path = Path(migrations_dir)

    if not migrations_path.is_dir():
        print(f"ERROR: Migrations directory not found: {migrations_dir}")
        return []

    for filepath in sorted(migrations_path.glob("*.sql")):
        filename = filepath.name
        match = PREFIX_RE.match(filename)
        if match:
            version = match.group(1)
            migrations.append((version, filename, str(filepath)))

    # Sort by numeric prefix (as integer for correct ordering)
    migrations.sort(key=lambda m: int(m[0]))
    return migrations


def compute_checksum(filepath: str) -> str:
    """Compute SHA-256 hex digest of a file's contents."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        sha256.update(f.read())
    return sha256.hexdigest()


def ensure_tracking_table(conn) -> None:
    """Create meta.schema_migrations table if it does not exist."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE SCHEMA IF NOT EXISTS meta;

            CREATE TABLE IF NOT EXISTS meta.schema_migrations (
                id              SERIAL PRIMARY KEY,
                version         VARCHAR(10)  NOT NULL UNIQUE,
                filename        VARCHAR(255) NOT NULL,
                checksum        VARCHAR(64)  NOT NULL,
                applied_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                applied_by      VARCHAR(100) DEFAULT 'migration-runner',
                execution_time_ms INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_schema_migrations_applied_at
                ON meta.schema_migrations (applied_at DESC);
        """)
        cur.execute("""
            DO $$
            DECLARE
                v_def     TEXT;
                v_relkind "char";
            BEGIN
                -- Only act when meta.schema_migrations.version is a
                -- length-bounded type narrower than 255 chars. When it
                -- is already >= 255 (or unbounded), do nothing.
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'meta'
                      AND table_name   = 'schema_migrations'
                      AND column_name  = 'version'
                      AND character_maximum_length IS NOT NULL
                      AND character_maximum_length < 255
                ) THEN
                    RETURN;
                END IF;

                -- Detect api.migration_status via pg_catalog so that
                -- BOTH plain views ('v') AND materialized views ('m')
                -- are seen, regardless of role-visibility quirks that
                -- can make information_schema.views omit the relation.
                SELECT c.relkind
                  INTO v_relkind
                  FROM pg_catalog.pg_class c
                  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                 WHERE n.nspname = 'api'
                   AND c.relname = 'migration_status'
                   AND c.relkind IN ('v', 'm');

                IF v_relkind IS NULL THEN
                    -- Relation does not exist as a view/matview. Nothing
                    -- to preserve; widen the column and return.
                    RAISE NOTICE
                        'ensure_tracking_table: api.migration_status not '
                        'present as view/matview; widening version only';
                    ALTER TABLE meta.schema_migrations
                        ALTER COLUMN version TYPE VARCHAR(255);
                    RETURN;
                END IF;

                IF v_relkind = 'm' THEN
                    -- Materialized view: a CREATE OR REPLACE VIEW
                    -- round-trip cannot reconstruct it. Refuse to drop
                    -- it. Roll the whole transaction back so the
                    -- operator handles the matview by hand.
                    RAISE EXCEPTION
                        'ensure_tracking_table: api.migration_status is a '
                        'MATERIALIZED VIEW; refusing to drop it to widen '
                        'meta.schema_migrations.version. Drop/recreate the '
                        'matview manually, then re-run migrations.';
                END IF;

                -- Plain view: capture its definition BEFORE any DROP.
                SELECT pg_get_viewdef('api.migration_status', true)
                  INTO v_def;

                IF v_def IS NULL OR btrim(v_def) = '' THEN
                    -- Exists per pg_catalog but the definition could not
                    -- be captured. Never DROP blind: roll back instead.
                    RAISE EXCEPTION
                        'ensure_tracking_table: api.migration_status '
                        'exists but its definition could not be captured; '
                        'refusing to DROP it. Aborting (transaction '
                        'rolled back).';
                END IF;

                RAISE NOTICE
                    'ensure_tracking_table: captured api.migration_status '
                    'definition before widening version: %', v_def;

                -- Safe to drop now: definition is in hand and will be
                -- recreated below.
                DROP VIEW IF EXISTS api.migration_status CASCADE;

                ALTER TABLE meta.schema_migrations
                    ALTER COLUMN version TYPE VARCHAR(255);

                EXECUTE 'CREATE OR REPLACE VIEW api.migration_status AS '
                        || v_def;
            END $$;
        """)

    conn.commit()


def get_applied_migrations(conn) -> set[str]:
    """Return set of version strings that have already been applied."""
    with conn.cursor() as cur:
        cur.execute("SELECT version FROM meta.schema_migrations")
        return {row[0] for row in cur.fetchall()}


def apply_migration(
    conn, filepath: str, version: str, filename: str, checksum: str
) -> int:
    """Execute a single migration SQL file within a transaction.

    Returns:
        Execution time in milliseconds.

    Raises:
        Exception: If migration SQL fails (transaction is rolled back).
    """
    sql = Path(filepath).read_text(encoding="utf-8")
    start = time.monotonic()

    with conn.cursor() as cur:
        cur.execute(sql)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        cur.execute(
            """
            INSERT INTO meta.schema_migrations
                (version, filename, checksum, applied_by, execution_time_ms)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (version, filename, checksum, "migration-runner", elapsed_ms),
        )

    conn.commit()
    return elapsed_ms


def apply_pending(conn, migrations_dir: str, dry_run: bool = False) -> bool:
    """Discover migrations, filter applied, apply remaining in order.

    Returns:
        True if all pending migrations succeeded (or none pending), False on failure.
    """
    ensure_tracking_table(conn)
    migrations = discover_migrations(migrations_dir)
    applied = get_applied_migrations(conn)

    pending = [(v, fn, fp) for v, fn, fp in migrations if v not in applied]

    if not pending:
        print("No pending migrations.")
        return True

    print(f"Found {len(pending)} pending migration(s):")

    for version, filename, filepath in pending:
        checksum = compute_checksum(filepath)

        if dry_run:
            print(f"  [DRY RUN] {filename} (checksum: {checksum[:12]}...)")
            continue

        print(f"  Applying {filename}...", end=" ", flush=True)
        try:
            elapsed_ms = apply_migration(conn, filepath, version, filename, checksum)
            print(f"OK ({elapsed_ms}ms)")
        except Exception as exc:
            conn.rollback()
            print("FAILED")
            print(f"  ERROR: {exc}")
            print("  Halting migration run. Fix the error and re-run.")
            return False

    if dry_run:
        print(f"\n[DRY RUN] {len(pending)} migration(s) would be applied.")

    return True


def baseline(conn, migrations_dir: str) -> bool:
    """Mark all discovered migrations as applied without executing SQL.

    Used for existing databases where migrations have already been applied
    manually or via db-init-job.

    Returns:
        True on success, False on failure.
    """
    ensure_tracking_table(conn)
    migrations = discover_migrations(migrations_dir)
    applied = get_applied_migrations(conn)

    pending = [(v, fn, fp) for v, fn, fp in migrations if v not in applied]

    if not pending:
        print("All migrations already baselined.")
        return True

    print(f"Baselining {len(pending)} migration(s):")

    with conn.cursor() as cur:
        for version, filename, filepath in pending:
            checksum = compute_checksum(filepath)
            cur.execute(
                """
                INSERT INTO meta.schema_migrations
                    (version, filename, checksum, applied_by, execution_time_ms)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (version) DO NOTHING
                """,
                (version, filename, checksum, "baseline", 0),
            )
            print(f"  BASELINED {filename}")

    conn.commit()
    print(f"\nBaseline complete: {len(pending)} migration(s) marked as applied.")
    return True


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Run pending database migrations in order."
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Mark all migrations as applied without executing SQL",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show pending migrations without applying them",
    )
    parser.add_argument(
        "--migrations-dir",
        default=DEFAULT_MIGRATIONS_DIR,
        help=f"Path to migrations directory (default: {DEFAULT_MIGRATIONS_DIR})",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Database Migration Runner")
    print(f"Migrations dir: {args.migrations_dir}")
    print("=" * 60)

    try:
        conn = get_connection()
    except psycopg2.Error as e:
        print(f"ERROR: Cannot connect to database: {e}", file=sys.stderr)
        return 1

    try:
        if args.baseline:
            success = baseline(conn, args.migrations_dir)
        else:
            success = apply_pending(conn, args.migrations_dir, dry_run=args.dry_run)

        return 0 if success else 1

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
