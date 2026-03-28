"""CMS Geographic Variation PUF Ingestor.

Loads CMS Medicare Geographic Variation data into hcs_raw.cms_geographic_variation.
Source: https://www.cms.gov/Research-Statistics-Data-and-Systems/Statistics-Trends-and-Reports/Medicare-Geographic-Variation

Column names follow the exact CMS GV PUF field names (mixed case with underscores).
"""

import hashlib
import logging
from pathlib import Path
import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, get_connection
from ..utils.validators import CMSGeographicVariationRecord

logger = logging.getLogger(__name__)

# CMS GV PUF column → internal column mapping
# CMS publishes columns with mixed case (e.g., Bene_Geo_Lvl).
# We map to snake_case names that match hcs_raw.cms_geographic_variation.
COLUMN_MAPPING = {
    # Geographic level / location
    'Bene_Geo_Lvl':                 'bene_geo_lvl',
    'Bene_Geo_Desc':                'bene_geo_desc',
    'Bene_Geo_Cd':                  'bene_geo_cd',

    # Beneficiary demographic slice
    'Bene_Age_Lvl':                 'bene_age_lvl',
    'Bene_Demo_Lvl':                'bene_demo_lvl',
    'Bene_Demo_Desc':               'bene_demo_desc',
    'Bene_MCC_Lvl':                 'bene_mcc_lvl',

    # Beneficiary counts
    'Tot_Benes':                    'tot_benes',

    # Utilization
    'IP_Cvrd_Stays_Per_1000_Benes': 'ip_cvrd_stays_per_1000_benes',
    'ER_Visits_Per_1000_Benes':     'er_visits_per_1000_benes',
    'Readmsn_Rate':                 'readmsn_rate',
    'Acute_Hosp_Readmsn_Rate':      'acute_hosp_readmsn_rate',

    # Spending
    'Tot_Mdcr_Stdzd_Pymt_PC':       'tot_mdcr_stdzd_pymt_pc',
    'Tot_Mdcr_Pymt_PC':             'tot_mdcr_pymt_pc',
    'Tot_Mdcr_Alowd_Amt_PC':        'tot_mdcr_alowd_amt_pc',

    # Medicare Advantage
    'MA_Prtcptn_Rate':              'ma_prtcptn_rate',
}

# Columns that must be read as TEXT to preserve leading zeros (FIPS codes)
TEXT_COLUMNS = {
    'Bene_Geo_Cd': str,
}

# Columns that are numeric — CMS uses '*' for suppressed values; coerce to NULL
NUMERIC_COLUMNS = [
    'tot_benes',
    'ip_cvrd_stays_per_1000_benes',
    'er_visits_per_1000_benes',
    'readmsn_rate',
    'acute_hosp_readmsn_rate',
    'tot_mdcr_stdzd_pymt_pc',
    'tot_mdcr_pymt_pc',
    'tot_mdcr_alowd_amt_pc',
    'ma_prtcptn_rate',
]


def calculate_file_hash(filepath: str) -> str:
    """Calculate MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def load_cms_geographic_variation(
    filepath: str,
    year: int,
    batch_size: int = 1000,
) -> dict:
    """
    Load CMS Geographic Variation PUF from a CSV file.

    Args:
        filepath: Path to the CMS GV PUF CSV file.
        year: Reference year of the data (e.g., 2022).
        batch_size: Number of records to commit at once.

    Returns:
        Dictionary with ingestion statistics.
    """
    logger.info(f"Loading CMS Geographic Variation ({year}) from {filepath}")

    source_hash = calculate_file_hash(filepath)
    source_file = Path(filepath).name

    # Idempotency check — skip if this exact file was already loaded
    with get_cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM hcs_raw.cms_geographic_variation
            WHERE _source_hash = %s
        """, (source_hash,))
        if cur.fetchone()[0] > 0:
            logger.warning(f"File {source_file} already loaded. Skipping.")
            return {'status': 'skipped', 'reason': 'already_loaded'}

    # Read CSV — FIPS codes must be TEXT; suppress marker '*' becomes NaN
    df = pd.read_csv(
        filepath,
        dtype=TEXT_COLUMNS,
        na_values=['*', 'N/A', 'NR', ''],
        low_memory=False,
    )

    # Rename to internal column names
    df = df.rename(columns=COLUMN_MAPPING)

    # Coerce numeric columns (CMS uses '*' for suppressed; already NaN after na_values)
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Add year column
    if 'year' not in df.columns:
        df['year'] = year

    logger.info(f"Found {len(df)} geographic variation records")

    records_inserted = 0
    records_failed = 0
    errors = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, row in df.iterrows():
                try:
                    record = CMSGeographicVariationRecord(
                        year=int(row['year']),
                        bene_geo_lvl=row['bene_geo_lvl'],
                        bene_geo_desc=row['bene_geo_desc'],
                        bene_geo_cd=row.get('bene_geo_cd') if pd.notna(row.get('bene_geo_cd')) else None,
                        bene_age_lvl=row.get('bene_age_lvl') if pd.notna(row.get('bene_age_lvl')) else None,
                        bene_demo_lvl=row.get('bene_demo_lvl') if pd.notna(row.get('bene_demo_lvl')) else None,
                        bene_demo_desc=row.get('bene_demo_desc') if pd.notna(row.get('bene_demo_desc')) else None,
                        bene_mcc_lvl=row.get('bene_mcc_lvl') if pd.notna(row.get('bene_mcc_lvl')) else None,
                        tot_benes=int(row['tot_benes']) if pd.notna(row.get('tot_benes')) else None,
                        ip_cvrd_stays_per_1000_benes=row.get('ip_cvrd_stays_per_1000_benes') if pd.notna(row.get('ip_cvrd_stays_per_1000_benes')) else None,
                        er_visits_per_1000_benes=row.get('er_visits_per_1000_benes') if pd.notna(row.get('er_visits_per_1000_benes')) else None,
                        readmsn_rate=row.get('readmsn_rate') if pd.notna(row.get('readmsn_rate')) else None,
                        acute_hosp_readmsn_rate=row.get('acute_hosp_readmsn_rate') if pd.notna(row.get('acute_hosp_readmsn_rate')) else None,
                        tot_mdcr_stdzd_pymt_pc=row.get('tot_mdcr_stdzd_pymt_pc') if pd.notna(row.get('tot_mdcr_stdzd_pymt_pc')) else None,
                        tot_mdcr_pymt_pc=row.get('tot_mdcr_pymt_pc') if pd.notna(row.get('tot_mdcr_pymt_pc')) else None,
                        tot_mdcr_alowd_amt_pc=row.get('tot_mdcr_alowd_amt_pc') if pd.notna(row.get('tot_mdcr_alowd_amt_pc')) else None,
                        ma_prtcptn_rate=row.get('ma_prtcptn_rate') if pd.notna(row.get('ma_prtcptn_rate')) else None,
                    )

                    cur.execute("""
                        INSERT INTO hcs_raw.cms_geographic_variation (
                            year, bene_geo_lvl, bene_geo_desc, bene_geo_cd,
                            bene_age_lvl, bene_demo_lvl, bene_demo_desc, bene_mcc_lvl,
                            tot_benes,
                            ip_cvrd_stays_per_1000_benes, er_visits_per_1000_benes,
                            readmsn_rate, acute_hosp_readmsn_rate,
                            tot_mdcr_stdzd_pymt_pc, tot_mdcr_pymt_pc, tot_mdcr_alowd_amt_pc,
                            ma_prtcptn_rate,
                            _source_file, _source_hash
                        ) VALUES (
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s,
                            %s, %s,
                            %s, %s,
                            %s, %s, %s,
                            %s,
                            %s, %s
                        )
                    """, (
                        record.year,
                        record.bene_geo_lvl,
                        record.bene_geo_desc,
                        record.bene_geo_cd,
                        record.bene_age_lvl,
                        record.bene_demo_lvl,
                        record.bene_demo_desc,
                        record.bene_mcc_lvl,
                        record.tot_benes,
                        record.ip_cvrd_stays_per_1000_benes,
                        record.er_visits_per_1000_benes,
                        record.readmsn_rate,
                        record.acute_hosp_readmsn_rate,
                        record.tot_mdcr_stdzd_pymt_pc,
                        record.tot_mdcr_pymt_pc,
                        record.tot_mdcr_alowd_amt_pc,
                        record.ma_prtcptn_rate,
                        source_file,
                        source_hash,
                    ))
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()

                except ValidationError as e:
                    records_failed += 1
                    errors.append({'row': idx, 'error': str(e)})

                except Exception as e:
                    records_failed += 1
                    errors.append({'row': idx, 'error': str(e)})
                    logger.error(f"Error at row {idx}: {e}")

            conn.commit()

    logger.info(
        f"CMS Geographic Variation ({year}) load complete: "
        f"{records_inserted} inserted, {records_failed} failed"
    )

    return {
        'status': 'success',
        'records_inserted': records_inserted,
        'records_failed': records_failed,
        'source_file': source_file,
        'year': year,
        'errors': errors[:10],
    }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Load CMS Geographic Variation PUF')
    parser.add_argument('filepath', help='Path to CMS GV PUF CSV file')
    parser.add_argument('year', type=int, help='Reference year of the data')
    parser.add_argument('--batch-size', type=int, default=1000)

    args = parser.parse_args()
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)

    result = load_cms_geographic_variation(args.filepath, args.year, args.batch_size)
    print(f"Result: {result}")


if __name__ == '__main__':
    main()
