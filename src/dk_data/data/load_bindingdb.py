#!/usr/bin/env python3
"""
Load BindingDB TSV data into PostgreSQL.

Processes the large TSV file in chunks and loads binding affinity data.

Tables populated:
- bronze.bindingdb_affinities: Binding affinity data (Ki, IC50, Kd, EC50)

Usage:
    python -m dk_data.data.load_bindingdb /path/to/BindingDB_All.tsv
    python -m dk_data.data.load_bindingdb --max-rows 100000

Environment:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
"""

import os
import sys
import csv
import re
from typing import Optional
import argparse

import psycopg2
from psycopg2.extras import execute_values
from loguru import logger
from tqdm import tqdm

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "dk_data"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
}


def parse_numeric(value: str) -> Optional[float]:
    """Parse numeric value, handling special cases like '>10000' or '<0.1'."""
    if not value or value.strip() == "":
        return None
    value = value.strip()
    value = re.sub(r'^[<>=~]+\s*', '', value)
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def parse_int(value: str) -> Optional[int]:
    """Parse integer value."""
    if not value or value.strip() == "":
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def count_lines(filepath: str) -> int:
    """Count lines in file for progress bar."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        return sum(1 for _ in f)


def ensure_tables(conn):
    """Ensure BindingDB tables exist."""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.bindingdb_affinities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            smiles TEXT,
            inchi_key VARCHAR(27),
            bindingdb_ligand_id VARCHAR(100),
            target_name TEXT,
            uniprot_id VARCHAR(20),
            ki_nm DOUBLE PRECISION,
            ic50_nm DOUBLE PRECISION,
            kd_nm DOUBLE PRECISION,
            ec50_nm DOUBLE PRECISION,
            kon DOUBLE PRECISION,
            koff DOUBLE PRECISION,
            ph DOUBLE PRECISION,
            temperature_c DOUBLE PRECISION,
            article_doi VARCHAR(200),
            pmid INTEGER,
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            processed_to_silver BOOLEAN DEFAULT FALSE
        );

        CREATE INDEX IF NOT EXISTS idx_bindingdb_smiles ON bronze.bindingdb_affinities(smiles) WHERE smiles IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_bindingdb_inchi ON bronze.bindingdb_affinities(inchi_key) WHERE inchi_key IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_bindingdb_uniprot ON bronze.bindingdb_affinities(uniprot_id) WHERE uniprot_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_bindingdb_processed ON bronze.bindingdb_affinities(processed_to_silver);
    """)
    conn.commit()
    logger.info("BindingDB tables ensured")


def load_bindingdb(
    tsv_path: str,
    batch_size: int = 10000,
    max_rows: int = None,
    skip_existing: bool = True
):
    """Load BindingDB TSV into PostgreSQL."""
    logger.info(f"Loading BindingDB from: {tsv_path}")

    conn = psycopg2.connect(**DB_CONFIG)
    ensure_tables(conn)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM bronze.bindingdb_affinities")
    existing_count = cursor.fetchone()[0]
    logger.info(f"Existing BindingDB records: {existing_count}")

    if skip_existing and existing_count > 0:
        logger.info("Clearing existing data for fresh load...")
        cursor.execute("TRUNCATE bronze.bindingdb_affinities RESTART IDENTITY")
        conn.commit()

    logger.info("Counting lines...")
    total_lines = count_lines(tsv_path) - 1
    logger.info(f"Total records to process: {total_lines:,}")

    if max_rows:
        total_lines = min(total_lines, max_rows)
        logger.info(f"Limited to: {max_rows:,} rows")

    inserted = 0
    skipped = 0
    errors = 0
    batch = []

    with open(tsv_path, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f, delimiter='\t')
        pbar = tqdm(total=total_lines, desc="Loading BindingDB")

        for i, row in enumerate(reader):
            if max_rows and i >= max_rows:
                break

            try:
                smiles = row.get("Ligand SMILES", "").strip()
                inchi_key = row.get("Ligand InChI Key", "").strip()

                if not smiles and not inchi_key:
                    skipped += 1
                    pbar.update(1)
                    continue

                ki = parse_numeric(row.get("Ki (nM)", ""))
                ic50 = parse_numeric(row.get("IC50 (nM)", ""))
                kd = parse_numeric(row.get("Kd (nM)", ""))
                ec50 = parse_numeric(row.get("EC50 (nM)", ""))
                kon = parse_numeric(row.get("kon (M-1-s-1)", ""))
                koff = parse_numeric(row.get("koff (s-1)", ""))

                if all(v is None for v in [ki, ic50, kd, ec50, kon, koff]):
                    skipped += 1
                    pbar.update(1)
                    continue

                record = (
                    smiles[:5000] if smiles else None,
                    inchi_key[:27] if inchi_key else None,
                    row.get("BindingDB MonomerID", "").strip()[:100] or None,
                    row.get("Target Name", "").strip()[:500] or None,
                    row.get("UniProt (SwissProt) Primary ID of Target Chain 1", "").strip()[:20] or None,
                    ki, ic50, kd, ec50, kon, koff,
                    parse_numeric(row.get("pH", "")),
                    parse_numeric(row.get("Temp (C)", "")),
                    row.get("Article DOI", "").strip()[:200] or None,
                    parse_int(row.get("PMID", "")),
                )
                batch.append(record)

                if len(batch) >= batch_size:
                    try:
                        execute_values(cursor, """
                            INSERT INTO bronze.bindingdb_affinities
                            (smiles, inchi_key, bindingdb_ligand_id, target_name, uniprot_id,
                             ki_nm, ic50_nm, kd_nm, ec50_nm, kon, koff, ph, temperature_c, article_doi, pmid)
                            VALUES %s
                        """, batch)
                        conn.commit()
                        inserted += len(batch)
                    except Exception as e:
                        logger.error(f"Batch insert error: {e}")
                        conn.rollback()
                        errors += len(batch)
                    batch = []

            except Exception as e:
                logger.debug(f"Row error: {e}")
                errors += 1

            pbar.update(1)

        if batch:
            try:
                execute_values(cursor, """
                    INSERT INTO bronze.bindingdb_affinities
                    (smiles, inchi_key, bindingdb_ligand_id, target_name, uniprot_id,
                     ki_nm, ic50_nm, kd_nm, ec50_nm, kon, koff, ph, temperature_c, article_doi, pmid)
                    VALUES %s
                """, batch)
                conn.commit()
                inserted += len(batch)
            except Exception as e:
                logger.error(f"Final batch error: {e}")
                errors += len(batch)

        pbar.close()

    cursor.execute("SELECT COUNT(*) FROM bronze.bindingdb_affinities")
    final_count = cursor.fetchone()[0]

    logger.info(f"\n=== Load Complete ===")
    logger.info(f"Total inserted: {inserted:,}")
    logger.info(f"Skipped (no data): {skipped:,}")
    logger.info(f"Errors: {errors:,}")
    logger.info(f"Total records: {final_count:,}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Load BindingDB TSV into PostgreSQL")
    parser.add_argument("tsv_path", nargs="?", default="/tmp/bindingdb/BindingDB_All.tsv",
                        help="Path to BindingDB TSV file")
    parser.add_argument("--batch-size", type=int, default=10000)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--append", action="store_true", help="Append to existing data")
    args = parser.parse_args()

    if not os.path.exists(args.tsv_path):
        logger.error(f"File not found: {args.tsv_path}")
        sys.exit(1)

    load_bindingdb(
        args.tsv_path,
        batch_size=args.batch_size,
        max_rows=args.max_rows,
        skip_existing=not args.append
    )


if __name__ == "__main__":
    main()
