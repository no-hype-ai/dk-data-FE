"""CMS Cost Reports PUF loader. Loads to hcs_hcs_raw.cms_cost_reports_puf.

NOTE: This is distinct from the existing cms_cost_reports.py which targets hcs_raw.cms_cost_reports.
This loader targets hcs_hcs_raw.cms_cost_reports_puf as part of the PUF ingestion pipeline.
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSCostReportsPUFRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'RPT_REC_NUM': 'rpt_rec_num',
    'PRVDR_CTRL_TYPE_CD': 'prvdr_ctrl_type_cd',
    'PRVDR_NUM': 'prvdr_num',
    'RPT_STUS_CD': 'rpt_stus_cd',
    'INITL_RPT_SW': 'initl_rpt_sw',
    'LAST_RPT_SW': 'last_rpt_sw',
    'TRNSMTL_NUM': 'trnsmtl_num',
    'FI_NUM': 'fi_num',
    'ADR_VNDR_CD': 'adr_vndr_cd',
    'FI_CREAT_DT': 'fi_creat_dt',
    'UTIL_CD': 'util_cd',
    'NPR_DT': 'npr_dt',
    'SPEC_IND': 'spec_ind',
    'FI_RCPT_DT': 'fi_rcpt_dt',
    'TOTAL_BEDS': 'total_beds',
    'TOTAL_DISCHARGES': 'total_discharges',
    'NET_PATIENT_REVENUE': 'net_patient_revenue',
    'TOTAL_OPERATING_EXPENSES': 'total_operating_expenses',
    # lower-case variants
    'rpt_rec_num': 'rpt_rec_num',
    'prvdr_num': 'prvdr_num',
}

TABLE = 'cms_cost_reports_puf'
SCHEMA = 'hcs_raw'


def load_cms_cost_reports_puf(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Cost Reports PUF data from CSV file."""
    logger.info(f"Loading CMS Cost Reports PUF from {filepath} (year={source_year})")

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
            rec = CMSCostReportsPUFRecord(
                rpt_rec_num=row.get('rpt_rec_num'),
                prvdr_ctrl_type_cd=row.get('prvdr_ctrl_type_cd'),
                prvdr_num=row.get('prvdr_num'),
                rpt_stus_cd=row.get('rpt_stus_cd'),
                initl_rpt_sw=row.get('initl_rpt_sw'),
                last_rpt_sw=row.get('last_rpt_sw'),
                trnsmtl_num=row.get('trnsmtl_num'),
                fi_num=row.get('fi_num'),
                adr_vndr_cd=row.get('adr_vndr_cd'),
                fi_creat_dt=row.get('fi_creat_dt'),
                util_cd=row.get('util_cd'),
                npr_dt=row.get('npr_dt'),
                spec_ind=row.get('spec_ind'),
                fi_rcpt_dt=row.get('fi_rcpt_dt'),
                total_beds=int(row['total_beds']) if row.get('total_beds') else None,
                total_discharges=int(row['total_discharges']) if row.get('total_discharges') else None,
                net_patient_revenue=row.get('net_patient_revenue') or None,
                total_operating_expenses=row.get('total_operating_expenses') or None,
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
        conflict_columns=['rpt_rec_num', '_source_year'],
        update_columns=['rpt_stus_cd', 'total_beds', 'total_discharges',
                        'net_patient_revenue', 'total_operating_expenses', '_loaded_at'],
    )

    logger.info(f"Cost Reports PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
