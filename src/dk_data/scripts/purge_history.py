#!/usr/bin/env python3
"""Score History Purge Script.

Purges score history records older than 2 years (rolling window retention policy).
Optionally purges all tables governed by meta.ops_data_classification retention policies.

Usage:
    python purge_history.py [--dry-run] [--days DAYS]
    python purge_history.py --all-tables [--dry-run]
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, str(__file__).rsplit('/scripts', 1)[0])

from ingestion.utils.database import get_cursor, get_connection, init_connection_pool, close_connection_pool

logger = logging.getLogger(__name__)

# Default retention period in days (2 years)
DEFAULT_RETENTION_DAYS = 730


def get_purge_stats(retention_days: int) -> dict:
    """Get statistics about records to be purged."""
    cutoff_date = datetime.now() - timedelta(days=retention_days)

    with get_cursor() as cur:
        # Count records to purge
        cur.execute("""
            SELECT COUNT(*) FROM scoring.score_history
            WHERE score_date < %s
        """, (cutoff_date.date(),))
        records_to_purge = cur.fetchone()[0]

        # Count total records
        cur.execute("SELECT COUNT(*) FROM scoring.score_history")
        total_records = cur.fetchone()[0]

        # Get date range of records to purge
        cur.execute("""
            SELECT MIN(score_date), MAX(score_date)
            FROM scoring.score_history
            WHERE score_date < %s
        """, (cutoff_date.date(),))
        row = cur.fetchone()
        min_date, max_date = row if row else (None, None)

        # Get count by month for records to purge
        cur.execute("""
            SELECT
                DATE_TRUNC('month', score_date) AS month,
                COUNT(*) AS count
            FROM scoring.score_history
            WHERE score_date < %s
            GROUP BY DATE_TRUNC('month', score_date)
            ORDER BY month
        """, (cutoff_date.date(),))
        monthly_counts = {row[0]: row[1] for row in cur.fetchall()}

    return {
        'cutoff_date': cutoff_date.date(),
        'records_to_purge': records_to_purge,
        'total_records': total_records,
        'min_date': min_date,
        'max_date': max_date,
        'monthly_counts': monthly_counts,
        'retention_days': retention_days,
    }


def purge_old_history(retention_days: int, dry_run: bool = False) -> dict:
    """Purge score history records older than retention period."""
    cutoff_date = datetime.now() - timedelta(days=retention_days)

    logger.info(f"Purging score history older than {cutoff_date.date()}")
    logger.info(f"Retention period: {retention_days} days")

    if dry_run:
        stats = get_purge_stats(retention_days)
        logger.info(f"[DRY RUN] Would purge {stats['records_to_purge']} records")
        return {
            'status': 'dry_run',
            'records_purged': 0,
            'would_purge': stats['records_to_purge'],
            'cutoff_date': str(cutoff_date.date()),
        }

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Delete old records
            cur.execute("""
                DELETE FROM scoring.score_history
                WHERE score_date < %s
            """, (cutoff_date.date(),))

            records_purged = cur.rowcount

            # Log the purge
            cur.execute("""
                INSERT INTO meta.ops_refresh_log (
                    source_id,
                    refresh_started_at,
                    refresh_completed_at,
                    status,
                    records_fetched,
                    records_inserted,
                    records_updated,
                    error_message
                )
                SELECT
                    source_id,
                    NOW(),
                    NOW(),
                    'success',
                    0,
                    0,
                    %s,
                    'Score history purge: removed records older than ' || %s::text
                FROM meta.ops_data_sources
                WHERE source_name = 'score_history_purge'
                LIMIT 1
            """, (records_purged, cutoff_date.date()))

        conn.commit()

    logger.info(f"Purged {records_purged} records from score_history")

    return {
        'status': 'success',
        'records_purged': records_purged,
        'cutoff_date': str(cutoff_date.date()),
        'retention_days': retention_days,
    }


# Mapping of schema prefixes to their default timestamp column
TIMESTAMP_COLUMN_MAP = {
    'raw': 'fetched_at',
    'meta': '_logged_at',
}

# Default timestamp column for schemas not in the map
DEFAULT_TIMESTAMP_COLUMN = 'created_at'

# Batch size for deletes
PURGE_BATCH_SIZE = 1000


def _get_timestamp_column(schema_name: str) -> str:
    """Determine the timestamp column for a given schema."""
    return TIMESTAMP_COLUMN_MAP.get(schema_name, DEFAULT_TIMESTAMP_COLUMN)


def purge_by_classification(conn, dry_run: bool = False) -> dict:
    """Purge records from all tables with retention policies defined in meta.ops_data_classification.

    Reads retention_days from meta.ops_data_classification for all non-perpetual tables.
    For each table, deletes records older than retention_days using the appropriate
    timestamp column.

    Args:
        conn: A psycopg2 database connection.
        dry_run: If True, report what would be purged without deleting.

    Returns:
        A summary dict with 'tables_processed', 'total_records_purged', and per-table details.
    """
    summary = {
        'status': 'dry_run' if dry_run else 'success',
        'tables_processed': 0,
        'total_records_purged': 0,
        'details': [],
    }

    with conn.cursor() as cur:
        # Read all classification rows where retention is defined (non-perpetual)
        cur.execute("""
            SELECT schema_name, table_name, classification, retention_days, retention_policy
            FROM meta.ops_data_classification
            WHERE retention_days IS NOT NULL
              AND table_name != '*'
            ORDER BY schema_name, table_name
        """)
        rows = cur.fetchall()

    if not rows:
        logger.info("No tables with retention policies found in meta.ops_data_classification")
        return summary

    for schema_name, table_name, classification, retention_days, retention_policy in rows:
        ts_col = _get_timestamp_column(schema_name)
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        qualified_table = f"{schema_name}.{table_name}"

        # Check if table actually exists before attempting purge
        with conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = %s AND table_name = %s
                )
            """, (schema_name, table_name))
            exists = cur.fetchone()[0]

        if not exists:
            logger.debug(f"Skipping {qualified_table}: table does not exist")
            continue

        # Check if the timestamp column exists on this table
        with conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s AND column_name = %s
                )
            """, (schema_name, table_name, ts_col))
            col_exists = cur.fetchone()[0]

        if not col_exists:
            logger.warning(
                f"Skipping {qualified_table}: timestamp column '{ts_col}' not found"
            )
            continue

        # Count records eligible for purge
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM {qualified_table} WHERE {ts_col} < %s",
                (cutoff_date,)
            )
            count_to_purge = cur.fetchone()[0]

        table_detail = {
            'table': qualified_table,
            'classification': classification,
            'retention_days': retention_days,
            'retention_policy': retention_policy,
            'timestamp_column': ts_col,
            'cutoff_date': str(cutoff_date.date()),
            'records_to_purge': count_to_purge,
            'records_purged': 0,
        }

        if count_to_purge == 0:
            logger.info(f"{qualified_table}: no records older than {cutoff_date.date()}")
            summary['details'].append(table_detail)
            summary['tables_processed'] += 1
            continue

        if dry_run:
            logger.info(
                f"[DRY RUN] {qualified_table}: would purge {count_to_purge} records "
                f"older than {cutoff_date.date()} (retention={retention_days}d)"
            )
            summary['details'].append(table_detail)
            summary['tables_processed'] += 1
            continue

        # Delete in batches to avoid long-running transactions
        total_deleted = 0
        while True:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    DELETE FROM {qualified_table}
                    WHERE ctid IN (
                        SELECT ctid FROM {qualified_table}
                        WHERE {ts_col} < %s
                        LIMIT %s
                    )
                    """,
                    (cutoff_date, PURGE_BATCH_SIZE)
                )
                batch_deleted = cur.rowcount
            conn.commit()

            total_deleted += batch_deleted
            if batch_deleted < PURGE_BATCH_SIZE:
                break

        table_detail['records_purged'] = total_deleted
        summary['details'].append(table_detail)
        summary['tables_processed'] += 1
        summary['total_records_purged'] += total_deleted

        logger.info(
            f"{qualified_table}: purged {total_deleted} records "
            f"(retention={retention_days}d, cutoff={cutoff_date.date()})"
        )

        # Log to meta.ops_refresh_log
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO meta.ops_refresh_log (
                    source_id,
                    refresh_started_at,
                    refresh_completed_at,
                    status,
                    records_fetched,
                    records_inserted,
                    records_updated,
                    error_message
                )
                SELECT
                    source_id,
                    NOW(),
                    NOW(),
                    'success',
                    0,
                    0,
                    %s,
                    'Classification-based purge of ' || %s || ': removed records older than ' || %s::text
                FROM meta.ops_data_sources
                WHERE source_name = 'score_history_purge'
                LIMIT 1
            """, (total_deleted, qualified_table, cutoff_date.date()))
        conn.commit()

    return summary


def print_purge_report(stats: dict) -> None:
    """Print a formatted purge report."""
    print("\n" + "=" * 60)
    print("Score History Purge Report")
    print("=" * 60)
    print(f"Report Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Retention Policy: {stats['retention_days']} days")
    print(f"Cutoff Date: {stats['cutoff_date']}")
    print("-" * 60)
    print(f"Total Records: {stats['total_records']:,}")
    print(f"Records to Purge: {stats['records_to_purge']:,}")

    if stats['records_to_purge'] > 0:
        pct = (stats['records_to_purge'] / stats['total_records']) * 100
        print(f"Percentage to Purge: {pct:.1f}%")
        print(f"Date Range: {stats['min_date']} to {stats['max_date']}")

        if stats['monthly_counts']:
            print("\nRecords by Month:")
            for month, count in sorted(stats['monthly_counts'].items()):
                if month:
                    print(f"  {month.strftime('%Y-%m')}: {count:,}")

    print("=" * 60 + "\n")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Purge old score history records'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be purged without deleting'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=DEFAULT_RETENTION_DAYS,
        help=f'Retention period in days (default: {DEFAULT_RETENTION_DAYS})'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Skip confirmation prompt'
    )
    parser.add_argument(
        '--all-tables',
        action='store_true',
        help='Purge all tables governed by meta.ops_data_classification retention policies'
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Initialize database
    init_connection_pool()

    try:
        # --all-tables: classification-based purge across all governed tables
        if args.all_tables:
            with get_connection() as conn:
                result = purge_by_classification(conn, dry_run=args.dry_run)

            print("\n" + "=" * 60)
            print("Classification-Based Purge Report")
            print("=" * 60)
            print(f"Tables processed: {result['tables_processed']}")
            print(f"Total records purged: {result['total_records_purged']:,}")
            if result['details']:
                print("-" * 60)
                for detail in result['details']:
                    purged = detail.get('records_purged', 0)
                    to_purge = detail.get('records_to_purge', 0)
                    label = f"would purge {to_purge:,}" if args.dry_run else f"purged {purged:,}"
                    print(
                        f"  {detail['table']}: {label} "
                        f"(retention={detail['retention_days']}d, "
                        f"class={detail['classification']})"
                    )
            print("=" * 60 + "\n")
            return 0

        # Default: single-table score_history purge
        # Get purge statistics
        stats = get_purge_stats(args.days)
        print_purge_report(stats)

        if stats['records_to_purge'] == 0:
            print("No records to purge.")
            return 0

        if args.dry_run:
            print("[DRY RUN] No records were deleted.")
            return 0

        # Confirmation prompt
        if not args.force:
            confirm = input(f"Delete {stats['records_to_purge']:,} records? (y/N): ")
            if confirm.lower() != 'y':
                print("Cancelled.")
                return 0

        # Execute purge
        result = purge_old_history(args.days, dry_run=False)

        print(f"\nSuccessfully purged {result['records_purged']:,} records")
        return 0

    except Exception as e:
        logger.error(f"Purge failed: {e}")
        return 1

    finally:
        close_connection_pool()


if __name__ == '__main__':
    sys.exit(main())
