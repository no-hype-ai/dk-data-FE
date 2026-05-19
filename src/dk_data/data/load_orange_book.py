#!/usr/bin/env python3
"""
FDA Orange Book Loader

Loads Orange Book data (approved drug products, patents, exclusivities) into PostgreSQL.

Tables populated:
- mol_bronze.orange_book_products: Approved drug products with therapeutic equivalence
- mol_bronze.orange_book_patents: Patent information (expiry dates, drug substance/product)
- mol_bronze.orange_book_exclusivities: Exclusivity information (NCE, orphan, pediatric)

Data Source: https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files

Usage:
    # Download and load all Orange Book data
    python -m dk_data.data.load_orange_book --download

    # Load from existing cache
    python -m dk_data.data.load_orange_book

    # Search for specific products
    python -m dk_data.data.load_orange_book --search "lipitor"

    # Test with limit
    python -m dk_data.data.load_orange_book --limit 1000

Environment:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
"""

import os
import sys
import asyncio
from typing import List
import argparse

import psycopg2
from psycopg2.extras import Json
from loguru import logger
from tqdm import tqdm

from dk_data.ingestion.utils.database import build_dsn
from dk_data.services.external_apis.orange_book_client import (
    OrangeBookClient,
    OrangeBookProduct,
    OrangeBookPatent,
    OrangeBookExclusivity,
)

# Database config
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "dk_data"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}


def ensure_tables(conn) -> None:
    """Create Orange Book tables if they don't exist."""
    with conn.cursor() as cur:
        # Products table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mol_bronze.orange_book_products (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                appl_no TEXT NOT NULL,
                product_no TEXT NOT NULL,
                trade_name TEXT,
                ingredient TEXT,
                applicant TEXT,
                strength TEXT,
                dosage_form TEXT,
                route TEXT,
                te_code TEXT,
                approval_date DATE,
                rld BOOLEAN DEFAULT FALSE,
                rs BOOLEAN DEFAULT FALSE,
                type TEXT DEFAULT 'RX',
                applicant_full_name TEXT,
                raw_data JSONB,
                source_updated_at TIMESTAMPTZ DEFAULT NOW(),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                processed_to_silver BOOLEAN DEFAULT FALSE,
                UNIQUE(appl_no, product_no)
            );

            CREATE INDEX IF NOT EXISTS idx_ob_products_appl ON mol_bronze.orange_book_products(appl_no);
            CREATE INDEX IF NOT EXISTS idx_ob_products_trade ON mol_bronze.orange_book_products(trade_name);
            CREATE INDEX IF NOT EXISTS idx_ob_products_ingredient ON mol_bronze.orange_book_products(ingredient);
            CREATE INDEX IF NOT EXISTS idx_ob_products_approval ON mol_bronze.orange_book_products(approval_date);
            CREATE INDEX IF NOT EXISTS idx_ob_products_te ON mol_bronze.orange_book_products(te_code);
            CREATE INDEX IF NOT EXISTS idx_ob_products_rld ON mol_bronze.orange_book_products(rld);
            CREATE INDEX IF NOT EXISTS idx_ob_products_processed ON mol_bronze.orange_book_products(processed_to_silver);
        """)

        # Patents table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mol_bronze.orange_book_patents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                appl_no TEXT NOT NULL,
                product_no TEXT NOT NULL,
                patent_no TEXT NOT NULL,
                patent_expire_date DATE,
                drug_substance_flag BOOLEAN DEFAULT FALSE,
                drug_product_flag BOOLEAN DEFAULT FALSE,
                patent_use_code TEXT,
                delist_flag BOOLEAN DEFAULT FALSE,
                raw_data JSONB,
                source_updated_at TIMESTAMPTZ DEFAULT NOW(),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                processed_to_silver BOOLEAN DEFAULT FALSE,
                UNIQUE(appl_no, product_no, patent_no)
            );

            CREATE INDEX IF NOT EXISTS idx_ob_patents_appl ON mol_bronze.orange_book_patents(appl_no);
            CREATE INDEX IF NOT EXISTS idx_ob_patents_patent ON mol_bronze.orange_book_patents(patent_no);
            CREATE INDEX IF NOT EXISTS idx_ob_patents_expire ON mol_bronze.orange_book_patents(patent_expire_date);
            CREATE INDEX IF NOT EXISTS idx_ob_patents_substance ON mol_bronze.orange_book_patents(drug_substance_flag);
            CREATE INDEX IF NOT EXISTS idx_ob_patents_processed ON mol_bronze.orange_book_patents(processed_to_silver);
        """)

        # Exclusivities table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mol_bronze.orange_book_exclusivities (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                appl_no TEXT NOT NULL,
                product_no TEXT NOT NULL,
                exclusivity_code TEXT NOT NULL,
                exclusivity_date DATE,
                raw_data JSONB,
                source_updated_at TIMESTAMPTZ DEFAULT NOW(),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                processed_to_silver BOOLEAN DEFAULT FALSE,
                UNIQUE(appl_no, product_no, exclusivity_code, exclusivity_date)
            );

            CREATE INDEX IF NOT EXISTS idx_ob_excl_appl ON mol_bronze.orange_book_exclusivities(appl_no);
            CREATE INDEX IF NOT EXISTS idx_ob_excl_code ON mol_bronze.orange_book_exclusivities(exclusivity_code);
            CREATE INDEX IF NOT EXISTS idx_ob_excl_date ON mol_bronze.orange_book_exclusivities(exclusivity_date);
            CREATE INDEX IF NOT EXISTS idx_ob_excl_processed ON mol_bronze.orange_book_exclusivities(processed_to_silver);
        """)

        conn.commit()
    logger.info("Orange Book tables ensured")


def insert_products(conn, products: List[OrangeBookProduct], limit: int = None) -> int:
    """Insert products into database."""
    inserted = 0

    products_to_insert = products[:limit] if limit else products

    with conn.cursor() as cur:
        for product in tqdm(products_to_insert, desc="Inserting products"):
            try:
                data = product.to_dict()
                cur.execute("""
                    INSERT INTO mol_bronze.orange_book_products (
                        appl_no, product_no, trade_name, ingredient, applicant,
                        strength, dosage_form, route, te_code, approval_date,
                        rld, rs, type, applicant_full_name, raw_data
                    ) VALUES (
                        %(appl_no)s, %(product_no)s, %(trade_name)s, %(ingredient)s, %(applicant)s,
                        %(strength)s, %(dosage_form)s, %(route)s, %(te_code)s, %(approval_date)s,
                        %(rld)s, %(rs)s, %(type)s, %(applicant_full_name)s, %(raw_data)s
                    )
                    ON CONFLICT (appl_no, product_no) DO UPDATE SET
                        trade_name = EXCLUDED.trade_name,
                        te_code = EXCLUDED.te_code,
                        source_updated_at = NOW()
                """, {
                    "appl_no": product.appl_no,
                    "product_no": product.product_no,
                    "trade_name": product.trade_name,
                    "ingredient": product.ingredient,
                    "applicant": product.applicant,
                    "strength": product.strength,
                    "dosage_form": product.dosage_form,
                    "route": product.route,
                    "te_code": product.te_code,
                    "approval_date": product.approval_date,
                    "rld": product.rld,
                    "rs": product.rs,
                    "type": product.type,
                    "applicant_full_name": product.applicant_full_name,
                    "raw_data": Json(data),
                })
                inserted += 1
            except Exception as e:
                logger.warning(f"Error inserting product {product.appl_no}: {e}")
                conn.rollback()
                continue

        conn.commit()

    return inserted


def insert_patents(conn, patents: List[OrangeBookPatent], limit: int = None) -> int:
    """Insert patents into database."""
    inserted = 0

    patents_to_insert = patents[:limit] if limit else patents

    with conn.cursor() as cur:
        for patent in tqdm(patents_to_insert, desc="Inserting patents"):
            try:
                data = patent.to_dict()
                cur.execute("""
                    INSERT INTO mol_bronze.orange_book_patents (
                        appl_no, product_no, patent_no, patent_expire_date,
                        drug_substance_flag, drug_product_flag, patent_use_code,
                        delist_flag, raw_data
                    ) VALUES (
                        %(appl_no)s, %(product_no)s, %(patent_no)s, %(patent_expire_date)s,
                        %(drug_substance_flag)s, %(drug_product_flag)s, %(patent_use_code)s,
                        %(delist_flag)s, %(raw_data)s
                    )
                    ON CONFLICT (appl_no, product_no, patent_no) DO UPDATE SET
                        patent_expire_date = EXCLUDED.patent_expire_date,
                        delist_flag = EXCLUDED.delist_flag,
                        source_updated_at = NOW()
                """, {
                    "appl_no": patent.appl_no,
                    "product_no": patent.product_no,
                    "patent_no": patent.patent_no,
                    "patent_expire_date": patent.patent_expire_date,
                    "drug_substance_flag": patent.drug_substance_flag,
                    "drug_product_flag": patent.drug_product_flag,
                    "patent_use_code": patent.patent_use_code,
                    "delist_flag": patent.delist_flag,
                    "raw_data": Json(data),
                })
                inserted += 1
            except Exception as e:
                logger.warning(f"Error inserting patent {patent.patent_no}: {e}")
                conn.rollback()
                continue

        conn.commit()

    return inserted


def insert_exclusivities(conn, exclusivities: List[OrangeBookExclusivity], limit: int = None) -> int:
    """Insert exclusivities into database."""
    inserted = 0

    excl_to_insert = exclusivities[:limit] if limit else exclusivities

    with conn.cursor() as cur:
        for excl in tqdm(excl_to_insert, desc="Inserting exclusivities"):
            try:
                data = excl.to_dict()
                cur.execute("""
                    INSERT INTO mol_bronze.orange_book_exclusivities (
                        appl_no, product_no, exclusivity_code, exclusivity_date, raw_data
                    ) VALUES (
                        %(appl_no)s, %(product_no)s, %(exclusivity_code)s, %(exclusivity_date)s, %(raw_data)s
                    )
                    ON CONFLICT (appl_no, product_no, exclusivity_code, exclusivity_date) DO UPDATE SET
                        source_updated_at = NOW()
                """, {
                    "appl_no": excl.appl_no,
                    "product_no": excl.product_no,
                    "exclusivity_code": excl.exclusivity_code,
                    "exclusivity_date": excl.exclusivity_date,
                    "raw_data": Json(data),
                })
                inserted += 1
            except Exception as e:
                logger.warning(f"Error inserting exclusivity {excl.appl_no}/{excl.exclusivity_code}: {e}")
                conn.rollback()
                continue

        conn.commit()

    return inserted


async def main():
    parser = argparse.ArgumentParser(description="Load FDA Orange Book data")
    parser.add_argument("--download", action="store_true", help="Download fresh data from FDA")
    parser.add_argument("--search", type=str, help="Search for products by name/ingredient")
    parser.add_argument("--limit", type=int, help="Limit records to load")
    args = parser.parse_args()

    logger.info("Starting Orange Book loader")

    # Initialize client
    client = OrangeBookClient()

    # Download data if requested
    if args.download:
        success = await client.download_data(force=True)
        if not success:
            logger.error("Failed to download Orange Book data")
            sys.exit(1)

    # Load data
    success = await client.load_data()
    if not success:
        logger.error("Failed to load Orange Book data. Try with --download flag.")
        sys.exit(1)

    # If search mode, just display results
    if args.search:
        products = await client.search_products(args.search, limit=args.limit or 20)
        logger.info(f"Found {len(products)} products matching '{args.search}':")
        for p in products:
            logger.info(f"  {p.trade_name} ({p.ingredient}) - {p.appl_no} - TE: {p.te_code}")
        return

    # Connect to database
    conn = psycopg2.connect(build_dsn())
    ensure_tables(conn)

    try:
        # Get all data
        products = await client.get_all_products()
        patents = await client.get_all_patents()
        exclusivities = await client.get_all_exclusivities()

        logger.info(f"Loaded {len(products)} products, {len(patents)} patents, {len(exclusivities)} exclusivities from cache")

        # Insert into database
        prod_count = insert_products(conn, products, args.limit)
        pat_count = insert_patents(conn, patents, args.limit)
        excl_count = insert_exclusivities(conn, exclusivities, args.limit)

        logger.info("Orange Book loading complete:")
        logger.info(f"  Products: {prod_count}")
        logger.info(f"  Patents: {pat_count}")
        logger.info(f"  Exclusivities: {excl_count}")

    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
