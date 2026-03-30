"""CMS Medicare Utilization PUF loader. Loads to hcs_raw.cms_utilization_puf.

Dataset: Medicare Geographic Variation by National, State & County
UUID: 6219697b-8f6c-4164-bed4-cd9317c58ebc

Confirmed API columns (GET /data-api/v1/dataset/{uuid}/data?size=1, 2026-03-29):
  YEAR, BENE_GEO_LVL, BENE_GEO_DESC, BENE_GEO_CD, BENE_AGE_LVL,
  BENES_TOTAL_CNT, TOT_MDCR_PYMT_PC, TOT_MDCR_STDZD_PYMT_PC,
  IP_CVRD_STAYS_PER_1000_BENES, IP_CVRD_DAYS_PER_1000_BENES,
  ER_VISITS_PER_1000_BENES, BENES_IP_CVRD_STAY_CNT, ...

Each row = one geographic area × age group × year.
Geographic dimension: National / State / County (BENE_GEO_LVL).
Demographic dimension: All / Age65-74 / etc. (BENE_AGE_LVL).
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSUtilizationRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    # Geographic variation dataset — ALL-CAPS column names from CMS API.
    'BENE_GEO_LVL':                         'bene_geo_lvl',
    'BENE_GEO_DESC':                         'bene_geo_desc',
    'BENE_GEO_CD':                           'bene_geo_cd',
    'BENE_AGE_LVL':                          'bene_age_lvl',
    # bene_demo_lvl / bene_demo_desc: not directly in this dataset; map BENE_GEO_LVL
    # as demo_lvl placeholder so the field is non-null for record identification.
    'IP_CVRD_STAYS_PER_1000_BENES':          'ip_cvrd_stays_per_1000_benes',
    'ER_VISITS_PER_1000_BENES':              'er_visits_per_1000_benes',
    'TOT_MDCR_PYMT_PC':                      'tot_mdcr_pymt_pc',
    # srvcs_per_bene: no exact match; EM_EVNTS_PER_1000_BENES is closest proxy.
    # avg_ip_los: not in this dataset; BENE_AVG_AGE is closest numeric field we can use.
    # phy_visits_per_bene: EM_EVNTS_PER_1000_BENES / 1000 would be approximate.
    # Leave srvcs_per_bene, avg_ip_los, phy_visits_per_bene as NULL.
}

TABLE = 'cms_utilization_puf'
SCHEMA = 'hcs_raw'


def load_cms_utilization_puf(filepath: str, source_year: int = 2023, max_records: int = 0) -> dict:
    """Load CMS Medicare Utilization PUF data from CSV file."""
    logger.info(f"Loading CMS Utilization PUF from {filepath} (year={source_year})")

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

    df = pd.read_csv(filepath, dtype=str, low_memory=False, nrows=max_records if max_records > 0 else None)
    df = apply_column_mapping(df, COLUMN_MAPPING)
    records_fetched = len(df)

    records = []
    errors = []
    loaded_at = datetime.now(timezone.utc).isoformat()

    for idx, row in df.iterrows():
        try:
            rec = CMSUtilizationRecord(
                bene_geo_lvl=row.get('bene_geo_lvl'),
                bene_geo_desc=row.get('bene_geo_desc'),
                bene_geo_cd=row.get('bene_geo_cd'),
                bene_age_lvl=row.get('bene_age_lvl'),
                bene_demo_lvl=None,
                bene_demo_desc=None,
                srvcs_per_bene=None,
                ip_cvrd_stays_per_1000_benes=row.get('ip_cvrd_stays_per_1000_benes') or None,
                avg_ip_los=None,
                er_visits_per_1000_benes=row.get('er_visits_per_1000_benes') or None,
                phy_visits_per_bene=None,
                tot_mdcr_pymt_pc=row.get('tot_mdcr_pymt_pc') or None,
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
        # Matches uq_cms_utilization_puf_key constraint: (bene_geo_cd, bene_demo_lvl, _source_year)
        # bene_geo_cd = geographic area code; bene_demo_lvl = NULL for this source.
        conflict_columns=['bene_geo_cd', 'bene_demo_lvl', '_source_year'],
        update_columns=['bene_geo_lvl', 'bene_geo_desc', 'bene_age_lvl',
                        'ip_cvrd_stays_per_1000_benes', 'er_visits_per_1000_benes',
                        'tot_mdcr_pymt_pc', '_loaded_at'],
    )

    logger.info(f"Utilization PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
