#!/usr/bin/env python3
"""
Load TDC (Therapeutics Data Commons) datasets into PostgreSQL.

This script:
1. Downloads TDC ADMET datasets
2. Calculates molecular features (RDKit descriptors)
3. Loads compounds and experimental data into the database

Tables populated:
- bronze.tdc_datasets: Dataset metadata
- bronze.tdc_compounds: Compound data with labels
- bronze.compounds: Shared compounds table with descriptors

Usage:
    python -m dk_data.data.load_tdc_data

Environment:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
"""

import os
import sys
import argparse

import psycopg2
from loguru import logger
from tqdm import tqdm

try:
    from tdc.single_pred import ADME, Tox
    TDC_AVAILABLE = True
except ImportError:
    TDC_AVAILABLE = False

try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, AllChem, MACCSkeys, DataStructs
    from rdkit.Chem import QED
    import numpy as np
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "dk_data"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

TDC_DATASETS = {
    "absorption": [
        ("Caco2_Wang", "regression"),
        ("HIA_Hou", "classification"),
        ("Pgp_Broccatelli", "classification"),
        ("Bioavailability_Ma", "classification"),
        ("Lipophilicity_AstraZeneca", "regression"),
        ("Solubility_AqSolDB", "regression"),
    ],
    "distribution": [
        ("PPBR_AZ", "regression"),
        ("VDss_Lombardo", "regression"),
        ("BBB_Martins", "classification"),
    ],
    "metabolism": [
        ("CYP2C9_Veith", "classification"),
        ("CYP2D6_Veith", "classification"),
        ("CYP3A4_Veith", "classification"),
        ("Half_Life_Obach", "regression"),
        ("Clearance_Hepatocyte_AZ", "regression"),
    ],
    "toxicity": [
        ("hERG", "classification"),
        ("AMES", "classification"),
        ("DILI", "classification"),
        ("LD50_Zhu", "regression"),
    ],
}


def calculate_descriptors(smiles: str) -> dict | None:
    """Calculate RDKit descriptors for a SMILES string."""
    if not RDKIT_AVAILABLE:
        return None

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None

    try:
        desc = {
            "smiles_canonical": Chem.MolToSmiles(mol, canonical=True),
            "inchi_key": Chem.MolToInchiKey(mol),
            "molecular_weight": Descriptors.MolWt(mol),
            "logp": Descriptors.MolLogP(mol),
            "tpsa": Descriptors.TPSA(mol),
            "hbd": Descriptors.NumHDonors(mol),
            "hba": Descriptors.NumHAcceptors(mol),
            "rotatable_bonds": Descriptors.NumRotatableBonds(mol),
            "num_rings": Descriptors.RingCount(mol),
            "qed": QED.qed(mol),
        }

        morgan_fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)
        morgan_arr = np.zeros(2048, dtype=np.int8)
        DataStructs.ConvertToNumpyArray(morgan_fp, morgan_arr)
        desc["morgan_fp"] = morgan_arr.tolist()

        maccs_fp = MACCSkeys.GenMACCSKeys(mol)
        maccs_arr = np.zeros(167, dtype=np.int8)
        DataStructs.ConvertToNumpyArray(maccs_fp, maccs_arr)
        desc["maccs_fp"] = maccs_arr.tolist()

        return desc
    except Exception as e:
        logger.warning(f"Descriptor calculation failed for {smiles}: {e}")
        return None


def ensure_tables(conn):
    """Ensure TDC tables exist."""
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.compounds (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            smiles TEXT,
            smiles_canonical TEXT,
            inchi_key VARCHAR(27) UNIQUE,
            molecular_weight DOUBLE PRECISION,
            logp DOUBLE PRECISION,
            tpsa DOUBLE PRECISION,
            hbd INTEGER,
            hba INTEGER,
            rotatable_bonds INTEGER,
            num_rings INTEGER,
            qed DOUBLE PRECISION,
            morgan_fp INTEGER[],
            maccs_fp INTEGER[],
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_compounds_inchi ON bronze.compounds(inchi_key);
        CREATE INDEX IF NOT EXISTS idx_compounds_smiles ON bronze.compounds(smiles_canonical);
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.tdc_datasets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            dataset_name VARCHAR(100) UNIQUE NOT NULL,
            category VARCHAR(50),
            task_type VARCHAR(20),
            n_compounds INTEGER,
            n_train INTEGER,
            n_valid INTEGER,
            n_test INTEGER,
            split_method VARCHAR(50),
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.tdc_compounds (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            dataset_id UUID REFERENCES bronze.tdc_datasets(id),
            compound_id UUID REFERENCES bronze.compounds(id),
            smiles TEXT,
            label DOUBLE PRECISION,
            split VARCHAR(10),
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            processed_to_silver BOOLEAN DEFAULT FALSE
        );

        CREATE INDEX IF NOT EXISTS idx_tdc_compounds_dataset ON bronze.tdc_compounds(dataset_id);
        CREATE INDEX IF NOT EXISTS idx_tdc_compounds_compound ON bronze.tdc_compounds(compound_id);
    """)

    conn.commit()
    logger.info("TDC tables ensured")


def get_or_create_compound(cursor, smiles: str, descriptors: dict) -> str | None:
    """Get existing compound ID or create new one."""
    if descriptors is None:
        return None

    inchi_key = descriptors.get("inchi_key")

    cursor.execute("SELECT id FROM bronze.compounds WHERE inchi_key = %s", (inchi_key,))
    result = cursor.fetchone()
    if result:
        return str(result[0])

    cursor.execute("""
        INSERT INTO bronze.compounds (
            smiles, smiles_canonical, inchi_key,
            molecular_weight, logp, tpsa, hbd, hba,
            rotatable_bonds, num_rings, qed, morgan_fp, maccs_fp
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        smiles, descriptors["smiles_canonical"], inchi_key,
        descriptors["molecular_weight"], descriptors["logp"], descriptors["tpsa"],
        descriptors["hbd"], descriptors["hba"], descriptors["rotatable_bonds"],
        descriptors["num_rings"], descriptors["qed"],
        descriptors["morgan_fp"], descriptors["maccs_fp"],
    ))
    return str(cursor.fetchone()[0])


def load_tdc_dataset(conn, category: str, dataset_name: str, task_type: str):
    """Load a single TDC dataset into the database."""
    logger.info(f"Loading TDC dataset: {dataset_name} ({category})")

    cursor = conn.cursor()

    cursor.execute("SELECT id FROM bronze.tdc_datasets WHERE dataset_name = %s", (dataset_name,))
    existing = cursor.fetchone()
    if existing:
        logger.info(f"  Dataset {dataset_name} already loaded, skipping")
        return

    try:
        if category == "toxicity":
            data = Tox(name=dataset_name)
        else:
            data = ADME(name=dataset_name)

        split = data.get_split(method="scaffold")

        cursor.execute("""
            INSERT INTO bronze.tdc_datasets (
                dataset_name, category, task_type,
                n_compounds, n_train, n_valid, n_test, split_method
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            dataset_name, category, task_type,
            len(split["train"]) + len(split["valid"]) + len(split["test"]),
            len(split["train"]), len(split["valid"]), len(split["test"]), "scaffold",
        ))
        dataset_id = str(cursor.fetchone()[0])

        compounds_added = 0
        compounds_failed = 0

        for split_name, df in split.items():
            logger.info(f"  Processing {split_name} split: {len(df)} compounds")

            for _, row in tqdm(df.iterrows(), total=len(df), desc=f"    {split_name}"):
                smiles = row["Drug"]
                label = row["Y"]

                descriptors = calculate_descriptors(smiles)
                if descriptors is None:
                    compounds_failed += 1
                    continue

                try:
                    compound_id = get_or_create_compound(cursor, smiles, descriptors)

                    cursor.execute("""
                        INSERT INTO bronze.tdc_compounds (
                            dataset_id, compound_id, smiles, label, split
                        ) VALUES (%s, %s, %s, %s, %s)
                    """, (dataset_id, compound_id, smiles, float(label), split_name))

                    compounds_added += 1
                except Exception as e:
                    conn.rollback()
                    logger.warning(f"    Failed to insert compound: {e}")
                    compounds_failed += 1
                    continue

            conn.commit()

        logger.info(f"  Completed {dataset_name}: {compounds_added} added, {compounds_failed} failed")

    except Exception as e:
        logger.error(f"Failed to load {dataset_name}: {e}")
        conn.rollback()


def main():
    parser = argparse.ArgumentParser(description="Load TDC datasets into PostgreSQL")
    parser.add_argument("--category", type=str, help="Only load specific category")
    parser.add_argument("--dataset", type=str, help="Only load specific dataset")
    args = parser.parse_args()

    if not TDC_AVAILABLE:
        logger.error("TDC not installed. Install with: pip install PyTDC")
        sys.exit(1)

    if not RDKIT_AVAILABLE:
        logger.error("RDKit not installed. Install with: pip install rdkit")
        sys.exit(1)

    logger.info("Starting TDC data loading")

    conn = psycopg2.connect(**DB_CONFIG)
    ensure_tables(conn)

    for category, datasets in TDC_DATASETS.items():
        if args.category and category != args.category:
            continue

        logger.info(f"\n=== Category: {category.upper()} ===")
        for dataset_name, task_type in datasets:
            if args.dataset and dataset_name != args.dataset:
                continue
            load_tdc_dataset(conn, category, dataset_name, task_type)

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM bronze.compounds")
    n_compounds = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM bronze.tdc_datasets")
    n_datasets = cursor.fetchone()[0]

    logger.info("\n=== SUMMARY ===")
    logger.info(f"Datasets loaded: {n_datasets}")
    logger.info(f"Compounds in database: {n_compounds}")

    conn.close()


if __name__ == "__main__":
    main()
