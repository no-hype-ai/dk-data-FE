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

    Supports one level of subdirectories: a directory named ``031_silver_hub_rebuild/``
    is treated as a migration *group* whose children run between top-level prefix 031
    and 032.  Children are sorted by their own numeric prefix within the group.

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
        if "_rollback" in filename.lower():
            continue
        match = PREFIX_RE.match(filename)
        if match:
            version = filepath.stem
            migrations.append((version, filename, str(filepath)))

    # Discover subdirectory migration groups (e.g. 031_silver_hub_rebuild/)
    # Opt-in via MIGRATIONS_INCLUDE_SUBDIRS=1 — subdirectory migrations depend on
    # SQLMesh tables existing, so they should only run in production (post-SQLMesh)
    # or when explicitly enabled.
    if not os.getenv("MIGRATIONS_INCLUDE_SUBDIRS", ""):
        return migrations

    for subdir in sorted(migrations_path.iterdir()):
        if not subdir.is_dir():
            continue
        dir_match = PREFIX_RE.match(subdir.name)
        if not dir_match:
            continue
        for filepath in sorted(subdir.glob("*.sql")):
            filename = filepath.name
            if "_rollback" in filename.lower():
                continue
            child_match = PREFIX_RE.match(filename)
            if child_match:
                # Version key includes subdirectory to avoid collisions:
                # e.g. "031_silver_hub_rebuild/004_resolve_molecule"
                version = f"{subdir.name}/{filepath.stem}"
                migrations.append((version, filename, str(filepath)))

    def sort_key(m):
        version, filename, filepath = m
        fp = Path(filepath)
        parent_name = fp.parent.name

        # Top-level file: sort by its own numeric prefix
        parent_match = PREFIX_RE.match(parent_name)
        if not parent_match or parent_name == migrations_path.name:
            prefix_match = PREFIX_RE.match(filename)
            return (int(prefix_match.group(1)) if prefix_match else 0, 0, filename)

        # Subdirectory child: sort after the parent directory's prefix,
        # then by the child's own numeric prefix within the group.
        parent_prefix = int(parent_match.group(1))
        child_match = PREFIX_RE.match(filename)
        child_prefix = int(child_match.group(1)) if child_match else 0
        return (parent_prefix, 1 + child_prefix, filename)

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


def _needs_autocommit(sql: str) -> bool:
    """Return True if the migration SQL contains CALL statements.

    CALL with procedures that use transaction control (COMMIT/ROLLBACK inside
    the procedure body) requires the session to be in autocommit mode —
    PostgreSQL raises "invalid transaction termination" otherwise.
    """
    return bool(re.search(r"^\s*CALL\s+", sql, re.IGNORECASE | re.MULTILINE))


def _split_statements(sql: str) -> list[str]:
    """Split SQL text into top-level statements, respecting $$-delimited bodies.

    Returns a list of non-empty statement strings. Semicolons inside $tag$...$tag$
    blocks are NOT treated as statement separators. Comments are preserved.
    """
    statements: list[str] = []
    current: list[str] = []
    in_dollar = False
    dollar_tag = ""
    i = 0

    while i < len(sql):
        ch = sql[i]

        # Detect $$ or $tag$ delimiter
        if ch == "$" and not in_dollar:
            # Find the closing $
            j = sql.index("$", i + 1) if "$" in sql[i + 1 :] else -1
            if j >= 0:
                tag = sql[i : j + 1]
                # Valid dollar-quote tag: $$ or $identifier$
                if re.match(r"^\$[a-zA-Z_]*\$$", tag):
                    in_dollar = True
                    dollar_tag = tag
                    current.append(tag)
                    i = j + 1
                    continue
        elif in_dollar and ch == "$":
            # Check if this is the closing tag
            end = sql[i : i + len(dollar_tag)]
            if end == dollar_tag:
                in_dollar = False
                current.append(dollar_tag)
                i += len(dollar_tag)
                continue

        if ch == ";" and not in_dollar:
            current.append(ch)
            stmt = "".join(current).strip()
            if stmt and stmt != ";":
                statements.append(stmt)
            current = []
        else:
            current.append(ch)
        i += 1

    # Trailing text without semicolon
    remainder = "".join(current).strip()
    if remainder:
        statements.append(remainder)

    return [s for s in statements if not s.startswith("--") or "\n" in s]


def apply_migration(
    conn, filepath: str, version: str, filename: str, checksum: str
) -> int:
    """Execute a single migration SQL file.

    If the migration contains CALL statements, it runs with autocommit=True
    and each top-level statement is executed individually so that CALL can
    use transaction control (COMMIT per chunk, etc.).
    Otherwise, the migration runs within the connection's implicit transaction.

    Returns:
        Execution time in milliseconds.

    Raises:
        Exception: If migration SQL fails (transaction is rolled back).
    """
    sql = Path(filepath).read_text(encoding="utf-8")
    start = time.monotonic()

    if _needs_autocommit(sql):
        # Commit any pending transaction before switching to autocommit
        conn.commit()
        old_autocommit = conn.autocommit
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                # Execute each statement individually so CALL gets its own
                # top-level invocation (required for transaction control).
                for stmt in _split_statements(sql):
                    # Strip leading comment-only lines to check if there's real SQL
                    lines = stmt.strip().splitlines()
                    code_lines = [
                        ln for ln in lines
                        if ln.strip() and not ln.strip().startswith("--")
                    ]
                    if not code_lines:
                        continue  # pure comment block, skip
                    cur.execute(stmt)
                elapsed_ms = int((time.monotonic() - start) * 1000)
                cur.execute(
                    """
                    INSERT INTO meta.schema_migrations
                        (version, filename, checksum, applied_by, execution_time_ms)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (version, filename, checksum, "migration-runner", elapsed_ms),
                )
            return elapsed_ms
        finally:
            conn.autocommit = old_autocommit
    else:
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
