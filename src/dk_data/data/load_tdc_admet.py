#!/usr/bin/env python3
"""
Load TDC ADMET benchmark datasets with Y labels into PostgreSQL.

This loader downloads all 22 TDC ADMET benchmark datasets and stores:
1. The Y labels (experimental measurements) for each compound
2. Train/valid/test splits using scaffold splitting
3. Links to existing compounds via InChI Key

Tables populated:
- bronze.tdc_admet_datasets: Dataset metadata
- bronze.tdc_admet_values: Y labels for each compound-dataset pair

Usage:
    python -m dk_data.data.load_tdc_admet
    python -m dk_data.data.load_tdc_admet --datasets caco2_wang hia_hou herg
    python -m dk_data.data.load_tdc_admet --info

Environment:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
"""

import os
import sys
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values
from loguru import logger
from tqdm import tqdm

try:
    from tdc.single_pred import ADME, Tox
except ImportError:
    logger.error("Please install tdc: pip install PyTDC")
    sys.exit(1)

try:
    from rdkit import Chem
    from rdkit.Chem.inchi import MolToInchiKey
except ImportError:
    logger.error("Please install rdkit: pip install rdkit")
    sys.exit(1)

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "dk_data"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
}

TDC_ADMET_DATASETS = {
    # Absorption
    "caco2_wang": ("ADME", "Caco2_Wang", "regression", "Caco-2 permeability (Wang)"),
    "hia_hou": ("ADME", "HIA_Hou", "classification", "Human intestinal absorption"),
    "pgp_broccatelli": ("ADME", "Pgp_Broccatelli", "classification", "P-gp substrate"),
    "bioavailability_ma": ("ADME", "Bioavailability_Ma", "classification", "Oral bioavailability"),

    # Distribution
    "bbb_martins": ("ADME", "BBB_Martins", "classification", "Blood-brain barrier penetration"),
    "ppbr_az": ("ADME", "PPBR_AZ", "regression", "Plasma protein binding rate"),
    "vdss_lombardo": ("ADME", "VDss_Lombardo", "regression", "Volume of distribution"),

    # Metabolism
    "cyp2c9_veith": ("ADME", "CYP2C9_Veith", "classification", "CYP2C9 inhibitor"),
    "cyp2d6_veith": ("ADME", "CYP2D6_Veith", "classification", "CYP2D6 inhibitor"),
    "cyp3a4_veith": ("ADME", "CYP3A4_Veith", "classification", "CYP3A4 inhibitor"),
    "cyp2c9_substrate_carbonmangels": ("ADME", "CYP2C9_Substrate_CarbonMangels", "classification", "CYP2C9 substrate"),
    "cyp2d6_substrate_carbonmangels": ("ADME", "CYP2D6_Substrate_CarbonMangels", "classification", "CYP2D6 substrate"),
    "cyp3a4_substrate_carbonmangels": ("ADME", "CYP3A4_Substrate_CarbonMangels", "classification", "CYP3A4 substrate"),
    "half_life_obach": ("ADME", "Half_Life_Obach", "regression", "Half-life"),
    "clearance_hepatocyte_az": ("ADME", "Clearance_Hepatocyte_AZ", "regression", "Hepatocyte clearance"),
    "clearance_microsome_az": ("ADME", "Clearance_Microsome_AZ", "regression", "Microsome clearance"),

    # Toxicity
    "herg": ("Tox", "hERG", "classification", "hERG channel inhibition"),
    "ames": ("Tox", "AMES", "classification", "Ames mutagenicity"),
    "dili": ("Tox", "DILI", "classification", "Drug-induced liver injury"),
    "ld50_zhu": ("Tox", "LD50_Zhu", "regression", "Acute toxicity LD50"),

    # Physicochemical
    "lipophilicity_astrazeneca": ("ADME", "Lipophilicity_AstraZeneca", "regression", "Lipophilicity (logD)"),
    "solubility_aqsoldb": ("ADME", "Solubility_AqSolDB", "regression", "Aqueous solubility"),
}


def smiles_to_inchi_key(smiles: str) -> Optional[str]:
    """Convert SMILES to InChI Key."""
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        return MolToInchiKey(mol)
    except Exception:
        return None


def ensure_tables(conn):
    """Ensure required tables exist."""
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.tdc_admet_datasets (
            dataset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            dataset_name VARCHAR(100) UNIQUE NOT NULL,
            tdc_name VARCHAR(100) NOT NULL,
            task_type VARCHAR(20) NOT NULL,
            description TEXT,
            num_compounds INTEGER,
            num_train INTEGER,
            num_valid INTEGER,
            num_test INTEGER,
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bronze.tdc_admet_values (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            dataset_id UUID REFERENCES bronze.tdc_admet_datasets(dataset_id),
            inchi_key VARCHAR(27) NOT NULL,
            smiles TEXT NOT NULL,
            y_value DOUBLE PRECISION NOT NULL,
            split VARCHAR(10) NOT NULL,
            drug_id TEXT,
            source_updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            processed_to_silver BOOLEAN DEFAULT FALSE,
            UNIQUE(dataset_id, inchi_key)
        );

        CREATE INDEX IF NOT EXISTS idx_admet_dataset ON bronze.tdc_admet_values(dataset_id);
        CREATE INDEX IF NOT EXISTS idx_admet_inchi ON bronze.tdc_admet_values(inchi_key);
        CREATE INDEX IF NOT EXISTS idx_admet_split ON bronze.tdc_admet_values(split);
    """)

    conn.commit()
    logger.info("TDC ADMET tables ensured")


def load_tdc_dataset(dataset_name: str, conn, split_method: str = "scaffold") -> dict:
    """Load a single TDC ADMET dataset into PostgreSQL."""
    if dataset_name not in TDC_ADMET_DATASETS:
        raise ValueError(f"Unknown dataset: {dataset_name}")

    loader_class, tdc_name, task_type, description = TDC_ADMET_DATASETS[dataset_name]
    logger.info(f"Loading {dataset_name} ({tdc_name}) - {description}")

    if loader_class == "ADME":
        data = ADME(name=tdc_name)
    else:
        data = Tox(name=tdc_name)

    split = data.get_split(method=split_method)

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO bronze.tdc_admet_datasets (dataset_name, tdc_name, task_type, description)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (dataset_name) DO UPDATE SET
            tdc_name = EXCLUDED.tdc_name,
            task_type = EXCLUDED.task_type,
            description = EXCLUDED.description
        RETURNING dataset_id
    """, (dataset_name, tdc_name, task_type, description))
    dataset_id = str(cursor.fetchone()[0])
    conn.commit()

    stats = {"train": 0, "valid": 0, "test": 0, "failed": 0}

    for split_name, df in split.items():
        logger.info(f"  Processing {split_name} split ({len(df)} samples)")

        values_dict = {}
        for _, row in tqdm(df.iterrows(), total=len(df), desc=f"  {split_name}"):
            smiles = row["Drug"]
            y_value = row["Y"]
            drug_id = row.get("Drug_ID", None)

            inchi_key = smiles_to_inchi_key(smiles)
            if inchi_key is None:
                stats["failed"] += 1
                continue

            values_dict[inchi_key] = (
                dataset_id, inchi_key, smiles, float(y_value),
                split_name, str(drug_id) if drug_id else None
            )

        values = list(values_dict.values())

        if values:
            try:
                execute_values(
                    cursor,
                    """
                    INSERT INTO bronze.tdc_admet_values (dataset_id, inchi_key, smiles, y_value, split, drug_id)
                    VALUES %s
                    ON CONFLICT (dataset_id, inchi_key) DO UPDATE SET
                        y_value = EXCLUDED.y_value,
                        split = EXCLUDED.split
                    """,
                    values
                )
                conn.commit()
                stats[split_name] = len(values)
            except Exception as e:
                conn.rollback()
                logger.error(f"  Failed to insert {split_name}: {e}")
                raise

    cursor.execute("""
        UPDATE bronze.tdc_admet_datasets SET
            num_compounds = %s,
            num_train = %s,
            num_valid = %s,
            num_test = %s
        WHERE dataset_id = %s
    """, (
        stats["train"] + stats["valid"] + stats["test"],
        stats["train"], stats["valid"], stats["test"], dataset_id
    ))
    conn.commit()

    logger.info(f"  Loaded: train={stats['train']}, valid={stats['valid']}, test={stats['test']}, failed={stats['failed']}")
    return stats


def show_dataset_info():
    """Show information about all TDC ADMET datasets."""
    print("\n=== TDC ADMET Benchmark Datasets ===\n")
    print(f"{'Dataset':<40} {'Type':<15} {'Description'}")
    print("-" * 90)

    for name, (loader, tdc_name, task_type, desc) in sorted(TDC_ADMET_DATASETS.items()):
        print(f"{name:<40} {task_type:<15} {desc}")

    print(f"\nTotal: {len(TDC_ADMET_DATASETS)} datasets")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Load TDC ADMET benchmark datasets")
    parser.add_argument("--datasets", "-d", nargs="+", help="Specific datasets to load")
    parser.add_argument("--split-method", choices=["scaffold", "random"], default="scaffold")
    parser.add_argument("--info", action="store_true", help="Show dataset information")

    args = parser.parse_args()

    if args.info:
        show_dataset_info()
        return

    logger.info("Connecting to PostgreSQL...")
    conn = psycopg2.connect(**DB_CONFIG)
    logger.info(f"Connected to {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")

    ensure_tables(conn)

    datasets_to_load = args.datasets if args.datasets else list(TDC_ADMET_DATASETS.keys())

    for ds in datasets_to_load:
        if ds not in TDC_ADMET_DATASETS:
            logger.error(f"Unknown dataset: {ds}")
            show_dataset_info()
            sys.exit(1)

    logger.info(f"\n=== Loading {len(datasets_to_load)} TDC ADMET Datasets ===")

    total_stats = {"train": 0, "valid": 0, "test": 0, "failed": 0}

    for dataset_name in datasets_to_load:
        try:
            stats = load_tdc_dataset(dataset_name, conn, args.split_method)
            for key in total_stats:
                total_stats[key] += stats.get(key, 0)
        except Exception as e:
            logger.error(f"Failed to load {dataset_name}: {e}")

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM bronze.tdc_admet_datasets")
    dataset_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM bronze.tdc_admet_values")
    value_count = cursor.fetchone()[0]

    logger.info(f"\n=== Summary ===")
    logger.info(f"Datasets loaded: {dataset_count}")
    logger.info(f"Total ADMET values: {value_count:,}")

    conn.close()


if __name__ == "__main__":
    main()
