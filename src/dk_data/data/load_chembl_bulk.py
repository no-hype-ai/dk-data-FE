#!/usr/bin/env python3
"""
Load ChEMBL data using bulk SQLite download.

This is much faster than API access (~3GB download vs 11+ days of API calls).

Strategy:
1. Download ChEMBL SQLite database (~3GB compressed, ~35GB uncompressed)
2. Collect InChI keys from all our compound sources
3. Extract matching activities and target info from ChEMBL

Tables populated:
- mol_bronze.chembl_activities: Bioactivity data
- mol_bronze.chembl_targets: Target information with UniProt mappings

Usage:
    # Download and load ChEMBL data for all our compounds
    python -m dk_data.data.load_chembl_bulk

    # Just download the database (don't load)
    python -m dk_data.data.load_chembl_bulk --download-only

    # Load without filtering (all ChEMBL activities) - WARNING: ~20M records
    python -m dk_data.data.load_chembl_bulk --standalone

    # Limit number of activities for testing
    python -m dk_data.data.load_chembl_bulk --limit 10000

Environment:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
"""

import os
import sys
import sqlite3
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from loguru import logger
from tqdm import tqdm
from dk_data.ingestion.utils.database import build_dsn

try:
    import chembl_downloader
except ImportError:
    logger.error("Please install chembl-downloader: pip install chembl-downloader")
    sys.exit(1)

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "dk_data"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}


def get_chembl_sqlite_path() -> Path:
    """Get path to ChEMBL SQLite database, downloading if needed."""
    logger.info("Getting ChEMBL SQLite database...")
    logger.info("This will download ~3GB compressed (~35GB uncompressed) on first run")
    sqlite_path = chembl_downloader.download_extract_sqlite()
    logger.info(f"ChEMBL database at: {sqlite_path}")
    return Path(sqlite_path)


def get_all_inchi_keys(pg_conn) -> set:
    """Get InChI keys from all our compound sources."""
    pg_cursor = pg_conn.cursor()
    all_keys = set()

    # Source 1: compounds table
    try:
        pg_cursor.execute("SELECT DISTINCT inchi_key FROM mol_bronze.compounds WHERE inchi_key IS NOT NULL")
        keys = {row[0] for row in pg_cursor.fetchall()}
        logger.info(f"  mol_bronze.compounds: {len(keys):,} InChI keys")
        all_keys.update(keys)
    except Exception as e:
        logger.warning(f"  mol_bronze.compounds: skipped ({e})")

    # Source 2: bindingdb_affinities table
    try:
        pg_cursor.execute("SELECT DISTINCT inchi_key FROM mol_bronze.bindingdb_affinities WHERE inchi_key IS NOT NULL")
        keys = {row[0] for row in pg_cursor.fetchall()}
        logger.info(f"  mol_bronze.bindingdb_affinities: {len(keys):,} InChI keys")
        all_keys.update(keys)
    except Exception as e:
        logger.warning(f"  mol_bronze.bindingdb_affinities: skipped ({e})")

    # Source 3: pubchem_compounds table
    try:
        pg_cursor.execute("SELECT DISTINCT inchi_key FROM mol_bronze.pubchem_compounds WHERE inchi_key IS NOT NULL")
        keys = {row[0] for row in pg_cursor.fetchall()}
        logger.info(f"  mol_bronze.pubchem_compounds: {len(keys):,} InChI keys")
        all_keys.update(keys)
    except Exception as e:
        logger.warning(f"  mol_bronze.pubchem_compounds: skipped ({e})")

    return all_keys


def ensure_tables(conn):
    """Ensure required tables exist."""
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mol_bronze.chembl_activities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            inchi_key VARCHAR(27),
            chembl_id VARCHAR(20),
            activity_id INTEGER UNIQUE,
            standard_type VARCHAR(50),
            standard_value DOUBLE PRECISION,
            standard_units VARCHAR(50),
            pchembl_value DOUBLE PRECISION,
            target_chembl_id VARCHAR(20),
            target_pref_name TEXT,
            target_organism VARCHAR(200),
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            processed_to_silver BOOLEAN DEFAULT FALSE
        );

        CREATE INDEX IF NOT EXISTS idx_chembl_activities_inchi ON mol_bronze.chembl_activities(inchi_key);
        CREATE INDEX IF NOT EXISTS idx_chembl_activities_target ON mol_bronze.chembl_activities(target_chembl_id);
        CREATE INDEX IF NOT EXISTS idx_chembl_activities_processed ON mol_bronze.chembl_activities(processed_to_silver);
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mol_bronze.chembl_targets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            chembl_target_id VARCHAR(20),
            protein_name TEXT,
            organism VARCHAR(200),
            target_type VARCHAR(50),
            uniprot_id VARCHAR(20) UNIQUE,
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            processed_to_silver BOOLEAN DEFAULT FALSE
        );

        CREATE INDEX IF NOT EXISTS idx_chembl_targets_uniprot ON mol_bronze.chembl_targets(uniprot_id);
        CREATE INDEX IF NOT EXISTS idx_chembl_targets_chembl ON mol_bronze.chembl_targets(chembl_target_id);
    """)

    conn.commit()
    logger.info("ChEMBL tables ensured")


def load_chembl_activities(
    pg_conn,
    sqlite_path: Path,
    batch_size: int = 10000,
    standalone: bool = False,
    limit: int = None,
) -> int:
    """Load ChEMBL activities for compounds we have."""
    logger.info("Loading ChEMBL activities from bulk database...")

    our_inchi_keys = None
    if not standalone:
        logger.info("Collecting InChI keys from all compound sources...")
        our_inchi_keys = get_all_inchi_keys(pg_conn)
        logger.info(f"Total unique InChI keys: {len(our_inchi_keys):,}")

        if not our_inchi_keys:
            logger.warning("No compounds with InChI keys found in any table")
            return 0
    else:
        logger.info("Standalone mode: loading ALL ChEMBL activities (no filtering)")

    chembl_conn = sqlite3.connect(str(sqlite_path))
    chembl_cursor = chembl_conn.cursor()

    query = """
        SELECT DISTINCT
            cs.standard_inchi_key,
            md.chembl_id as molecule_chembl_id,
            act.activity_id,
            act.standard_type,
            act.standard_value,
            act.standard_units,
            act.pchembl_value,
            td.chembl_id as target_chembl_id,
            td.pref_name as target_name,
            td.organism as target_organism
        FROM compound_structures cs
        JOIN molecule_dictionary md ON cs.molregno = md.molregno
        JOIN activities act ON md.molregno = act.molregno
        JOIN assays ass ON act.assay_id = ass.assay_id
        LEFT JOIN target_dictionary td ON ass.tid = td.tid
        WHERE cs.standard_inchi_key IS NOT NULL
            AND act.standard_value IS NOT NULL
            AND act.standard_type IN ('IC50', 'Ki', 'Kd', 'EC50', 'pIC50', 'pKi', 'pKd')
        ORDER BY cs.standard_inchi_key
    """

    logger.info("Querying ChEMBL database (this may take a few minutes)...")
    chembl_cursor.execute(query)

    total_loaded = 0
    total_processed = 0
    skipped = 0
    batch = []

    pg_cursor = pg_conn.cursor()

    for row in tqdm(chembl_cursor, desc="Processing ChEMBL activities"):
        inchi_key = row[0]
        total_processed += 1

        if our_inchi_keys is not None and inchi_key not in our_inchi_keys:
            skipped += 1
            continue

        batch.append((
            inchi_key, row[1], row[2], row[3], row[4],
            row[5], row[6], row[7], row[8], row[9]
        ))

        if len(batch) >= batch_size:
            execute_values(
                pg_cursor,
                """
                INSERT INTO mol_bronze.chembl_activities (
                    inchi_key, chembl_id, activity_id,
                    standard_type, standard_value, standard_units,
                    pchembl_value, target_chembl_id, target_pref_name, target_organism
                ) VALUES %s
                ON CONFLICT (activity_id) DO NOTHING
                """,
                batch
            )
            pg_conn.commit()
            total_loaded += len(batch)
            batch = []

            if limit and total_loaded >= limit:
                logger.info(f"Reached limit of {limit:,} activities")
                break

        if total_processed % 1_000_000 == 0:
            logger.info(f"  Processed {total_processed:,}, matched {total_loaded:,}, skipped {skipped:,}")

    if batch and (not limit or total_loaded < limit):
        execute_values(
            pg_cursor,
            """
            INSERT INTO mol_bronze.chembl_activities (
                inchi_key, chembl_id, activity_id,
                standard_type, standard_value, standard_units,
                pchembl_value, target_chembl_id, target_pref_name, target_organism
            ) VALUES %s
            ON CONFLICT (activity_id) DO NOTHING
            """,
            batch
        )
        pg_conn.commit()
        total_loaded += len(batch)

    chembl_conn.close()
    logger.info(f"Loaded {total_loaded:,} ChEMBL activities (processed {total_processed:,}, skipped {skipped:,})")
    return total_loaded


def load_target_info(pg_conn, sqlite_path: Path) -> int:
    """Load target information from ChEMBL including UniProt mappings."""
    logger.info("Loading target information from ChEMBL...")

    chembl_conn = sqlite3.connect(str(sqlite_path))
    chembl_cursor = chembl_conn.cursor()

    query = """
        SELECT DISTINCT
            td.chembl_id as target_chembl_id,
            td.pref_name,
            td.organism,
            td.target_type,
            cs.accession as uniprot_id
        FROM target_dictionary td
        JOIN target_components tc ON td.tid = tc.tid
        JOIN component_sequences cs ON tc.component_id = cs.component_id
        WHERE cs.accession IS NOT NULL
    """

    chembl_cursor.execute(query)
    rows = chembl_cursor.fetchall()
    logger.info(f"Found {len(rows)} target-UniProt mappings")

    pg_cursor = pg_conn.cursor()

    seen_uniprot = set()
    values = []
    for row in rows:
        uniprot_id = row[4]
        if uniprot_id not in seen_uniprot:
            seen_uniprot.add(uniprot_id)
            values.append((row[0], row[1], row[2], row[3], row[4]))

    logger.info(f"Deduplicated to {len(values)} unique UniProt IDs")

    execute_values(
        pg_cursor,
        """
        INSERT INTO mol_bronze.chembl_targets (
            chembl_target_id, protein_name, organism, target_type, uniprot_id
        ) VALUES %s
        ON CONFLICT (uniprot_id) DO UPDATE SET
            chembl_target_id = COALESCE(EXCLUDED.chembl_target_id, mol_bronze.chembl_targets.chembl_target_id),
            protein_name = COALESCE(EXCLUDED.protein_name, mol_bronze.chembl_targets.protein_name)
        """,
        values
    )
    pg_conn.commit()

    chembl_conn.close()
    logger.info(f"Loaded {len(values)} target records")
    return len(values)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Load ChEMBL data from bulk SQLite download")
    parser.add_argument("--download-only", action="store_true", help="Only download the database")
    parser.add_argument("--targets-only", action="store_true", help="Only load target information")
    parser.add_argument("--standalone", action="store_true", help="Load ALL ChEMBL activities (~20M records)")
    parser.add_argument("--limit", type=int, default=None, help="Maximum activities to load")
    parser.add_argument("--batch-size", type=int, default=10000, help="Batch size for inserts")

    args = parser.parse_args()

    sqlite_path = get_chembl_sqlite_path()

    if args.download_only:
        logger.info(f"Download complete: {sqlite_path}")
        return

    logger.info("Connecting to PostgreSQL...")
    pg_conn = psycopg2.connect(build_dsn())
    logger.info(f"Connected to {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")

    ensure_tables(pg_conn)

    try:
        if args.targets_only:
            load_target_info(pg_conn, sqlite_path)
        else:
            load_chembl_activities(pg_conn, sqlite_path, args.batch_size, args.standalone, args.limit)
            load_target_info(pg_conn, sqlite_path)

        cursor = pg_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM mol_bronze.chembl_activities")
        act_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM mol_bronze.chembl_targets")
        target_count = cursor.fetchone()[0]

        logger.info("=== Summary ===")
        logger.info(f"ChEMBL activities: {act_count:,}")
        logger.info(f"ChEMBL targets: {target_count:,}")

    finally:
        pg_conn.close()


if __name__ == "__main__":
    main()
