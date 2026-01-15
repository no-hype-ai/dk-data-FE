#!/usr/bin/env python3
"""Hospital Enrichment Batch Processing Script.

Runs AI-assisted enrichment on hospitals missing health system or EMR data.

Usage:
    python run_enrichment.py [--limit N] [--min-confidence FLOAT] [--dry-run]
"""

import argparse
import logging
import sys
import json
from typing import List

# Add parent directory to path for imports
sys.path.insert(0, str(__file__).rsplit('/scripts', 1)[0])

from ingestion.utils.database import (
    get_cursor, get_connection,
    init_connection_pool, close_connection_pool
)
from claude_sdk.enrichment import (
    HospitalEnrichmentAgent,
    HospitalContext,
    HospitalEnrichmentData,
    update_staging_hospitals
)

logger = logging.getLogger(__name__)


def get_hospitals_needing_enrichment(limit: int = 100) -> List[HospitalContext]:
    """Get hospitals that need enrichment (missing health_system or emr_system).

    Args:
        limit: Maximum number of hospitals to return.

    Returns:
        List of hospital contexts needing enrichment.
    """
    hospitals = []

    with get_cursor() as cur:
        cur.execute("""
            SELECT
                hospital_id,
                hospital_name,
                city,
                state,
                hospital_type,
                bed_count
            FROM staging.hospitals
            WHERE (health_system_name IS NULL OR emr_system IS NULL)
              AND hospital_name IS NOT NULL
              AND state IS NOT NULL
            ORDER BY
                -- Prioritize larger hospitals
                bed_count DESC NULLS LAST,
                hospital_name
            LIMIT %s
        """, (limit,))

        for row in cur.fetchall():
            hospitals.append(HospitalContext(
                hospital_id=row[0],
                hospital_name=row[1],
                city=row[2] or '',
                state=row[3],
                hospital_type=row[4],
                bed_count=row[5]
            ))

    return hospitals


def log_enrichment_run(
    hospitals_processed: int,
    hospitals_updated: int,
    errors: int
) -> None:
    """Log the enrichment run to meta.refresh_log."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Try to get or create enrichment source
            cur.execute("""
                INSERT INTO meta.data_sources (
                    source_name, source_type, description, is_active
                )
                VALUES (
                    'ai_enrichment',
                    'ai',
                    'AI-assisted hospital data enrichment',
                    TRUE
                )
                ON CONFLICT (source_name) DO NOTHING
                RETURNING source_id
            """)

            result = cur.fetchone()
            if result:
                source_id = result[0]
            else:
                cur.execute("""
                    SELECT source_id FROM meta.data_sources
                    WHERE source_name = 'ai_enrichment'
                """)
                source_id = cur.fetchone()[0]

            # Log the run
            cur.execute("""
                INSERT INTO meta.refresh_log (
                    source_id,
                    refresh_started_at,
                    refresh_completed_at,
                    status,
                    records_fetched,
                    records_updated,
                    error_message
                )
                VALUES (%s, NOW(), NOW(), %s, %s, %s, %s)
            """, (
                source_id,
                'success' if errors == 0 else 'partial',
                hospitals_processed,
                hospitals_updated,
                f"{errors} errors" if errors > 0 else None
            ))

        conn.commit()


def print_enrichment_report(
    results: dict,
    hospitals_processed: int,
    hospitals_updated: int
) -> None:
    """Print enrichment results report."""
    print("\n" + "=" * 60)
    print("Hospital Enrichment Report")
    print("=" * 60)
    print(f"Hospitals Processed: {hospitals_processed}")
    print(f"Hospitals Enriched: {len(results)}")
    print(f"Records Updated: {hospitals_updated}")
    print("-" * 60)

    if results:
        print("\nEnrichment Results:")
        print(f"{'Hospital ID':<12} {'Health System':<30} {'EMR':<15} {'Conf':<6}")
        print("-" * 60)

        for hospital_id, data in list(results.items())[:20]:
            health_sys = (data.health_system_name or '-')[:28]
            emr = (data.emr_system or '-')[:13]
            conf = f"{data.confidence_score:.2f}"
            print(f"{hospital_id:<12} {health_sys:<30} {emr:<15} {conf:<6}")

        if len(results) > 20:
            print(f"... and {len(results) - 20} more")

    print("=" * 60 + "\n")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Run AI-assisted hospital enrichment'
    )
    parser.add_argument(
        '--limit', '-n',
        type=int,
        default=50,
        help='Maximum hospitals to process (default: 50)'
    )
    parser.add_argument(
        '--min-confidence',
        type=float,
        default=0.5,
        help='Minimum confidence to accept results (default: 0.5)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output results as JSON'
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
        # Get hospitals needing enrichment
        logger.info(f"Finding hospitals needing enrichment (limit: {args.limit})")
        hospitals = get_hospitals_needing_enrichment(args.limit)

        if not hospitals:
            print("No hospitals found needing enrichment.")
            return 0

        logger.info(f"Found {len(hospitals)} hospitals to enrich")

        if args.dry_run:
            print(f"[DRY RUN] Would process {len(hospitals)} hospitals:")
            for h in hospitals[:10]:
                print(f"  - {h.hospital_id}: {h.hospital_name} ({h.city}, {h.state})")
            if len(hospitals) > 10:
                print(f"  ... and {len(hospitals) - 10} more")
            return 0

        # Initialize enrichment agent
        agent = HospitalEnrichmentAgent()

        # Run enrichment
        logger.info("Starting enrichment...")
        results = agent.enrich_batch(
            hospitals,
            min_confidence=args.min_confidence
        )

        # Update database
        hospitals_updated = 0
        if results:
            logger.info(f"Updating {len(results)} hospital records...")
            hospitals_updated = update_staging_hospitals(results)

        # Log the run
        log_enrichment_run(
            hospitals_processed=len(hospitals),
            hospitals_updated=hospitals_updated,
            errors=len(hospitals) - len(results)
        )

        # Output results
        if args.json:
            output = {
                'hospitals_processed': len(hospitals),
                'hospitals_enriched': len(results),
                'records_updated': hospitals_updated,
                'results': {k: v.model_dump() for k, v in results.items()}
            }
            print(json.dumps(output, indent=2, default=str))
        else:
            print_enrichment_report(results, len(hospitals), hospitals_updated)

        return 0

    except Exception as e:
        logger.error(f"Enrichment failed: {e}")
        return 1

    finally:
        close_connection_pool()


if __name__ == '__main__':
    sys.exit(main())
