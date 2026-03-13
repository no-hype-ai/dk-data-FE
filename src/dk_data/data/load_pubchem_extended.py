#!/usr/bin/env python3
"""
Extended PubChem data loader for bioassays, pharmacology, and safety data.

Tables populated:
- bronze.pubchem_bioassays: Bioassay results
- bronze.pubchem_xrefs: Cross-references to other databases
- bronze.pubchem_safety: GHS safety/hazard data
- bronze.pubchem_pharmacology: Pharmacology data

Usage:
    python -m dk_data.data.load_pubchem_extended --all
    python -m dk_data.data.load_pubchem_extended --bioassays --limit 1000
    python -m dk_data.data.load_pubchem_extended --xrefs --limit 1000
    python -m dk_data.data.load_pubchem_extended --safety --limit 1000

Environment:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
"""

import os
import sys
import re
import time

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

PUBCHEM_RATE = 0.35


def ensure_tables(conn):
    """Create tables for extended PubChem data."""
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.pubchem_bioassays (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            inchi_key VARCHAR(27),
            cid BIGINT,
            aid BIGINT,
            assay_name TEXT,
            assay_type VARCHAR(50),
            assay_source VARCHAR(200),
            activity_outcome VARCHAR(20),
            activity_score DOUBLE PRECISION,
            target_name TEXT,
            target_gi BIGINT,
            gene_symbol VARCHAR(50),
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(cid, aid)
        );

        CREATE INDEX IF NOT EXISTS idx_pubchem_bioassays_inchi ON bronze.pubchem_bioassays(inchi_key);
        CREATE INDEX IF NOT EXISTS idx_pubchem_bioassays_cid ON bronze.pubchem_bioassays(cid);
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.pubchem_xrefs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            inchi_key VARCHAR(27),
            cid BIGINT,
            xref_type VARCHAR(50),
            xref_id VARCHAR(100),
            xref_name TEXT,
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(cid, xref_type, xref_id)
        );

        CREATE INDEX IF NOT EXISTS idx_pubchem_xrefs_inchi ON bronze.pubchem_xrefs(inchi_key);
        CREATE INDEX IF NOT EXISTS idx_pubchem_xrefs_cid ON bronze.pubchem_xrefs(cid);
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.pubchem_safety (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            inchi_key VARCHAR(27),
            cid BIGINT,
            ghs_code VARCHAR(20),
            ghs_statement TEXT,
            signal_word VARCHAR(20),
            hazard_class VARCHAR(100),
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(cid, ghs_code)
        );

        CREATE INDEX IF NOT EXISTS idx_pubchem_safety_inchi ON bronze.pubchem_safety(inchi_key);
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.pubchem_pharmacology (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            inchi_key VARCHAR(27),
            cid BIGINT,
            pharmacology_type VARCHAR(50),
            description TEXT,
            source VARCHAR(200),
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_pubchem_pharmacology_inchi ON bronze.pubchem_pharmacology(inchi_key);
    """)

    conn.commit()
    logger.info("Extended PubChem tables created")


class PubChemExtendedEnricher:
    """Extended PubChem enrichment for bioassays, xrefs, and safety data."""

    BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
    VIEW_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view"

    def __init__(self, conn):
        self.conn = conn
        self.session = requests.Session()

    def get_compounds_with_cids(self, limit: int = None):
        """Get compounds that have PubChem CIDs."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT DISTINCT pc.inchi_key, pc.cid
            FROM bronze.pubchem_compounds pc
            WHERE pc.cid IS NOT NULL
            ORDER BY pc.inchi_key
            LIMIT %s
        """, (limit or 100000,))
        return cursor.fetchall()

    def load_bioassays(self, limit: int = None) -> int:
        """Load PubChem bioassay results for our compounds."""
        compounds = self.get_compounds_with_cids(limit)
        logger.info(f"Loading bioassays for {len(compounds)} compounds")

        cursor = self.conn.cursor()
        total_loaded = 0
        batch = []
        batch_size = 500

        for inchi_key, cid in tqdm(compounds, desc="Loading bioassays"):
            try:
                cursor.execute("SELECT COUNT(*) FROM bronze.pubchem_bioassays WHERE cid = %s", (cid,))
                if cursor.fetchone()[0] > 0:
                    continue

                time.sleep(PUBCHEM_RATE)

                response = self.session.get(
                    f"{self.BASE_URL}/compound/cid/{cid}/assaysummary/JSON",
                    timeout=30
                )

                if response.status_code != 200:
                    continue

                data = response.json()
                assays = data.get("Table", {}).get("Row", [])

                if not assays:
                    continue

                for row in assays[:50]:
                    cells = row.get("Cell", [])
                    if len(cells) < 5:
                        continue

                    record = {
                        "inchi_key": inchi_key,
                        "cid": cid,
                        "aid": self._safe_int(cells[0]),
                        "activity_outcome": cells[1] if len(cells) > 1 else None,
                        "target_gi": self._safe_int(cells[2]) if len(cells) > 2 else None,
                        "target_name": cells[3] if len(cells) > 3 else None,
                        "assay_name": cells[4] if len(cells) > 4 else None,
                    }

                    if record["aid"]:
                        batch.append(record)

                if len(batch) >= batch_size:
                    total_loaded += self._insert_bioassay_batch(cursor, batch)
                    batch = []
                    self.conn.commit()

            except Exception as e:
                logger.debug(f"Bioassay error for CID {cid}: {e}")
                continue

        if batch:
            total_loaded += self._insert_bioassay_batch(cursor, batch)
            self.conn.commit()

        logger.info(f"Loaded {total_loaded} bioassay records")
        return total_loaded

    def _insert_bioassay_batch(self, cursor, records: list) -> int:
        """Insert batch of bioassay records."""
        if not records:
            return 0

        values = [
            (r["inchi_key"], r["cid"], r["aid"], r.get("assay_name"),
             r.get("assay_type"), r.get("assay_source"), r.get("activity_outcome"),
             r.get("activity_score"), r.get("target_name"), r.get("target_gi"),
             r.get("gene_symbol"))
            for r in records
        ]

        execute_values(
            cursor,
            """
            INSERT INTO bronze.pubchem_bioassays (
                inchi_key, cid, aid, assay_name, assay_type, assay_source,
                activity_outcome, activity_score, target_name, target_gi, gene_symbol
            ) VALUES %s
            ON CONFLICT (cid, aid) DO NOTHING
            """,
            values
        )
        return len(values)

    def load_xrefs(self, limit: int = None) -> int:
        """Load cross-references to other databases."""
        compounds = self.get_compounds_with_cids(limit)
        logger.info(f"Loading xrefs for {len(compounds)} compounds")

        cursor = self.conn.cursor()
        total_loaded = 0
        batch = []
        batch_size = 500

        important_xrefs = [
            "DrugBank", "PharmGKB", "ChEMBL", "KEGG",
            "UniProtKB", "NCI Thesaurus", "Human Metabolome Database"
        ]

        for inchi_key, cid in tqdm(compounds, desc="Loading xrefs"):
            try:
                cursor.execute("SELECT COUNT(*) FROM bronze.pubchem_xrefs WHERE cid = %s", (cid,))
                if cursor.fetchone()[0] > 0:
                    continue

                time.sleep(PUBCHEM_RATE)

                response = self.session.get(
                    f"{self.BASE_URL}/compound/cid/{cid}/xrefs/SourceName,RegistryID/JSON",
                    timeout=30
                )

                if response.status_code != 200:
                    continue

                data = response.json()
                info_list = data.get("InformationList", {}).get("Information", [])

                for info in info_list:
                    if info.get("CID") != cid:
                        continue

                    source_names = info.get("SourceName", [])
                    registry_ids = info.get("RegistryID", [])

                    for i, source in enumerate(source_names):
                        if source in important_xrefs:
                            xref_id = registry_ids[i] if i < len(registry_ids) else None
                            if xref_id:
                                batch.append({
                                    "inchi_key": inchi_key,
                                    "cid": cid,
                                    "xref_type": source,
                                    "xref_id": str(xref_id),
                                    "xref_name": None
                                })

                if len(batch) >= batch_size:
                    total_loaded += self._insert_xref_batch(cursor, batch)
                    batch = []
                    self.conn.commit()

            except Exception as e:
                logger.debug(f"Xref error for CID {cid}: {e}")
                continue

        if batch:
            total_loaded += self._insert_xref_batch(cursor, batch)
            self.conn.commit()

        logger.info(f"Loaded {total_loaded} xref records")
        return total_loaded

    def _insert_xref_batch(self, cursor, records: list) -> int:
        """Insert batch of xref records."""
        if not records:
            return 0

        values = [
            (r["inchi_key"], r["cid"], r["xref_type"], r["xref_id"], r["xref_name"])
            for r in records
        ]

        execute_values(
            cursor,
            """
            INSERT INTO bronze.pubchem_xrefs (inchi_key, cid, xref_type, xref_id, xref_name)
            VALUES %s
            ON CONFLICT (cid, xref_type, xref_id) DO NOTHING
            """,
            values
        )
        return len(values)

    def load_safety_data(self, limit: int = None) -> int:
        """Load GHS safety/hazard classifications."""
        compounds = self.get_compounds_with_cids(limit)
        logger.info(f"Loading safety data for {len(compounds)} compounds")

        cursor = self.conn.cursor()
        total_loaded = 0
        batch = []
        batch_size = 500

        for inchi_key, cid in tqdm(compounds, desc="Loading safety data"):
            try:
                cursor.execute("SELECT COUNT(*) FROM bronze.pubchem_safety WHERE cid = %s", (cid,))
                if cursor.fetchone()[0] > 0:
                    continue

                time.sleep(PUBCHEM_RATE)

                response = self.session.get(
                    f"{self.VIEW_URL}/data/compound/{cid}/JSON",
                    params={"heading": "GHS Classification"},
                    timeout=30
                )

                if response.status_code != 200:
                    continue

                data = response.json()
                record = data.get("Record", {})
                sections = record.get("Section", [])

                for section in sections:
                    if section.get("TOCHeading") == "GHS Classification":
                        ghs_sections = section.get("Section", [])
                        for ghs in ghs_sections:
                            heading = ghs.get("TOCHeading", "")
                            info = ghs.get("Information", [])

                            for item in info:
                                value = item.get("Value", {})
                                string_val = value.get("StringWithMarkup", [])

                                for s in string_val:
                                    text = s.get("String", "")
                                    if text:
                                        ghs_codes = re.findall(r'H\d{3}', text)

                                        for code in ghs_codes:
                                            batch.append({
                                                "inchi_key": inchi_key,
                                                "cid": cid,
                                                "ghs_code": code,
                                                "ghs_statement": text[:500],
                                                "signal_word": heading if "Signal" in heading else None,
                                                "hazard_class": heading
                                            })

                if len(batch) >= batch_size:
                    total_loaded += self._insert_safety_batch(cursor, batch)
                    batch = []
                    self.conn.commit()

            except Exception as e:
                logger.debug(f"Safety error for CID {cid}: {e}")
                continue

        if batch:
            total_loaded += self._insert_safety_batch(cursor, batch)
            self.conn.commit()

        logger.info(f"Loaded {total_loaded} safety records")
        return total_loaded

    def _insert_safety_batch(self, cursor, records: list) -> int:
        """Insert batch of safety records."""
        if not records:
            return 0

        values = [
            (r["inchi_key"], r["cid"], r["ghs_code"],
             r["ghs_statement"], r["signal_word"], r["hazard_class"])
            for r in records
        ]

        execute_values(
            cursor,
            """
            INSERT INTO bronze.pubchem_safety (
                inchi_key, cid, ghs_code, ghs_statement, signal_word, hazard_class
            ) VALUES %s
            ON CONFLICT (cid, ghs_code) DO NOTHING
            """,
            values
        )
        return len(values)

    def _safe_int(self, val) -> int | None:
        """Safely convert to int."""
        try:
            if val is not None:
                return int(val)
        except (ValueError, TypeError):
            pass
        return None


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Load extended PubChem data")
    parser.add_argument("--all", action="store_true", help="Load all data types")
    parser.add_argument("--bioassays", action="store_true", help="Load bioassay results")
    parser.add_argument("--xrefs", action="store_true", help="Load cross-references")
    parser.add_argument("--safety", action="store_true", help="Load GHS safety data")
    parser.add_argument("--limit", type=int, help="Max compounds to process")

    args = parser.parse_args()

    if not any([args.all, args.bioassays, args.xrefs, args.safety]):
        parser.print_help()
        sys.exit(1)

    logger.info("Connecting to database...")
    conn = psycopg2.connect(**DB_CONFIG)
    logger.info(f"Connected to {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")

    ensure_tables(conn)

    try:
        enricher = PubChemExtendedEnricher(conn)

        if args.all or args.bioassays:
            enricher.load_bioassays(limit=args.limit)

        if args.all or args.xrefs:
            enricher.load_xrefs(limit=args.limit)

        if args.all or args.safety:
            enricher.load_safety_data(limit=args.limit)

        cursor = conn.cursor()
        logger.info("\n=== SUMMARY ===")
        from psycopg2 import sql as psql
        for table in ['pubchem_bioassays', 'pubchem_xrefs', 'pubchem_safety', 'pubchem_pharmacology']:
            cursor.execute(psql.SQL("SELECT COUNT(*) FROM bronze.{}").format(psql.Identifier(table)))
            count = cursor.fetchone()[0]
            logger.info(f"bronze.{table}: {count:,} records")

    finally:
        conn.close()

    logger.info("Done!")


if __name__ == "__main__":
    main()
