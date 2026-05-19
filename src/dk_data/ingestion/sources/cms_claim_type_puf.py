"""CMS Claim Type Utilization PUF loader. Loads to hcs_raw.cms_claim_type_puf.

Dataset: CMS Physician/Supplier Procedure Summary (PSPS) — HCPCS-level pricing
UUID: 164fc736-4179-4100-9f79-592b69e41975

Confirmed API columns (GET /data-api/v1/dataset/{uuid}/data?size=2, 2026-03-29):
  HCPCS_CD, HCPCS_INITIAL_MODIFIER_CD, PROVIDER_SPEC_CD, CARRIER_NUM,
  PRICING_LOCALITY_CD, TYPE_OF_SERVICE_CD, PLACE_OF_SERVICE_CD,
  HCPCS_SECOND_MODIFIER_CD, PSPS_SUBMITTED_SERVICE_CNT,
  PSPS_SUBMITTED_CHARGE_AMT, PSPS_ALLOWED_CHARGE_AMT,
  PSPS_DENIED_SERVICES_CNT, PSPS_DENIED_CHARGE_AMT,
  PSPS_ASSIGNED_SERVICES_CNT, PSPS_NCH_PAYMENT_AMT,
  PSPS_HCPCS_ASC_IND_CD, PSPS_ERROR_IND_CD, HCPCS_BETOS_CD

NOTE: This is a HCPCS procedure-pricing dataset, not a geographic claim-type
summary.  The CMSClaimTypeRecord validator fields are mapped as follows:
  bene_geo_lvl  ← CARRIER_NUM (carrier ID)
  bene_geo_desc ← PRICING_LOCALITY_CD
  clm_type      ← TYPE_OF_SERVICE_CD
  clm_type_desc ← PLACE_OF_SERVICE_CD
  tot_clms      ← PSPS_SUBMITTED_SERVICE_CNT
  tot_mdcr_pymt_amt ← PSPS_NCH_PAYMENT_AMT
  avg_mdcr_pymt_amt ← PSPS_ALLOWED_CHARGE_AMT
  tot_benes is not present (NULL).
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSClaimTypeRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    # Actual PSPS HCPCS-pricing columns mapped to CMSClaimTypeRecord validator fields.
    'CARRIER_NUM':                  'bene_geo_lvl',      # carrier ID → geo level slot
    'PRICING_LOCALITY_CD':          'bene_geo_desc',     # locality code → geo desc slot
    'TYPE_OF_SERVICE_CD':           'clm_type',
    'PLACE_OF_SERVICE_CD':          'clm_type_desc',
    'PSPS_SUBMITTED_SERVICE_CNT':   'tot_clms',
    # tot_benes is not present in this dataset; will be NULL.
    'PSPS_NCH_PAYMENT_AMT':         'tot_mdcr_pymt_amt',
    'PSPS_ALLOWED_CHARGE_AMT':      'avg_mdcr_pymt_amt',
    # Additional columns available but not mapped to existing validator fields:
    # HCPCS_CD, HCPCS_INITIAL_MODIFIER_CD, PROVIDER_SPEC_CD,
    # PSPS_SUBMITTED_CHARGE_AMT, PSPS_DENIED_SERVICES_CNT, etc.
}

TABLE = 'cms_claim_type_puf'
SCHEMA = 'hcs_raw'


def load_cms_claim_type_puf(filepath: Optional[str] = None, rows: Optional[List[Dict]] = None, source_year: int = 2023, max_records: int = 0, source_hash: Optional[str] = None) -> dict:
    """Load CMS Claim Type PUF data from CSV file."""
    logger.info(f"Loading CMS Claim Type PUF (year={source_year})")

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
            rec = CMSClaimTypeRecord(
                bene_geo_lvl=row.get('bene_geo_lvl'),
                bene_geo_desc=row.get('bene_geo_desc'),
                clm_type=row.get('clm_type'),
                clm_type_desc=row.get('clm_type_desc'),
                tot_clms=(lambda v: int(float(str(v).strip())) if pd.notna(v) and str(v).strip() not in ('', '*', '**', '+', '-', 'N/A', '#') else None)(row.get('tot_clms')),
                tot_benes=None,   # not available in PSPS HCPCS-pricing dataset
                tot_mdcr_pymt_amt=row.get('tot_mdcr_pymt_amt') or None,
                avg_mdcr_pymt_amt=row.get('avg_mdcr_pymt_amt') or None,
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
        # bene_geo_lvl=CARRIER_NUM, bene_geo_desc=PRICING_LOCALITY_CD, clm_type=TYPE_OF_SERVICE_CD
        conflict_columns=['bene_geo_lvl', 'clm_type', '_source_year'],
        update_columns=['tot_clms', 'tot_mdcr_pymt_amt', 'avg_mdcr_pymt_amt', '_loaded_at'],
    )

    logger.info(f"Claim Type PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
