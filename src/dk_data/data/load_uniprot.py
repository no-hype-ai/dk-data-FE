#!/usr/bin/env python3
"""
UniProt Protein Targets Loader

Loads protein target data from UniProt API into PostgreSQL.
Focuses on drug targets and disease-relevant proteins.

Tables populated:
- mol_bronze.uniprot: Protein data with cross-references to PDB, ChEMBL, DrugBank

Usage:
    # Load drug targets for known drugs
    python -m dk_data.data.load_uniprot --mode drug-targets

    # Load by gene names
    python -m dk_data.data.load_uniprot --mode genes --genes EGFR,VEGFA,IL4

    # Load human reviewed proteins (Swiss-Prot)
    python -m dk_data.data.load_uniprot --mode human-reviewed --limit 1000

    # Test with limit
    python -m dk_data.data.load_uniprot --limit 100

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

from dk_data.services.external_apis.uniprot_client import UniProtClient, UniProtProtein
from dk_data.ingestion.utils.database import build_dsn

# Database config
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "dk_data"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}


def ensure_tables(conn) -> None:
    """Create UniProt tables if they don't exist."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mol_bronze.uniprot (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                accession TEXT UNIQUE NOT NULL,
                entry_name TEXT,
                protein_name TEXT,
                gene_names JSONB DEFAULT '[]',
                organism TEXT,
                organism_id INTEGER,
                sequence_length INTEGER,
                mass INTEGER,
                function_description TEXT,
                pathway JSONB DEFAULT '[]',
                subcellular_location JSONB DEFAULT '[]',
                disease_involvement JSONB DEFAULT '[]',
                protein_families JSONB DEFAULT '[]',
                go_terms JSONB DEFAULT '[]',
                ec_numbers JSONB DEFAULT '[]',
                keywords JSONB DEFAULT '[]',
                pdb_ids JSONB DEFAULT '[]',
                chembl_id TEXT,
                drugbank_ids JSONB DEFAULT '[]',
                features JSONB DEFAULT '[]',
                reviewed BOOLEAN DEFAULT FALSE,
                annotation_score INTEGER,
                raw_data JSONB,
                source_updated_at TIMESTAMPTZ DEFAULT NOW(),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                processed_to_silver BOOLEAN DEFAULT FALSE
            );

            CREATE INDEX IF NOT EXISTS idx_uniprot_gene ON mol_bronze.uniprot USING GIN(gene_names);
            CREATE INDEX IF NOT EXISTS idx_uniprot_chembl ON mol_bronze.uniprot(chembl_id);
            CREATE INDEX IF NOT EXISTS idx_uniprot_organism ON mol_bronze.uniprot(organism);
            CREATE INDEX IF NOT EXISTS idx_uniprot_reviewed ON mol_bronze.uniprot(reviewed);
            CREATE INDEX IF NOT EXISTS idx_uniprot_processed ON mol_bronze.uniprot(processed_to_silver);
        """)
        conn.commit()
    logger.info("UniProt tables ensured")


def insert_protein(conn, protein: UniProtProtein, search_type: str) -> bool:
    """Insert a single protein into database."""
    try:
        data = protein.to_dict()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO mol_bronze.uniprot (
                    accession, entry_name, protein_name, gene_names, organism,
                    organism_id, sequence_length, mass, function_description,
                    pathway, subcellular_location, disease_involvement,
                    protein_families, go_terms, ec_numbers, keywords,
                    pdb_ids, chembl_id, drugbank_ids, features, reviewed,
                    annotation_score, raw_data
                ) VALUES (
                    %(accession)s, %(entry_name)s, %(protein_name)s, %(gene_names)s, %(organism)s,
                    %(organism_id)s, %(sequence_length)s, %(mass)s, %(function_description)s,
                    %(pathway)s, %(subcellular_location)s, %(disease_involvement)s,
                    %(protein_families)s, %(go_terms)s, %(ec_numbers)s, %(keywords)s,
                    %(pdb_ids)s, %(chembl_id)s, %(drugbank_ids)s, %(features)s, %(reviewed)s,
                    %(annotation_score)s, %(raw_data)s
                )
                ON CONFLICT (accession) DO UPDATE SET
                    protein_name = EXCLUDED.protein_name,
                    gene_names = EXCLUDED.gene_names,
                    function_description = EXCLUDED.function_description,
                    chembl_id = EXCLUDED.chembl_id,
                    drugbank_ids = EXCLUDED.drugbank_ids,
                    source_updated_at = NOW()
            """, {
                **data,
                "gene_names": Json(data.get("gene_names", [])),
                "pathway": Json(data.get("pathway", [])),
                "subcellular_location": Json(data.get("subcellular_location", [])),
                "disease_involvement": Json(data.get("disease_involvement", [])),
                "protein_families": Json(data.get("protein_families", [])),
                "go_terms": Json(data.get("go_terms", [])),
                "ec_numbers": Json(data.get("ec_numbers", [])),
                "keywords": Json(data.get("keywords", [])),
                "pdb_ids": Json(data.get("pdb_ids", [])),
                "drugbank_ids": Json(data.get("drugbank_ids", [])),
                "features": Json(data.get("features", [])),
                "raw_data": Json(data),
            })
            conn.commit()
        return True
    except Exception as e:
        logger.warning(f"Error inserting protein {protein.accession}: {e}")
        conn.rollback()
        return False


async def load_drug_targets(conn, client: UniProtClient, limit: int = None) -> int:
    """Load protein targets for drugs in the database."""
    total_inserted = 0

    # Get drug names from mol_silver.molecules or mol_bronze.drugbank_targets
    accessions = []
    try:
        with conn.cursor() as cur:
            # Try to get target accessions from DrugBank first
            cur.execute("""
                SELECT DISTINCT uniprot_id
                FROM mol_bronze.drugbank_targets
                WHERE uniprot_id IS NOT NULL AND uniprot_id != ''
                LIMIT 1000
            """)
            accessions = [row[0] for row in cur.fetchall()]
    except Exception:
        pass

    if accessions:
        logger.info(f"Loading {len(accessions)} UniProt targets from DrugBank cross-refs")
        for accession in tqdm(accessions, desc="Loading UniProt targets"):
            try:
                protein = await client.get_protein(accession)
                if protein:
                    if insert_protein(conn, protein, "drugbank_target"):
                        total_inserted += 1

                if limit and total_inserted >= limit:
                    break

                await asyncio.sleep(0.2)  # Rate limiting
            except Exception as e:
                logger.warning(f"Error loading {accession}: {e}")
                continue
    else:
        # Fallback: search for drug targets
        logger.info("No DrugBank targets found, searching for drug targets")
        proteins = await client.search_proteins(
            "keyword:drug AND organism_id:9606",
            reviewed_only=True,
            limit=limit or 500
        )
        for protein in tqdm(proteins, desc="Inserting proteins"):
            if insert_protein(conn, protein, "drug_keyword"):
                total_inserted += 1

    return total_inserted


async def load_by_genes(conn, client: UniProtClient, genes: List[str], limit: int = None) -> int:
    """Load proteins by gene names."""
    total_inserted = 0

    for gene in tqdm(genes, desc="Loading genes"):
        try:
            proteins = await client.search_by_gene(gene, organism="human", limit=5)
            for protein in proteins:
                if insert_protein(conn, protein, f"gene:{gene}"):
                    total_inserted += 1

            if limit and total_inserted >= limit:
                break

            await asyncio.sleep(0.2)
        except Exception as e:
            logger.warning(f"Error loading gene {gene}: {e}")
            continue

    return total_inserted


async def load_human_reviewed(conn, client: UniProtClient, limit: int = 1000) -> int:
    """Load human reviewed proteins (Swiss-Prot)."""
    total_inserted = 0

    # Search for reviewed human proteins with drug relevance
    queries = [
        "keyword:pharmaceutical AND organism_id:9606",
        "keyword:receptor AND organism_id:9606",
        "keyword:kinase AND organism_id:9606",
        "keyword:protease AND organism_id:9606",
    ]

    per_query = limit // len(queries)

    for query in queries:
        try:
            proteins = await client.search_proteins(query, reviewed_only=True, limit=per_query)
            for protein in tqdm(proteins, desc=f"Loading {query[:30]}..."):
                if insert_protein(conn, protein, query):
                    total_inserted += 1

            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(f"Error with query {query}: {e}")
            continue

    return total_inserted


async def main():
    parser = argparse.ArgumentParser(description="Load UniProt protein data")
    parser.add_argument("--mode", choices=["drug-targets", "genes", "human-reviewed"],
                        default="drug-targets", help="Loading mode")
    parser.add_argument("--genes", type=str, help="Comma-separated gene names for genes mode")
    parser.add_argument("--limit", type=int, help="Limit records to load")
    args = parser.parse_args()

    logger.info(f"Starting UniProt loader in {args.mode} mode")

    # Connect to database
    conn = psycopg2.connect(build_dsn())
    ensure_tables(conn)

    # Initialize client
    client = UniProtClient()

    try:
        if args.mode == "drug-targets":
            total = await load_drug_targets(conn, client, args.limit)

        elif args.mode == "genes":
            if not args.genes:
                logger.error("--genes required for genes mode")
                sys.exit(1)
            genes = [g.strip() for g in args.genes.split(",")]
            total = await load_by_genes(conn, client, genes, args.limit)

        elif args.mode == "human-reviewed":
            total = await load_human_reviewed(conn, client, args.limit or 1000)

        logger.info(f"UniProt loading complete. Inserted {total} proteins.")

    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
