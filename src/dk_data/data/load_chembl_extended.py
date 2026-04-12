#!/usr/bin/env python3
"""
Extended ChEMBL bulk loader - loads additional tables beyond activities.

Loads:
- drug_mechanism: Mechanism of action annotations
- drug_indication: Therapeutic indications
- metabolism: Drug metabolism relationships
- drug_warning: Safety warnings/withdrawals
- cell_dictionary: Cell line information
- component_sequences: Protein sequences for ESM-2
- assays: Full assay descriptions

Tables populated:
- mol_bronze.chembl_drug_mechanism
- mol_bronze.chembl_drug_indication
- mol_bronze.chembl_metabolism
- mol_bronze.chembl_drug_warning
- mol_bronze.chembl_cell_dictionary
- mol_bronze.chembl_component_sequences
- mol_bronze.chembl_assays

Usage:
    python -m dk_data.data.load_chembl_extended
    python -m dk_data.data.load_chembl_extended --table drug_mechanism
    python -m dk_data.data.load_chembl_extended --list-tables

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
    sqlite_path = chembl_downloader.download_extract_sqlite()
    logger.info(f"ChEMBL database at: {sqlite_path}")
    return Path(sqlite_path)


def ensure_extended_tables(conn):
    """Create PostgreSQL tables for extended ChEMBL data."""
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mol_bronze.chembl_drug_mechanism (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            molregno INTEGER,
            chembl_id VARCHAR(20),
            mechanism_of_action TEXT,
            target_chembl_id VARCHAR(20),
            target_name TEXT,
            target_type VARCHAR(50),
            action_type VARCHAR(50),
            direct_interaction BOOLEAN,
            molecular_mechanism TEXT,
            disease_efficacy BOOLEAN,
            mechanism_comment TEXT,
            selectivity_comment TEXT,
            binding_site_comment TEXT,
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(chembl_id, target_chembl_id, mechanism_of_action)
        );

        CREATE INDEX IF NOT EXISTS idx_mechanism_chembl ON mol_bronze.chembl_drug_mechanism(chembl_id);
        CREATE INDEX IF NOT EXISTS idx_mechanism_target ON mol_bronze.chembl_drug_mechanism(target_chembl_id);
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mol_bronze.chembl_drug_indication (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            molregno INTEGER,
            chembl_id VARCHAR(20),
            mesh_id VARCHAR(20),
            mesh_heading TEXT,
            efo_id VARCHAR(50),
            efo_term TEXT,
            max_phase_for_ind INTEGER,
            indication_refs TEXT,
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(chembl_id, mesh_id)
        );

        CREATE INDEX IF NOT EXISTS idx_indication_chembl ON mol_bronze.chembl_drug_indication(chembl_id);
        CREATE INDEX IF NOT EXISTS idx_indication_mesh ON mol_bronze.chembl_drug_indication(mesh_id);
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mol_bronze.chembl_metabolism (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            drug_chembl_id VARCHAR(20),
            drug_name TEXT,
            substrate_chembl_id VARCHAR(20),
            substrate_name TEXT,
            metabolite_chembl_id VARCHAR(20),
            metabolite_name TEXT,
            enzyme_name TEXT,
            enzyme_chembl_id VARCHAR(20),
            met_conversion TEXT,
            organism VARCHAR(100),
            tax_id INTEGER,
            met_comment TEXT,
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(drug_chembl_id, metabolite_chembl_id, enzyme_chembl_id)
        );

        CREATE INDEX IF NOT EXISTS idx_metabolism_drug ON mol_bronze.chembl_metabolism(drug_chembl_id);
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mol_bronze.chembl_drug_warning (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            molregno INTEGER,
            chembl_id VARCHAR(20),
            warning_type VARCHAR(100),
            warning_class VARCHAR(100),
            warning_description TEXT,
            warning_country VARCHAR(100),
            warning_year INTEGER,
            efo_term TEXT,
            efo_id VARCHAR(50),
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(chembl_id, warning_type, warning_country)
        );

        CREATE INDEX IF NOT EXISTS idx_warning_chembl ON mol_bronze.chembl_drug_warning(chembl_id);
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mol_bronze.chembl_cell_dictionary (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            cell_id INTEGER UNIQUE,
            cell_name VARCHAR(200),
            cell_description TEXT,
            cell_source_tissue VARCHAR(100),
            cell_source_organism VARCHAR(100),
            cell_source_tax_id INTEGER,
            clo_id VARCHAR(50),
            efo_id VARCHAR(50),
            cellosaurus_id VARCHAR(50),
            cl_lincs_id VARCHAR(50),
            chembl_id VARCHAR(20),
            cell_ontology_id VARCHAR(50),
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_cell_name ON mol_bronze.chembl_cell_dictionary(cell_name);
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mol_bronze.chembl_component_sequences (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            component_id INTEGER UNIQUE,
            component_type VARCHAR(50),
            accession VARCHAR(50),
            sequence TEXT,
            sequence_md5sum VARCHAR(32),
            description TEXT,
            tax_id INTEGER,
            organism VARCHAR(200),
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_component_accession ON mol_bronze.chembl_component_sequences(accession);
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mol_bronze.chembl_assays (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            assay_id INTEGER UNIQUE,
            assay_chembl_id VARCHAR(20),
            assay_type VARCHAR(10),
            assay_type_description VARCHAR(100),
            assay_test_type VARCHAR(50),
            assay_category VARCHAR(50),
            assay_organism VARCHAR(200),
            assay_tax_id INTEGER,
            assay_strain VARCHAR(200),
            assay_tissue VARCHAR(200),
            assay_cell_type VARCHAR(200),
            assay_subcellular_fraction VARCHAR(200),
            target_chembl_id VARCHAR(20),
            target_name TEXT,
            target_type VARCHAR(50),
            relationship_type VARCHAR(10),
            confidence_score INTEGER,
            description TEXT,
            document_chembl_id VARCHAR(20),
            src_id INTEGER,
            bao_format VARCHAR(50),
            tissue_chembl_id VARCHAR(20),
            cell_chembl_id VARCHAR(20),
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_assay_chembl ON mol_bronze.chembl_assays(assay_chembl_id);
        CREATE INDEX IF NOT EXISTS idx_assay_target ON mol_bronze.chembl_assays(target_chembl_id);
    """)

    conn.commit()
    logger.info("Extended ChEMBL tables ensured")


def load_drug_mechanism(pg_conn, sqlite_path: Path, batch_size: int = 5000) -> int:
    """Load drug mechanism of action data."""
    logger.info("Loading drug mechanism of action...")

    chembl_conn = sqlite3.connect(str(sqlite_path))
    chembl_cursor = chembl_conn.cursor()

    query = """
        SELECT DISTINCT
            dm.molregno, md.chembl_id, dm.mechanism_of_action,
            td.chembl_id as target_chembl_id, td.pref_name as target_name,
            td.target_type, dm.action_type, dm.direct_interaction,
            dm.molecular_mechanism, dm.disease_efficacy, dm.mechanism_comment,
            dm.selectivity_comment, dm.binding_site_comment
        FROM drug_mechanism dm
        JOIN molecule_dictionary md ON dm.molregno = md.molregno
        LEFT JOIN target_dictionary td ON dm.tid = td.tid
    """

    chembl_cursor.execute(query)
    rows = chembl_cursor.fetchall()
    logger.info(f"Found {len(rows)} drug mechanism records")

    pg_cursor = pg_conn.cursor()
    total_loaded = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        values = [
            (row[0], row[1], row[2], row[3], row[4], row[5], row[6],
             bool(row[7]) if row[7] is not None else None, row[8],
             bool(row[9]) if row[9] is not None else None, row[10], row[11], row[12])
            for row in batch
        ]

        execute_values(
            pg_cursor,
            """
            INSERT INTO mol_bronze.chembl_drug_mechanism (
                molregno, chembl_id, mechanism_of_action, target_chembl_id,
                target_name, target_type, action_type, direct_interaction,
                molecular_mechanism, disease_efficacy, mechanism_comment,
                selectivity_comment, binding_site_comment
            ) VALUES %s
            ON CONFLICT (chembl_id, target_chembl_id, mechanism_of_action) DO NOTHING
            """,
            values,
        )
        total_loaded += len(batch)

    pg_conn.commit()
    chembl_conn.close()
    logger.info(f"Loaded {total_loaded} drug mechanism records")
    return total_loaded


def load_drug_indication(pg_conn, sqlite_path: Path, batch_size: int = 5000) -> int:
    """Load drug indication data."""
    logger.info("Loading drug indication...")

    chembl_conn = sqlite3.connect(str(sqlite_path))
    chembl_cursor = chembl_conn.cursor()

    query = """
        SELECT DISTINCT
            di.molregno, md.chembl_id, di.mesh_id, di.mesh_heading,
            di.efo_id, di.efo_term, di.max_phase_for_ind, di.indication_refs
        FROM drug_indication di
        JOIN molecule_dictionary md ON di.molregno = md.molregno
    """

    chembl_cursor.execute(query)
    rows = chembl_cursor.fetchall()
    logger.info(f"Found {len(rows)} drug indication records")

    pg_cursor = pg_conn.cursor()
    total_loaded = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        execute_values(
            pg_cursor,
            """
            INSERT INTO mol_bronze.chembl_drug_indication (
                molregno, chembl_id, mesh_id, mesh_heading,
                efo_id, efo_term, max_phase_for_ind, indication_refs
            ) VALUES %s
            ON CONFLICT (chembl_id, mesh_id) DO NOTHING
            """,
            [tuple(row) for row in batch],
        )
        total_loaded += len(batch)

    pg_conn.commit()
    chembl_conn.close()
    logger.info(f"Loaded {total_loaded} drug indication records")
    return total_loaded


def load_drug_warning(pg_conn, sqlite_path: Path, batch_size: int = 5000) -> int:
    """Load drug warning/safety data."""
    logger.info("Loading drug warnings...")

    chembl_conn = sqlite3.connect(str(sqlite_path))
    chembl_cursor = chembl_conn.cursor()

    query = """
        SELECT DISTINCT
            dw.molregno, md.chembl_id, dw.warning_type, dw.warning_class,
            dw.warning_description, dw.warning_country, dw.warning_year,
            dw.efo_term, dw.efo_id
        FROM drug_warning dw
        JOIN molecule_dictionary md ON dw.molregno = md.molregno
    """

    chembl_cursor.execute(query)
    rows = chembl_cursor.fetchall()
    logger.info(f"Found {len(rows)} drug warning records")

    pg_cursor = pg_conn.cursor()
    total_loaded = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        execute_values(
            pg_cursor,
            """
            INSERT INTO mol_bronze.chembl_drug_warning (
                molregno, chembl_id, warning_type, warning_class,
                warning_description, warning_country, warning_year,
                efo_term, efo_id
            ) VALUES %s
            ON CONFLICT (chembl_id, warning_type, warning_country) DO NOTHING
            """,
            [tuple(row) for row in batch],
        )
        total_loaded += len(batch)

    pg_conn.commit()
    chembl_conn.close()
    logger.info(f"Loaded {total_loaded} drug warning records")
    return total_loaded


def load_component_sequences(pg_conn, sqlite_path: Path, batch_size: int = 5000) -> int:
    """Load protein sequences for ESM-2 embeddings."""
    logger.info("Loading component sequences...")

    chembl_conn = sqlite3.connect(str(sqlite_path))
    chembl_cursor = chembl_conn.cursor()

    query = """
        SELECT component_id, component_type, accession, sequence,
               sequence_md5sum, description, tax_id, organism
        FROM component_sequences
        WHERE sequence IS NOT NULL
    """

    chembl_cursor.execute(query)
    rows = chembl_cursor.fetchall()
    logger.info(f"Found {len(rows)} component sequence records")

    pg_cursor = pg_conn.cursor()
    total_loaded = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        execute_values(
            pg_cursor,
            """
            INSERT INTO mol_bronze.chembl_component_sequences (
                component_id, component_type, accession, sequence,
                sequence_md5sum, description, tax_id, organism
            ) VALUES %s
            ON CONFLICT (component_id) DO NOTHING
            """,
            [tuple(row) for row in batch],
        )
        total_loaded += len(batch)

    pg_conn.commit()
    chembl_conn.close()
    logger.info(f"Loaded {total_loaded} component sequence records")
    return total_loaded


LOADERS = {
    "drug_mechanism": load_drug_mechanism,
    "drug_indication": load_drug_indication,
    "drug_warning": load_drug_warning,
    "component_sequences": load_component_sequences,
}


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Load extended ChEMBL data from bulk SQLite")
    parser.add_argument("--table", choices=list(LOADERS.keys()), help="Load specific table only")
    parser.add_argument("--list-tables", action="store_true", help="List available tables")
    parser.add_argument("--batch-size", type=int, default=5000, help="Batch size for inserts")

    args = parser.parse_args()

    if args.list_tables:
        print("Available tables:")
        for name in LOADERS:
            print(f"  - {name}")
        return

    sqlite_path = get_chembl_sqlite_path()

    logger.info("Connecting to PostgreSQL...")
    pg_conn = psycopg2.connect(build_dsn())
    logger.info(f"Connected to {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")

    ensure_extended_tables(pg_conn)

    results = {}
    if args.table:
        loader = LOADERS[args.table]
        results[args.table] = loader(pg_conn, sqlite_path, args.batch_size)
    else:
        for name, loader in LOADERS.items():
            try:
                results[name] = loader(pg_conn, sqlite_path, args.batch_size)
            except Exception as e:
                logger.error(f"Error loading {name}: {e}")
                results[name] = 0

    logger.info("\n=== Summary ===")
    for name, count in results.items():
        logger.info(f"{name}: {count:,} records")

    pg_conn.close()


if __name__ == "__main__":
    main()
