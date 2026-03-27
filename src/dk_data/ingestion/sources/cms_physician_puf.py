"""CMS Physician and Other Practitioners PUF loader. Loads to hcs_raw.cms_physician_puf."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSPhysicianPUFRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'Rndrng_NPI': 'npi',
    'Rndrng_Prvdr_Last_Org_Name': 'provider_last_name',
    'Rndrng_Prvdr_First_Name': 'provider_first_name',
    'Rndrng_Prvdr_Crdntls': 'provider_credentials',
    'Rndrng_Prvdr_Gndr': 'provider_gender',
    'Rndrng_Prvdr_Ent_Cd': 'provider_entity_type',
    'Rndrng_Prvdr_St1': 'provider_street_address_1',
    'Rndrng_Prvdr_City': 'provider_city',
    'Rndrng_Prvdr_Zip5': 'provider_zip_code',
    'Rndrng_Prvdr_State_Abrvtn': 'provider_state',
    'Rndrng_Prvdr_Cntry': 'provider_country',
    'Rndrng_Prvdr_Type': 'provider_type',
    'Rndrng_Prvdr_Mdcr_Prtcptg_Ind': 'medicare_participation_indicator',
    'Tot_HCPCS_Cds': 'total_hcpcs_cds',
    'Tot_Srvcs': 'total_services',
    'Tot_Benes': 'total_unique_benes',
    'Tot_Mdcr_Pymt_Amt': 'total_medicare_payment_amt',
    'Tot_Mdcr_Alowd_Amt': 'total_medicare_allowed_amt',
}

TABLE = 'cms_physician_puf'
SCHEMA = 'hcs_raw'


def load_cms_physician_puf(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Physician PUF data from CSV file."""
    logger.info(f"Loading CMS Physician PUF from {filepath} (year={source_year})")

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
            rec = CMSPhysicianPUFRecord(
                npi=row.get('npi'),
                provider_last_name=row.get('provider_last_name'),
                provider_first_name=row.get('provider_first_name'),
                provider_credentials=row.get('provider_credentials'),
                provider_gender=row.get('provider_gender'),
                provider_entity_type=row.get('provider_entity_type'),
                provider_street_address_1=row.get('provider_street_address_1'),
                provider_city=row.get('provider_city'),
                provider_zip_code=row.get('provider_zip_code'),
                provider_state=row.get('provider_state'),
                provider_country=row.get('provider_country'),
                provider_type=row.get('provider_type'),
                medicare_participation_indicator=row.get('medicare_participation_indicator'),
                total_hcpcs_cds=int(row['total_hcpcs_cds']) if row.get('total_hcpcs_cds') else None,
                total_services=row.get('total_services') or None,
                total_unique_benes=int(row['total_unique_benes']) if row.get('total_unique_benes') else None,
                total_medicare_payment_amt=row.get('total_medicare_payment_amt') or None,
                total_medicare_allowed_amt=row.get('total_medicare_allowed_amt') or None,
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
        conflict_columns=['npi', '_source_year'],
        update_columns=['total_services', 'total_unique_benes', 'total_medicare_payment_amt',
                        'total_medicare_allowed_amt', '_loaded_at'],
    )

    logger.info(f"Physician PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
