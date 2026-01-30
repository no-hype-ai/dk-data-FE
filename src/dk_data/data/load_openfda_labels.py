#!/usr/bin/env python3
"""
Load OpenFDA Drug Labels (SPL) data into PostgreSQL.

Uses the OpenFDA Drug Label API to fetch structured product labeling.

Tables populated:
- bronze.openfda_labels: Drug label/SPL records

Usage:
    python -m dk_data.data.load_openfda_labels
    python -m dk_data.data.load_openfda_labels --drug "aspirin"
    python -m dk_data.data.load_openfda_labels --manufacturer "pfizer"
    python -m dk_data.data.load_openfda_labels --limit 5000

Environment:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    OPENFDA_API_KEY (optional, for higher rate limits)
"""

import os
import time
from typing import Optional, List, Dict, Any

import requests
import psycopg2
from psycopg2.extras import execute_values, Json
from loguru import logger
from tqdm import tqdm

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "dk_data"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

OPENFDA_API_BASE = "https://api.fda.gov/drug/label.json"
OPENFDA_API_KEY = os.getenv("OPENFDA_API_KEY")
RATE_LIMIT_DELAY = 0.25 if OPENFDA_API_KEY else 0.5
PAGE_SIZE = 100
MAX_SKIP = 25000


def ensure_tables(conn):
    """Ensure OpenFDA Labels tables exist."""
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.openfda_labels (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            spl_id VARCHAR(50) UNIQUE,
            spl_set_id VARCHAR(50),
            effective_time DATE,
            version VARCHAR(20),
            product_type VARCHAR(100),
            brand_name TEXT,
            generic_name TEXT,
            manufacturer_name TEXT,
            substance_name TEXT[],
            route TEXT[],
            dosage_form TEXT,
            ndc TEXT[],
            unii TEXT[],
            rxcui TEXT[],
            spl_product_data_elements TEXT[],
            indications_and_usage TEXT,
            dosage_and_administration TEXT,
            contraindications TEXT,
            warnings TEXT,
            warnings_and_cautions TEXT,
            adverse_reactions TEXT,
            drug_interactions TEXT,
            clinical_pharmacology TEXT,
            mechanism_of_action TEXT,
            pharmacodynamics TEXT,
            pharmacokinetics TEXT,
            overdosage TEXT,
            pregnancy TEXT,
            nursing_mothers TEXT,
            pediatric_use TEXT,
            geriatric_use TEXT,
            boxed_warning TEXT,
            openfda_data JSONB,
            raw_json JSONB,
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            processed_to_silver BOOLEAN DEFAULT FALSE
        );

        CREATE INDEX IF NOT EXISTS idx_labels_spl_id ON bronze.openfda_labels(spl_id);
        CREATE INDEX IF NOT EXISTS idx_labels_brand ON bronze.openfda_labels(brand_name);
        CREATE INDEX IF NOT EXISTS idx_labels_generic ON bronze.openfda_labels(generic_name);
        CREATE INDEX IF NOT EXISTS idx_labels_manufacturer ON bronze.openfda_labels(manufacturer_name);
        CREATE INDEX IF NOT EXISTS idx_labels_substance ON bronze.openfda_labels USING GIN(substance_name);
        CREATE INDEX IF NOT EXISTS idx_labels_unii ON bronze.openfda_labels USING GIN(unii);
        CREATE INDEX IF NOT EXISTS idx_labels_processed ON bronze.openfda_labels(processed_to_silver);
    """)

    conn.commit()
    logger.info("OpenFDA Labels tables ensured")


class OpenFDALabelsLoader:
    """Load data from OpenFDA Drug Label API."""

    def __init__(self, conn):
        self.conn = conn
        self.session = requests.Session()

    def load_labels(
        self,
        drug: str = None,
        manufacturer: str = None,
        route: str = None,
        product_type: str = None,
        limit: int = None
    ) -> int:
        """
        Load drug labels.

        Args:
            drug: Drug name filter (brand or generic)
            manufacturer: Manufacturer name filter
            route: Route of administration filter
            product_type: Product type filter
            limit: Maximum number of labels to load

        Returns:
            Number of labels loaded
        """
        cursor = self.conn.cursor()

        # Build search query
        search_parts = []
        if drug:
            search_parts.append(f'(openfda.brand_name:"{drug}"+OR+openfda.generic_name:"{drug}")')
        if manufacturer:
            search_parts.append(f'openfda.manufacturer_name:"{manufacturer}"')
        if route:
            search_parts.append(f'openfda.route:"{route}"')
        if product_type:
            search_parts.append(f'openfda.product_type:"{product_type}"')

        search_query = "+AND+".join(search_parts) if search_parts else None

        total_loaded = 0
        skip = 0

        with tqdm(desc="Loading drug labels", unit=" labels") as pbar:
            while True:
                if limit and total_loaded >= limit:
                    break

                if skip >= MAX_SKIP:
                    logger.warning(f"Reached OpenFDA skip limit ({MAX_SKIP})")
                    break

                params = {
                    "limit": min(PAGE_SIZE, limit - total_loaded if limit else PAGE_SIZE),
                    "skip": skip
                }

                if search_query:
                    params["search"] = search_query

                if OPENFDA_API_KEY:
                    params["api_key"] = OPENFDA_API_KEY

                try:
                    time.sleep(RATE_LIMIT_DELAY)
                    response = self.session.get(
                        OPENFDA_API_BASE,
                        params=params,
                        timeout=60
                    )

                    if response.status_code == 404:
                        break

                    response.raise_for_status()
                    data = response.json()

                except requests.exceptions.RequestException as e:
                    logger.error(f"API error: {e}")
                    break

                results = data.get("results", [])
                if not results:
                    break

                batch = []
                for label in results:
                    record = self._parse_label(label)
                    if record:
                        batch.append(record)

                if batch:
                    self._insert_batch(cursor, batch)
                    self.conn.commit()
                    total_loaded += len(batch)
                    pbar.update(len(batch))

                skip += len(results)

                if len(results) < PAGE_SIZE:
                    break

        logger.info(f"Loaded {total_loaded} drug labels")
        return total_loaded

    def _parse_label(self, label: Dict[str, Any]) -> Optional[tuple]:
        """Parse a drug label record."""
        try:
            spl_id = label.get("id")
            if not spl_id:
                return None

            openfda = label.get("openfda", {})

            # Parse date
            effective_time = label.get("effective_time")
            if effective_time and len(effective_time) == 8:
                effective_time = f"{effective_time[:4]}-{effective_time[4:6]}-{effective_time[6:8]}"
            else:
                effective_time = None

            # Helper to get first element or join list
            def get_text(key):
                val = label.get(key)
                if isinstance(val, list):
                    return "\n\n".join(val) if val else None
                return val

            return (
                spl_id,
                label.get("set_id"),
                effective_time,
                label.get("version"),
                openfda.get("product_type", [None])[0] if openfda.get("product_type") else None,
                openfda.get("brand_name", [None])[0] if openfda.get("brand_name") else None,
                openfda.get("generic_name", [None])[0] if openfda.get("generic_name") else None,
                openfda.get("manufacturer_name", [None])[0] if openfda.get("manufacturer_name") else None,
                openfda.get("substance_name") or None,
                openfda.get("route") or None,
                label.get("dosage_forms_and_strengths", [""])[0] if label.get("dosage_forms_and_strengths") else None,
                openfda.get("package_ndc") or None,
                openfda.get("unii") or None,
                openfda.get("rxcui") or None,
                openfda.get("spl_product_data_elements") or None,
                get_text("indications_and_usage"),
                get_text("dosage_and_administration"),
                get_text("contraindications"),
                get_text("warnings"),
                get_text("warnings_and_cautions"),
                get_text("adverse_reactions"),
                get_text("drug_interactions"),
                get_text("clinical_pharmacology"),
                get_text("mechanism_of_action"),
                get_text("pharmacodynamics"),
                get_text("pharmacokinetics"),
                get_text("overdosage"),
                get_text("pregnancy"),
                get_text("nursing_mothers"),
                get_text("pediatric_use"),
                get_text("geriatric_use"),
                get_text("boxed_warning"),
                Json(openfda) if openfda else None,
                Json(label),
            )

        except Exception as e:
            logger.debug(f"Error parsing label: {e}")
            return None

    def _insert_batch(self, cursor, records: List[tuple]):
        """Insert batch of records."""
        execute_values(
            cursor,
            """
            INSERT INTO bronze.openfda_labels (
                spl_id, spl_set_id, effective_time, version,
                product_type, brand_name, generic_name, manufacturer_name,
                substance_name, route, dosage_form, ndc, unii, rxcui,
                spl_product_data_elements, indications_and_usage,
                dosage_and_administration, contraindications, warnings,
                warnings_and_cautions, adverse_reactions, drug_interactions,
                clinical_pharmacology, mechanism_of_action, pharmacodynamics,
                pharmacokinetics, overdosage, pregnancy, nursing_mothers,
                pediatric_use, geriatric_use, boxed_warning,
                openfda_data, raw_json
            ) VALUES %s
            ON CONFLICT (spl_id) DO UPDATE SET
                effective_time = EXCLUDED.effective_time,
                version = EXCLUDED.version,
                raw_json = EXCLUDED.raw_json,
                source_updated_at = NOW()
            """,
            records
        )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Load OpenFDA Drug Labels")
    parser.add_argument("--drug", "-d", type=str, help="Drug name filter")
    parser.add_argument("--manufacturer", "-m", type=str, help="Manufacturer filter")
    parser.add_argument("--route", "-r", type=str, help="Route of administration filter")
    parser.add_argument("--product-type", type=str, help="Product type filter")
    parser.add_argument("--limit", type=int, help="Maximum labels to load")

    args = parser.parse_args()

    logger.info("Connecting to PostgreSQL...")
    conn = psycopg2.connect(**DB_CONFIG)
    logger.info(f"Connected to {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")

    ensure_tables(conn)

    try:
        loader = OpenFDALabelsLoader(conn)
        total = loader.load_labels(
            drug=args.drug,
            manufacturer=args.manufacturer,
            route=args.route,
            product_type=args.product_type,
            limit=args.limit
        )

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM bronze.openfda_labels")
        count = cursor.fetchone()[0]

        logger.info("\n=== Summary ===")
        logger.info(f"Loaded in this run: {total}")
        logger.info(f"Total in database: {count:,}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
