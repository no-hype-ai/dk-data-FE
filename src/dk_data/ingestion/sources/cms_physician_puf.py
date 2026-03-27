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
    # Current CMS format (post-2020) — maps to raw table column names
    'Rndrng_NPI': 'npi',
    'Rndrng_Prvdr_Last_Org_Name': 'nppes_provider_last_org_name',
    'Rndrng_Prvdr_First_Name': 'nppes_provider_first_name',
    'Rndrng_Prvdr_MI': 'nppes_provider_mi',
    'Rndrng_Prvdr_Crdntls': 'nppes_credentials',
    'Rndrng_Prvdr_Gndr': 'nppes_provider_gender',
    'Rndrng_Prvdr_Ent_Cd': 'nppes_entity_code',
    'Rndrng_Prvdr_St1': 'nppes_provider_street1',
    'Rndrng_Prvdr_St2': 'nppes_provider_street2',
    'Rndrng_Prvdr_City': 'nppes_provider_city',
    'Rndrng_Prvdr_State_Abrvtn': 'nppes_provider_state',
    'Rndrng_Prvdr_State_FIPS': 'nppes_provider_state_fips',
    'Rndrng_Prvdr_Zip5': 'nppes_provider_zip',
    'Rndrng_Prvdr_RUCA': 'nppes_provider_ruca',
    'Rndrng_Prvdr_Cntry': 'nppes_provider_country',
    'Rndrng_Prvdr_Type': 'provider_type',
    'Rndrng_Prvdr_Mdcr_Prtcptg_Ind': 'medicare_participation_indicator',
    # Summary metrics (NPI-grain aggregate file)
    'Tot_HCPCS_Cds': 'number_of_hcpcs',
    'Tot_Srvcs': 'total_services',
    'Tot_Benes': 'total_unique_benes',
    'Tot_Sbmtd_Chrg': 'total_submitted_chrg_amt',
    'Tot_Mdcr_Alowd_Amt': 'total_medicare_allowed_amt',
    'Tot_Mdcr_Pymt_Amt': 'total_medicare_payment_amt',
    'Tot_Mdcr_Stdzd_Amt': 'total_medicare_stnd_amt',
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
                nppes_provider_last_org_name=row.get('nppes_provider_last_org_name'),
                nppes_provider_first_name=row.get('nppes_provider_first_name'),
                nppes_provider_mi=row.get('nppes_provider_mi'),
                nppes_credentials=row.get('nppes_credentials'),
                nppes_provider_gender=row.get('nppes_provider_gender'),
                nppes_entity_code=row.get('nppes_entity_code'),
                nppes_provider_street1=row.get('nppes_provider_street1'),
                nppes_provider_street2=row.get('nppes_provider_street2'),
                nppes_provider_city=row.get('nppes_provider_city'),
                nppes_provider_state=row.get('nppes_provider_state'),
                nppes_provider_state_fips=row.get('nppes_provider_state_fips'),
                nppes_provider_zip=row.get('nppes_provider_zip'),
                nppes_provider_ruca=row.get('nppes_provider_ruca'),
                nppes_provider_country=row.get('nppes_provider_country'),
                provider_type=row.get('provider_type'),
                medicare_participation_indicator=row.get('medicare_participation_indicator'),
                number_of_hcpcs=int(row['number_of_hcpcs']) if row.get('number_of_hcpcs') else None,
                total_services=row.get('total_services') or None,
                total_unique_benes=int(row['total_unique_benes']) if row.get('total_unique_benes') else None,
                total_submitted_chrg_amt=row.get('total_submitted_chrg_amt') or None,
                total_medicare_allowed_amt=row.get('total_medicare_allowed_amt') or None,
                total_medicare_payment_amt=row.get('total_medicare_payment_amt') or None,
                total_medicare_stnd_amt=row.get('total_medicare_stnd_amt') or None,
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
        update_columns=['total_services', 'total_unique_benes', 'total_submitted_chrg_amt',
                        'total_medicare_allowed_amt', 'total_medicare_payment_amt',
                        'total_medicare_stnd_amt', '_loaded_at'],
    )

    logger.info(f"Physician PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
