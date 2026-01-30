#!/usr/bin/env python3
"""
Catalog Refresh Script
Feature: 001-data-layer-postgrest-gitops
Task: T019

Populates semantic metadata (descriptions, topic_tags, ai_description)
for data sources in the catalog.

Usage:
    python scripts/catalog_refresh.py [--check-only]
"""

import argparse
import os
import sys
from datetime import datetime
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor, Json

# Database configuration from environment
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5433")),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
    "database": os.getenv("POSTGRES_DB", "edwards_tavr"),
}

# Semantic metadata definitions for known data sources
SOURCE_METADATA = {
    "cms_medicare_inpatient": {
        "topic_tags": ["cms", "medicare", "hospital", "financial", "drg"],
        "ai_description": "CMS Medicare inpatient hospital discharge data by DRG code. Contains procedure volumes, charges, and payments for Medicare fee-for-service patients. Key source for TAVR volume estimation.",
        "column_descriptions": {
            "provider_id": {
                "description": "CMS 6-digit provider identification number",
                "type": "string",
                "examples": ["010001", "050001"],
            },
            "drg_code": {
                "description": "Diagnosis Related Group code for procedure classification",
                "type": "string",
                "examples": ["266", "267"],
            },
            "total_discharges": {
                "description": "Number of Medicare fee-for-service discharges for this DRG",
                "type": "integer",
            },
            "average_medicare_payments": {
                "description": "Average Medicare payment per discharge in USD",
                "type": "decimal",
            },
        },
        "staleness_threshold_hours": 720,  # Monthly data - 30 days
        "target_tables": ["staging.tavr_volumes", "mart.fact_tavr_program"],
    },
    "cms_hospital_info": {
        "topic_tags": ["cms", "hospital", "demographics", "quality"],
        "ai_description": "CMS Hospital Compare general information dataset. Contains hospital demographics, ownership, bed counts, quality ratings, and contact information.",
        "column_descriptions": {
            "provider_id": {
                "description": "CMS 6-digit provider identification number",
                "type": "string",
            },
            "hospital_name": {
                "description": "Official hospital name",
                "type": "string",
            },
            "hospital_overall_rating": {
                "description": "CMS overall quality star rating (1-5)",
                "type": "integer",
                "range": "1-5",
            },
            "hospital_type": {
                "description": "Type of hospital (Acute Care, Critical Access, etc.)",
                "type": "string",
            },
        },
        "staleness_threshold_hours": 168,  # Weekly updates
        "target_tables": ["staging.hospitals", "mart.dim_hospital"],
    },
    "acc_tvc": {
        "topic_tags": ["acc", "certification", "tavr", "quality"],
        "ai_description": "ACC TVT Registry certification data for TAVR programs. Indicates which hospitals have official ACC certification for transcatheter valve procedures.",
        "column_descriptions": {
            "facility_name": {
                "description": "Name of the certified facility",
                "type": "string",
            },
            "certification_type": {
                "description": "Type of ACC certification (TAVR, MITRAL, etc.)",
                "type": "string",
            },
            "certification_date": {
                "description": "Date certification was granted",
                "type": "date",
            },
            "expiration_date": {
                "description": "Date certification expires",
                "type": "date",
            },
        },
        "staleness_threshold_hours": 720,  # Monthly
        "target_tables": ["staging.certifications"],
    },
    "hrsa_shortage_areas": {
        "topic_tags": ["hrsa", "geographic", "hpsa", "rural"],
        "ai_description": "HRSA Health Professional Shortage Area designations. Identifies underserved areas for healthcare access analysis and rural hospital targeting.",
        "column_descriptions": {
            "hpsa_id": {
                "description": "HRSA unique identifier for the shortage area",
                "type": "string",
            },
            "hpsa_score": {
                "description": "Shortage severity score (higher = more severe)",
                "type": "integer",
            },
            "rural_status": {
                "description": "Urban/rural classification",
                "type": "string",
            },
        },
        "staleness_threshold_hours": 720,  # Monthly
        "target_tables": ["staging.geographic_designations"],
    },
    "cms_cost_reports": {
        "topic_tags": ["cms", "financial", "hospital", "cost"],
        "ai_description": "CMS Hospital Cost Report data with financial metrics. Contains operating margins, revenue, expenses, and bed counts for financial capacity analysis.",
        "column_descriptions": {
            "provider_id": {
                "description": "CMS 6-digit provider identification number",
                "type": "string",
            },
            "operating_margin": {
                "description": "Operating margin ratio (revenue - expenses) / revenue",
                "type": "decimal",
            },
            "total_beds": {
                "description": "Total number of hospital beds",
                "type": "integer",
            },
        },
        "staleness_threshold_hours": 2160,  # Quarterly - 90 days
        "target_tables": ["mart.fact_financial_metrics"],
    },
}


def get_connection():
    """Get database connection."""
    return psycopg2.connect(**DB_CONFIG)


def get_current_sources(cursor) -> list[dict[str, Any]]:
    """Get all active data sources."""
    cursor.execute("""
        SELECT source_id, source_name, topic_tags, ai_description,
               column_descriptions, staleness_threshold_hours, target_tables
        FROM meta.data_sources
        WHERE is_active = TRUE
        ORDER BY source_name
    """)
    return cursor.fetchall()


def update_source_metadata(cursor, source_id: int, metadata: dict) -> bool:
    """Update metadata for a data source."""
    cursor.execute("""
        UPDATE meta.data_sources
        SET
            topic_tags = %(topic_tags)s,
            ai_description = %(ai_description)s,
            column_descriptions = %(column_descriptions)s,
            staleness_threshold_hours = %(staleness_threshold_hours)s,
            target_tables = %(target_tables)s
        WHERE source_id = %(source_id)s
    """, {
        "source_id": source_id,
        "topic_tags": metadata.get("topic_tags", []),
        "ai_description": metadata.get("ai_description"),
        "column_descriptions": Json(metadata.get("column_descriptions", {})),
        "staleness_threshold_hours": metadata.get("staleness_threshold_hours", 24),
        "target_tables": metadata.get("target_tables", []),
    })
    return cursor.rowcount > 0


def record_health_check(cursor, source_id: int) -> int | None:
    """Record a health check for the source."""
    cursor.execute("""
        SELECT meta.record_health_check(%(source_id)s, 0, 0, %(details)s) AS health_id
    """, {
        "source_id": source_id,
        "details": Json({"source": "catalog_refresh", "timestamp": datetime.now().isoformat()}),
    })
    result = cursor.fetchone()
    return result["health_id"] if result else None


def main():
    parser = argparse.ArgumentParser(description="Refresh catalog metadata")
    parser.add_argument("--check-only", action="store_true",
                        help="Only check current status, don't update")
    args = parser.parse_args()

    print("=" * 60)
    print("Catalog Refresh Script")
    print(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    print("=" * 60)

    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Get current sources
        sources = get_current_sources(cursor)
        print(f"\nFound {len(sources)} active data sources")

        updated_count = 0
        skipped_count = 0
        unknown_count = 0

        for source in sources:
            source_name = source["source_name"]
            source_id = source["source_id"]

            if source_name in SOURCE_METADATA:
                metadata = SOURCE_METADATA[source_name]
                has_metadata = bool(source["ai_description"])

                if args.check_only:
                    status = "HAS_METADATA" if has_metadata else "NEEDS_UPDATE"
                    print(f"  [{status}] {source_name}")
                else:
                    if update_source_metadata(cursor, source_id, metadata):
                        print(f"  [UPDATED] {source_name}")
                        updated_count += 1
                        # Record health check after update
                        health_id = record_health_check(cursor, source_id)
                        if health_id:
                            print(f"    -> Health check recorded (id: {health_id})")
                    else:
                        print(f"  [SKIPPED] {source_name} - no changes")
                        skipped_count += 1
            else:
                print(f"  [UNKNOWN] {source_name} - no metadata defined")
                unknown_count += 1

        if not args.check_only:
            conn.commit()
            print(f"\n{'=' * 60}")
            print(f"Summary: {updated_count} updated, {skipped_count} skipped, {unknown_count} unknown")
        else:
            print(f"\n{'=' * 60}")
            print("Check-only mode - no changes made")

        cursor.close()
        conn.close()
        return 0

    except psycopg2.Error as e:
        print(f"\nDatabase error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
