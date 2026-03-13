#!/usr/bin/env python3
"""
Load SIDER (Side Effect Resource) data into PostgreSQL.

Downloads SIDER 4.1 data files and loads side effects, indications, and drug info.

Tables populated:
- bronze.sider_drugs: Drug information
- bronze.sider_side_effects: Side effect associations
- bronze.sider_indications: Drug indications
- bronze.sider_frequencies: Side effect frequencies

Data source: http://sideeffects.embl.de/

Usage:
    python -m dk_data.data.load_sider
    python -m dk_data.data.load_sider --download
    python -m dk_data.data.load_sider --data-dir /path/to/sider/files

Environment:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
"""

import os
import sys
import gzip
from pathlib import Path

import requests
import psycopg2
from psycopg2.extras import execute_values
from loguru import logger
from tqdm import tqdm

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "dk_data"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

# SIDER 4.1 URLs
SIDER_BASE_URL = "http://sideeffects.embl.de/media/download/"
SIDER_FILES = {
    "drug_names": "drug_names.tsv",
    "drug_atc": "drug_atc.tsv",
    "meddra_all_se": "meddra_all_se.tsv.gz",
    "meddra_all_indications": "meddra_all_indications.tsv.gz",
    "meddra_freq": "meddra_freq.tsv.gz",
}


def ensure_tables(conn):
    """Ensure SIDER tables exist."""
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.sider_drugs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            stitch_id_flat VARCHAR(20),
            stitch_id_stereo VARCHAR(20),
            drug_name TEXT,
            atc_codes TEXT[],
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(stitch_id_flat)
        );

        CREATE INDEX IF NOT EXISTS idx_sider_drugs_stitch ON bronze.sider_drugs(stitch_id_flat);
        CREATE INDEX IF NOT EXISTS idx_sider_drugs_name ON bronze.sider_drugs(drug_name);
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.sider_side_effects (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            stitch_id_flat VARCHAR(20),
            stitch_id_stereo VARCHAR(20),
            umls_cui_label VARCHAR(20),
            meddra_type VARCHAR(20),
            umls_cui_meddra VARCHAR(20),
            side_effect_name TEXT,
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            processed_to_silver BOOLEAN DEFAULT FALSE,
            UNIQUE(stitch_id_flat, umls_cui_meddra, meddra_type)
        );

        CREATE INDEX IF NOT EXISTS idx_sider_se_stitch ON bronze.sider_side_effects(stitch_id_flat);
        CREATE INDEX IF NOT EXISTS idx_sider_se_name ON bronze.sider_side_effects(side_effect_name);
        CREATE INDEX IF NOT EXISTS idx_sider_se_processed ON bronze.sider_side_effects(processed_to_silver);
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.sider_indications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            stitch_id_flat VARCHAR(20),
            umls_cui_label VARCHAR(20),
            detection_method VARCHAR(50),
            concept_name TEXT,
            meddra_type VARCHAR(20),
            umls_cui_meddra VARCHAR(20),
            meddra_name TEXT,
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            processed_to_silver BOOLEAN DEFAULT FALSE,
            UNIQUE(stitch_id_flat, umls_cui_meddra, meddra_type)
        );

        CREATE INDEX IF NOT EXISTS idx_sider_ind_stitch ON bronze.sider_indications(stitch_id_flat);
        CREATE INDEX IF NOT EXISTS idx_sider_ind_name ON bronze.sider_indications(meddra_name);
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.sider_frequencies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            stitch_id_flat VARCHAR(20),
            stitch_id_stereo VARCHAR(20),
            umls_cui_label VARCHAR(20),
            placebo VARCHAR(20),
            frequency_type VARCHAR(50),
            frequency_lower DOUBLE PRECISION,
            frequency_upper DOUBLE PRECISION,
            meddra_type VARCHAR(20),
            umls_cui_meddra VARCHAR(20),
            side_effect_name TEXT,
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(stitch_id_flat, umls_cui_meddra, frequency_type)
        );

        CREATE INDEX IF NOT EXISTS idx_sider_freq_stitch ON bronze.sider_frequencies(stitch_id_flat);
    """)

    conn.commit()
    logger.info("SIDER tables ensured")


class SIDERLoader:
    """Load data from SIDER database files."""

    def __init__(self, conn, data_dir: Path = None):
        self.conn = conn
        self.data_dir = data_dir or Path("/tmp/sider")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()

    def download_files(self, force: bool = False) -> bool:
        """Download SIDER data files."""
        logger.info("Downloading SIDER data files...")

        for name, filename in SIDER_FILES.items():
            local_path = self.data_dir / filename

            if local_path.exists() and not force:
                logger.info(f"  {filename} already exists")
                continue

            url = SIDER_BASE_URL + filename
            logger.info(f"  Downloading {filename}...")

            try:
                response = self.session.get(url, stream=True, timeout=300)
                response.raise_for_status()

                total = int(response.headers.get('content-length', 0))
                with open(local_path, 'wb') as f:
                    with tqdm(total=total, unit='B', unit_scale=True, desc=filename) as pbar:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                            pbar.update(len(chunk))

            except Exception as e:
                logger.error(f"  Failed to download {filename}: {e}")
                return False

        logger.info("Download complete")
        return True

    def load_drug_names(self) -> int:
        """Load drug names from SIDER."""
        filepath = self.data_dir / SIDER_FILES["drug_names"]
        if not filepath.exists():
            logger.warning(f"File not found: {filepath}")
            return 0

        logger.info("Loading SIDER drug names...")
        cursor = self.conn.cursor()
        records = []

        with open(filepath, 'r', encoding='utf-8') as f:
            for line in tqdm(f, desc="Parsing drug names"):
                parts = line.strip().split('\t')
                if len(parts) >= 2:
                    stitch_id = parts[0]
                    drug_name = parts[1]
                    records.append((stitch_id, None, drug_name, None))

        if records:
            execute_values(
                cursor,
                """
                INSERT INTO bronze.sider_drugs (stitch_id_flat, stitch_id_stereo, drug_name, atc_codes)
                VALUES %s
                ON CONFLICT (stitch_id_flat) DO UPDATE SET
                    drug_name = EXCLUDED.drug_name
                """,
                records
            )
            self.conn.commit()

        logger.info(f"Loaded {len(records)} drug names")
        return len(records)

    def load_side_effects(self) -> int:
        """Load side effects from SIDER."""
        filepath = self.data_dir / SIDER_FILES["meddra_all_se"]
        if not filepath.exists():
            logger.warning(f"File not found: {filepath}")
            return 0

        logger.info("Loading SIDER side effects...")
        cursor = self.conn.cursor()
        records = []
        batch_size = 10000
        total = 0

        opener = gzip.open if filepath.suffix == '.gz' else open

        with opener(filepath, 'rt', encoding='utf-8') as f:
            for line in tqdm(f, desc="Parsing side effects"):
                parts = line.strip().split('\t')
                if len(parts) >= 6:
                    records.append((
                        parts[0],  # stitch_id_flat
                        parts[1],  # stitch_id_stereo
                        parts[2],  # umls_cui_label
                        parts[3],  # meddra_type
                        parts[4],  # umls_cui_meddra
                        parts[5],  # side_effect_name
                    ))

                if len(records) >= batch_size:
                    execute_values(
                        cursor,
                        """
                        INSERT INTO bronze.sider_side_effects (
                            stitch_id_flat, stitch_id_stereo, umls_cui_label,
                            meddra_type, umls_cui_meddra, side_effect_name
                        ) VALUES %s
                        ON CONFLICT (stitch_id_flat, umls_cui_meddra, meddra_type) DO NOTHING
                        """,
                        records
                    )
                    self.conn.commit()
                    total += len(records)
                    records = []

        if records:
            execute_values(
                cursor,
                """
                INSERT INTO bronze.sider_side_effects (
                    stitch_id_flat, stitch_id_stereo, umls_cui_label,
                    meddra_type, umls_cui_meddra, side_effect_name
                ) VALUES %s
                ON CONFLICT (stitch_id_flat, umls_cui_meddra, meddra_type) DO NOTHING
                """,
                records
            )
            self.conn.commit()
            total += len(records)

        logger.info(f"Loaded {total} side effect records")
        return total

    def load_indications(self) -> int:
        """Load indications from SIDER."""
        filepath = self.data_dir / SIDER_FILES["meddra_all_indications"]
        if not filepath.exists():
            logger.warning(f"File not found: {filepath}")
            return 0

        logger.info("Loading SIDER indications...")
        cursor = self.conn.cursor()
        records = []
        batch_size = 10000
        total = 0

        opener = gzip.open if filepath.suffix == '.gz' else open

        with opener(filepath, 'rt', encoding='utf-8') as f:
            for line in tqdm(f, desc="Parsing indications"):
                parts = line.strip().split('\t')
                if len(parts) >= 7:
                    records.append((
                        parts[0],  # stitch_id_flat
                        parts[1],  # umls_cui_label
                        parts[2],  # detection_method
                        parts[3],  # concept_name
                        parts[4],  # meddra_type
                        parts[5],  # umls_cui_meddra
                        parts[6],  # meddra_name
                    ))

                if len(records) >= batch_size:
                    execute_values(
                        cursor,
                        """
                        INSERT INTO bronze.sider_indications (
                            stitch_id_flat, umls_cui_label, detection_method,
                            concept_name, meddra_type, umls_cui_meddra, meddra_name
                        ) VALUES %s
                        ON CONFLICT (stitch_id_flat, umls_cui_meddra, meddra_type) DO NOTHING
                        """,
                        records
                    )
                    self.conn.commit()
                    total += len(records)
                    records = []

        if records:
            execute_values(
                cursor,
                """
                INSERT INTO bronze.sider_indications (
                    stitch_id_flat, umls_cui_label, detection_method,
                    concept_name, meddra_type, umls_cui_meddra, meddra_name
                ) VALUES %s
                ON CONFLICT (stitch_id_flat, umls_cui_meddra, meddra_type) DO NOTHING
                """,
                records
            )
            self.conn.commit()
            total += len(records)

        logger.info(f"Loaded {total} indication records")
        return total

    def load_frequencies(self) -> int:
        """Load side effect frequencies from SIDER."""
        filepath = self.data_dir / SIDER_FILES["meddra_freq"]
        if not filepath.exists():
            logger.warning(f"File not found: {filepath}")
            return 0

        logger.info("Loading SIDER frequencies...")
        cursor = self.conn.cursor()
        records = []
        batch_size = 10000
        total = 0

        def parse_freq(val):
            try:
                if val and val != '':
                    return float(val)
            except Exception:
                pass
            return None

        opener = gzip.open if filepath.suffix == '.gz' else open

        with opener(filepath, 'rt', encoding='utf-8') as f:
            for line in tqdm(f, desc="Parsing frequencies"):
                parts = line.strip().split('\t')
                if len(parts) >= 10:
                    records.append((
                        parts[0],  # stitch_id_flat
                        parts[1],  # stitch_id_stereo
                        parts[2],  # umls_cui_label
                        parts[3],  # placebo
                        parts[4],  # frequency_type
                        parse_freq(parts[5]),  # frequency_lower
                        parse_freq(parts[6]),  # frequency_upper
                        parts[7],  # meddra_type
                        parts[8],  # umls_cui_meddra
                        parts[9],  # side_effect_name
                    ))

                if len(records) >= batch_size:
                    execute_values(
                        cursor,
                        """
                        INSERT INTO bronze.sider_frequencies (
                            stitch_id_flat, stitch_id_stereo, umls_cui_label,
                            placebo, frequency_type, frequency_lower, frequency_upper,
                            meddra_type, umls_cui_meddra, side_effect_name
                        ) VALUES %s
                        ON CONFLICT (stitch_id_flat, umls_cui_meddra, frequency_type) DO NOTHING
                        """,
                        records
                    )
                    self.conn.commit()
                    total += len(records)
                    records = []

        if records:
            execute_values(
                cursor,
                """
                INSERT INTO bronze.sider_frequencies (
                    stitch_id_flat, stitch_id_stereo, umls_cui_label,
                    placebo, frequency_type, frequency_lower, frequency_upper,
                    meddra_type, umls_cui_meddra, side_effect_name
                ) VALUES %s
                ON CONFLICT (stitch_id_flat, umls_cui_meddra, frequency_type) DO NOTHING
                """,
                records
            )
            self.conn.commit()
            total += len(records)

        logger.info(f"Loaded {total} frequency records")
        return total


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Load SIDER data")
    parser.add_argument("--download", action="store_true", help="Download SIDER files")
    parser.add_argument("--data-dir", type=str, default="/tmp/sider", help="Data directory")
    parser.add_argument("--drugs-only", action="store_true", help="Load only drug names")
    parser.add_argument("--side-effects-only", action="store_true", help="Load only side effects")
    parser.add_argument("--indications-only", action="store_true", help="Load only indications")

    args = parser.parse_args()

    logger.info("Connecting to PostgreSQL...")
    conn = psycopg2.connect(**DB_CONFIG)
    logger.info(f"Connected to {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")

    ensure_tables(conn)

    try:
        loader = SIDERLoader(conn, data_dir=Path(args.data_dir))

        if args.download:
            if not loader.download_files():
                logger.error("Failed to download SIDER files")
                sys.exit(1)

        # Load data
        if args.drugs_only:
            loader.load_drug_names()
        elif args.side_effects_only:
            loader.load_side_effects()
        elif args.indications_only:
            loader.load_indications()
        else:
            loader.load_drug_names()
            loader.load_side_effects()
            loader.load_indications()
            loader.load_frequencies()

        # Summary
        cursor = conn.cursor()
        logger.info("\n=== Summary ===")
        from psycopg2 import sql as psql
        for table in ['sider_drugs', 'sider_side_effects', 'sider_indications', 'sider_frequencies']:
            cursor.execute(psql.SQL("SELECT COUNT(*) FROM bronze.{}").format(psql.Identifier(table)))
            count = cursor.fetchone()[0]
            logger.info(f"bronze.{table}: {count:,}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
