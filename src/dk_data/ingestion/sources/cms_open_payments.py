"""CMS Open Payments (Sunshine Act) loader. Loads to hcs_raw.cms_open_payments."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSOpenPaymentsRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'Physician_Profile_ID': 'physician_profile_id',
    'Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_Name': 'applicable_manufacturer_or_gpo_name',
    'Total_Amount_of_Payment_USDollars': 'total_amount_of_payment_usdollars',
    'Nature_of_Payment_or_Transfer_of_Value': 'nature_of_payment_or_transfer_of_value',
    'Recipient_State': 'recipient_state',
    'Payment_Publication_Date': 'payment_publication_date',
    'Covered_Recipient_Type': 'covered_recipient_type',
    'Record_ID': 'record_id',
    'Program_Year': 'program_year',
}

TABLE = 'cms_open_payments'
SCHEMA = 'hcs_raw'


def load_cms_open_payments(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Open Payments data from CSV file."""
    logger.info(f"Loading CMS Open Payments from {filepath} (year={source_year})")

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
            rec = CMSOpenPaymentsRecord(
                physician_profile_id=row.get('physician_profile_id'),
                applicable_manufacturer_or_gpo_name=row.get('applicable_manufacturer_or_gpo_name'),
                total_amount_of_payment_usdollars=row.get('total_amount_of_payment_usdollars') or None,
                nature_of_payment_or_transfer_of_value=row.get('nature_of_payment_or_transfer_of_value'),
                recipient_state=row.get('recipient_state'),
                payment_publication_date=row.get('payment_publication_date'),
                covered_recipient_type=row.get('covered_recipient_type'),
                record_id=row.get('record_id'),
                program_year=row.get('program_year'),
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
        conflict_columns=['_source_hash', 'record_id', '_source_year'],
        update_columns=['total_amount_of_payment_usdollars', 'nature_of_payment_or_transfer_of_value', '_loaded_at'],
    )

    logger.info(f"Open Payments load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
