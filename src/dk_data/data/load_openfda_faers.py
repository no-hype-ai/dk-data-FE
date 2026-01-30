#!/usr/bin/env python3
"""
Load OpenFDA FAERS (FDA Adverse Event Reporting System) data into PostgreSQL.

Uses the OpenFDA Drug Adverse Events API.

Tables populated:
- bronze.openfda_faers: Adverse event reports

Usage:
    python -m dk_data.data.load_openfda_faers
    python -m dk_data.data.load_openfda_faers --drug "aspirin"
    python -m dk_data.data.load_openfda_faers --reaction "headache"
    python -m dk_data.data.load_openfda_faers --limit 10000

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

OPENFDA_API_BASE = "https://api.fda.gov/drug/event.json"
OPENFDA_API_KEY = os.getenv("OPENFDA_API_KEY")
RATE_LIMIT_DELAY = 0.25 if OPENFDA_API_KEY else 0.5
PAGE_SIZE = 100
MAX_SKIP = 25000  # OpenFDA limits skip to 25000


def ensure_tables(conn):
    """Ensure OpenFDA FAERS tables exist."""
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.openfda_faers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            safety_report_id VARCHAR(50) UNIQUE,
            report_type VARCHAR(10),
            receive_date DATE,
            receipt_date DATE,
            serious BOOLEAN,
            serious_death BOOLEAN,
            serious_hospitalization BOOLEAN,
            serious_life_threatening BOOLEAN,
            serious_disability BOOLEAN,
            serious_congenital_anomaly BOOLEAN,
            serious_other BOOLEAN,
            patient_age DOUBLE PRECISION,
            patient_age_unit VARCHAR(20),
            patient_sex VARCHAR(10),
            patient_weight DOUBLE PRECISION,
            patient_weight_unit VARCHAR(10),
            occurrence_country VARCHAR(10),
            reporter_qualification VARCHAR(50),
            drugs JSONB,
            drug_names TEXT[],
            drug_indications TEXT[],
            reactions JSONB,
            reaction_terms TEXT[],
            outcomes TEXT[],
            openfda_data JSONB,
            raw_json JSONB,
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            processed_to_silver BOOLEAN DEFAULT FALSE
        );

        CREATE INDEX IF NOT EXISTS idx_faers_report_id ON bronze.openfda_faers(safety_report_id);
        CREATE INDEX IF NOT EXISTS idx_faers_receive_date ON bronze.openfda_faers(receive_date);
        CREATE INDEX IF NOT EXISTS idx_faers_serious ON bronze.openfda_faers(serious);
        CREATE INDEX IF NOT EXISTS idx_faers_drugs ON bronze.openfda_faers USING GIN(drug_names);
        CREATE INDEX IF NOT EXISTS idx_faers_reactions ON bronze.openfda_faers USING GIN(reaction_terms);
        CREATE INDEX IF NOT EXISTS idx_faers_processed ON bronze.openfda_faers(processed_to_silver);
    """)

    conn.commit()
    logger.info("OpenFDA FAERS tables ensured")


class OpenFDAFaersLoader:
    """Load data from OpenFDA Drug Adverse Events API."""

    def __init__(self, conn):
        self.conn = conn
        self.session = requests.Session()

    def load_events(
        self,
        drug: str = None,
        reaction: str = None,
        serious: bool = None,
        date_start: str = None,
        date_end: str = None,
        limit: int = None
    ) -> int:
        """
        Load adverse event reports.

        Args:
            drug: Drug name filter
            reaction: Reaction term filter
            serious: Filter for serious events only
            date_start: Start date (YYYYMMDD)
            date_end: End date (YYYYMMDD)
            limit: Maximum number of events to load

        Returns:
            Number of events loaded
        """
        cursor = self.conn.cursor()

        # Build search query
        search_parts = []
        if drug:
            search_parts.append(f'patient.drug.medicinalproduct:"{drug}"')
        if reaction:
            search_parts.append(f'patient.reaction.reactionmeddrapt:"{reaction}"')
        if serious is True:
            search_parts.append("serious:1")
        if date_start and date_end:
            search_parts.append(f"receivedate:[{date_start}+TO+{date_end}]")

        search_query = "+AND+".join(search_parts) if search_parts else None

        total_loaded = 0
        skip = 0

        with tqdm(desc="Loading FAERS events", unit=" events") as pbar:
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
                        # No more results
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
                for event in results:
                    record = self._parse_event(event)
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

        logger.info(f"Loaded {total_loaded} adverse event reports")
        return total_loaded

    def _parse_event(self, event: Dict[str, Any]) -> Optional[tuple]:
        """Parse an adverse event record."""
        try:
            safety_report_id = event.get("safetyreportid")
            if not safety_report_id:
                return None

            patient = event.get("patient", {})

            # Parse drugs
            drugs = patient.get("drug", [])
            drug_names = list(set([
                d.get("medicinalproduct", "").upper()
                for d in drugs if d.get("medicinalproduct")
            ]))
            drug_indications = list(set([
                d.get("drugindication", "")
                for d in drugs if d.get("drugindication")
            ]))

            # Parse reactions
            reactions = patient.get("reaction", [])
            reaction_terms = list(set([
                r.get("reactionmeddrapt", "")
                for r in reactions if r.get("reactionmeddrapt")
            ]))
            outcomes = list(set([
                r.get("reactionoutcome")
                for r in reactions if r.get("reactionoutcome")
            ]))

            # Parse dates
            def parse_date(date_str):
                if date_str and len(date_str) == 8:
                    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                return None

            # Parse age
            patient_age = None
            patient_age_unit = None
            if patient.get("patientonsetage"):
                patient_age = float(patient.get("patientonsetage"))
                patient_age_unit = patient.get("patientonsetageunit")

            return (
                safety_report_id,
                event.get("reporttype"),
                parse_date(event.get("receivedate")),
                parse_date(event.get("receiptdate")),
                event.get("serious") == "1",
                event.get("seriousnessdeath") == "1",
                event.get("seriousnesshospitalization") == "1",
                event.get("seriousnesslifethreatening") == "1",
                event.get("seriousnessdisabling") == "1",
                event.get("seriousnesscongenitalanomali") == "1",
                event.get("seriousnessother") == "1",
                patient_age,
                patient_age_unit,
                patient.get("patientsex"),
                float(patient.get("patientweight")) if patient.get("patientweight") else None,
                patient.get("patientweightunit"),
                event.get("occurcountry"),
                event.get("primarysource", {}).get("qualification"),
                Json(drugs) if drugs else None,
                drug_names or None,
                drug_indications or None,
                Json(reactions) if reactions else None,
                reaction_terms or None,
                outcomes or None,
                Json(event.get("openfda", {})) if event.get("openfda") else None,
                Json(event),
            )

        except Exception as e:
            logger.debug(f"Error parsing event: {e}")
            return None

    def _insert_batch(self, cursor, records: List[tuple]):
        """Insert batch of records."""
        execute_values(
            cursor,
            """
            INSERT INTO bronze.openfda_faers (
                safety_report_id, report_type, receive_date, receipt_date,
                serious, serious_death, serious_hospitalization,
                serious_life_threatening, serious_disability,
                serious_congenital_anomaly, serious_other,
                patient_age, patient_age_unit, patient_sex,
                patient_weight, patient_weight_unit,
                occurrence_country, reporter_qualification,
                drugs, drug_names, drug_indications,
                reactions, reaction_terms, outcomes,
                openfda_data, raw_json
            ) VALUES %s
            ON CONFLICT (safety_report_id) DO UPDATE SET
                source_updated_at = NOW()
            """,
            records
        )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Load OpenFDA FAERS data")
    parser.add_argument("--drug", "-d", type=str, help="Drug name filter")
    parser.add_argument("--reaction", "-r", type=str, help="Reaction term filter")
    parser.add_argument("--serious", action="store_true", help="Only serious events")
    parser.add_argument("--date-start", type=str, help="Start date (YYYYMMDD)")
    parser.add_argument("--date-end", type=str, help="End date (YYYYMMDD)")
    parser.add_argument("--limit", type=int, help="Maximum events to load")

    args = parser.parse_args()

    logger.info("Connecting to PostgreSQL...")
    conn = psycopg2.connect(**DB_CONFIG)
    logger.info(f"Connected to {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")

    ensure_tables(conn)

    try:
        loader = OpenFDAFaersLoader(conn)
        total = loader.load_events(
            drug=args.drug,
            reaction=args.reaction,
            serious=args.serious if args.serious else None,
            date_start=args.date_start,
            date_end=args.date_end,
            limit=args.limit
        )

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM bronze.openfda_faers")
        count = cursor.fetchone()[0]

        logger.info("\n=== Summary ===")
        logger.info(f"Loaded in this run: {total}")
        logger.info(f"Total in database: {count:,}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
