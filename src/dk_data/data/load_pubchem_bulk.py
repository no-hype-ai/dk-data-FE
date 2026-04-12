#!/usr/bin/env python3
"""
Bulk PubChem data loader.

Downloads PubChem compound properties in bulk for all compounds in our database.
Uses the FTP bulk files for CID mapping and PUG-REST batch API for properties.

Strategy:
1. Download CID-InChI-Key.gz (~6.8GB) to map InChI keys to CIDs
2. Find CIDs for all our compounds
3. Batch fetch properties via PUG-REST (100 CIDs per request)

Tables populated:
- mol_bronze.pubchem_compounds: PubChem compound properties

Usage:
    python -m dk_data.data.load_pubchem_bulk
    python -m dk_data.data.load_pubchem_bulk --download-only
    python -m dk_data.data.load_pubchem_bulk --limit 1000

Environment:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
"""

import os
import gzip
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Set

import psycopg2
from psycopg2.extras import execute_values
from loguru import logger
from tqdm import tqdm
import requests
from dk_data.ingestion.utils.database import build_dsn

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "dk_data"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

PUBCHEM_FTP_BASE = "https://ftp.ncbi.nlm.nih.gov/pubchem/Compound/Extras/"
CID_INCHIKEY_FILE = "CID-InChI-Key.gz"

PUBCHEM_API_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

PUBCHEM_PROPERTIES = [
    "MolecularFormula", "MolecularWeight", "ExactMass", "MonoisotopicMass",
    "XLogP", "TPSA", "Complexity", "HBondDonorCount", "HBondAcceptorCount",
    "RotatableBondCount", "HeavyAtomCount", "CanonicalSMILES", "IUPACName",
]

RATE_LIMIT_DELAY = 0.35
BATCH_SIZE = 100


def ensure_tables(conn):
    """Ensure PubChem tables exist."""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mol_bronze.pubchem_compounds (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            cid BIGINT,
            inchi_key VARCHAR(27) UNIQUE,
            smiles_canonical TEXT,
            molecular_formula VARCHAR(200),
            molecular_weight DOUBLE PRECISION,
            exact_mass DOUBLE PRECISION,
            monoisotopic_mass DOUBLE PRECISION,
            xlogp DOUBLE PRECISION,
            tpsa DOUBLE PRECISION,
            complexity DOUBLE PRECISION,
            hbond_donor INTEGER,
            hbond_acceptor INTEGER,
            rotatable_bonds INTEGER,
            heavy_atoms INTEGER,
            iupac_name TEXT,
            fetched_at TIMESTAMPTZ DEFAULT NOW(),
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            processed_to_silver BOOLEAN DEFAULT FALSE
        );

        CREATE INDEX IF NOT EXISTS idx_pubchem_cid ON mol_bronze.pubchem_compounds(cid);
        CREATE INDEX IF NOT EXISTS idx_pubchem_inchi ON mol_bronze.pubchem_compounds(inchi_key);
        CREATE INDEX IF NOT EXISTS idx_pubchem_processed ON mol_bronze.pubchem_compounds(processed_to_silver);
    """)
    conn.commit()
    logger.info("PubChem tables ensured")


class PubChemBulkLoader:
    """Bulk loader for PubChem compound properties."""

    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or Path("/tmp/pubchem_bulk")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.inchikey_to_cid: Dict[str, int] = {}
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "DKDataPlatform/1.0"})

    def download_mapping_file(self, force: bool = False) -> Path:
        """Download CID-InChI-Key mapping file from PubChem FTP."""
        local_path = self.data_dir / CID_INCHIKEY_FILE

        if local_path.exists() and not force:
            logger.info(f"Using cached mapping file: {local_path}")
            return local_path

        url = PUBCHEM_FTP_BASE + CID_INCHIKEY_FILE
        logger.info("Downloading PubChem InChI Key mapping (~6.8GB)...")

        response = urllib.request.urlopen(url)
        total_size = int(response.headers.get('content-length', 0))

        with open(local_path, 'wb') as f:
            with tqdm(total=total_size, unit='B', unit_scale=True, desc="Downloading") as pbar:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    pbar.update(len(chunk))

        logger.info(f"Downloaded to: {local_path}")
        return local_path

    def load_mapping(self, target_inchikeys: Set[str] = None) -> int:
        """Load CID-InChI-Key mapping, filtering to target compounds."""
        mapping_file = self.data_dir / CID_INCHIKEY_FILE

        if not mapping_file.exists():
            mapping_file = self.download_mapping_file()

        logger.info("Parsing CID-InChI-Key mapping...")
        logger.info(f"Target compounds: {len(target_inchikeys) if target_inchikeys else 'all'}")

        count = 0
        matched = 0

        with gzip.open(mapping_file, 'rt', encoding='utf-8') as f:
            for line in tqdm(f, desc="Parsing mapping", unit=" lines"):
                count += 1
                parts = line.strip().split('\t')
                if len(parts) >= 3:
                    try:
                        cid = int(parts[0])
                        inchikey = parts[2]

                        if target_inchikeys is None or inchikey in target_inchikeys:
                            self.inchikey_to_cid[inchikey] = cid
                            matched += 1
                    except (ValueError, IndexError):
                        continue

                if count % 10_000_000 == 0:
                    logger.info(f"Processed {count:,} lines, matched {matched:,}")

        logger.info(f"Loaded {len(self.inchikey_to_cid):,} CID mappings from {count:,} total")
        return len(self.inchikey_to_cid)

    def fetch_properties_batch(self, cids: List[int]) -> List[Dict]:
        """Fetch properties for a batch of CIDs via PUG-REST."""
        if not cids:
            return []

        cid_str = ",".join(str(c) for c in cids)
        props_str = ",".join(PUBCHEM_PROPERTIES)
        url = f"{PUBCHEM_API_BASE}/compound/cid/{cid_str}/property/{props_str}/JSON"

        try:
            response = self.session.get(url, timeout=60)
            response.raise_for_status()
            data = response.json()
            return data.get("PropertyTable", {}).get("Properties", [])
        except Exception as e:
            logger.warning(f"API error for batch: {e}")
            return []

    def bulk_enrich(self, conn, limit: int = None, batch_size: int = BATCH_SIZE) -> int:
        """Bulk enrich compounds with PubChem properties."""
        cursor = conn.cursor()

        logger.info("Finding compounds to enrich...")
        cursor.execute("""
            SELECT DISTINCT b.inchi_key
            FROM mol_bronze.bindingdb_affinities b
            WHERE b.inchi_key IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM mol_bronze.pubchem_compounds p
                  WHERE p.inchi_key = b.inchi_key
              )
            ORDER BY b.inchi_key
        """)

        target_inchikeys = {row[0] for row in cursor.fetchall()}
        logger.info(f"Found {len(target_inchikeys):,} compounds needing PubChem enrichment")

        if limit:
            target_inchikeys = set(list(target_inchikeys)[:limit])
            logger.info(f"Limited to {len(target_inchikeys):,} compounds")

        if not target_inchikeys:
            logger.info("All compounds already enriched!")
            return 0

        self.load_mapping(target_inchikeys)

        if not self.inchikey_to_cid:
            logger.warning("No CID mappings found for target compounds")
            return 0

        logger.info(f"Fetching properties for {len(self.inchikey_to_cid):,} compounds...")

        cid_to_inchikey = {v: k for k, v in self.inchikey_to_cid.items()}
        all_cids = list(self.inchikey_to_cid.values())

        enriched = 0
        records = []

        for i in tqdm(range(0, len(all_cids), batch_size), desc="Fetching properties"):
            batch_cids = all_cids[i:i + batch_size]
            properties = self.fetch_properties_batch(batch_cids)

            for prop in properties:
                cid = prop.get("CID")
                inchikey = cid_to_inchikey.get(cid)

                if inchikey:
                    records.append((
                        cid, inchikey, prop.get("CanonicalSMILES"),
                        prop.get("MolecularFormula"), prop.get("MolecularWeight"),
                        prop.get("ExactMass"), prop.get("MonoisotopicMass"),
                        prop.get("XLogP"), prop.get("TPSA"), prop.get("Complexity"),
                        prop.get("HBondDonorCount"), prop.get("HBondAcceptorCount"),
                        prop.get("RotatableBondCount"), prop.get("HeavyAtomCount"),
                        prop.get("IUPACName"),
                    ))

            if len(records) >= 1000:
                self._insert_records(cursor, records)
                conn.commit()
                enriched += len(records)
                records = []

            time.sleep(RATE_LIMIT_DELAY)

        if records:
            self._insert_records(cursor, records)
            conn.commit()
            enriched += len(records)

        logger.info(f"Enriched {enriched:,} compounds with PubChem properties")
        return enriched

    def _insert_records(self, cursor, records: List[tuple]):
        """Insert batch of PubChem records."""
        execute_values(
            cursor,
            """
            INSERT INTO mol_bronze.pubchem_compounds (
                cid, inchi_key, smiles_canonical, molecular_formula,
                molecular_weight, exact_mass, monoisotopic_mass,
                xlogp, tpsa, complexity, hbond_donor, hbond_acceptor,
                rotatable_bonds, heavy_atoms, iupac_name
            ) VALUES %s
            ON CONFLICT (inchi_key) DO UPDATE SET
                cid = EXCLUDED.cid,
                smiles_canonical = COALESCE(EXCLUDED.smiles_canonical, mol_bronze.pubchem_compounds.smiles_canonical),
                molecular_weight = COALESCE(EXCLUDED.molecular_weight, mol_bronze.pubchem_compounds.molecular_weight),
                fetched_at = CURRENT_TIMESTAMP
            """,
            records
        )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Bulk PubChem Data Loader")
    parser.add_argument("--download-only", action="store_true", help="Only download mapping file")
    parser.add_argument("--use-existing", action="store_true", help="Use existing mapping file")
    parser.add_argument("--limit", type=int, help="Limit number of compounds to process")
    parser.add_argument("--data-dir", type=str, default="/tmp/pubchem_bulk", help="Directory for downloads")

    args = parser.parse_args()

    logger.info("PubChem Bulk Loader")

    loader = PubChemBulkLoader(data_dir=Path(args.data_dir))

    if args.download_only:
        loader.download_mapping_file(force=not args.use_existing)
        logger.info("Download complete.")
        return

    conn = psycopg2.connect(build_dsn())
    logger.info(f"Connected to {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")

    ensure_tables(conn)

    try:
        if not args.use_existing:
            loader.download_mapping_file()

        enriched = loader.bulk_enrich(conn, limit=args.limit)
        logger.info(f"Complete! Enriched {enriched:,} compounds")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
