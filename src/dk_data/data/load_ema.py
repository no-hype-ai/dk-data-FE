#!/usr/bin/env python3
"""
EMA (European Medicines Agency) Medicines Loader

Loads EMA authorized medicines data into PostgreSQL.
Uses downloadable EMA medicine data and local JSON cache.

Tables populated:
- mol_bronze.ema: EMA authorized medicines with regulatory details

Data source: https://www.ema.europa.eu/en/medicines/download-medicine-data

Usage:
    # Download and load EMA data
    python -m dk_data.data.load_ema --download

    # Load from existing JSON cache
    python -m dk_data.data.load_ema

    # Test with limit
    python -m dk_data.data.load_ema --limit 100

Environment:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
"""

import os
import sys
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import argparse

import psycopg2
from psycopg2.extras import Json
from loguru import logger
from tqdm import tqdm
from dk_data.ingestion.utils.database import build_dsn

try:
    import aiohttp
    import pandas as pd
    DOWNLOAD_AVAILABLE = True
except ImportError:
    DOWNLOAD_AVAILABLE = False

# Database config
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "dk_data"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

# Data paths
DATA_DIR = Path(__file__).parent.parent / "services" / "external_apis" / "data"
EMA_JSON_PATH = DATA_DIR / "ema_medicines.json"

# EMA download URLs
EMA_EXCEL_URL = "https://www.ema.europa.eu/sites/default/files/Medicines_output_european_public_assessment_reports.xlsx"


def ensure_tables(conn) -> None:
    """Create EMA tables if they don't exist."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mol_bronze.ema (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                product_name TEXT NOT NULL,
                active_substance TEXT,
                inn TEXT,
                authorization_number TEXT UNIQUE,
                authorization_date DATE,
                authorization_type TEXT DEFAULT 'centralised',
                status TEXT DEFAULT 'authorized',
                therapeutic_area TEXT,
                atc_code TEXT,
                marketing_auth_holder TEXT,
                orphan_medicine BOOLEAN DEFAULT FALSE,
                biosimilar BOOLEAN DEFAULT FALSE,
                generic BOOLEAN DEFAULT FALSE,
                conditions JSONB DEFAULT '[]',
                smpc_url TEXT,
                epar_url TEXT,
                revision_date DATE,
                raw_data JSONB,
                source_updated_at TIMESTAMPTZ DEFAULT NOW(),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                processed_to_silver BOOLEAN DEFAULT FALSE
            );

            CREATE INDEX IF NOT EXISTS idx_ema_name ON mol_bronze.ema(product_name);
            CREATE INDEX IF NOT EXISTS idx_ema_substance ON mol_bronze.ema(active_substance);
            CREATE INDEX IF NOT EXISTS idx_ema_inn ON mol_bronze.ema(inn);
            CREATE INDEX IF NOT EXISTS idx_ema_atc ON mol_bronze.ema(atc_code);
            CREATE INDEX IF NOT EXISTS idx_ema_status ON mol_bronze.ema(status);
            CREATE INDEX IF NOT EXISTS idx_ema_processed ON mol_bronze.ema(processed_to_silver);
        """)
        conn.commit()
    logger.info("EMA tables ensured")


async def download_ema_data() -> Optional[List[Dict[str, Any]]]:
    """Download EMA medicine data from official source."""
    if not DOWNLOAD_AVAILABLE:
        logger.error("pandas and aiohttp required for download. Install with: pip install pandas aiohttp openpyxl")
        return None

    logger.info("Downloading EMA medicine data...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(EMA_EXCEL_URL, timeout=aiohttp.ClientTimeout(total=120)) as response:
                if response.status != 200:
                    logger.error(f"Failed to download EMA data: HTTP {response.status}")
                    return None

                content = await response.read()

        # Parse Excel file
        import io
        df = pd.read_excel(io.BytesIO(content), engine='openpyxl')

        # Convert to list of dicts
        medicines = []
        for _, row in df.iterrows():
            medicine = {
                "name": row.get("Medicine name", ""),
                "active_substance": row.get("Active substance", ""),
                "inn": row.get("International non-proprietary name (INN) / common name", ""),
                "ema_product_number": row.get("Product number", ""),
                "status": row.get("Authorisation status", "Authorised"),
                "therapeutic_area": row.get("Therapeutic area", ""),
                "atc_code": row.get("ATC code", ""),
                "marketing_auth_holder": row.get("Marketing-authorisation holder", ""),
                "orphan_medicine": "Yes" in str(row.get("Orphan medicine", "")),
                "biosimilar": "Yes" in str(row.get("Biosimilar", "")),
                "generic": "Yes" in str(row.get("Generic", "")),
            }

            # Parse authorization date
            auth_date = row.get("Marketing authorisation date")
            if pd.notna(auth_date):
                try:
                    if isinstance(auth_date, datetime):
                        medicine["authorization_date"] = auth_date.strftime("%Y-%m-%d")
                    else:
                        medicine["authorization_date"] = str(auth_date)
                except Exception:
                    pass

            medicines.append(medicine)

        # Save to JSON cache
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(EMA_JSON_PATH, "w") as f:
            json.dump({"medicines": medicines, "updated": datetime.now().isoformat()}, f, indent=2)

        logger.info(f"Downloaded and cached {len(medicines)} EMA medicines")
        return medicines

    except Exception as e:
        logger.error(f"Error downloading EMA data: {e}")
        return None


def load_from_json() -> Optional[List[Dict[str, Any]]]:
    """Load EMA data from JSON cache."""
    if not EMA_JSON_PATH.exists():
        logger.warning(f"EMA JSON cache not found: {EMA_JSON_PATH}")
        return None

    try:
        with open(EMA_JSON_PATH) as f:
            data = json.load(f)
        medicines = data.get("medicines", [])
        logger.info(f"Loaded {len(medicines)} medicines from JSON cache")
        return medicines
    except Exception as e:
        logger.error(f"Error loading EMA JSON: {e}")
        return None


def insert_medicines(conn, medicines: List[Dict[str, Any]], limit: int = None) -> int:
    """Insert EMA medicines into database."""
    inserted = 0

    with conn.cursor() as cur:
        for medicine in tqdm(medicines[:limit] if limit else medicines, desc="Inserting EMA medicines"):
            try:
                # Parse authorization date
                auth_date = None
                if medicine.get("authorization_date"):
                    try:
                        auth_date = datetime.strptime(medicine["authorization_date"], "%Y-%m-%d").date()
                    except Exception:
                        pass

                cur.execute("""
                    INSERT INTO mol_bronze.ema (
                        product_name, active_substance, inn, authorization_number,
                        authorization_date, status, therapeutic_area, atc_code,
                        marketing_auth_holder, orphan_medicine, biosimilar, generic,
                        raw_data
                    ) VALUES (
                        %(name)s, %(active_substance)s, %(inn)s, %(ema_product_number)s,
                        %(auth_date)s, %(status)s, %(therapeutic_area)s, %(atc_code)s,
                        %(marketing_auth_holder)s, %(orphan_medicine)s, %(biosimilar)s, %(generic)s,
                        %(raw_data)s
                    )
                    ON CONFLICT (authorization_number) DO UPDATE SET
                        status = EXCLUDED.status,
                        source_updated_at = NOW()
                """, {
                    **medicine,
                    "auth_date": auth_date,
                    "raw_data": Json(medicine),
                })
                inserted += 1

            except Exception as e:
                logger.warning(f"Error inserting {medicine.get('name')}: {e}")
                conn.rollback()
                continue

        conn.commit()

    return inserted


async def main():
    parser = argparse.ArgumentParser(description="Load EMA medicines data")
    parser.add_argument("--download", action="store_true", help="Download fresh data from EMA")
    parser.add_argument("--limit", type=int, help="Limit records to load")
    args = parser.parse_args()

    logger.info("Starting EMA loader")

    # Connect to database
    conn = psycopg2.connect(build_dsn())
    ensure_tables(conn)

    try:
        # Get medicines data
        if args.download:
            medicines = await download_ema_data()
        else:
            medicines = load_from_json()

        if not medicines:
            logger.error("No EMA data available. Try with --download flag.")
            sys.exit(1)

        # Insert into database
        total = insert_medicines(conn, medicines, args.limit)
        logger.info(f"EMA loading complete. Inserted {total} medicines.")

    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
