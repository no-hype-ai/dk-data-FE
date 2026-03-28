"""CMS Medicaid Drug Spending loader. Loads to hcs_raw.cms_medicaid_drug_spending."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSMedicaidDrugSpendingRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'Brnd_Name': 'brnd_name',
    'Gnrc_Name': 'gnrc_name',
    'Tot_Mftr': 'tot_mftr',
    'Util_Type': 'util_type',
    'Tot_Spndng': 'tot_spndng',
    'Medicaid_Spndng_Per_Dosage_Unit': 'medicaid_spndng_per_dosage_unit',
    'Medicaid_Spndng_Per_Prescription': 'medicaid_spndng_per_prescription',
    'Unit_Type': 'unit_type',
    'Tot_Dosage_Units': 'tot_dosage_units',
    'Tot_Prescriptions': 'tot_prescriptions',
    'Tot_Benes': 'tot_benes',
    # snake_case variants that CMS sometimes ships
    'brnd_name': 'brnd_name',
    'gnrc_name': 'gnrc_name',
}

TABLE = 'cms_medicaid_drug_spending'
SCHEMA = 'hcs_raw'


def load_cms_medicaid_drug_spending(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Medicaid Drug Spending data from CSV file."""
    logger.info(f"Loading CMS Medicaid Drug Spending from {filepath} (year={source_year})")

    source_file = Path(filepath).name
    hash_md5 = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    source_hash = hash_md5.hexdigest()

    with get_cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) FROM {SCHEMA}.{TABLE} WHERE _source_hash = %s",
            (source_hash,)
        )
        if cur.fetchone()[0] > 0:
            logger.info(f"File {source_file} already loaded. Skipping.")
            return {"status": "skipped", "records_fetched": 0, "records_inserted": 0, "records_updated": 0, "errors": []}

    df = pd.read_csv(filepath, dtype=str, low_memory=False)
    df = apply_column_mapping(df, COLUMN_MAPPING)
    records_fetched = len(df)

    records = []
    errors = []
    loaded_at = datetime.now(timezone.utc).isoformat()

    for idx, row in df.iterrows():
        try:
            rec = CMSMedicaidDrugSpendingRecord(
                brnd_name=row.get('brnd_name'),
                gnrc_name=row.get('gnrc_name'),
                tot_mftr=row.get('tot_mftr'),
                util_type=row.get('util_type'),
                tot_spndng=row.get('tot_spndng') or None,
                medicaid_spndng_per_dosage_unit=row.get('medicaid_spndng_per_dosage_unit') or None,
                medicaid_spndng_per_prescription=row.get('medicaid_spndng_per_prescription') or None,
                unit_type=row.get('unit_type'),
                tot_dosage_units=row.get('tot_dosage_units') or None,
                tot_prescriptions=row.get('tot_prescriptions') or None,
                tot_benes=row.get('tot_benes') or None,
                _source_year=source_year,
            )
            d = rec.model_dump(by_alias=True)
            d['_source_hash'] = source_hash
            d['_source_file'] = source_file
            d['_loaded_at'] = loaded_at
            d['_source_year'] = source_year
            records.append(d)
        except (ValidationError, Exception) as e:
            errors.append(f"Row {idx}: {e}")

    inserted = upsert_records(
        SCHEMA, TABLE, records,
        conflict_columns=['gnrc_name', 'util_type', '_source_year'],
        update_columns=['tot_prescriptions', 'tot_spndng', '_loaded_at'],
    )

    logger.info(f"Medicaid Drug Spending load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
