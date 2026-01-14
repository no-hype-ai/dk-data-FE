#!/usr/bin/env python3
"""Score History Purge Script.

Purges score history records older than 2 years (rolling window retention policy).

Usage:
    python purge_history.py [--dry-run] [--days DAYS]
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
                INSERT INTO meta.refresh_log (
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
                FROM meta.data_sources
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

        print(f"\n✅ Successfully purged {result['records_purged']:,} records")
        return 0

    except Exception as e:
        logger.error(f"Purge failed: {e}")
        return 1

    finally:
        close_connection_pool()


if __name__ == '__main__':
    sys.exit(main())
