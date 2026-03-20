#!/usr/bin/env python3
"""
Load FDA Drugs@FDA approval history into PostgreSQL.

Uses the openFDA Drugs@FDA API to fetch complete regulatory submission
timelines: original BLA/NDA approvals, supplemental approvals (sNDA/sBLA),
review priority, and submission class codes.

Tables populated:
- bronze.fda_approvals: Individual submission records

Usage:
    python -m dk_data.data.load_fda_approvals --drug "IMFINZI"
    python -m dk_data.data.load_fda_approvals --application "BLA761069"

Environment:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
"""

import os
import time
from typing import Optional, List, Dict, Any

import requests
import psycopg2
from psycopg2.extras import execute_values, Json
from loguru import logger

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "dk_data"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

FDA_API_BASE = "https://api.fda.gov/drug/drugsfda.json"
RATE_LIMIT_DELAY = 0.5


def ensure_tables(conn):
    """Ensure FDA approvals tables exist."""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.fda_approvals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            application_number VARCHAR(20) NOT NULL,
            sponsor_name VARCHAR(500),
            brand_name VARCHAR(500),
            generic_name VARCHAR(500),
            product_type VARCHAR(50),
            dosage_form VARCHAR(200),
            route VARCHAR(200),
            active_ingredients JSONB,
            submission_type VARCHAR(20),
            submission_number VARCHAR(10),
            submission_status VARCHAR(10),
            submission_status_date DATE,
            review_priority VARCHAR(20),
            submission_class_code VARCHAR(20),
            submission_class_code_description TEXT,
            te_code VARCHAR(20),
            raw_json JSONB,
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            processed_to_silver BOOLEAN DEFAULT FALSE,
            UNIQUE(application_number, submission_type, submission_number)
        );

        CREATE INDEX IF NOT EXISTS idx_fda_app_no ON bronze.fda_approvals(application_number);
        CREATE INDEX IF NOT EXISTS idx_fda_brand ON bronze.fda_approvals(brand_name);
        CREATE INDEX IF NOT EXISTS idx_fda_generic ON bronze.fda_approvals(generic_name);
        CREATE INDEX IF NOT EXISTS idx_fda_date ON bronze.fda_approvals(submission_status_date);
    """)
    conn.commit()
    logger.info("FDA approvals tables ensured")


class FDAApprovalsLoader:
    """Load data from FDA Drugs@FDA API."""

    def __init__(self, conn):
        self.conn = conn
        self.session = requests.Session()

    def load_by_brand(self, brand_name: str) -> int:
        """Load approval history for a drug by brand name."""
        return self._load(f'products.brand_name:"{brand_name}"')

    def load_by_generic(self, generic_name: str) -> int:
        """Load approval history for a drug by generic name."""
        return self._load(
            f'(products.active_ingredients.name:"{generic_name}"'
            f'+openfda.generic_name:"{generic_name}")'
        )

    def load_by_application(self, app_number: str) -> int:
        """Load approval history by application number."""
        return self._load(f'application_number:"{app_number}"')

    def _load(self, search_query: str) -> int:
        """Fetch and store FDA approval data."""
        cursor = self.conn.cursor()
        total = 0

        try:
            time.sleep(RATE_LIMIT_DELAY)
            url = f"{FDA_API_BASE}?search={search_query}&limit=100"
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error(f"FDA API error: {e}")
            return 0

        for result in data.get("results", []):
            app_number = result.get("application_number", "")
            sponsor = result.get("sponsor_name", "")

            # Extract product info
            products = result.get("products", [])
            brand_name = None
            generic_name = None
            dosage_form = None
            route = None
            active_ingredients = []
            te_code = None

            for prod in products:
                if not brand_name:
                    brand_name = prod.get("brand_name")
                if not dosage_form:
                    dosage_form = prod.get("dosage_form")
                if not route:
                    route = prod.get("route")
                if not te_code:
                    te_code = prod.get("te_code")
                for ai in prod.get("active_ingredients", []):
                    if not generic_name:
                        generic_name = ai.get("name")
                    active_ingredients.append(ai)

            # Insert each submission as a separate record
            for sub in result.get("submissions", []):
                date_str = sub.get("submission_status_date", "")
                sub_date = None
                if date_str and len(date_str) == 8:
                    try:
                        sub_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                    except Exception:
                        pass

                record = (
                    app_number,
                    sponsor,
                    brand_name,
                    generic_name,
                    result.get("product_type"),
                    dosage_form,
                    route,
                    Json(active_ingredients) if active_ingredients else None,
                    sub.get("submission_type"),
                    sub.get("submission_number"),
                    sub.get("submission_status"),
                    sub_date,
                    sub.get("review_priority"),
                    sub.get("submission_class_code"),
                    sub.get("submission_class_code_description"),
                    te_code,
                    Json(result),
                )

                try:
                    cursor.execute("""
                        INSERT INTO mol_bronze.fda_approvals (
                            application_number, sponsor_name, brand_name, generic_name,
                            product_type, dosage_form, route, active_ingredients,
                            submission_type, submission_number, submission_status,
                            submission_status_date, review_priority,
                            submission_class_code, submission_class_code_description,
                            te_code, raw_json
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (application_number, submission_type, submission_number) DO UPDATE SET
                            submission_status = EXCLUDED.submission_status,
                            submission_status_date = EXCLUDED.submission_status_date,
                            review_priority = EXCLUDED.review_priority,
                            submission_class_code_description = EXCLUDED.submission_class_code_description,
                            raw_json = EXCLUDED.raw_json,
                            source_updated_at = NOW()
                    """, record)
                    total += 1
                except Exception as e:
                    logger.debug(f"Insert error: {e}")

            self.conn.commit()

        logger.info(f"Loaded {total} FDA approval submissions")
        return total


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Load FDA Drugs@FDA Approvals")
    parser.add_argument("--drug", "-d", type=str, help="Brand name to search")
    parser.add_argument("--generic", "-g", type=str, help="Generic name to search")
    parser.add_argument("--application", "-a", type=str, help="Application number (e.g., BLA761069)")

    args = parser.parse_args()

    conn = psycopg2.connect(**DB_CONFIG)
    ensure_tables(conn)

    try:
        loader = FDAApprovalsLoader(conn)
        if args.application:
            total = loader.load_by_application(args.application)
        elif args.generic:
            total = loader.load_by_generic(args.generic)
        elif args.drug:
            total = loader.load_by_brand(args.drug)
        else:
            logger.error("Must specify --drug, --generic, or --application")
            return

        logger.info(f"Total submissions loaded: {total}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
