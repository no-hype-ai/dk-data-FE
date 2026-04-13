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
    """Get a database connection for the migration runner.

    Migration runners MUST bypass PgBouncer because:
      1. PgBouncer transaction mode wraps each statement in an
         implicit transaction, which breaks `CREATE INDEX CONCURRENTLY`.
      2. Session-scoped settings (advisory locks, `SET LOCAL`) don't
         survive across statements in transaction mode.
      3. We need autocommit control to handle CONCURRENTLY operations
         that span multiple commits.

    Priority:
      1. POSTGRES_HOST_DIRECT — bypasses PgBouncer (preferred)
      2. POSTGRES_HOST        — falls back if _DIRECT is unset; logs a
                                warning because this is the WRONG path
                                for migrations
      3. DATABASE_URL         — local dev fallback only
      4. Hardcoded localhost defaults
    """
    direct_host = os.getenv("POSTGRES_HOST_DIRECT")
    if direct_host:
        return psycopg2.connect(
            host=direct_host,
            port=int(os.getenv("POSTGRES_PORT_DIRECT", os.getenv("POSTGRES_PORT", "5432"))),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres"),
            database=os.getenv("POSTGRES_DB", "dk_data"),
        )
    if os.getenv("POSTGRES_HOST"):
        print(
            "WARN: POSTGRES_HOST_DIRECT not set; falling back to POSTGRES_HOST. "
            "If POSTGRES_HOST routes through PgBouncer, CREATE INDEX CONCURRENTLY "
            "and similar non-transactional migrations will fail. Set "
            "POSTGRES_HOST_DIRECT to bypass PgBouncer.",
            file=sys.stderr,
        )
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


# Markers that signal a migration MUST run in autocommit mode
# (cannot be wrapped in a transaction). The most common case is
# `CREATE INDEX CONCURRENTLY`, but others exist (e.g. `VACUUM FULL`,
# `REINDEX CONCURRENTLY`, `CLUSTER`).
NON_TRANSACTIONAL_MARKERS = (
    "CREATE INDEX CONCURRENTLY",
    "DROP INDEX CONCURRENTLY",
    "REINDEX CONCURRENTLY",
    "ALTER SYSTEM",
    "VACUUM FULL",
    "VACUUM",
    "CLUSTER",
)


def _iter_statements(sql: str):
    """Yield individual SQL statements from a multi-statement string.

    Splits on semicolons that are NOT inside dollar-quoted blocks
    ($$...$$  or  $tag$...$tag$). Empty / comment-only fragments are
    skipped so callers can safely execute every yielded statement.

    Why this exists: calling cur.execute() with a full multi-statement
    SQL string causes PostgreSQL's simple query protocol to wrap all
    statements in an implicit transaction — even when the psycopg2
    connection is in autocommit mode.  Executing each statement in a
    separate cur.execute() call avoids that implicit transaction, which
    is required for CREATE INDEX CONCURRENTLY and similar operations.
    """
    in_dollar_quote = False
    dollar_tag: str | None = None
    buf: list[str] = []
    i = 0
    n = len(sql)

    while i < n:
        # Inside a dollar-quoted block — look for the closing tag only.
        if in_dollar_quote:
            assert dollar_tag is not None
            if sql[i:].startswith(dollar_tag):
                buf.append(dollar_tag)
                i += len(dollar_tag)
                in_dollar_quote = False
                dollar_tag = None
            else:
                buf.append(sql[i])
                i += 1
            continue

        ch = sql[i]

        # Detect the start of a dollar-quote ($$ or $tag$).
        if ch == "$":
            j = i + 1
            while j < n and (sql[j].isalnum() or sql[j] == "_"):
                j += 1
            if j < n and sql[j] == "$":
                tag = sql[i : j + 1]
                buf.append(tag)
                i = j + 1
                in_dollar_quote = True
                dollar_tag = tag
                continue

        # Statement terminator — yield whatever is buffered.
        if ch == ";":
            stmt = "".join(buf).strip()
            if _stmt_has_code(stmt):
                yield stmt
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    # Flush any trailing content that has no closing semicolon.
    if buf:
        stmt = "".join(buf).strip()
        if _stmt_has_code(stmt):
            yield stmt


def _stmt_has_code(stmt: str) -> bool:
    """Return True if *stmt* contains at least one non-comment, non-blank line."""
    for line in stmt.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            return True
    return False


def is_non_transactional(sql: str) -> bool:
    """Return True if the SQL contains any operation that requires
    running outside a transaction block.

    The check is case-insensitive and ignores SQL line comments. Any
    occurrence of one of NON_TRANSACTIONAL_MARKERS in non-comment
    text triggers autocommit mode for the file.
    """
    code_only_lines = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        # Strip inline `-- comment` tail
        if "--" in stripped:
            stripped = stripped.split("--", 1)[0]
        code_only_lines.append(stripped)
    upper = "\n".join(code_only_lines).upper()
    return any(marker in upper for marker in NON_TRANSACTIONAL_MARKERS)


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
    """Execute a single migration SQL file.

    Most migrations run inside a transaction so a failure leaves the
    DB in its pre-migration state. A migration containing CREATE
    INDEX CONCURRENTLY (or any other non-transactional operation —
    see NON_TRANSACTIONAL_MARKERS) is detected automatically and
    runs in autocommit mode instead. The bookkeeping insert into
    meta.schema_migrations always runs in its own transaction
    immediately after.

    Returns:
        Execution time in milliseconds.

    Raises:
        Exception: If migration SQL fails. For transactional
        migrations, the failed transaction is rolled back. For
        autocommit (CONCURRENTLY) migrations, partial progress
        (e.g. some indexes created, others failed) is preserved
        and the operator must investigate manually.
    """
    sql = Path(filepath).read_text(encoding="utf-8")
    start = time.monotonic()

    if is_non_transactional(sql):
        # CONCURRENTLY operations cannot run inside a transaction.
        # Switch the connection to autocommit, run each statement
        # individually, then restore the previous mode.
        #
        # IMPORTANT: we call cur.execute() once per statement, NOT once
        # for the whole file. Sending multiple semicolon-separated
        # statements in a single execute() call causes PostgreSQL's
        # simple query protocol to wrap them in an implicit transaction
        # on the server side — even when psycopg2's autocommit=True is
        # set — which makes CREATE INDEX CONCURRENTLY fail with
        # "cannot run inside a transaction block".
        previous_autocommit = conn.autocommit
        try:
            conn.autocommit = True
            print(
                "  (running in autocommit mode — non-transactional migration)"
            )
            for stmt in _iter_statements(sql):
                with conn.cursor() as cur:
                    cur.execute(stmt)
        finally:
            conn.autocommit = previous_autocommit
        elapsed_ms = int((time.monotonic() - start) * 1000)

        # Record bookkeeping in a separate transaction.
        with conn.cursor() as cur:
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

    # Transactional path (default — every other migration).
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
