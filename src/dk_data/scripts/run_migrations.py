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

# Regex to extract numeric prefix from migration filename
PREFIX_RE = re.compile(r"^(\d+)")


def get_connection():
    """Get a database connection. Individual POSTGRES_* vars take priority over DATABASE_URL.

    Priority (matches api/dependencies.py and the rest of the codebase):
      1. POSTGRES_HOST + individual vars  — set by k8s dk-data-secrets
      2. DATABASE_URL                     — local dev fallback only
      3. Hardcoded localhost defaults
    """
    if os.getenv("POSTGRES_HOST"):
        return psycopg2.connect(
            host=os.environ["POSTGRES_HOST"],
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres"),
            database=os.getenv("POSTGRES_DB", "dk_data"),
        )
    if os.getenv("DATABASE_URL"):
        return psycopg2.connect(os.environ["DATABASE_URL"])
    return psycopg2.connect(
        host="localhost",
        port=int(os.getenv("POSTGRES_PORT", "5433")),
        user="postgres",
        password="postgres",
        database="dk_data",
    )


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
        # Skip rollback files — they are never applied as forward migrations
        if "_rollback" in filename.lower():
            continue
        match = PREFIX_RE.match(filename)
        if match:
            # Use filename without .sql extension as the unique version key so
            # that multiple files sharing the same numeric prefix (e.g.,
            # 085_bindingdb_sider_catalog.sql and 085_cms_geographic_variation_raw.sql)
            # are tracked as separate migrations and do not conflict.
            version = filepath.stem  # e.g. "085_cms_geographic_variation_raw"
            migrations.append((version, filename, str(filepath)))

    # Sort by numeric prefix (as integer) then alphabetically by full filename
    # so that 085_bindingdb_sider_catalog.sql runs before 085_cms_*.sql, etc.
    def sort_key(m):
        prefix_match = PREFIX_RE.match(m[1])  # m[1] is filename
        return (int(prefix_match.group(1)) if prefix_match else 0, m[1])

    migrations.sort(key=sort_key)
    return migrations


def compute_checksum(filepath: str) -> str:
    """Compute SHA-256 hex digest of a file's contents."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        sha256.update(f.read())
    return sha256.hexdigest()


def ensure_tracking_table(conn) -> None:
    """Create meta.schema_migrations table if it does not exist.

    Version key uses the full filename (without .sql extension) so that
    multiple files sharing the same numeric prefix (e.g., 085_foo.sql and
    085_bar.sql) are tracked independently.
    """
    with conn.cursor() as cur:
        cur.execute("""
            CREATE SCHEMA IF NOT EXISTS meta;

            CREATE TABLE IF NOT EXISTS meta.schema_migrations (
                id              SERIAL PRIMARY KEY,
                version         VARCHAR(255) NOT NULL UNIQUE,
                filename        VARCHAR(255) NOT NULL,
                checksum        VARCHAR(64)  NOT NULL,
                applied_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                applied_by      VARCHAR(100) DEFAULT 'migration-runner',
                execution_time_ms INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_schema_migrations_applied_at
                ON meta.schema_migrations (applied_at DESC);
        """)
        # Widen version column on existing DBs that were created with VARCHAR(10).
        # Must drop any views that depend on the column before altering it, then
        # recreate them afterwards (Postgres cannot alter a column type in-place
        # when a view depends on it — error 0A000 / "cannot alter type of a column
        # used by a view or rule").
        cur.execute("""
            DO $$
            DECLARE
                v_def TEXT;
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'meta'
                      AND table_name   = 'schema_migrations'
                      AND column_name  = 'version'
                      AND character_maximum_length IS NOT NULL
                      AND character_maximum_length < 255
                ) THEN
                    -- Capture the view definition before dropping it
                    SELECT pg_get_viewdef('api.migration_status', true)
                      INTO v_def;

                    -- Drop the dependent view so the column alter can proceed
                    DROP VIEW IF EXISTS api.migration_status CASCADE;

                    ALTER TABLE meta.schema_migrations
                        ALTER COLUMN version TYPE VARCHAR(255);

                    -- Recreate the view using its original definition
                    IF v_def IS NOT NULL THEN
                        EXECUTE 'CREATE OR REPLACE VIEW api.migration_status AS ' || v_def;
                    END IF;
                END IF;
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
