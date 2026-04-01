#!/usr/bin/env python3
"""
DrugBank Database Loader

Loads DrugBank XML database into PostgreSQL tables:
- mol_bronze.drugbank_data: Core drug information (SMILES, indications, PK data)
- mol_bronze.drugbank_interactions: Drug-drug interactions
- mol_bronze.drugbank_targets: Drug-target interactions with mechanisms

Uses streaming XML parsing (iterparse) for memory efficiency.

Usage:
    # Load all DrugBank data
    python -m dk_data.data.load_drugbank --xml /path/to/full_database.xml

    # Load only drug information (skip interactions)
    python -m dk_data.data.load_drugbank --xml /path/to/full_database.xml --drugs-only

    # Test with limit
    python -m dk_data.data.load_drugbank --xml /path/to/full_database.xml --limit 100

Environment:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
"""

import os
import sys
import gzip
import zipfile
from pathlib import Path
from typing import Iterator, Optional
from dataclasses import dataclass, field
from xml.etree.ElementTree import iterparse
import argparse

import psycopg2
from psycopg2.extras import execute_values
from loguru import logger
from tqdm import tqdm

# Database config
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "dk_data"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

# DrugBank XML namespace
NS = "{http://www.drugbank.ca}"


@dataclass
class DrugBankDrug:
    """Represents a DrugBank drug entry."""
    drugbank_id: str
    name: str
    drug_type: str = "small molecule"
    description: str = ""
    cas_number: str = ""
    unii: str = ""
    state: str = ""
    groups: list = field(default_factory=list)
    smiles: str = ""
    inchi_key: str = ""
    molecular_formula: str = ""
    molecular_weight: float = None
    indication: str = ""
    mechanism_of_action: str = ""
    half_life: str = ""
    pubchem_cid: str = ""
    chembl_id: str = ""
    drug_interactions: list = field(default_factory=list)
    targets: list = field(default_factory=list)


@dataclass
class DrugBankTarget:
    """Represents a drug-target interaction."""
    target_id: str
    name: str
    organism: str = ""
    actions: list = field(default_factory=list)
    known_action: str = ""
    uniprot_id: str = ""
    gene_name: str = ""


def get_text(element, tag: str, ns: str = NS) -> str:
    """Safely get text from XML element."""
    child = element.find(f"{ns}{tag}")
    if child is not None and child.text:
        return child.text.strip()
    return ""


def get_all_text(element, tag: str, ns: str = NS) -> list:
    """Get text from all matching elements."""
    children = element.findall(f"{ns}{tag}")
    return [c.text.strip() for c in children if c.text]


def parse_target(target_elem, ns: str = NS) -> DrugBankTarget:
    """Parse a target element."""
    target = DrugBankTarget(
        target_id=get_text(target_elem, "id", ns),
        name=get_text(target_elem, "name", ns),
        organism=get_text(target_elem, "organism", ns),
        known_action=get_text(target_elem, "known-action", ns),
    )

    actions_elem = target_elem.find(f"{ns}actions")
    if actions_elem is not None:
        target.actions = get_all_text(actions_elem, "action", ns)

    polypeptide = target_elem.find(f"{ns}polypeptide")
    if polypeptide is not None:
        target.uniprot_id = polypeptide.get("id", "")
        target.gene_name = get_text(polypeptide, "gene-name", ns)

    return target


def parse_drug(drug_elem, ns: str = NS) -> DrugBankDrug:
    """Parse a drug element into DrugBankDrug."""
    drug = DrugBankDrug(
        drugbank_id="",
        name=get_text(drug_elem, "name", ns),
        drug_type=drug_elem.get("type", "small molecule"),
    )

    for db_id in drug_elem.findall(f"{ns}drugbank-id"):
        if db_id.get("primary") == "true":
            drug.drugbank_id = db_id.text.strip() if db_id.text else ""
            break

    drug.description = get_text(drug_elem, "description", ns)[:10000]
    drug.cas_number = get_text(drug_elem, "cas-number", ns)
    drug.unii = get_text(drug_elem, "unii", ns)
    drug.state = get_text(drug_elem, "state", ns)

    groups_elem = drug_elem.find(f"{ns}groups")
    if groups_elem is not None:
        drug.groups = get_all_text(groups_elem, "group", ns)

    drug.indication = get_text(drug_elem, "indication", ns)[:10000]
    drug.mechanism_of_action = get_text(drug_elem, "mechanism-of-action", ns)[:10000]
    drug.half_life = get_text(drug_elem, "half-life", ns)[:1000]

    # Calculated properties
    calc_props = drug_elem.find(f"{ns}calculated-properties")
    if calc_props is not None:
        for prop in calc_props.findall(f"{ns}property"):
            kind = get_text(prop, "kind", ns)
            value = get_text(prop, "value", ns)
            if kind == "SMILES":
                drug.smiles = value
            elif kind == "InChIKey":
                drug.inchi_key = value
            elif kind == "Molecular Formula":
                drug.molecular_formula = value
            elif kind == "Molecular Weight":
                try:
                    drug.molecular_weight = float(value)
                except Exception:
                    pass

    # External identifiers
    ext_ids = drug_elem.find(f"{ns}external-identifiers")
    if ext_ids is not None:
        for ext_id in ext_ids.findall(f"{ns}external-identifier"):
            resource = get_text(ext_id, "resource", ns)
            identifier = get_text(ext_id, "identifier", ns)
            if resource == "PubChem Compound":
                drug.pubchem_cid = identifier
            elif resource == "ChEMBL":
                drug.chembl_id = identifier

    # Drug interactions
    ddi_elem = drug_elem.find(f"{ns}drug-interactions")
    if ddi_elem is not None:
        for interaction in ddi_elem.findall(f"{ns}drug-interaction"):
            other_id = get_text(interaction, "drugbank-id", ns)
            other_name = get_text(interaction, "name", ns)
            description = get_text(interaction, "description", ns)
            if other_id:
                drug.drug_interactions.append((other_id, other_name, description))

    # Targets
    targets_elem = drug_elem.find(f"{ns}targets")
    if targets_elem is not None:
        for target_elem in targets_elem.findall(f"{ns}target"):
            target = parse_target(target_elem, ns)
            if target.target_id:
                drug.targets.append(target)

    return drug


def iter_drugs(xml_path: str, limit: Optional[int] = None) -> Iterator[DrugBankDrug]:
    """Stream parse DrugBank XML file."""
    if xml_path.endswith('.zip'):
        # Check for Git LFS pointer file (not actual zip data)
        with open(xml_path, 'rb') as check:
            header = check.read(40)
            if header.startswith(b'version https://git-lfs'):
                raise ValueError(
                    f"File is a Git LFS pointer, not actual data: {xml_path}. "
                    "Run 'git lfs pull' to fetch the actual file."
                )
        with zipfile.ZipFile(xml_path, 'r') as zf:
            xml_files = [f for f in zf.namelist() if f.endswith('.xml')]
            if not xml_files:
                raise ValueError("No XML file found in zip archive")
            with zf.open(xml_files[0]) as xml_file:
                yield from _iter_drugs_from_file(xml_file, limit)
    elif xml_path.endswith('.gz'):
        with gzip.open(xml_path, 'rb') as f:
            yield from _iter_drugs_from_file(f, limit)
    else:
        with open(xml_path, 'rb') as f:
            yield from _iter_drugs_from_file(f, limit)


def _iter_drugs_from_file(file_obj, limit: Optional[int] = None) -> Iterator[DrugBankDrug]:
    """Internal function to iterate drugs from file object.

    The DrugBank XML contains ~17k top-level ``<drug type="...">``
    elements and ~56k bare ``<drug>`` stubs nested inside
    ``<pathways>/<drugs>`` and similar containers.  We track depth
    so that only top-level drug elements are parsed and cleared.
    """
    count = 0
    drug_depth = 0

    for event, elem in iterparse(file_obj, events=('start', 'end')):
        is_drug = elem.tag == f"{NS}drug" or elem.tag == 'drug'

        if event == 'start' and is_drug:
            drug_depth += 1
            continue

        if event == 'end' and is_drug:
            if drug_depth == 1:
                drug = parse_drug(elem, NS)
                if drug.drugbank_id:
                    yield drug
                    count += 1
                    if limit and count >= limit:
                        return
                elem.clear()
            drug_depth -= 1


def ensure_tables(conn):
    """Ensure DrugBank tables exist."""
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mol_bronze.drugbank_data (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            drugbank_id VARCHAR(20) UNIQUE NOT NULL,
            drug_name TEXT,
            drug_type VARCHAR(50),
            drug_groups TEXT[],
            smiles TEXT,
            inchi_key VARCHAR(27),
            cas_number VARCHAR(20),
            unii VARCHAR(20),
            indication TEXT,
            pharmacodynamics TEXT,
            mechanism_of_action TEXT,
            absorption TEXT,
            metabolism TEXT,
            half_life TEXT,
            clearance TEXT,
            pubchem_cid VARCHAR(20),
            chembl_id VARCHAR(20),
            kegg_id VARCHAR(20),
            molecular_weight DOUBLE PRECISION,
            molecular_formula VARCHAR(200),
            toxicity TEXT,
            protein_binding TEXT,
            route_of_elimination TEXT,
            volume_of_distribution TEXT,
            food_interactions TEXT[],
            raw_data JSONB,
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            processed_to_silver BOOLEAN DEFAULT FALSE
        );

        CREATE INDEX IF NOT EXISTS idx_drugbank_smiles ON mol_bronze.drugbank_data(smiles) WHERE smiles IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_drugbank_inchi ON mol_bronze.drugbank_data(inchi_key) WHERE inchi_key IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_drugbank_pubchem ON mol_bronze.drugbank_data(pubchem_cid);
        CREATE INDEX IF NOT EXISTS idx_drugbank_chembl ON mol_bronze.drugbank_data(chembl_id);
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mol_bronze.drugbank_interactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            drugbank_id_1 VARCHAR(20) NOT NULL,
            drugbank_id_2 VARCHAR(20) NOT NULL,
            drug_name_1 TEXT,
            drug_name_2 TEXT,
            interaction_description TEXT,
            inchi_key_1 VARCHAR(27),
            inchi_key_2 VARCHAR(27),
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(drugbank_id_1, drugbank_id_2)
        );

        CREATE INDEX IF NOT EXISTS idx_ddi_drug1 ON mol_bronze.drugbank_interactions(drugbank_id_1);
        CREATE INDEX IF NOT EXISTS idx_ddi_drug2 ON mol_bronze.drugbank_interactions(drugbank_id_2);
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mol_bronze.drugbank_targets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            drugbank_id VARCHAR(20) NOT NULL,
            target_id VARCHAR(20),
            target_name TEXT,
            organism VARCHAR(200),
            uniprot_id VARCHAR(20),
            gene_name VARCHAR(50),
            actions TEXT[],
            known_action VARCHAR(10),
            general_function TEXT,
            specific_function TEXT,
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(drugbank_id, uniprot_id)
        );

        CREATE INDEX IF NOT EXISTS idx_drugbank_targets_uniprot ON mol_bronze.drugbank_targets(uniprot_id);
        CREATE INDEX IF NOT EXISTS idx_drugbank_targets_drug ON mol_bronze.drugbank_targets(drugbank_id);
    """)

    conn.commit()
    logger.info("DrugBank tables ensured")


def load_drugbank(
    xml_path: str,
    conn,
    load_drugs: bool = True,
    load_interactions: bool = True,
    load_targets: bool = True,
    limit: Optional[int] = None,
    batch_size: int = 1000,
) -> dict:
    """Load DrugBank XML into PostgreSQL."""
    ensure_tables(conn)
    cursor = conn.cursor()

    stats = {
        "drugs_processed": 0,
        "drugs_loaded": 0,
        "interactions_loaded": 0,
        "targets_loaded": 0,
    }

    interaction_batch = []
    target_batch = []

    total_estimate = 17430 if limit is None else min(limit, 17430)

    for drug in tqdm(iter_drugs(xml_path, limit), total=total_estimate, desc="Processing drugs"):
        stats["drugs_processed"] += 1

        if load_drugs:
            try:
                cursor.execute("""
                    INSERT INTO mol_bronze.drugbank_data (
                        drugbank_id, drug_name, drug_type, drug_groups,
                        smiles, inchi_key, cas_number, unii,
                        indication, mechanism_of_action, half_life,
                        pubchem_cid, chembl_id, molecular_weight, molecular_formula
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (drugbank_id) DO UPDATE SET
                        drug_name = EXCLUDED.drug_name,
                        smiles = COALESCE(EXCLUDED.smiles, mol_bronze.drugbank_data.smiles),
                        source_updated_at = NOW()
                """, (
                    drug.drugbank_id, drug.name, drug.drug_type, drug.groups or None,
                    drug.smiles or None, drug.inchi_key or None, drug.cas_number or None,
                    drug.unii or None, drug.indication or None, drug.mechanism_of_action or None,
                    drug.half_life or None, drug.pubchem_cid or None, drug.chembl_id or None,
                    drug.molecular_weight, drug.molecular_formula or None,
                ))
                stats["drugs_loaded"] += 1
            except Exception as e:
                logger.warning(f"Failed to insert drug {drug.drugbank_id}: {e}")
                conn.rollback()

        if load_interactions and drug.drug_interactions:
            for other_id, other_name, description in drug.drug_interactions:
                interaction_batch.append((
                    drug.drugbank_id, other_id, drug.name, other_name,
                    description[:5000] if description else None,
                ))

            if len(interaction_batch) >= batch_size:
                execute_values(cursor, """
                    INSERT INTO mol_bronze.drugbank_interactions (
                        drugbank_id_1, drugbank_id_2, drug_name_1, drug_name_2, interaction_description
                    ) VALUES %s
                    ON CONFLICT (drugbank_id_1, drugbank_id_2) DO UPDATE SET
                        interaction_description = EXCLUDED.interaction_description
                """, interaction_batch)
                stats["interactions_loaded"] += len(interaction_batch)
                interaction_batch = []
                conn.commit()

        if load_targets and drug.targets:
            for target in drug.targets:
                if target.uniprot_id:
                    target_batch.append((
                        drug.drugbank_id, target.target_id, target.name, target.organism,
                        target.uniprot_id, target.gene_name or None, target.actions or None,
                        target.known_action or None,
                    ))

            if len(target_batch) >= batch_size:
                seen_keys = set()
                deduped = []
                for t in target_batch:
                    key = (t[0], t[4])
                    if key not in seen_keys:
                        seen_keys.add(key)
                        deduped.append(t)
                execute_values(cursor, """
                    INSERT INTO mol_bronze.drugbank_targets (
                        drugbank_id, target_id, target_name, organism,
                        uniprot_id, gene_name, actions, known_action
                    ) VALUES %s
                    ON CONFLICT (drugbank_id, uniprot_id) DO UPDATE SET
                        target_name = EXCLUDED.target_name
                """, deduped)
                stats["targets_loaded"] += len(deduped)
                target_batch = []
                conn.commit()

        if stats["drugs_processed"] % 1000 == 0:
            conn.commit()

    # Insert remaining batches
    if interaction_batch:
        execute_values(cursor, """
            INSERT INTO mol_bronze.drugbank_interactions (
                drugbank_id_1, drugbank_id_2, drug_name_1, drug_name_2, interaction_description
            ) VALUES %s
            ON CONFLICT (drugbank_id_1, drugbank_id_2) DO UPDATE SET
                interaction_description = EXCLUDED.interaction_description
        """, interaction_batch)
        stats["interactions_loaded"] += len(interaction_batch)

    if target_batch:
        seen_keys = set()
        deduped = []
        for t in target_batch:
            key = (t[0], t[4])
            if key not in seen_keys:
                seen_keys.add(key)
                deduped.append(t)
        execute_values(cursor, """
            INSERT INTO mol_bronze.drugbank_targets (
                drugbank_id, target_id, target_name, organism,
                uniprot_id, gene_name, actions, known_action
            ) VALUES %s
            ON CONFLICT (drugbank_id, uniprot_id) DO UPDATE SET
                target_name = EXCLUDED.target_name
        """, deduped)
        stats["targets_loaded"] += len(deduped)

    conn.commit()
    return stats


def main():
    parser = argparse.ArgumentParser(description="Load DrugBank XML into PostgreSQL")
    parser.add_argument("--xml", type=str, required=True, help="Path to DrugBank XML file")
    parser.add_argument("--drugs-only", action="store_true", help="Only load drug information")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of drugs")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size for inserts")
    args = parser.parse_args()

    load_drugs = True
    load_interactions = not args.drugs_only
    load_targets = not args.drugs_only

    logger.info(f"Loading DrugBank from: {args.xml}")

    xml_path = Path(args.xml)
    if not xml_path.exists():
        logger.error(f"XML file not found: {xml_path}")
        sys.exit(1)

    conn = psycopg2.connect(**DB_CONFIG)

    try:
        stats = load_drugbank(
            str(xml_path), conn,
            load_drugs=load_drugs,
            load_interactions=load_interactions,
            load_targets=load_targets,
            limit=args.limit,
            batch_size=args.batch_size,
        )
        logger.info(f"Load statistics: {stats}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
