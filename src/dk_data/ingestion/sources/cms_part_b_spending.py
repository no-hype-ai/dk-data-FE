"""CMS Part B Drug Spending loader. Loads to hcs_raw.cms_part_b_spending."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSPartBSpendingRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'HCPCS_Cd': 'hcpcs_cd',
    'HCPCS_Desc': 'hcpcs_desc',
    'Brnd_Name': 'brnd_name',
    'Gnrc_Name': 'gnrc_name',
    'Tot_Mftr': 'tot_mftr',
    'Mftr_Name': 'mftr_name',
    # Legacy (pre-2020) non-suffixed column names
    'Tot_Spndng': 'tot_spndng',
    'Tot_Dsg_Unts': 'tot_dsg_unts',
    'Tot_Benes': 'tot_benes',
    'Tot_Clms': 'tot_clms',
    'Avg_Spnd_Per_Dsg_Unt': 'avg_spnd_per_dsg_unt',
    'Avg_Spndng_Per_Dsg_Unt': 'avg_spnd_per_dsg_unt',
    'Avg_Spnd_Per_Clm': 'avg_spnd_per_clm',
    'Avg_Spndng_Per_Clm': 'avg_spnd_per_clm',
    'Avg_Spnd_Per_Bene': 'avg_spnd_per_bene',
    'Avg_Spndng_Per_Bene': 'avg_spnd_per_bene',
    'Outlier_Flag': 'outlier_flag',
    # Year-suffixed column names (CMS API format since 2020 onward).
    # Most recent year wins since apply_column_mapping processes left-to-right.
    'Tot_Spndng_2019': 'tot_spndng',
    'Tot_Dsg_Unts_2019': 'tot_dsg_unts',
    'Tot_Benes_2019': 'tot_benes',
    'Tot_Clms_2019': 'tot_clms',
    'Avg_Spndng_Per_Dsg_Unt_2019': 'avg_spnd_per_dsg_unt',
    'Avg_Spndng_Per_Clm_2019': 'avg_spnd_per_clm',
    'Avg_Spndng_Per_Bene_2019': 'avg_spnd_per_bene',
    'Outlier_Flag_2019': 'outlier_flag',
    'Tot_Spndng_2020': 'tot_spndng',
    'Tot_Dsg_Unts_2020': 'tot_dsg_unts',
    'Tot_Benes_2020': 'tot_benes',
    'Tot_Clms_2020': 'tot_clms',
    'Avg_Spndng_Per_Dsg_Unt_2020': 'avg_spnd_per_dsg_unt',
    'Avg_Spndng_Per_Clm_2020': 'avg_spnd_per_clm',
    'Avg_Spndng_Per_Bene_2020': 'avg_spnd_per_bene',
    'Outlier_Flag_2020': 'outlier_flag',
    'Tot_Spndng_2021': 'tot_spndng',
    'Tot_Dsg_Unts_2021': 'tot_dsg_unts',
    'Tot_Benes_2021': 'tot_benes',
    'Tot_Clms_2021': 'tot_clms',
    'Avg_Spndng_Per_Dsg_Unt_2021': 'avg_spnd_per_dsg_unt',
    'Avg_Spndng_Per_Clm_2021': 'avg_spnd_per_clm',
    'Avg_Spndng_Per_Bene_2021': 'avg_spnd_per_bene',
    'Outlier_Flag_2021': 'outlier_flag',
    'Tot_Spndng_2022': 'tot_spndng',
    'Tot_Dsg_Unts_2022': 'tot_dsg_unts',
    'Tot_Benes_2022': 'tot_benes',
    'Tot_Clms_2022': 'tot_clms',
    'Avg_Spndng_Per_Dsg_Unt_2022': 'avg_spnd_per_dsg_unt',
    'Avg_Spndng_Per_Clm_2022': 'avg_spnd_per_clm',
    'Avg_Spndng_Per_Bene_2022': 'avg_spnd_per_bene',
    'Outlier_Flag_2022': 'outlier_flag',
    'Tot_Spndng_2023': 'tot_spndng',
    'Tot_Dsg_Unts_2023': 'tot_dsg_unts',
    'Tot_Benes_2023': 'tot_benes',
    'Tot_Clms_2023': 'tot_clms',
    'Avg_Spndng_Per_Dsg_Unt_2023': 'avg_spnd_per_dsg_unt',
    'Avg_Spndng_Per_Clm_2023': 'avg_spnd_per_clm',
    'Avg_Spndng_Per_Bene_2023': 'avg_spnd_per_bene',
    'Outlier_Flag_2023': 'outlier_flag',
}

TABLE = 'cms_part_b_spending'
SCHEMA = 'hcs_raw'


def load_cms_part_b_spending(filepath: str, source_year: int = 2023, max_records: int = 0) -> dict:
    """Load CMS Part B Drug Spending data from CSV file."""
    logger.info(f"Loading CMS Part B Spending from {filepath} (year={source_year})")

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
            rec = CMSPartBSpendingRecord(
                hcpcs_cd=row.get('hcpcs_cd'),
                hcpcs_desc=row.get('hcpcs_desc'),
                tot_mftr=row.get('tot_mftr'),
                mftr_name=row.get('mftr_name'),
                tot_spndng=row.get('tot_spndng') or None,
                tot_dsg_unts=row.get('tot_dsg_unts') or None,
                tot_benes=row.get('tot_benes') or None,
                tot_clms=row.get('tot_clms') or None,
                avg_spnd_per_dsg_unt=row.get('avg_spnd_per_dsg_unt') or None,
                avg_spnd_per_clm=row.get('avg_spnd_per_clm') or None,
                avg_spnd_per_bene=row.get('avg_spnd_per_bene') or None,
                outlier_flag=row.get('outlier_flag'),
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
        conflict_columns=['_source_hash', 'hcpcs_cd', '_source_year'],
        update_columns=['tot_spndng', 'tot_clms', '_loaded_at'],
    )

    logger.info(f"Part B Spending load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
