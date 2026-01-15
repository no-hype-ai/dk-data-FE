#!/usr/bin/env python3
"""TAVR Targeting Data Loading Script.

This script loads targeting data from various sources into the targeting schema:
1. Targeting CSV (manual import from sales team)
2. Volume history from CMS Medicare Inpatient data

Feature: 002-tavr-targeting-tool
Tasks: T013, T014, T020-T024

Usage:
    # Load targeting CSV
    python load_targeting_data.py --input "/path/to/targeting.csv"

    # Dry run (validate without inserting)
    python load_targeting_data.py --input "/path/to/targeting.csv" --dry-run

    # Refresh volume history from CMS data
    python load_targeting_data.py --refresh-volumes

    # Load everything
    python load_targeting_data.py --input "/path/to/targeting.csv" --refresh-volumes
"""

import os
import sys
import logging
import argparse
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.sources.targeting_import import load_targeting_csv
from ingestion.utils.database import get_cursor, get_connection

logger = logging.getLogger(__name__)


# ============================================================================
# T020-T023: Volume History from CMS Data
# ============================================================================

def refresh_volume_history(
    fiscal_years: Optional[list[int]] = None,
    dry_run: bool = False
) -> dict:
    """
    Populate targeting.volume_history from raw.cms_medicare_inpatient.

    This extracts DRG 266/267 volumes by hospital and year, then calculates
    YoY growth percentages.

    Args:
        fiscal_years: List of fiscal years to process. If None, process all available.
        dry_run: If True, show what would be done without committing.

    Returns:
        Dictionary with refresh statistics.
    """
    logger.info("Refreshing volume_history from CMS Medicare Inpatient data")

    # T020: Volume extraction query
    volume_query = """
        WITH volume_by_year AS (
            -- T021: DRG 266/267 aggregation by hospital and year
            SELECT
                provider_id AS hospital_id,
                fiscal_year,
                SUM(CASE WHEN drg_code = '266' THEN total_discharges ELSE 0 END) AS drg_266_volume,
                SUM(CASE WHEN drg_code = '267' THEN total_discharges ELSE 0 END) AS drg_267_volume
            FROM raw.cms_medicare_inpatient
            WHERE drg_code IN ('266', '267')
            GROUP BY provider_id, fiscal_year
        ),
        volume_with_growth AS (
            -- T022: YoY growth calculation
            SELECT
                v.hospital_id,
                v.fiscal_year,
                v.drg_266_volume,
                v.drg_267_volume,
                (v.drg_266_volume + v.drg_267_volume) AS total_volume,
                LAG(v.drg_266_volume + v.drg_267_volume) OVER (
                    PARTITION BY v.hospital_id ORDER BY v.fiscal_year
                ) AS prior_year_volume
            FROM volume_by_year v
        )
        SELECT
            hospital_id,
            fiscal_year,
            drg_266_volume,
            drg_267_volume,
            CASE
                WHEN prior_year_volume IS NULL OR prior_year_volume = 0 THEN NULL
                ELSE ROUND(
                    ((total_volume - prior_year_volume)::NUMERIC / prior_year_volume) * 100,
                    2
                )
            END AS yoy_growth_pct
        FROM volume_with_growth
        WHERE total_volume > 0
    """

    if fiscal_years:
        volume_query = volume_query.replace(
            "GROUP BY provider_id, fiscal_year",
            f"AND fiscal_year = ANY(ARRAY{fiscal_years}) GROUP BY provider_id, fiscal_year"
        )

    records_processed = 0
    records_inserted = 0
    errors = []

    if dry_run:
        with get_cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM ({volume_query}) q")
            count = cur.fetchone()[0]
            logger.info(f"DRY RUN: Would process {count} volume_history records")
            return {
                'status': 'dry_run',
                'records_would_process': count
            }

    # T023: Populate volume_history
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Execute volume query and insert results
            cur.execute(volume_query)
            rows = cur.fetchall()
            records_processed = len(rows)

            for row in rows:
                hospital_id, fiscal_year, drg_266, drg_267, yoy_growth = row
                try:
                    cur.execute("""
                        INSERT INTO targeting.volume_history (
                            hospital_id, fiscal_year, drg_266_volume, drg_267_volume,
                            yoy_growth_pct, _loaded_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, NOW()
                        )
                        ON CONFLICT (hospital_id, fiscal_year) DO UPDATE SET
                            drg_266_volume = EXCLUDED.drg_266_volume,
                            drg_267_volume = EXCLUDED.drg_267_volume,
                            yoy_growth_pct = EXCLUDED.yoy_growth_pct,
                            _loaded_at = NOW()
                    """, (hospital_id, fiscal_year, drg_266, drg_267, yoy_growth))
                    records_inserted += 1
                except Exception as e:
                    errors.append({'hospital_id': hospital_id, 'error': str(e)})
                    logger.error(f"Error inserting volume for {hospital_id}/{fiscal_year}: {e}")

            conn.commit()

    logger.info(f"Volume history refresh complete: {records_inserted}/{records_processed} records")

    return {
        'status': 'success' if not errors else 'partial',
        'records_processed': records_processed,
        'records_inserted': records_inserted,
        'errors': errors[:10]
    }


# ============================================================================
# T024: Market Share Calculation
# ============================================================================

def calculate_market_shares(dry_run: bool = False) -> dict:
    """
    Calculate market share percentages for each hospital by year.

    Market share is calculated as:
    hospital_volume / total_state_volume * 100

    Args:
        dry_run: If True, show what would be done without committing.

    Returns:
        Dictionary with calculation statistics.
    """
    logger.info("Calculating market shares")

    market_share_query = """
        WITH state_totals AS (
            SELECT
                v.fiscal_year,
                h.state,
                SUM(v.total_tavr_volume) AS state_total_volume
            FROM targeting.volume_history v
            JOIN mart.dim_hospital h ON v.hospital_id = h.hospital_id
            GROUP BY v.fiscal_year, h.state
        )
        UPDATE targeting.volume_history vh
        SET market_share_pct = ROUND(
            (vh.total_tavr_volume::NUMERIC / st.state_total_volume) * 100,
            2
        )
        FROM mart.dim_hospital h
        JOIN state_totals st ON h.state = st.state
        WHERE vh.hospital_id = h.hospital_id
          AND vh.fiscal_year = st.fiscal_year
          AND st.state_total_volume > 0
    """

    if dry_run:
        logger.info("DRY RUN: Would calculate market shares for all volume_history records")
        return {'status': 'dry_run'}

    with get_cursor() as cur:
        cur.execute(market_share_query)
        rows_updated = cur.rowcount

    logger.info(f"Updated market shares for {rows_updated} records")

    return {
        'status': 'success',
        'records_updated': rows_updated
    }


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point for targeting data loading."""
    parser = argparse.ArgumentParser(
        description='Load targeting data into the targeting schema',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Load targeting CSV with dry run
    python load_targeting_data.py --input targeting.csv --dry-run

    # Load targeting CSV
    python load_targeting_data.py --input targeting.csv

    # Refresh volume history from CMS data
    python load_targeting_data.py --refresh-volumes

    # Full load (CSV + volumes + market shares)
    python load_targeting_data.py --input targeting.csv --refresh-volumes --calculate-market-shares
        """
    )

    parser.add_argument(
        '--input', '-i',
        help='Path to targeting CSV file'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate without inserting data (T014)'
    )
    parser.add_argument(
        '--refresh-volumes',
        action='store_true',
        help='Refresh volume_history from CMS data (T020-T023)'
    )
    parser.add_argument(
        '--calculate-market-shares',
        action='store_true',
        help='Calculate market share percentages (T024)'
    )
    parser.add_argument(
        '--fiscal-years',
        nargs='+',
        type=int,
        help='Specific fiscal years to process for volume refresh'
    )
    parser.add_argument(
        '--skip-validation',
        action='store_true',
        help='Skip hospital ID validation against mart.dim_hospital'
    )
    parser.add_argument(
        '--updated-by',
        default='load_targeting_data',
        help='User identifier for audit trail'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    results = {}

    # Refresh volume history from CMS data
    if args.refresh_volumes:
        logger.info("=" * 60)
        logger.info("STEP 1: Refreshing volume history from CMS data")
        logger.info("=" * 60)
        results['volume_history'] = refresh_volume_history(
            fiscal_years=args.fiscal_years,
            dry_run=args.dry_run
        )

    # Calculate market shares
    if args.calculate_market_shares:
        logger.info("=" * 60)
        logger.info("STEP 2: Calculating market shares")
        logger.info("=" * 60)
        results['market_shares'] = calculate_market_shares(dry_run=args.dry_run)

    # Load targeting CSV
    if args.input:
        logger.info("=" * 60)
        logger.info("STEP 3: Loading targeting CSV")
        logger.info("=" * 60)
        results['targeting_csv'] = load_targeting_csv(
            filepath=args.input,
            dry_run=args.dry_run,
            skip_validation=args.skip_validation,
            updated_by=args.updated_by
        )

    if not any([args.input, args.refresh_volumes, args.calculate_market_shares]):
        parser.print_help()
        return

    # Print results
    import json
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(json.dumps(results, indent=2))

    # Check for any failures
    has_failures = any(
        r.get('status') not in ('success', 'dry_run')
        for r in results.values()
    )

    sys.exit(1 if has_failures else 0)


if __name__ == '__main__':
    main()
