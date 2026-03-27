"""CMS Medicaid Drug Spending loader. Loads to hcs_raw.cms_medicaid_drug_spending."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSMedicaidDrugSpendingRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'Drug Name': 'drug_name',
    'State': 'state',
    'Labeler Code': 'labeler_code',
    'Product Code': 'product_code',
    'Package Size': 'package_size_code',
    'NDC': 'ndc',
    'Units Reimbursed': 'units_reimbursed',
    'Number of Prescriptions': 'number_of_prescriptions',
    'Total Amount Reimbursed': 'total_amount_reimbursed',
    'Medicaid Amount Reimbursed': 'medicaid_amount_reimbursed',
    'Non Medicaid Amount Reimbursed': 'non_medicaid_amount_reimbursed',
    'Quarter': 'quarter',
    # snake_case variants
    'drug_name': 'drug_name',
    'state': 'state',
    'ndc': 'ndc',
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
    df = df.rename(columns=COLUMN_MAPPING)
    records_fetched = len(df)

    records = []
    errors = []
    loaded_at = datetime.now(timezone.utc).isoformat()

    for idx, row in df.iterrows():
        try:
            rec = CMSMedicaidDrugSpendingRecord(
                drug_name=row.get('drug_name'),
                state=row.get('state'),
                labeler_code=row.get('labeler_code'),
                product_code=row.get('product_code'),
                package_size_code=row.get('package_size_code'),
                ndc=row.get('ndc'),
                units_reimbursed=row.get('units_reimbursed') or None,
                number_of_prescriptions=int(row['number_of_prescriptions']) if row.get('number_of_prescriptions') else None,
                total_amount_reimbursed=row.get('total_amount_reimbursed') or None,
                medicaid_amount_reimbursed=row.get('medicaid_amount_reimbursed') or None,
                non_medicaid_amount_reimbursed=row.get('non_medicaid_amount_reimbursed') or None,
                quarter=row.get('quarter'),
                _source_year=source_year,
            )
            d = rec.model_dump(by_alias=True)
            d['_source_hash'] = source_hash
            d['_source_file'] = source_file
            d['_loaded_at'] = loaded_at
            records.append(d)
        except (ValidationError, Exception) as e:
            errors.append(f"Row {idx}: {e}")

    inserted = upsert_records(
        SCHEMA, TABLE, records,
        conflict_columns=['_source_hash', 'ndc', 'state', '_source_year'],
        update_columns=['units_reimbursed', 'number_of_prescriptions', 'total_amount_reimbursed', '_loaded_at'],
    )

    logger.info(f"Medicaid Drug Spending load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
