"""CMS Medicare Utilization PUF loader. Loads to hcs_raw.cms_utilization_puf.

Raw CMS field names (snake_case mapping):
  Bene_Geo_Lvl → bene_geo_lvl
  Bene_Geo_Desc → bene_geo_desc
  Bene_Geo_Cd → bene_geo_cd
  Bene_Age_Lvl → bene_age_lvl
  Bene_Demo_Lvl → bene_demo_lvl
  Bene_Demo_Desc → bene_demo_desc
  Srvcs_Per_Bene → srvcs_per_bene
  IP_Cvrd_Stays_Per_1000_Benes → ip_cvrd_stays_per_1000_benes
  Avg_IP_LOS → avg_ip_los
  ER_Visits_Per_1000_Benes → er_visits_per_1000_benes
  Phy_Visits_Per_Bene → phy_visits_per_bene
  Tot_Mdcr_Pymt_PC → tot_mdcr_pymt_pc
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSUtilizationRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'Bene_Geo_Lvl': 'bene_geo_lvl',
    'Bene_Geo_Desc': 'bene_geo_desc',
    'Bene_Geo_Cd': 'bene_geo_cd',
    'Bene_Age_Lvl': 'bene_age_lvl',
    'Bene_Demo_Lvl': 'bene_demo_lvl',
    'Bene_Demo_Desc': 'bene_demo_desc',
    'Srvcs_Per_Bene': 'srvcs_per_bene',
    'IP_Cvrd_Stays_Per_1000_Benes': 'ip_cvrd_stays_per_1000_benes',
    'Avg_IP_LOS': 'avg_ip_los',
    'ER_Visits_Per_1000_Benes': 'er_visits_per_1000_benes',
    'Phy_Visits_Per_Bene': 'phy_visits_per_bene',
    'Tot_Mdcr_Pymt_PC': 'tot_mdcr_pymt_pc',
}

TABLE = 'cms_utilization_puf'
SCHEMA = 'hcs_raw'


def load_cms_utilization_puf(filepath: str, source_year: int = 2023) -> dict:
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

    df = pd.read_csv(filepath, dtype=str, low_memory=False)
    df = df.rename(columns=COLUMN_MAPPING)
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
                bene_demo_lvl=row.get('bene_demo_lvl'),
                bene_demo_desc=row.get('bene_demo_desc'),
                srvcs_per_bene=row.get('srvcs_per_bene') or None,
                ip_cvrd_stays_per_1000_benes=row.get('ip_cvrd_stays_per_1000_benes') or None,
                avg_ip_los=row.get('avg_ip_los') or None,
                er_visits_per_1000_benes=row.get('er_visits_per_1000_benes') or None,
                phy_visits_per_bene=row.get('phy_visits_per_bene') or None,
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
        conflict_columns=['bene_geo_cd', 'bene_age_lvl', 'bene_demo_lvl', '_source_year'],
        update_columns=['srvcs_per_bene', 'ip_cvrd_stays_per_1000_benes', 'avg_ip_los',
                        'er_visits_per_1000_benes', 'phy_visits_per_bene', 'tot_mdcr_pymt_pc',
                        '_loaded_at'],
    )

    logger.info(f"Utilization PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
