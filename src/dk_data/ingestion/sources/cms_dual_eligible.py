"""CMS Dual Eligible Beneficiary loader. Loads to hcs_raw.cms_dual_eligible."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSDualEligibleRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'State': 'state',
    'State Name': 'state_name',
    'Bene Count': 'bene_count',
    'Full Dual Count': 'full_dual_count',
    'Partial Dual Count': 'partial_dual_count',
    'Medicaid Managed Care Count': 'medicaid_managed_care_count',
    # snake_case variants
    'state': 'state',
    'state_name': 'state_name',
    'bene_count': 'bene_count',
}

TABLE = 'cms_dual_eligible'
SCHEMA = 'hcs_raw'


def load_cms_dual_eligible(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Dual Eligible beneficiary data from CSV file."""
    logger.info(f"Loading CMS Dual Eligible from {filepath} (year={source_year})")

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
            rec = CMSDualEligibleRecord(
                state=row.get('state'),
                state_name=row.get('state_name'),
                bene_count=int(row['bene_count']) if row.get('bene_count') else None,
                full_dual_count=int(row['full_dual_count']) if row.get('full_dual_count') else None,
                partial_dual_count=int(row['partial_dual_count']) if row.get('partial_dual_count') else None,
                medicaid_managed_care_count=int(row['medicaid_managed_care_count']) if row.get('medicaid_managed_care_count') else None,
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
        conflict_columns=['state', '_source_year'],
        update_columns=['bene_count', 'full_dual_count', 'partial_dual_count',
                        'medicaid_managed_care_count', '_loaded_at'],
    )

    logger.info(f"Dual Eligible load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
