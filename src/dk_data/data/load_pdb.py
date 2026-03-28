#!/usr/bin/env python3
"""
RCSB PDB Protein Structure Loader

Loads protein structure data from RCSB PDB into PostgreSQL.
Focuses on drug-target protein structures.

Tables populated:
- mol_bronze.pdb: Protein structure data with ligand information

Usage:
    # Load structures for drug targets
    python -m dk_data.data.load_pdb --mode drug-targets

    # Load by UniProt accessions
    python -m dk_data.data.load_pdb --mode uniprot --accessions P05112,P01308

    # Load structures with bound ligands
    python -m dk_data.data.load_pdb --mode ligand-bound --limit 1000

    # Test with limit
    python -m dk_data.data.load_pdb --limit 100

Environment:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
"""

import os
import sys
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
import argparse

import psycopg2
from psycopg2.extras import Json
from loguru import logger
from tqdm import tqdm
import aiohttp

# Database config
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "dk_data"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

# RCSB PDB API
PDB_SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
PDB_DATA_URL = "https://data.rcsb.org/rest/v1/core/entry"


def ensure_tables(conn) -> None:
    """Create PDB tables if they don't exist."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mol_bronze.pdb (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                pdb_id TEXT UNIQUE NOT NULL,
                title TEXT,
                description TEXT,
                experimental_method TEXT,
                resolution NUMERIC(5,2),
                release_date DATE,
                revision_date DATE,

                -- Structure info
                polymer_count INTEGER,
                entity_count INTEGER,
                deposited_model_count INTEGER,

                -- Organism
                organism TEXT,
                organism_id INTEGER,

                -- Authors
                authors JSONB DEFAULT '[]',
                citation_title TEXT,
                citation_doi TEXT,

                -- Cross-references
                uniprot_ids JSONB DEFAULT '[]',
                gene_names JSONB DEFAULT '[]',

                -- Ligands
                ligands JSONB DEFAULT '[]',
                has_ligand BOOLEAN DEFAULT FALSE,

                -- Classification
                keywords JSONB DEFAULT '[]',

                raw_data JSONB,
                source_updated_at TIMESTAMPTZ DEFAULT NOW(),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                processed_to_silver BOOLEAN DEFAULT FALSE
            );

            CREATE INDEX IF NOT EXISTS idx_pdb_organism ON mol_bronze.pdb(organism);
            CREATE INDEX IF NOT EXISTS idx_pdb_method ON mol_bronze.pdb(experimental_method);
            CREATE INDEX IF NOT EXISTS idx_pdb_resolution ON mol_bronze.pdb(resolution);
            CREATE INDEX IF NOT EXISTS idx_pdb_ligand ON mol_bronze.pdb(has_ligand);
            CREATE INDEX IF NOT EXISTS idx_pdb_uniprot ON mol_bronze.pdb USING GIN(uniprot_ids);
            CREATE INDEX IF NOT EXISTS idx_pdb_processed ON mol_bronze.pdb(processed_to_silver);
        """)
        conn.commit()
    logger.info("PDB tables ensured")


async def search_pdb(query: Dict[str, Any], limit: int = 100) -> List[str]:
    """Search PDB and return list of PDB IDs."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                PDB_SEARCH_URL,
                json=query,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status != 200:
                    logger.warning(f"PDB search returned {response.status}")
                    return []

                data = await response.json()
                results = data.get("result_set", [])
                return [r.get("identifier") for r in results[:limit] if r.get("identifier")]

    except Exception as e:
        logger.error(f"PDB search error: {e}")
        return []


async def get_pdb_entry(pdb_id: str) -> Optional[Dict[str, Any]]:
    """Get detailed PDB entry data."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{PDB_DATA_URL}/{pdb_id}",
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    return await response.json()
                return None
    except Exception as e:
        logger.warning(f"Error fetching PDB {pdb_id}: {e}")
        return None


def parse_pdb_entry(data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse PDB entry data."""
    entry = data.get("entry", {})
    struct = data.get("struct", {})
    citation = data.get("citation", [{}])[0] if data.get("citation") else {}
    exptl = data.get("exptl", [{}])[0] if data.get("exptl") else {}
    rcsb_entry = data.get("rcsb_entry_info", {})

    # Parse UniProt cross-refs
    uniprot_ids = []
    gene_names = []
    polymer_entities = data.get("polymer_entities", [])
    for entity in polymer_entities:
        for ref in entity.get("rcsb_polymer_entity_container_identifiers", {}).get("uniprot_ids", []):
            if ref not in uniprot_ids:
                uniprot_ids.append(ref)
        for name in entity.get("rcsb_polymer_entity", {}).get("pdbx_gene_names", []):
            if name not in gene_names:
                gene_names.append(name)

    # Parse ligands
    ligands = []
    nonpolymer_entities = data.get("nonpolymer_entities", [])
    for entity in nonpolymer_entities:
        comp = entity.get("nonpolymer_comp", {})
        ligands.append({
            "id": comp.get("chem_comp", {}).get("id"),
            "name": comp.get("chem_comp", {}).get("name"),
            "formula": comp.get("chem_comp", {}).get("formula"),
        })

    # Parse organism
    organism = None
    organism_id = None
    for entity in polymer_entities:
        src = entity.get("entity_src_gen", [{}])[0] if entity.get("entity_src_gen") else {}
        if src.get("pdbx_gene_src_scientific_name"):
            organism = src["pdbx_gene_src_scientific_name"]
            organism_id = src.get("pdbx_gene_src_ncbi_taxonomy_id")
            break

    # Parse release date
    release_date = None
    if entry.get("rcsb_accession_info", {}).get("initial_release_date"):
        try:
            release_date = datetime.fromisoformat(
                entry["rcsb_accession_info"]["initial_release_date"].replace("Z", "+00:00")
            ).date()
        except Exception:
            pass

    return {
        "pdb_id": entry.get("id"),
        "title": struct.get("title"),
        "description": struct.get("pdbx_descriptor"),
        "experimental_method": exptl.get("method"),
        "resolution": rcsb_entry.get("resolution_combined", [None])[0],
        "release_date": release_date,
        "polymer_count": rcsb_entry.get("polymer_entity_count"),
        "entity_count": rcsb_entry.get("entity_count"),
        "deposited_model_count": rcsb_entry.get("deposited_model_count"),
        "organism": organism,
        "organism_id": organism_id,
        "authors": data.get("audit_author", []),
        "citation_title": citation.get("title"),
        "citation_doi": citation.get("pdbx_database_id_DOI"),
        "uniprot_ids": uniprot_ids,
        "gene_names": gene_names,
        "ligands": ligands,
        "has_ligand": len(ligands) > 0,
        "keywords": struct.get("pdbx_keywords", "").split(", ") if struct.get("pdbx_keywords") else [],
    }


def insert_pdb_entry(conn, entry: Dict[str, Any]) -> bool:
    """Insert PDB entry into database."""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO mol_bronze.pdb (
                    pdb_id, title, description, experimental_method, resolution,
                    release_date, polymer_count, entity_count, deposited_model_count,
                    organism, organism_id, authors, citation_title, citation_doi,
                    uniprot_ids, gene_names, ligands, has_ligand, keywords, raw_data
                ) VALUES (
                    %(pdb_id)s, %(title)s, %(description)s, %(experimental_method)s, %(resolution)s,
                    %(release_date)s, %(polymer_count)s, %(entity_count)s, %(deposited_model_count)s,
                    %(organism)s, %(organism_id)s, %(authors)s, %(citation_title)s, %(citation_doi)s,
                    %(uniprot_ids)s, %(gene_names)s, %(ligands)s, %(has_ligand)s, %(keywords)s, %(raw_data)s
                )
                ON CONFLICT (pdb_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    resolution = EXCLUDED.resolution,
                    source_updated_at = NOW()
            """, {
                **entry,
                "authors": Json(entry.get("authors", [])),
                "uniprot_ids": Json(entry.get("uniprot_ids", [])),
                "gene_names": Json(entry.get("gene_names", [])),
                "ligands": Json(entry.get("ligands", [])),
                "keywords": Json(entry.get("keywords", [])),
                "raw_data": Json(entry),
            })
            conn.commit()
        return True
    except Exception as e:
        logger.warning(f"Error inserting PDB {entry.get('pdb_id')}: {e}")
        conn.rollback()
        return False


async def load_drug_targets(conn, limit: int = 500) -> int:
    """Load structures for drug-relevant proteins."""
    # Search for human protein structures with ligands
    query = {
        "query": {
            "type": "group",
            "logical_operator": "and",
            "nodes": [
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "rcsb_entity_source_organism.taxonomy_lineage.name",
                        "operator": "exact_match",
                        "value": "Homo sapiens"
                    }
                },
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "rcsb_entry_info.nonpolymer_entity_count",
                        "operator": "greater",
                        "value": 0
                    }
                }
            ]
        },
        "return_type": "entry",
        "request_options": {
            "paginate": {"start": 0, "rows": limit},
            "sort": [{"sort_by": "rcsb_accession_info.initial_release_date", "direction": "desc"}]
        }
    }

    pdb_ids = await search_pdb(query, limit)
    logger.info(f"Found {len(pdb_ids)} PDB structures")

    total_inserted = 0
    for pdb_id in tqdm(pdb_ids, desc="Loading PDB structures"):
        data = await get_pdb_entry(pdb_id)
        if data:
            entry = parse_pdb_entry(data)
            if insert_pdb_entry(conn, entry):
                total_inserted += 1
        await asyncio.sleep(0.1)

    return total_inserted


async def load_by_uniprot(conn, accessions: List[str], limit: int = None) -> int:
    """Load structures by UniProt accessions."""
    total_inserted = 0

    for accession in tqdm(accessions[:limit] if limit else accessions, desc="Loading by UniProt"):
        query = {
            "query": {
                "type": "terminal",
                "service": "text",
                "parameters": {
                    "attribute": "rcsb_polymer_entity_container_identifiers.uniprot_ids",
                    "operator": "exact_match",
                    "value": accession
                }
            },
            "return_type": "entry",
            "request_options": {"paginate": {"start": 0, "rows": 10}}
        }

        pdb_ids = await search_pdb(query, 10)
        for pdb_id in pdb_ids:
            data = await get_pdb_entry(pdb_id)
            if data:
                entry = parse_pdb_entry(data)
                if insert_pdb_entry(conn, entry):
                    total_inserted += 1

        await asyncio.sleep(0.2)

    return total_inserted


async def main():
    parser = argparse.ArgumentParser(description="Load PDB structure data")
    parser.add_argument("--mode", choices=["drug-targets", "uniprot", "ligand-bound"],
                        default="drug-targets", help="Loading mode")
    parser.add_argument("--accessions", type=str, help="Comma-separated UniProt accessions")
    parser.add_argument("--limit", type=int, default=500, help="Limit records to load")
    args = parser.parse_args()

    logger.info(f"Starting PDB loader in {args.mode} mode")

    conn = psycopg2.connect(**DB_CONFIG)
    ensure_tables(conn)

    try:
        if args.mode == "drug-targets":
            total = await load_drug_targets(conn, args.limit)

        elif args.mode == "uniprot":
            if not args.accessions:
                logger.error("--accessions required for uniprot mode")
                sys.exit(1)
            accessions = [a.strip() for a in args.accessions.split(",")]
            total = await load_by_uniprot(conn, accessions, args.limit)

        elif args.mode == "ligand-bound":
            total = await load_drug_targets(conn, args.limit)

        logger.info(f"PDB loading complete. Inserted {total} structures.")

    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
