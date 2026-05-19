"""CMS Outpatient PUF loader (hospital APC-level charges). Loads to hcs_raw.cms_outpatient_puf."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSOutpatientRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    # Legacy CMS format (pre-2021)
    'Provider Id': 'provider_id',
    'Provider Name': 'provider_name',
    'Provider Street Address': 'provider_street_address',
    'Provider City': 'provider_city',
    'Provider State': 'provider_state',
    'Provider Zip Code': 'provider_zip_code',
    'APC': 'apc',
    'APC Description': 'apc_desc',
    'Outpatient Services': 'total_services',
    'Average Estimated Submitted Charges': 'average_estimated_submitted_charges',
    'Average Total Payments': 'average_total_payments',
    'Average Medicare Payments': 'average_medicare_payments',
    # Current CMS format — confirmed API column names (UUID ccbc9a44, 2026-03-29):
    # Rndrng_Prvdr_CCN, Rndrng_Prvdr_Org_Name, Rndrng_Prvdr_St, Rndrng_Prvdr_City,
    # Rndrng_Prvdr_State_Abrvtn, Rndrng_Prvdr_State_FIPS, Rndrng_Prvdr_Zip5,
    # Rndrng_Prvdr_RUCA, APC_Cd, APC_Desc, Bene_Cnt, CAPC_Srvcs,
    # Avg_Tot_Sbmtd_Chrgs, Avg_Mdcr_Alowd_Amt, Avg_Mdcr_Pymt_Amt
    'Rndrng_Prvdr_Id': 'provider_id',
    'Rndrng_Prvdr_CCN': 'provider_id',
    'Rndrng_Prvdr_Org_Name': 'provider_name',
    'Rndrng_Prvdr_Name': 'provider_name',
    'Rndrng_Prvdr_St': 'provider_street_address',
    'Rndrng_Prvdr_City': 'provider_city',
    'Rndrng_Prvdr_State_Abrvtn': 'provider_state',
    'Rndrng_Prvdr_State_FIPS': 'provider_state_fips',
    'Rndrng_Prvdr_Zip5': 'provider_zip_code',
    'Rndrng_Prvdr_RUCA': 'provider_ruca',
    'APC_Cd': 'apc',
    'APC_Desc': 'apc_desc',
    'Bene_Cnt': 'bene_cnt',
    'Comp_Asgn_Pymt_Cnt': 'comp_asgn_pymt_cnt',   # older dataset variant
    'Tot_Srvcs': 'total_services',                 # older dataset variant
    'CAPC_Srvcs': 'total_services',                # confirmed API column (UUID ccbc9a44)
    'Avg_Submtd_Cvrd_Chrg': 'average_estimated_submitted_charges',   # older variant
    'Avg_Tot_Sbmtd_Chrgs': 'average_estimated_submitted_charges',    # confirmed API column
    'Avg_Mdcr_Alowd_Amt': 'average_medicare_allowed_amt',
    'Avg_Mdcr_Pymt_Amt': 'average_medicare_payments',
    'Avg_Mdcr_Stdzd_Amt': 'average_medicare_stnd_amt',
    'Avg_Tot_Pymt_Amt': 'average_total_payments',
}

TABLE = 'cms_outpatient_puf'
SCHEMA = 'hcs_raw'


def load_cms_outpatient_puf(filepath: Optional[str] = None, rows: Optional[List[Dict]] = None, source_year: int = 2023, max_records: int = 0, source_hash: Optional[str] = None) -> dict:
    """Load CMS Outpatient PUF charge data from CSV file."""
    logger.info(f"Loading CMS Outpatient PUF (year={source_year})")

    if rows is not None:
        # Streaming mode: rows passed directly from API, no file needed
        normalized = [{k: ('' if v is None else str(v)) for k, v in row.items()} for row in rows]
        df = pd.DataFrame(normalized) if normalized else pd.DataFrame()
        _source_hash = source_hash or f"api_stream_{source_year}"
        source_file = f"api_stream_{source_year}"
    else:
        if filepath is None:
            raise ValueError("Either filepath or rows must be provided")
        source_file = Path(filepath).name
        hash_md5 = hashlib.md5()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_md5.update(chunk)
        _source_hash = source_hash or hash_md5.hexdigest()

        with get_cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM {SCHEMA}.{TABLE} WHERE _source_hash = %s",
                (_source_hash,)
            )
            if cur.fetchone()[0] > 0:
                logger.info(f"File {source_file} already loaded. Skipping.")
                return {"status": "skipped", "records_fetched": 0, "records_inserted": 0, "records_updated": 0, "errors": []}

        df = pd.read_csv(filepath, dtype=str, low_memory=False, nrows=max_records if max_records > 0 else None)

    df = apply_column_mapping(df, COLUMN_MAPPING)
    records_fetched = len(df)

    records = []
    errors = []
    loaded_at = datetime.now(timezone.utc).isoformat()

    for idx, row in df.iterrows():
        try:
            rec = CMSOutpatientRecord(
                provider_id=row.get('provider_id'),
                provider_name=row.get('provider_name'),
                provider_street_address=row.get('provider_street_address'),
                provider_city=row.get('provider_city'),
                provider_state=row.get('provider_state'),
                provider_state_fips=row.get('provider_state_fips'),
                provider_zip_code=row.get('provider_zip_code'),
                provider_ruca=row.get('provider_ruca'),
                apc=row.get('apc'),
                apc_desc=row.get('apc_desc'),
                total_services=int(float(row['total_services'])) if pd.notna(row.get('total_services')) else None,
                bene_cnt=int(float(row['bene_cnt'])) if pd.notna(row.get('bene_cnt')) else None,
                comp_asgn_pymt_cnt=int(float(row['comp_asgn_pymt_cnt'])) if pd.notna(row.get('comp_asgn_pymt_cnt')) else None,
                average_estimated_submitted_charges=row.get('average_estimated_submitted_charges') or None,
                average_medicare_allowed_amt=row.get('average_medicare_allowed_amt') or None,
                average_total_payments=row.get('average_total_payments') or None,
                average_medicare_payments=row.get('average_medicare_payments') or None,
                average_medicare_stnd_amt=row.get('average_medicare_stnd_amt') or None,
                _source_year=source_year,
            )
            d = rec.model_dump(by_alias=True)
            d['_source_hash'] = _source_hash
            d['_source_file'] = source_file
            d['_loaded_at'] = loaded_at
            d['_source_year'] = source_year
            records.append(d)
        except (ValidationError, Exception) as e:
            errors.append(f"Row {idx}: {e}")

    inserted = upsert_records(
        SCHEMA, TABLE, records,
        conflict_columns=['_source_hash', 'provider_id', 'apc', '_source_year'],
        update_columns=['total_services', 'bene_cnt', 'comp_asgn_pymt_cnt',
                        'average_estimated_submitted_charges', 'average_medicare_allowed_amt',
                        'average_total_payments', 'average_medicare_payments',
                        'average_medicare_stnd_amt', '_loaded_at'],
    )

    logger.info(f"Outpatient PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
