#!/usr/bin/env python3
"""Data Freshness and Quality Check Script.

Monitors data source freshness and calculates quality metrics.
Updates meta.data_quality table with results.

Usage:
    python check_freshness.py [--source SOURCE] [--verbose]
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import json

# Add parent directory to path for imports
sys.path.insert(0, str(__file__).rsplit('/scripts', 1)[0])

from ingestion.utils.database import get_cursor, get_connection, init_connection_pool, close_connection_pool

logger = logging.getLogger(__name__)

# Freshness thresholds by source (in days)
FRESHNESS_THRESHOLDS = {
    'cms_medicare_inpatient': {'fresh': 90, 'stale': 180},  # Quarterly
    'cms_hospital_info': {'fresh': 30, 'stale': 60},         # Monthly
    'cms_cost_reports': {'fresh': 365, 'stale': 450},        # Annual
    'acc_tvc': {'fresh': 90, 'stale': 180},                  # Quarterly
    'hrsa_shortage_areas': {'fresh': 30, 'stale': 60},       # Monthly
}

# Quality check queries by source
QUALITY_CHECKS = {
    'cms_medicare_inpatient': {
        'total_records': "SELECT COUNT(*) FROM raw.cms_medicare_inpatient",
        'null_provider_id': "SELECT COUNT(*) FROM raw.cms_medicare_inpatient WHERE provider_id IS NULL",
        'null_drg_code': "SELECT COUNT(*) FROM raw.cms_medicare_inpatient WHERE drg_code IS NULL",
        'invalid_discharges': "SELECT COUNT(*) FROM raw.cms_medicare_inpatient WHERE total_discharges < 0",
        'tavr_records': "SELECT COUNT(*) FROM raw.cms_medicare_inpatient WHERE drg_code IN ('266', '267')",
    },
    'cms_hospital_info': {
        'total_records': "SELECT COUNT(*) FROM raw.cms_hospital_info",
        'null_provider_id': "SELECT COUNT(*) FROM raw.cms_hospital_info WHERE provider_id IS NULL",
        'null_state': "SELECT COUNT(*) FROM raw.cms_hospital_info WHERE state IS NULL",
        'invalid_rating': "SELECT COUNT(*) FROM raw.cms_hospital_info WHERE hospital_overall_rating NOT BETWEEN 1 AND 5 AND hospital_overall_rating IS NOT NULL",
    },
    'cms_cost_reports': {
        'total_records': "SELECT COUNT(*) FROM raw.cms_cost_reports",
        'null_provider_id': "SELECT COUNT(*) FROM raw.cms_cost_reports WHERE provider_id IS NULL",
        'negative_revenue': "SELECT COUNT(*) FROM raw.cms_cost_reports WHERE net_patient_revenue < 0",
        'invalid_margin': "SELECT COUNT(*) FROM raw.cms_cost_reports WHERE operating_margin < -1 OR operating_margin > 1",
    },
    'acc_tvc': {
        'total_records': "SELECT COUNT(*) FROM raw.acc_tvc_certification",
        'null_facility_name': "SELECT COUNT(*) FROM raw.acc_tvc_certification WHERE facility_name IS NULL",
        'expired_certs': "SELECT COUNT(*) FROM raw.acc_tvc_certification WHERE expiration_date < CURRENT_DATE",
        'future_cert_date': "SELECT COUNT(*) FROM raw.acc_tvc_certification WHERE certification_date > CURRENT_DATE",
    },
    'hrsa_shortage_areas': {
        'total_records': "SELECT COUNT(*) FROM raw.hrsa_shortage_areas",
        'null_hpsa_id': "SELECT COUNT(*) FROM raw.hrsa_shortage_areas WHERE hpsa_id IS NULL",
        'null_state': "SELECT COUNT(*) FROM raw.hrsa_shortage_areas WHERE state_abbr IS NULL",
        'invalid_score': "SELECT COUNT(*) FROM raw.hrsa_shortage_areas WHERE hpsa_score < 0 OR hpsa_score > 25",
    },
}


def get_source_info(source_name: str) -> Optional[Dict[str, Any]]:
    """Get source metadata from meta.data_sources."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT source_id, source_name, last_successful_refresh,
                   last_refresh_status, record_count
            FROM meta.data_sources
            WHERE source_name = %s
        """, (source_name,))
        row = cur.fetchone()

        if row:
            return {
                'source_id': row[0],
                'source_name': row[1],
                'last_successful_refresh': row[2],
                'last_refresh_status': row[3],
                'record_count': row[4],
            }
    return None


def calculate_freshness_days(last_refresh: Optional[datetime]) -> Optional[int]:
    """Calculate days since last refresh."""
    if last_refresh is None:
        return None
    delta = datetime.now() - last_refresh
    return delta.days


def get_freshness_status(source_name: str, freshness_days: Optional[int]) -> str:
    """Determine freshness status based on thresholds."""
    if freshness_days is None:
        return 'unknown'

    thresholds = FRESHNESS_THRESHOLDS.get(source_name, {'fresh': 7, 'stale': 30})

    if freshness_days <= thresholds['fresh']:
        return 'fresh'
    elif freshness_days <= thresholds['stale']:
        return 'stale'
    else:
        return 'outdated'


def run_quality_checks(source_name: str) -> Dict[str, Any]:
    """Run quality checks for a source and return results."""
    checks = QUALITY_CHECKS.get(source_name, {})
    results = {}
    issues = []

    with get_cursor() as cur:
        for check_name, query in checks.items():
            try:
                cur.execute(query)
                value = cur.fetchone()[0]
                results[check_name] = value
            except Exception as e:
                logger.error(f"Quality check '{check_name}' failed: {e}")
                results[check_name] = None
                issues.append(f"Check '{check_name}' failed: {str(e)}")

    # Calculate completeness and validity
    total = results.get('total_records', 0) or 0

    if total > 0:
        # Count null/invalid records
        null_checks = [v for k, v in results.items() if k.startswith('null_') and v is not None]
        invalid_checks = [v for k, v in results.items() if k.startswith('invalid_') and v is not None]

        null_count = sum(null_checks)
        invalid_count = sum(invalid_checks)

        # Completeness: % of records with no null key fields
        completeness = ((total - null_count) / total) * 100 if total > 0 else 0

        # Validity: % of records passing validation
        validity = ((total - invalid_count) / total) * 100 if total > 0 else 0
    else:
        completeness = 0
        validity = 0
        issues.append("No records found in source table")

    # Add issues for quality problems
    for check_name, value in results.items():
        if value and value > 0 and check_name != 'total_records' and check_name != 'tavr_records':
            issues.append(f"{check_name}: {value} records")

    return {
        'total_records': total,
        'completeness_pct': round(completeness, 2),
        'validity_pct': round(validity, 2),
        'check_results': results,
        'issues': issues,
    }


def calculate_quality_score(
    completeness: float,
    validity: float,
    freshness_status: str
) -> float:
    """Calculate composite quality score (0-100)."""
    # Weights: completeness 40%, validity 40%, freshness 20%
    freshness_score = {
        'fresh': 100,
        'stale': 50,
        'outdated': 20,
        'unknown': 0,
    }.get(freshness_status, 0)

    score = (completeness * 0.4) + (validity * 0.4) + (freshness_score * 0.2)
    return round(score, 2)


def update_data_quality(
    source_id: int,
    completeness_pct: float,
    validity_pct: float,
    freshness_days: Optional[int],
    quality_score: float,
    issues: List[str]
) -> None:
    """Insert quality metrics into meta.data_quality."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO meta.data_quality (
                    source_id, check_date, completeness_pct, validity_pct,
                    freshness_days, quality_score, issues_found, _checked_at
                ) VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (source_id, check_date) DO UPDATE SET
                    completeness_pct = EXCLUDED.completeness_pct,
                    validity_pct = EXCLUDED.validity_pct,
                    freshness_days = EXCLUDED.freshness_days,
                    quality_score = EXCLUDED.quality_score,
                    issues_found = EXCLUDED.issues_found,
                    _checked_at = NOW()
            """, (
                source_id,
                completeness_pct,
                validity_pct,
                freshness_days,
                quality_score,
                json.dumps(issues) if issues else None,
            ))
        conn.commit()


def check_source(source_name: str, verbose: bool = False) -> Dict[str, Any]:
    """Run freshness and quality checks for a single source."""
    logger.info(f"Checking source: {source_name}")

    # Get source info
    source_info = get_source_info(source_name)
    if not source_info:
        logger.warning(f"Source '{source_name}' not found in meta.data_sources")
        return {'status': 'error', 'message': 'Source not found'}

    # Calculate freshness
    freshness_days = calculate_freshness_days(source_info['last_successful_refresh'])
    freshness_status = get_freshness_status(source_name, freshness_days)

    # Run quality checks
    quality_results = run_quality_checks(source_name)

    # Calculate quality score
    quality_score = calculate_quality_score(
        quality_results['completeness_pct'],
        quality_results['validity_pct'],
        freshness_status
    )

    # Update meta.data_quality
    update_data_quality(
        source_info['source_id'],
        quality_results['completeness_pct'],
        quality_results['validity_pct'],
        freshness_days,
        quality_score,
        quality_results['issues']
    )

    result = {
        'source_name': source_name,
        'freshness_days': freshness_days,
        'freshness_status': freshness_status,
        'total_records': quality_results['total_records'],
        'completeness_pct': quality_results['completeness_pct'],
        'validity_pct': quality_results['validity_pct'],
        'quality_score': quality_score,
        'issues_count': len(quality_results['issues']),
        'status': 'success',
    }

    if verbose:
        result['issues'] = quality_results['issues']
        result['check_results'] = quality_results['check_results']

    return result


def check_all_sources(verbose: bool = False) -> List[Dict[str, Any]]:
    """Run checks for all active sources."""
    results = []

    with get_cursor() as cur:
        cur.execute("""
            SELECT source_name FROM meta.data_sources WHERE is_active = TRUE
        """)
        sources = [row[0] for row in cur.fetchall()]

    for source_name in sources:
        result = check_source(source_name, verbose)
        results.append(result)

    return results


def print_report(results: List[Dict[str, Any]]) -> None:
    """Print a formatted report of check results."""
    print("\n" + "=" * 70)
    print("Data Freshness and Quality Report")
    print("=" * 70)
    print(f"Report Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 70)

    # Summary table header
    print(f"{'Source':<25} {'Fresh':<10} {'Records':<10} {'Complete':<10} {'Valid':<10} {'Score':<8}")
    print("-" * 70)

    for r in results:
        if r['status'] == 'success':
            freshness = f"{r['freshness_days']}d" if r['freshness_days'] is not None else 'N/A'
            print(f"{r['source_name']:<25} {freshness:<10} {r['total_records']:<10} "
                  f"{r['completeness_pct']:<10.1f} {r['validity_pct']:<10.1f} {r['quality_score']:<8.1f}")
        else:
            print(f"{r['source_name']:<25} {'ERROR':<10}")

    print("-" * 70)

    # Alerts
    alerts = []
    for r in results:
        if r['status'] == 'success':
            if r['freshness_status'] == 'outdated':
                alerts.append(f"⚠️  {r['source_name']}: Data is OUTDATED ({r['freshness_days']} days old)")
            elif r['freshness_status'] == 'stale':
                alerts.append(f"⚡ {r['source_name']}: Data is STALE ({r['freshness_days']} days old)")
            if r['quality_score'] < 50:
                alerts.append(f"🔴 {r['source_name']}: Low quality score ({r['quality_score']})")
            if r['issues_count'] > 0:
                alerts.append(f"📋 {r['source_name']}: {r['issues_count']} quality issues found")

    if alerts:
        print("\nAlerts:")
        for alert in alerts:
            print(f"  {alert}")
    else:
        print("\n✅ All sources healthy")

    print("=" * 70 + "\n")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Check data freshness and quality metrics'
    )
    parser.add_argument(
        '--source', '-s',
        help='Check specific source (default: all sources)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed check results'
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
        if args.source:
            results = [check_source(args.source, args.verbose)]
        else:
            results = check_all_sources(args.verbose)

        if args.json:
            print(json.dumps(results, indent=2, default=str))
        else:
            print_report(results)

        # Exit with error if any source has issues
        has_errors = any(r['status'] != 'success' for r in results)
        has_quality_issues = any(
            r.get('quality_score', 100) < 50
            for r in results if r['status'] == 'success'
        )

        return 1 if has_errors or has_quality_issues else 0

    finally:
        close_connection_pool()


if __name__ == '__main__':
    sys.exit(main())
